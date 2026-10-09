"""The whole courier flow against the recorded Shiprocket (test mode): quote, book, label, pickup, manifest, the
courier's scans, delivered, the COD remittance expected and the statement's charges; and booking's refusals."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from integrations.client import IntegrationUnavailable
from integrations.models import IntegrationCall
from shipping import services
from shipping.carriers import Scan, carrier_for
from shipping.carriers.fake import FAKE
from shipping.models import CodRemittance, ShipmentCharge, ShipmentDetail, ShipmentEvent
from shipping.status import Status
from shop.factories import ProductFactory, make_order
from shop.models import Order, OrderNote, Payment

pytestmark = pytest.mark.django_db
POLL = ShipmentEvent.Source.POLL


def booked(order, account, courier=51, **kwargs):
    return services.book(services.prepare(order, account=account, courier_company_id=courier, **kwargs))


def scans(shipment, *codes):
    """The recorded Shiprocket's tracking of the parcel after scans with these status codes."""
    FAKE.move(shipment.tracking_number, *codes)
    return carrier_for(shipment.detail.account).track([shipment.tracking_number])[shipment.tracking_number]


def test_quote_book_label_pickup_manifest_deliver_cod_and_charges(
    account, pickup, cod, texts, django_capture_on_commit_callbacks
):
    result = services.quote(cod, account)
    names = [quote.courier_name for quote in result["couriers"]]
    assert names == ["Xpressbees Surface", "Delhivery Surface", "Blue Dart"]  # no Amazon (no COD), Ekart rated 3.9
    assert result["india_post"] == [] and result["weight_g"] == 2 * 300 + 50  # COD: no India Post
    with django_capture_on_commit_callbacks(execute=True):
        shipment = booked(cod, account, courier=51, courier_name="Xpressbees Surface", quoted_rate=Decimal("63.25"))
    detail = shipment.detail
    assert detail.status == Status.BOOKED and shipment.tracking_number.startswith("1411")
    assert detail.reference == cod.number and detail.cod_amount == cod.total.amount == Decimal("598.00")
    assert shipment.courier == "Xpressbees" and "17track" in shipment.tracking_url
    detail.refresh_from_db()
    assert detail.label.read().startswith(b"%PDF")  # fetched by its task after the commit, kept with us
    day = services.schedule_pickup(shipment)
    assert services.parcel(shipment).detail.pickup_date == day
    assert services.manifest([shipment]).endswith("manifest.pdf")
    assert ShipmentDetail.objects.get(pk=detail.pk).manifested_at
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_events(shipment, scans(shipment, 42, 18), POLL)
    cod.refresh_from_db()
    assert cod.status == Order.Status.SHIPPED and mail.outbox[-1].subject.endswith("is on its way")
    assert shipment.tracking_number in mail.outbox[-1].body and cod.get_link_url() in mail.outbox[-1].body
    assert texts == [(cod.number, "shipped")]
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_events(shipment, scans(shipment, 17), POLL)
    assert texts[-1] == (cod.number, "out_for_delivery")  # COD: keep the cash ready
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_events(shipment, scans(shipment, 7), POLL)
    cod.refresh_from_db()
    assert cod.status == Order.Status.DELIVERED and texts[-1] == (cod.number, "delivered")
    assert cod.payments.get(method="cod").status == Payment.Status.CAPTURED
    remittance = CodRemittance.objects.get(shipment=shipment)
    assert remittance.expected_amount == Decimal("598.00") and remittance.state == "expected"
    assert (remittance.expected_on - timezone.localdate()).days >= 12  # 10 working days
    assert services.sync_statement(account) == 2  # the freight and the COD charge
    assert services.sync_statement(account) == 0  # once each
    charges = sorted(ShipmentCharge.objects.filter(shipment=shipment).values_list("kind", "amount"))
    assert charges == [("cod", Decimal("25.96")), ("freight", Decimal("63.25"))]
    assert IntegrationCall.objects.filter(operation="login").count() == 1  # one token for every call


def test_prepaid_quotes_have_india_post_beside_the_couriers(account, pickup, prepaid, settings):
    from django.core.management import call_command

    call_command("loaddata", "postal_tariffs", verbosity=0)
    result = services.quote(prepaid, account)
    assert [q.courier_name for q in result["couriers"]][0] == "Amazon Shipping 1kg"  # prepaid: COD does not matter
    assert result["weight_g"] == 350  # the book and its packing: Book Post's 350 g slab (₹4, then ₹3 per 50 g)
    assert result["india_post"] == [{"service": "book_post", "label": "Book Post (open, untracked)", "price": 22}]
    settings.SHIPPING_GYAN_POST = True  # once the postal division confirms the books qualify: its 500 g slab
    assert [p["price"] for p in services.quote(prepaid, account)["india_post"]] == [22, 25]


def test_a_quote_is_kept_ten_minutes_and_the_last_one_shown_while_the_courier_is_down(
    account, pickup, prepaid, settings
):
    first = services.quote(prepaid, account)
    services.quote(prepaid, account)
    assert sum(path.endswith("/serviceability/") for _, path in FAKE.calls) == 1  # the second from the cache
    settings.SHIPPING_QUOTE_CACHE_SECONDS = 0  # kept no time at all: asked every time, its last answer kept
    services.quote(prepaid, account, weight_g=999)
    FAKE.fail("/courier/serviceability/", status=503)
    stale = services.quote(prepaid, account, weight_g=999)
    assert stale["stale"] and "HTTP 503" in stale["error"] and stale["couriers"] == first["couriers"]
    FAKE.fail("/courier/serviceability/", status=503)
    nothing = services.quote(prepaid, account, weight_g=111)  # never asked before: nothing to show
    assert not nothing["stale"] and nothing["couriers"] == [] and nothing["error"]


def test_the_cash_to_collect_is_what_shiprocket_is_sent_and_a_mismatch_is_refused(account, pickup, cod):
    shipment = booked(cod, account)
    sent = FAKE.orders[cod.number]["payload"]
    assert (sent["sub_total"], sent["payment_method"], sent["shipping_charges"], sent["total_discount"]) == (
        598.0,
        "COD",
        0,
        0,
    )
    services.cancel(shipment)
    again = services.prepare(cod, account=account, courier_company_id=51)
    ShipmentDetail.objects.filter(shipment=again).update(cod_amount=Decimal("498.00"))  # stale, or edited
    with pytest.raises(services.ShippingError, match="cash to collect"):
        services.book(again)
    Order.objects.filter(pk=cod.pk).update(total=Decimal("1.00"))  # a total that no longer adds up
    with pytest.raises(services.ShippingError, match="its total"):
        services.book(again)
    assert len(FAKE.orders) == 1  # nothing more sent


def test_booking_is_idempotent(account, pickup, prepaid):
    shipment = booked(prepaid, account)
    assert services.book(shipment).tracking_number == shipment.tracking_number  # booked: left as it is
    assert [call for call in FAKE.calls if call[1].endswith("/orders/create/adhoc")] == [
        ("POST", "/v1/external/orders/create/adhoc")
    ]
    assert FAKE.orders[prepaid.number]["payload"]["payment_method"] == "Prepaid"


def test_a_lost_answer_is_found_again_and_a_parcel_being_booked_waits(account, pickup, prepaid):
    shipment = services.prepare(prepaid, account=account, courier_company_id=51)
    ShipmentDetail.objects.filter(shipment=shipment).update(locked_until=timezone.now() + timedelta(minutes=5))
    with pytest.raises(services.ParcelBusy):  # another worker is talking to Shiprocket about it
        services.book(shipment)
    ShipmentDetail.objects.filter(shipment=shipment).update(locked_until=None)
    FAKE.fail("/courier/assign/awb", status=504)  # the order was made, the AWB's answer lost
    with pytest.raises(IntegrationUnavailable):
        services.book(shipment)
    detail = ShipmentDetail.objects.get(shipment=shipment)
    assert detail.external_shipment_id and detail.status is None and detail.locked_until is None  # ids kept
    FAKE.orders[prepaid.number]["awb"] = "1411000000000777"  # it was assigned after all, the answer lost
    assert services.book(shipment).tracking_number == "1411000000000777"  # found, not assigned again
    assert len(FAKE.orders) == 1 and sum(path.endswith("/assign/awb") for _, path in FAKE.calls) == 1


def test_a_reused_order_id_is_found_and_adopted(account, pickup, prepaid):
    shipment = services.prepare(prepaid, account=account, courier_company_id=51)
    FAKE.orders[prepaid.number] = {  # made by a try whose answer never came
        "reference": prepaid.number,
        "order_id": 555,
        "shipment_id": 556,
        "awb": None,
        "courier_id": None,
        "courier_name": "",
        "cancelled": False,
        "payload": {},
    }
    assert services.book(shipment).detail.external_order_id == "555"


def test_booking_refusals(account, pickup, prepaid, book):
    booked(prepaid, account)
    with pytest.raises(services.ShippingError, match="booked or on its way"):
        services.prepare(prepaid, account=account, courier_company_id=51)
    with pytest.raises(services.ShippingError, match="only packed orders"):
        services.prepare(make_order((book, 1)), account=account, courier_company_id=51)
    unweighed = make_order((ProductFactory(title="Unweighed", weight_grams=0), 1))
    with pytest.raises(services.ShippingError, match="No weight for Unweighed"):
        services.parcel_weight(unweighed)


def test_a_reshipment_gets_its_own_reference(account, pickup, prepaid):
    first = booked(prepaid, account)
    services.cancel(first)
    second = booked(prepaid, account)
    assert second.detail.reference == f"{prepaid.number}-R1" and second.tracking_number != first.tracking_number
    assert services.parcel(first).detail.status == Status.CANCELLED


def test_cancel_only_before_the_courier_is_out_to_collect(account, pickup, prepaid):
    shipment = booked(prepaid, account)
    services.apply_events(shipment, scans(shipment, 19), POLL)  # out for pickup
    with pytest.raises(services.ShippingError, match="can no longer be cancelled"):
        services.cancel(shipment)


def test_a_returned_cod_parcel_asks_staff_and_a_prepaid_one_to_reship_or_refund(
    account, pickup, cod, prepaid, django_capture_on_commit_callbacks
):
    for order in (cod, prepaid):
        shipment = booked(order, account)
        with django_capture_on_commit_callbacks(execute=True):
            services.apply_events(shipment, scans(shipment, 42, 18, 21), POLL)  # a failed attempt
            services.apply_events(shipment, scans(shipment, 9, 46), POLL)  # returning (the customer is told)
            services.apply_events(shipment, scans(shipment, 10), POLL)  # back with us
        order.refresh_from_db()
        assert services.parcel(shipment).detail.status == Status.RETURNED
        assert order.status == Order.Status.SHIPPED  # the order's states stay its own: no "returned"
        exception = shipment.exceptions.get(kind="rto")
        wanted = "cancel the order" if order.is_cod else "reship or refund"
        assert exception.data["stage"] == "returned" and wanted in exception.data["todo"]
        assert OrderNote.objects.filter(order=order, text__contains=wanted).count() == 1
        assert shipment.exceptions.filter(kind="ndr").exists()
    assert sum(message.subject.endswith("is coming back to us") for message in mail.outbox) == 2
    assert sum(message.subject.endswith("could not be delivered") for message in mail.outbox) == 2
    assert not CodRemittance.objects.exists()


def test_a_shipped_order_whose_parcel_came_back_can_be_sent_again(account, pickup, prepaid):
    shipment = booked(prepaid, account)
    services.apply_events(shipment, scans(shipment, 42, 9, 10), POLL)
    again = booked(Order.objects.get(pk=prepaid.pk), account)
    assert again.detail.reference == f"{prepaid.number}-R1"


def test_scans_out_of_order_and_twice_are_kept_once(account, pickup, prepaid):
    shipment = booked(prepaid, account)
    read = scans(shipment, 42, 18, 17)
    services.apply_events(shipment, list(reversed(read)), ShipmentEvent.Source.WEBHOOK)
    assert services.apply_events(shipment, read, POLL) == []  # the same scans again: nothing new
    assert shipment.events.exclude(source="manual").count() == 3
    assert services.parcel(shipment).detail.status == Status.OUT_FOR_DELIVERY
    late = Scan(shipment.tracking_number, "18", "IN TRANSIT", Status.IN_TRANSIT, read[-1].occurred_at, activity="x")
    services.apply_events(shipment, [late], ShipmentEvent.Source.WEBHOOK)  # an older status, arriving late
    assert services.parcel(shipment).detail.status == Status.OUT_FOR_DELIVERY


def test_a_parcel_sent_by_hand_ships_the_order_as_the_admin_does(prepaid, texts):
    shipment = services.ship_by_hand(prepaid, "India Post", "EA123456789IN")
    prepaid.refresh_from_db()
    assert prepaid.status == Order.Status.SHIPPED and shipment.detail.carrier == "manual"
    assert shipment.detail.status == Status.IN_TRANSIT and "17track" in shipment.tracking_url
    assert shipment.events.get().carrier_label == "Handed over to India Post"
