"""A courier's parcel (Shiprocket's recorded double): its delivery note written when its scans say it has left, after
the invoice it goes against (a cash-on-delivery bill is made at dispatch), and again for a re-shipment; the cash
collected and remitted after it."""

import pytest
from django.db import transaction
from django.utils import timezone

from erp.fake import FAKE
from integrations import crypto
from integrations.models import IntegrationAccount
from shipping import messages
from shipping import services as shipping
from shipping.carriers.fake import FAKE as SHIPROCKET
from shipping.models import CodRemittance, PickupLocation, ShipmentEvent
from shop import services as shop

from .helpers import code, invoiced, ordered, relay, relay_all, row, rows, stock_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def recorded_shiprocket(monkeypatch):
    SHIPROCKET.reset()
    monkeypatch.setattr(messages, "quiet", lambda now=None: False)
    yield SHIPROCKET
    SHIPROCKET.reset()


@pytest.fixture
def courier(db):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=True, label="API user")
    account.set_credentials({"email": "api-user@example.com", "password": "a-long-api-password"})
    account.save()
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_token=crypto.encrypt("x" * 40))
    PickupLocation.objects.create(
        nickname="Primary", city="Guwahati", state="Assam", pin_code="781024", is_default=True
    )
    account.refresh_from_db()
    return account


def scans(parcel, *codes):
    SHIPROCKET.move(parcel.tracking_number, *codes)
    read = shipping.carrier_for(parcel.detail.account).track([parcel.tracking_number])[parcel.tracking_number]
    shipping.apply_events(parcel, read, ShipmentEvent.Source.POLL)


def test_a_cash_on_delivery_parcel_through_a_courier(on, courier, book, customer, settings):
    settings.SHOP_COD_ENABLED = True
    order = ordered((book, 2), method="cod", user=customer, pin="781024")
    shop.place_cod(order)
    shop.pack_order(order)
    parcel = shipping.book(shipping.prepare(order, account=courier, courier_company_id=51))
    assert not rows(aggregate_id=order.number)  # booked, not gone: nothing for ERPNext
    scans(parcel, 42, 18)  # picked up, in transit: the order is shipped, its bill queued (not yet made)
    assert not rows(aggregate_id=order.number)  # the delivery note waits for the invoice it goes against
    order = invoiced(order)
    assert [r.event for r in rows(aggregate_id=order.number)] == ["invoice.issued", "parcel.dispatched"]
    dispatched = row("parcel.dispatched").payload
    assert dispatched["tracking_number"] == parcel.tracking_number and dispatched["courier"] == parcel.courier
    scans(parcel, 17, 7)  # out for delivery, delivered: the cash collected, a remittance expected
    payment = row("payment.received").payload
    assert (payment["mode"], payment["reference_no"], payment["amount"]) == ("cod", parcel.tracking_number, "598.00")
    remittance = CodRemittance.objects.get(shipment=parcel)
    remittance.remitted_amount, remittance.utr, remittance.remitted_at = 598, "UTR0099", timezone.localdate()
    remittance.state = CodRemittance.State.REMITTED
    with transaction.atomic():
        remittance.save()
    assert [r.event for r in rows(aggregate_id=order.number)] == [
        "invoice.issued",
        "parcel.dispatched",
        "payment.received",
        "settlement.received",
    ]
    relay()  # the item; then ERPNext has the copies
    stock_in(book, 5)
    relay_all()
    assert {r.state for r in rows(aggregate_id=order.number)} == {"sent"}
    assert FAKE.bins[(code(book), "Main - EL")] == 3


def test_a_re_shipment_has_a_delivery_note_of_its_own(on, courier, book, customer):
    order = ordered((book, 1), user=customer, pin="781024")
    shop.record_offline_payment(order, "UTR 401234567890")
    order = invoiced(shop.pack_order(order))
    first = shipping.book(shipping.prepare(order, account=courier, courier_company_id=51))
    scans(first, 42, 18)
    scans(first, 12)  # lost
    second = shipping.book(shipping.prepare(order, account=courier, courier_company_id=51))
    scans(second, 42)
    refs = [r.examleaf_ref for r in rows(event="parcel.dispatched")]
    assert refs == [f"delivery:{first.pk}", f"delivery:{second.pk}"]
