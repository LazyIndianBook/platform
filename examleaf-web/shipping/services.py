"""The shipping flows (research-integrations.md section 3): quote, prepare and book a parcel, its label, pickup and
manifest, cancellation and NDR actions; the carrier's scans applied to the parcel and what they mean for the order
and the customer; the money (statement lines, COD remittances, weight disputes); the exceptions staff deal with; the
survey of the North-East's PINs. Views, admin actions, tasks and commands all go through these functions.

None of them holds a transaction while it talks to a carrier (integrations/client.py): a parcel is claimed instead
(ShipmentDetail.claim) and each step's result is saved as soon as it is known. The order changes only through its
existing transitions (shop.services): ship at the first scan that says the parcel has left, deliver once a delivery
is confirmed; it gets no state of its own for a return."""

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django_fsm import can_proceed

from integrations.client import CircuitOpen, IntegrationError, IntegrationUnavailable
from integrations.models import IntegrationAccount
from shop import services as shop
from shop.models import Order, OrderNote, PinCode, Product, Shipment

from . import messages, signals
from .carriers import ManualCarrier, Parcel, carrier_for
from .carriers.shiprocket import decimal, parse_time  # the statement's rows are in Shiprocket's shape
from .models import (
    CodRemittance,
    PickupLocation,
    PinServiceability,
    PostalTariff,
    ShipmentCharge,
    ShipmentDetail,
    ShipmentEvent,
    ShippingException,
)
from .status import CONFIRM, FINAL, LEFT, OUT_FOR_PICKUP, Status, moves_forward

logger = logging.getLogger(__name__)
Kind = ShippingException.Kind
NORTH_EAST = {"AS", "AR", "MN", "ML", "MZ", "NL", "TR", "SK"}  # by state: Sikkim's 737 sits in West Bengal's range
COURIERS = [  # a courier's name at the carrier → the shop's Courier (its tracking page), else "another courier"
    ("delhivery", Shipment.Courier.DELHIVERY),
    ("blue dart", Shipment.Courier.BLUE_DART),
    ("bluedart", Shipment.Courier.BLUE_DART),
    ("ekart", Shipment.Courier.EKART),
    ("dtdc", Shipment.Courier.DTDC),
    ("xpressbees", Shipment.Courier.XPRESSBEES),
    ("india post", Shipment.Courier.INDIA_POST),
]
CHARGES = {  # a statement line's description (Shiprocket's passbook entries, research 1.10) → its kind
    "freight charge": ShipmentCharge.Kind.FREIGHT,
    "freight charge reversed": ShipmentCharge.Kind.FREIGHT_REVERSAL,
    "cod charge": ShipmentCharge.Kind.COD,
    "cod charge reversed": ShipmentCharge.Kind.COD_REVERSAL,
    "rto freight charge": ShipmentCharge.Kind.RTO_FREIGHT,
    "rto freight reversed": ShipmentCharge.Kind.RTO_FREIGHT_REVERSAL,
    "excess weight charge": ShipmentCharge.Kind.EXCESS_WEIGHT,
    "rto excess weight charge": ShipmentCharge.Kind.EXCESS_WEIGHT,
    "excess weight charge reversed": ShipmentCharge.Kind.EXCESS_WEIGHT_REVERSAL,
    "rto excess freight reversed": ShipmentCharge.Kind.EXCESS_WEIGHT_REVERSAL,
}


class ShippingError(Exception):
    """Something staff must fix first, said as it is."""


class ParcelBusy(IntegrationUnavailable):
    """Another worker is talking to the carrier about this parcel: try again shortly."""


def working_days_after(day, count):
    """`day` plus `count` working days (Monday to Friday; public holidays are not counted)."""
    while count > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def end_of(day):
    return timezone.make_aware(datetime.combine(day, time(23, 59)))


def courier_choice(name):
    lowered = (name or "").lower()
    return next((courier for key, courier in COURIERS if key in lowered), Shipment.Courier.OTHER)


def grams(kilograms):
    try:
        return int(Decimal(str(kilograms)) * 1000) if kilograms not in (None, "") else None
    except ArithmeticError, ValueError:
        return None


# The parcel


def parcel_weight(order):
    """The parcel's weight in grams: its books' (Product.weight_grams; a bundle's own, else its books'), and the
    packing (SHIPPING_PACKING_GRAMS). Raises ShippingError for a book without a weight."""
    total, missing = 0, []
    for item in order.items.select_related("product"):
        product = item.product
        if product.digital_only:
            continue
        weight = product.weight_grams
        if not weight and product.kind == Product.Kind.BUNDLE:
            books = product.bundle_items.select_related("product")
            weight = sum(book.product.weight_grams * book.quantity for book in books if not book.product.is_digital)
        if not weight:
            missing.append(product.title)
        total += weight * item.quantity
    if missing:
        raise ShippingError(f"No weight for {', '.join(missing)}: fill in “weight (g)” in the catalogue, or weigh it.")
    return total + settings.SHIPPING_PACKING_GRAMS


def dimensions():
    """A parcel's length, breadth and height in cm: a flyer by default (SHIPPING_PARCEL_CM)."""
    return [int(value) for value in settings.SHIPPING_PARCEL_CM]


def collect_amount(order):
    """The cash a courier collects for a cash-on-delivery order: its total (nothing of it is paid), checked against
    its own lines (the books, less the discount, plus shipping) and its payment. None for a prepaid order. Raises
    ShippingError when they do not agree: a parcel is never sent to collect another amount."""
    if not order.is_cod:
        return None
    books = sum((item.line_total.amount for item in order.items.all()), Decimal("0.00"))
    payment = order.payments.filter(method=Order.Method.COD).first()
    total = order.total.amount
    if books - order.discount.amount + order.shipping_fee.amount != total or payment is None:
        raise ShippingError(f"Order {order.number}: its total is not its books less the discount plus shipping.")
    if payment.amount.amount != total:
        raise ShippingError(f"Order {order.number}: its cash-on-delivery payment is not its total.")
    return total


# Choosing the courier


def rank(quotes, cod):
    """Research 3.4: no courier without COD for a COD parcel, none blocked or out of its area; first the cheapest of
    those rated SHIPPING_MIN_RATING or more that deliver within SHIPPING_MAX_DAYS (a tie goes to the carrier's own
    pick), then the others, cheapest first."""

    def good(quote):
        days = quote.etd_days
        return (
            (quote.rating or 0) >= settings.SHIPPING_MIN_RATING
            and days is not None
            and days <= settings.SHIPPING_MAX_DAYS
        )

    eligible = [quote for quote in quotes if not quote.blocked and (quote.cod or not cod)]
    return sorted(eligible, key=lambda q: (not good(q), q.rate, not q.recommended, q.courier_company_id))


def postal_prices(order, weight_g):
    """India Post beside the couriers for a prepaid order (no COD there): Book Post, and Gyan Post once the postal
    division has confirmed in writing that the books qualify (SHIPPING_GYAN_POST), from PostalTariff."""
    if order.is_cod:
        return []
    services = [PostalTariff.Service.BOOK_POST]
    if settings.SHIPPING_GYAN_POST:
        services.append(PostalTariff.Service.GYAN_POST)
    prices = [(service, PostalTariff.price_for(service, weight_g)) for service in services]
    return [
        {"service": service, "label": service.label, "price": price} for service, price in prices if price is not None
    ]


def quote(order, account=None, *, weight_g=None, pickup=None):
    """The couriers for an order (the top three, ranked), with India Post's prices for a prepaid one. The carrier is
    asked with a short timeout (SHIPPING_QUOTE_TIMEOUT); its answer is kept SHIPPING_QUOTE_CACHE_SECONDS, and when
    it cannot be asked the last good answer is given, marked `stale`, with the `error`."""
    account = account or IntegrationAccount.enabled_for("shiprocket")
    if account is None:
        raise ShippingError("No courier account is enabled (Integrations).")
    pickup = pickup or PickupLocation.default()
    if pickup is None:
        raise ShippingError("No pickup location yet (Shipping → Pickup locations).")
    weight = weight_g or parcel_weight(order)
    length, breadth, height = dimensions()
    parcel = Parcel(
        pickup.pin_code,
        order.shipping_address["pin"],
        weight,
        order.is_cod,
        order.total.amount,
        length,
        breadth,
        height,
    )
    key = "shipping:quote:" + hashlib.sha256(f"{account.pk}|{parcel}".encode()).hexdigest()
    result = {
        "couriers": [],
        "india_post": postal_prices(order, weight),
        "weight_g": weight,
        "stale": False,
        "error": "",
    }
    quotes = cache.get(key)
    if quotes is None:
        try:
            quotes = carrier_for(account).quote(parcel, timeout=settings.SHIPPING_QUOTE_TIMEOUT)
        except IntegrationError as error:
            quotes = cache.get(f"{key}:last")
            result["stale"], result["error"] = quotes is not None, str(error)
            quotes = quotes or []
        else:
            cache.set(key, quotes, settings.SHIPPING_QUOTE_CACHE_SECONDS)
            cache.set(f"{key}:last", quotes, 7 * 86400)
    result["couriers"] = rank(quotes, order.is_cod)[:3]
    return result


# Booking


def next_reference(order, carrier):
    """Our order id at the carrier: the order number, then "-R1", "-R2" for each booking made before it (a cancelled
    one counts: Shiprocket never takes an id twice)."""
    made = ShipmentDetail.objects.filter(shipment__order=order, carrier=carrier).exclude(reference="").count()
    return order.number if made == 0 else f"{order.number}-R{made}"


ACTIVE = Q(status__isnull=True) | ~Q(status__in=[Status.CANCELLED, Status.RETURNED, Status.LOST_OR_DAMAGED])


def bookable(order):
    """A packed order, or a shipped one whose parcel came back or was lost (a re-shipment)."""
    if order.status == Order.Status.PACKED:
        return True
    gone = [Status.RETURNED, Status.LOST_OR_DAMAGED]
    return (
        order.status == Order.Status.SHIPPED
        and ShipmentDetail.objects.filter(shipment__order=order, status__in=gone).exists()
    )


def prepare(
    order, *, account, courier_company_id, courier_name="", quoted_rate=None, weight_g=None, dims=None, pickup=None
):
    """A parcel to book with this courier (book_shipment does it): the shipment and its detail, with the cash to
    collect, the declared value, the weight and our reference. For a packed order; or a shipped one whose parcel came
    back or was lost (a re-shipment). Refuses a test order with a live account and an order with a parcel already
    being booked or on its way."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if not bookable(order):
            raise ShippingError(f"Order {order.number} is {order.get_status_display()}: only packed orders are booked.")
        if order.is_test and account.mode == IntegrationAccount.Mode.LIVE:
            raise ShippingError(f"Order {order.number} was made with test keys: it is never handed to a courier.")
        if ShipmentDetail.objects.filter(shipment__order=order).filter(ACTIVE).exists():
            raise ShippingError(f"Order {order.number} has a parcel booked or on its way already.")
        pickup = pickup or PickupLocation.default()
        if pickup is None:
            raise ShippingError("No pickup location yet (Shipping → Pickup locations).")
        weight = weight_g or parcel_weight(order)
        length, breadth, height = dims or dimensions()
        shipment = Shipment.objects.create(order=order, courier=courier_choice(courier_name), tracking_number="")
        ShipmentDetail.objects.create(
            shipment=shipment,
            carrier=account.provider,
            account=account,
            reference=next_reference(order, account.provider),
            courier_company_id=courier_company_id,
            courier_name=courier_name,
            quoted_rate=quoted_rate,
            cod_amount=collect_amount(order),
            declared_value=order.total.amount,
            weight_g=weight,
            length_cm=length,
            breadth_cm=breadth,
            height_cm=height,
            pickup_location=pickup,
            last_event_at=timezone.now(),
        )
    return shipment


def parcel(shipment):
    """The shipment again from the database, with its order and detail."""
    return Shipment.objects.select_related("order", "detail__account", "detail__pickup_location").get(pk=shipment.pk)


def book(shipment, courier_company_id=None):
    """Book a prepared parcel with its carrier (its order, then its AWB) and queue its label. Idempotent: a parcel
    with its AWB is left as it is, one another worker is booking raises ParcelBusy (retried), and a booking whose
    answer was lost is found again at the carrier. Refuses a cancelled parcel, an order no longer packed (or being
    re-shipped), and a parcel whose cash to collect is not the order's total (the `sub_total` Shiprocket's courier
    would collect)."""
    shipment = parcel(shipment)
    detail, order = shipment.detail, shipment.order
    if detail.status is not None:
        if detail.status == Status.CANCELLED:
            raise ShippingError(f"{detail.reference}: this booking was cancelled; book a new parcel.")
        return shipment  # booked before
    if not bookable(order):  # cancelled meanwhile, or shipped by hand
        raise ShippingError(f"Order {order.number} is {order.get_status_display()}: the parcel is not booked.")
    if detail.cod_amount != collect_amount(order):
        raise ShippingError(f"{detail.reference}: the cash to collect is not the order's total; prepare it again.")
    if not detail.claim():
        raise ParcelBusy(f"{detail.reference} is being booked by another worker", account=detail.account)
    try:
        carrier = carrier_for(detail.account)
        booking = carrier.book(shipment, courier_company_id or detail.courier_company_id)
    finally:
        detail.release()
    now = timezone.now()
    name = booking.courier_name or detail.courier_name
    with transaction.atomic():
        courier = courier_choice(name)
        Shipment.objects.filter(pk=shipment.pk).update(
            tracking_number=booking.awb, courier=courier, tracking_url=carrier.tracking_url(courier, booking.awb)
        )
        detail.change(
            status=Status.BOOKED,
            external_order_id=booking.external_order_id,
            external_shipment_id=booking.external_shipment_id,
            courier_company_id=booking.courier_company_id,
            courier_name=name,
            last_event_at=now,
        )
        record_staff_event(shipment, booking.awb, Status.BOOKED, "AWB assigned", now)
        from . import tasks

        transaction.on_commit(lambda: tasks.fetch_label.delay(shipment.pk), robust=True)
    return parcel(shipment)


def ship_by_hand(order, courier, tracking_number, tracking_url="", by=None):
    """The manual carrier: staff handed the parcel over (India Post, or a courier without an API) and typed its
    courier and number. The order is shipped as the admin's "Mark shipped" does (shop.services.ship_order: the
    customer is told), and the parcel gets its detail (in transit) and a first event."""
    order = shop.ship_order(order, courier, tracking_number, tracking_url)
    shipment = order.shipments.order_by("-pk").first()
    booking = ManualCarrier().book(shipment)
    ShipmentDetail.objects.create(
        shipment=shipment,
        carrier=ShipmentDetail.Carrier.MANUAL,
        status=Status.IN_TRANSIT,
        courier_name=booking.courier_name,
        declared_value=order.total.amount,
        cod_amount=collect_amount(order),
        last_event_at=timezone.now(),
    )
    record_staff_event(shipment, tracking_number, Status.IN_TRANSIT, f"Handed over to {booking.courier_name}", None, by)
    return shipment


def record_staff_event(shipment, awb, status, label, when=None, by=None):
    when = when or timezone.now()
    digest = hashlib.sha256(f"{awb}|staff|{status}|{when.isoformat()}".encode()).hexdigest()
    raw = {"by": by.pk} if getattr(by, "pk", None) else {}
    ShipmentEvent.objects.create(
        shipment=shipment,
        source=ShipmentEvent.Source.MANUAL,
        carrier_label=label,
        status=status,
        occurred_at=when,
        raw=raw,
        digest=digest,
    )


def fetch_label(shipment):
    """The label's PDF, fetched once and kept with us (private storage): a reprint never depends on the carrier."""
    shipment = parcel(shipment)
    detail = shipment.detail
    if detail.label:
        return detail.label
    if not shipment.tracking_number or detail.status is None:
        raise ShippingError(f"{detail.reference or shipment}: not booked yet, no label.")
    content = carrier_for(detail.account).label(shipment)
    detail.label.save(f"{detail.reference}.pdf", ContentFile(content), save=False)
    detail.change(label=detail.label.name)
    return detail.label


def schedule_pickup(shipment, on=None):
    """Ask the courier to collect the parcel (on a date, or the next possible one; one call per parcel): the date."""
    shipment = parcel(shipment)
    detail = shipment.detail
    if detail.status not in (Status.BOOKED, Status.PICKUP_PROBLEM):
        raise ShippingError(f"{detail.reference or shipment}: only a booked parcel waits for a pickup.")
    day = carrier_for(detail.account).schedule_pickup(shipment, on)
    detail.change(pickup_date=day)
    return day


def manifest(shipments):
    """The handover list of booked parcels of one account: the link to its PDF; the parcels are marked manifested."""
    shipments = [parcel(shipment) for shipment in shipments]
    accounts = {shipment.detail.account_id for shipment in shipments}
    if not shipments or len(accounts) != 1 or None in accounts:
        raise ShippingError("A manifest is for booked parcels of one courier account.")
    if any(shipment.detail.status not in (Status.BOOKED, Status.PICKUP_PROBLEM) for shipment in shipments):
        raise ShippingError("Only parcels waiting for their pickup go on a manifest.")
    url = carrier_for(shipments[0].detail.account).manifest(shipments)
    ShipmentDetail.objects.filter(shipment__in=shipments).update(manifested_at=timezone.now())
    return url


def cancel(shipment, by=None):
    """Cancel a booking, possible only until the courier is out to collect it (after that: deliver, or ask for a
    return through an NDR action). The freight comes back to the wallet (the statement's reversal lines)."""
    shipment = parcel(shipment)
    detail = shipment.detail
    last = shipment.events.exclude(carrier_code="").order_by("-occurred_at", "-pk").first()
    if not detail.cancellable or (last and last.carrier_code == str(OUT_FOR_PICKUP)):
        raise ShippingError(f"{detail.reference}: picked up or out for pickup, it can no longer be cancelled.")
    if detail.external_order_id or shipment.tracking_number:
        if not detail.claim():
            raise ShippingError(f"{detail.reference} is being booked just now: try again in a minute.")
        try:
            carrier_for(detail.account).cancel(shipment)
        finally:
            detail.release()
    with transaction.atomic():
        detail.change(status=Status.CANCELLED, last_event_at=timezone.now())
        record_staff_event(
            shipment, shipment.tracking_number or detail.reference, Status.CANCELLED, "Cancelled", None, by
        )
        close_exceptions(shipment, [Kind.PICKUP_PROBLEM, Kind.NO_MOVEMENT], "The booking was cancelled.")
    return parcel(shipment)


NDR_ACTIONS = ("re-attempt", "return", "fake-attempt")


def ndr_action(shipment, action, comments, by=None, **fields):
    """After a failed delivery: try again (optionally with a date, a phone number or an address), dispute a fake
    attempt, or have it returned. Noted on the parcel's NDR exception (what was done, not the new details)."""
    shipment = parcel(shipment)
    if action not in NDR_ACTIONS:
        raise ShippingError(f"The action is one of {', '.join(NDR_ACTIONS)}.")
    if shipment.detail.status != Status.DELIVERY_FAILED:
        raise ShippingError(f"{shipment.detail.reference}: no failed delivery to act on.")
    carrier_for(shipment.detail.account).ndr_action(shipment, action, comments, **fields)
    exception = open_exception(shipment, Kind.NDR)
    taken = {
        "action": action,
        "comments": comments[:300],
        "changed": sorted(name for name, value in fields.items() if value),
    }
    taken.update(at=timezone.now().isoformat(), by=getattr(by, "pk", None))
    exception.data = {**exception.data, "actions": [*exception.data.get("actions", []), taken]}
    exception.save(update_fields=["data", "modified"])
    return exception


# Tracking


def apply_events(shipment, scans, source):
    """A carrier's scans of a parcel: each kept once (its digest), the parcel's status moved forward by them in the
    order they happened (status.moves_forward), then what the new status means for the order and the customer
    (effects). All in one transaction under a lock on the parcel: a webhook and a poll at once cannot move it back,
    and if an effect fails nothing is kept, so the same scans apply again on the task's retry or the next poll.
    Returns the new events."""
    with transaction.atomic():
        detail = ShipmentDetail.objects.select_for_update().get(shipment=shipment)
        new = []
        for scan in sorted(scans, key=lambda scan: scan.occurred_at):
            try:
                with transaction.atomic():  # a savepoint: a scan seen before is skipped
                    new.append(
                        ShipmentEvent.objects.create(
                            shipment=shipment,
                            source=source,
                            carrier_code=scan.code[:40],
                            carrier_label=scan.label[:100],
                            status=scan.status,
                            occurred_at=scan.occurred_at,
                            location=scan.location[:200],
                            activity=scan.activity[:300],
                            raw=scan.raw,
                            digest=scan.digest,
                        )
                    )
            except IntegrityError:
                continue
        if not new:
            return []
        before = status = detail.status
        for event in new:
            if moves_forward(status, event.status):
                status = event.status
        latest = max(event.occurred_at for event in new)
        detail.change(status=status, last_event_at=max(latest, detail.last_event_at or latest))
        if status != before:
            effects(parcel(shipment), before, status)
        if before not in LEFT and status in LEFT:  # a first parcel or a re-shipment: the erp app's delivery note
            signals.parcel_left.send(sender=ShipmentDetail, shipment=shipment)
    return new


def effects(shipment, before, after):
    """What a parcel's new status means (research 3.6 and 3.7): the order shipped at the first scan that says it
    has left, delivered once delivered (a COD remittance expected), the exceptions staff deal with, the customer told.
    Nothing for a parcel sent by hand: staff mark those themselves."""
    if shipment.detail.carrier == ShipmentDetail.Carrier.MANUAL:
        return
    if after in LEFT:
        ship(shipment, tell=after != Status.DELIVERED)
    if after in (Status.RETURNING, Status.RETURNED, Status.LOST_OR_DAMAGED, Status.CANCELLED):
        CodRemittance.objects.filter(shipment=shipment, state=CodRemittance.State.EXPECTED).update(
            state=CodRemittance.State.NOT_EXPECTED
        )
    match after:
        case Status.PICKUP_PROBLEM:
            open_exception(shipment, Kind.PICKUP_PROBLEM, data={"carrier_label": last_label(shipment)})
        case Status.OUT_FOR_DELIVERY:
            messages.tell(shipment, "out_for_delivery")
        case Status.DELIVERED:
            deliver(shipment)
        case Status.DELIVERY_FAILED:
            failed = shipment.events.filter(status=Status.DELIVERY_FAILED).count()
            data = {"reason": last_label(shipment), "attempts": failed}
            open_exception(shipment, Kind.NDR, hours=settings.SHIPPING_NDR_HOURS, data=data)
            messages.tell(shipment, "delivery_failed")
        case Status.RETURNING:
            open_exception(shipment, Kind.RTO, days=7, data={"stage": "returning"})
            messages.tell(shipment, "returning")
        case Status.RETURNED:
            returned(shipment)
        case Status.LOST_OR_DAMAGED:
            close_exceptions(shipment, [Kind.NDR, Kind.NO_MOVEMENT], "Reported lost or damaged.")
            open_exception(shipment, Kind.LOST, days=2, data={"todo": "claim with the courier; reship or refund"})
        case Status.PARTIAL:
            open_exception(shipment, Kind.PARTIAL, data={"todo": "find what was not delivered"})


def last_label(shipment):
    event = shipment.events.order_by("-occurred_at", "-pk").first()
    return (event.carrier_label or event.activity) if event else ""


def ship(shipment, tell=True):
    """The order's existing "shipped" transition at the first scan that says the parcel has left: as when staff mark
    it shipped, the customer is emailed and a cash-on-delivery order's bill is made (shop.services.shipped); the SMS
    is ours (quiet hours). An order shipped already (by staff, or by an earlier parcel) is left as it is."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=shipment.order_id)
        if order.status != Order.Status.PACKED or not can_proceed(order.ship):  # not packed, or a test order
            if order.status not in (Order.Status.SHIPPED, Order.Status.DELIVERED):
                logger.error("Parcel of order %s is moving while the order is %s", order.number, order.status)
            return False
        order.ship()
        order.save()
        Shipment.objects.filter(pk=shipment.pk).update(shipped_at=timezone.now())
        shipment.refresh_from_db()
        if tell:
            shop.shipped(order, shipment, sms=False)
            messages.tell(shipment, "shipped")
        else:  # delivered at once: the bill all the same, no "on its way"
            shop.shipped(order, shipment, sms=False, email=False)
    return True


def deliver(shipment):
    """Delivered (confirmed by a tracking read): the order's existing "delivered" transition (shop.services.
    deliver_order: a cash-on-delivery payment captured, the customer emailed), the cash expected from the courier,
    the parcel's open exceptions closed."""
    order = Order.objects.get(pk=shipment.order_id)
    if can_proceed(order.deliver):
        shop.deliver_order(order, sms=False)
        messages.tell(shipment, "delivered")
    expect_cod(shipment)
    close_exceptions(shipment, [Kind.NDR, Kind.NO_MOVEMENT, Kind.PICKUP_PROBLEM], "Delivered.")


def returned(shipment):
    """Back with us (RTO): the packing room checks it and puts it back in stock (or marks it damaged), and staff decide
    for the order: a cash-on-delivery order is cancelled (Order.cancel_returned, the staff Cancel action: the parcel
    came back, nothing was collected), a prepaid one is sent again or refunded (the refund action of the order).
    Here the order stays shipped with a note and an open RTO exception until staff decide."""
    order = shipment.order
    action = "cancel the order (nothing was collected)" if order.is_cod else "reship or refund"
    exception = open_exception(
        shipment, Kind.RTO, days=2, data={"stage": "returned", "todo": f"check the parcel, then {action}"}
    )
    if not exception.data.get("noted"):
        text = f"Parcel {shipment.tracking_number} came back to us undelivered (RTO). To do: check it, then {action}."
        OrderNote.objects.create(order=order, text=text)
        exception.data = {**exception.data, "noted": True}
        exception.save(update_fields=["data", "modified"])


def due_for_poll(now=None):
    """The parcels with a courier account that are booked, not final and silent for SHIPPING_POLL_AFTER_HOURS."""
    now = now or timezone.now()
    since = now - timedelta(hours=settings.SHIPPING_POLL_AFTER_HOURS)
    parcels = Shipment.objects.filter(detail__account__enabled=True, detail__status__isnull=False).exclude(
        detail__status__in=FINAL
    )
    return parcels.exclude(tracking_number="").filter(
        Q(detail__last_event_at__lt=since) | Q(detail__last_event_at__isnull=True)
    )


def poll(now=None, batch=50):
    """Every two hours (the net under the webhook): read the tracking of the parcels due, 50 a call per account; a
    parcel without a scan for SHIPPING_NO_MOVEMENT_DAYS gets a no-movement exception. An account whose circuit is open
    waits for the next run. Returns how many parcels were read."""
    now = now or timezone.now()
    by_account = defaultdict(list)
    for shipment in due_for_poll(now).select_related("detail__account", "order"):
        by_account[shipment.detail.account].append(shipment)
    read = 0
    for account, shipments in by_account.items():
        carrier = carrier_for(account)
        for start in range(0, len(shipments), batch):
            chunk = shipments[start : start + batch]
            try:
                answers = carrier.track([shipment.tracking_number for shipment in chunk])
            except IntegrationError as error:
                logger.warning("Tracking of %s parcel(s) not read: %s", len(chunk), error)
                break
            for shipment in chunk:
                try:
                    apply_events(shipment, answers.get(shipment.tracking_number, []), ShipmentEvent.Source.POLL)
                except Exception:  # one parcel's trouble must not stop the others: it is read again next time
                    logger.exception("Tracking of parcel %s not applied", shipment.tracking_number)
                    continue
                read += 1
    stale = now - timedelta(days=settings.SHIPPING_NO_MOVEMENT_DAYS)
    for shipment in due_for_poll(now).filter(detail__last_event_at__lt=stale):
        open_exception(shipment, Kind.NO_MOVEMENT, data={"last_event_at": shipment.detail.last_event_at.isoformat()})
    return read


def process_event(event):
    """A stored webhook (InboundEvent) of a parcel: its scans applied; but a claim of delivered, returned or lost is
    first read again at the carrier (the webhook is unsigned) and only the tracking read's scans count for those.
    Returns the new events (none: the event was a duplicate), or None for a parcel that is not ours."""
    carrier = carrier_for(event.account)
    payload = carrier.parse_webhook(json.loads(event.body))
    shipment = Shipment.objects.filter(tracking_number=payload.awb, detail__account=event.account).first()
    if shipment is None or not payload.awb:
        return None  # not one of ours (a parcel booked in the carrier's own panel)
    new = []
    if any(scan.status in CONFIRM for scan in payload.scans):
        read = carrier.track([payload.awb]).get(payload.awb, [])
        new += apply_events(shipment, read, ShipmentEvent.Source.POLL)
        payload.scans = [scan for scan in payload.scans if scan.status not in CONFIRM]
    new += apply_events(shipment, payload.scans, ShipmentEvent.Source.WEBHOOK)
    return new


# Money


def expect_cod(shipment):
    """A delivered cash-on-delivery parcel: the courier owes its cash, by SHIPPING_COD_REMITTANCE_DAYS working days
    after the delivery (Shiprocket: D+8 working days, paid on Mondays, Wednesdays and Fridays, research 1.10). Once."""
    cod = shipment.detail.cod_amount
    if not cod:
        return None
    delivered = shipment.events.filter(status=Status.DELIVERED).order_by("occurred_at").first()
    day = timezone.localdate(delivered.occurred_at if delivered else timezone.now())
    remittance, _ = CodRemittance.objects.get_or_create(
        shipment=shipment,
        defaults={
            "expected_amount": cod,
            "expected_on": working_days_after(day, settings.SHIPPING_COD_REMITTANCE_DAYS),
        },
    )
    return remittance


def check_cod(today=None):
    """Daily: for each remittance still awaited, ask the carrier (the order's remittance status, UTR and date):
    remitted (another amount: mismatch, an exception), or overdue SHIPPING_COD_GRACE_DAYS working days after its day
    (an exception). A carrier that cannot be asked is asked again tomorrow. Returns {state: count}."""
    today = today or timezone.localdate()
    counts = defaultdict(int)
    waiting = CodRemittance.objects.filter(state__in=[CodRemittance.State.EXPECTED, CodRemittance.State.OVERDUE])
    for remittance in waiting.select_related("shipment__detail__account"):
        detail = remittance.shipment.detail
        if detail.account is None or not detail.external_order_id:
            continue
        try:
            info = carrier_for(detail.account).order_detail(detail.external_order_id)
        except IntegrationError as error:
            logger.warning("COD remittance of %s not checked: %s", detail.reference, error)
            continue
        utr = str(info.get("remittance_utr") or "").strip()
        if utr or str(info.get("remittance_status") or "").lower() in ("remitted", "paid", "completed", "success"):
            amount = decimal(info["remittance_amount"]) if info.get("remittance_amount") not in (None, "") else None
            remittance.remitted_amount = amount if amount is not None else remittance.expected_amount
            remittance.utr = utr[:60]
            when = parse_time(info.get("remittance_date"))
            remittance.remitted_at = when.date() if when else today
            matches = remittance.remitted_amount == remittance.expected_amount
            remittance.state = CodRemittance.State.REMITTED if matches else CodRemittance.State.MISMATCH
            if not matches:
                data = {
                    "expected": str(remittance.expected_amount),
                    "remitted": str(remittance.remitted_amount),
                    "utr": utr,
                }
                open_exception(
                    remittance.shipment, Kind.COD_OVERDUE, data=data, reference=f"cod-mismatch-{remittance.pk}"
                )
        elif today > working_days_after(remittance.expected_on, settings.SHIPPING_COD_GRACE_DAYS):
            remittance.state = CodRemittance.State.OVERDUE
            data = {"expected": str(remittance.expected_amount), "expected_on": remittance.expected_on.isoformat()}
            open_exception(remittance.shipment, Kind.COD_OVERDUE, data=data, reference=f"cod-overdue-{remittance.pk}")
        remittance.checked_at = timezone.now()
        with transaction.atomic():  # with what its post_save receivers write (the erp app's settlement)
            remittance.save()
        counts[remittance.state] += 1
    return dict(counts)


def reconcile_cod(remittance, utr, amount, on=None):
    """Finance: the bank's credit for a remittance, matched by its UTR (plan 5.7). The amount expected: remitted, and
    the parcel's COD exception settled; another: a mismatch, with its exception (once)."""
    if remittance.state == CodRemittance.State.NOT_EXPECTED:
        raise ShippingError("No cash is expected for this parcel (it came back, was lost or was cancelled).")
    remittance.utr, remittance.remitted_amount = utr.strip()[:60], amount
    remittance.remitted_at, remittance.checked_at = on or timezone.localdate(), timezone.now()
    matches = amount == remittance.expected_amount
    remittance.state = CodRemittance.State.REMITTED if matches else CodRemittance.State.MISMATCH
    with transaction.atomic():  # with what its post_save receivers write (the erp app's settlement), as check_cod
        remittance.save()
    if matches:
        close_exceptions(remittance.shipment, [Kind.COD_OVERDUE], "Remitted: matched with the bank's credit.")
    else:
        data = {"expected": str(remittance.expected_amount), "remitted": str(amount), "utr": remittance.utr}
        open_exception(remittance.shipment, Kind.COD_OVERDUE, data=data, reference=f"cod-mismatch-{remittance.pk}")
    return remittance


def statement_line_id(row):
    """A statement line's own id, or (none being documented) the digest of what makes it that line: its AWB,
    description, amounts, time and the balance after it."""
    if row.get("id"):
        return str(row["id"])[:64]
    fields = [
        "awb_code",
        "channel_order_id",
        "description",
        "debit_amount",
        "credit_amount",
        "created_at",
        "balance_amount",
    ]
    return hashlib.sha256("|".join(str(row.get(name, "")) for name in fields).encode()).hexdigest()


def find_parcel(account, awb="", reference=""):
    parcels = Shipment.objects.filter(detail__account=account)
    if awb and (found := parcels.filter(tracking_number=awb).first()):
        return found
    return parcels.filter(detail__reference=reference).first() if reference else None


def record_statement_lines(account, rows):
    """The wallet statement's rows as ShipmentCharge, each once (by its line id), matched to our parcel by AWB (else
    by our order id); the parcel's charged weight is the statement's. Returns how many were new."""
    new = 0
    for row in rows:
        line_id = statement_line_id(row)
        awb, reference = str(row.get("awb_code") or ""), str(row.get("channel_order_id") or "")
        shipment = find_parcel(account, awb, reference)
        description = str(row.get("description") or "")
        charged = grams(row.get("charged_weight"))
        try:
            with transaction.atomic():
                ShipmentCharge.objects.create(
                    shipment=shipment,
                    account=account,
                    kind=CHARGES.get(description.strip().lower(), ShipmentCharge.Kind.OTHER),
                    amount=decimal(row.get("debit_amount")) - decimal(row.get("credit_amount")),
                    statement_line_id=line_id,
                    charged_weight_g=charged,
                    awb=awb[:40],
                    description=description[:200],
                    charged_at=parse_time(row.get("created_at")) or timezone.now(),
                )
        except IntegrityError:
            continue  # recorded before
        new += 1
        if shipment and charged:
            ShipmentDetail.objects.filter(shipment=shipment).update(charged_weight_g=charged)
    return new


def sync_statement(account, days=7, today=None):
    """Daily: the last `days` of the wallet statement (lines already kept are skipped). Returns how many were new."""
    today = today or timezone.localdate()
    rows = carrier_for(account).statement(today - timedelta(days=days), today)
    return record_statement_lines(account, rows)


def record_discrepancies(account, rows):
    """Each weight dispute the carrier raised, as an exception due SHIPPING_DISPUTE_DAYS working days after it was
    raised (after that the courier's weight is accepted, research 1.10), with our weight and whether we have the
    photograph. Once per dispute. Returns the exceptions opened or found."""
    found = []
    for row in rows:
        awb, reference = str(row.get("awb_code") or row.get("awb") or ""), str(row.get("channel_order_id") or "")
        shipment = find_parcel(account, awb, reference)
        key = str(row.get("id") or awb)
        if shipment is None or not key:
            logger.warning("Weight dispute for a parcel that is not ours (AWB %s)", awb or "unknown")
            continue
        raised = parse_time(row.get("created_at")) or timezone.now()
        due = end_of(working_days_after(timezone.localdate(raised), settings.SHIPPING_DISPUTE_DAYS))
        detail = shipment.detail
        data = {
            "our_weight_g": detail.weight_g,
            "courier_weight_g": grams(row.get("charged_weight")),
            "amount": str(decimal(row.get("discrepancy_amount") or row.get("amount"))),
            "photo": bool(detail.parcel_photo),
            "raised_at": raised.isoformat(),
        }
        found.append(open_exception(shipment, Kind.WEIGHT_DISPUTE, due_at=due, data=data, reference=f"weight-{key}"))
    return found


def check_discrepancies(account):
    return record_discrepancies(account, carrier_for(account).discrepancies())


# Exceptions


def open_exception(shipment, kind, *, due_at=None, hours=24, days=None, data=None, reference=""):
    """A parcel that needs staff by a deadline: one open exception per parcel and kind (a new one tells the staff
    inbox: exception_opened; an open one is updated with the new data); with a `reference`, once for good."""
    data = data or {}
    with transaction.atomic():
        ShipmentDetail.objects.select_for_update().filter(shipment=shipment).first()  # one at a time per parcel
        if reference and (known := ShippingException.objects.filter(kind=kind, reference=reference).first()):
            return known
        deadline = due_at or timezone.now() + (timedelta(days=days) if days else timedelta(hours=hours))
        if not reference and (open_ := shipment.exceptions.filter(kind=kind, state="open").first()):
            open_.data, open_.due_at = {**open_.data, **data}, min(open_.due_at, deadline)  # news may bring it forward
            open_.save(update_fields=["data", "due_at", "modified"])
            return open_
        exception = ShippingException.objects.create(
            shipment=shipment, kind=kind, due_at=deadline, data=data, reference=reference
        )
        exception.opened()
    return exception


def resolve_exception(exception, resolution, by=None, dismiss=False):
    """Staff: what was done (or why it is dismissed). Once; returns whether it was still open."""
    resolution = (resolution or "").strip()
    if not resolution:
        raise ShippingError("Say what was done, or why it is dismissed.")
    state = ShippingException.State.DISMISSED if dismiss else ShippingException.State.RESOLVED
    now, user = timezone.now(), by if getattr(by, "pk", None) else None
    closed = ShippingException.objects.filter(pk=exception.pk, state=ShippingException.State.OPEN).update(
        state=state, resolution=resolution[:300], resolved_at=now, resolved_by=user, modified=now
    )
    exception.refresh_from_db()
    if closed:
        closing([exception.pk])
    return bool(closed)


def close_exceptions(shipment, kinds, resolution):
    """The site resolves what the parcel's news has settled (delivered after a failed attempt)."""
    now = timezone.now()
    settled = ShippingException.objects.filter(shipment=shipment, kind__in=kinds, state="open")
    ids = list(settled.values_list("pk", flat=True))
    settled.filter(pk__in=ids).update(
        state=ShippingException.State.RESOLVED, resolution=resolution, resolved_at=now, modified=now
    )
    if ids:
        closing(ids)


def closing(ids):
    """Tell the staff inbox, once the transaction is committed (exceptions_closed)."""
    transaction.on_commit(lambda: signals.exceptions_closed.send(sender=ShippingException, ids=ids), robust=True)


# PINs


def survey_pins(account, pins=None, limit=None):
    """The serviceability of the North-East's PINs (the PIN directory's, by state) from our default pickup, for a
    500 g prepaid parcel: each courier's rate, days and whether it takes COD; a PIN no courier serves gets one row of
    courier 0 (it goes by India Post). The PINs surveyed longest ago come first, at most SHIPPING_SURVEY_BATCH a run.
    Returns (surveyed, without a courier, without a COD courier)."""
    pickup = PickupLocation.default()
    if pickup is None:
        raise ShippingError("No pickup location yet (Shipping → Pickup locations).")
    if pins is None:
        north_east = [pin for pin, states in PinCode.objects.values_list("pin", "states") if set(states) & NORTH_EAST]
        last = dict(PinServiceability.objects.values_list("pin", "surveyed_at"))
        never = timezone.make_aware(datetime(2000, 1, 1))
        pins = sorted(north_east, key=lambda pin: (last.get(pin, never), pin))
    pins = pins[: limit or settings.SHIPPING_SURVEY_BATCH]
    carrier, (length, breadth, height) = carrier_for(account), dimensions()
    surveyed = without = without_cod = 0
    for pin in pins:
        try:
            quotes = carrier.quote(Parcel(pickup.pin_code, pin, 500, False, Decimal("500.00"), length, breadth, height))
        except CircuitOpen:
            break
        except IntegrationError as error:
            logger.warning("PIN %s not surveyed: %s", pin, error)
            continue
        now = timezone.now()
        with transaction.atomic():
            PinServiceability.objects.filter(pin=pin).delete()
            rows = [
                PinServiceability(
                    pin=pin,
                    courier_company_id=q.courier_company_id,
                    courier_name=q.courier_name[:80],
                    cod=q.cod,
                    prepaid=not q.blocked,
                    rate=q.rate,
                    etd_days=q.etd_days,
                    surveyed_at=now,
                )
                for q in {q.courier_company_id: q for q in quotes}.values()
            ]
            PinServiceability.objects.bulk_create(
                rows or [PinServiceability(pin=pin, courier_company_id=0, surveyed_at=now)]
            )
        surveyed += 1
        without += not any(row.prepaid for row in rows)
        without_cod += not any(row.cod and row.prepaid for row in rows)
    return surveyed, without, without_cod


# Pickup locations


def sync_pickup_locations(account):
    """Our pickup addresses as the carrier has them (its nicknames), kept as PickupLocation; the first becomes the
    default when there is none."""
    kept = []
    for place in carrier_for(account).pickup_locations():
        nickname = str(place.get("pickup_location") or "")[:36]
        if not nickname:
            continue
        location, _ = PickupLocation.objects.update_or_create(
            nickname=nickname,
            defaults={
                "external_id": str(place.get("id") or "")[:40],
                "address": str(place.get("address") or "")[:200],
                "city": str(place.get("city") or "")[:80],
                "state": str(place.get("state") or "")[:80],
                "pin_code": str(place.get("pin_code") or "")[:6],
                "phone": str(place.get("phone") or "")[:20],
                "active": True,
            },
        )
        kept.append(location)
    if kept and not PickupLocation.objects.filter(is_default=True).exists():
        PickupLocation.objects.filter(pk=kept[0].pk).update(is_default=True)
    return kept
