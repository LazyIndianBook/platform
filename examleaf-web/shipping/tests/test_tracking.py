"""Polling, the net under the webhook: which parcels are read (booked, not final, silent for 6 hours, their account
enabled), in batches of 50, the no-movement exception after 5 days, and an open circuit that waits for the next run."""

from datetime import timedelta

import pytest
from django.utils import timezone

from integrations.models import IntegrationAccount
from shipping import services
from shipping.carriers.fake import FAKE
from shipping.models import ShipmentDetail, ShippingException
from shipping.status import Status
from shipping.tasks import poll_tracking
from shop import services as shop
from shop.factories import ProductFactory

from .conftest import ordered

pytestmark = pytest.mark.django_db


def parcels(account, customer, count):
    made = []
    for _ in range(count):
        order = ordered((ProductFactory(weight_grams=300), 1), user=customer, email=customer.email)
        shop.record_offline_payment(order, f"UTR-{order.pk}")
        made.append(services.book(services.prepare(shop.pack_order(order), account=account, courier_company_id=51)))
    return made


def silent(shipments, hours):
    ShipmentDetail.objects.filter(shipment__in=shipments).update(last_event_at=timezone.now() - timedelta(hours=hours))


def test_the_parcels_silent_for_six_hours_are_read(account, pickup, customer):
    quiet, recent, final, by_hand = parcels(account, customer, 4)
    silent([quiet, final, by_hand], 7)
    ShipmentDetail.objects.filter(shipment=final).update(status=Status.DELIVERED)
    ShipmentDetail.objects.filter(shipment=by_hand).update(account=None, carrier="manual")
    assert list(services.due_for_poll()) == [quiet]
    FAKE.move(quiet.tracking_number, 42)
    assert poll_tracking() == 1
    assert services.parcel(quiet).detail.status == Status.IN_TRANSIT
    IntegrationAccount.objects.filter(pk=account.pk).update(enabled=False)
    assert not services.due_for_poll().exists()  # a disabled account is not asked


def test_fifty_awbs_a_call(account, pickup, customer, monkeypatch):
    shipments = parcels(account, customer, 3)
    silent(shipments, 7)
    calls = []
    original = type(services.carrier_for(account)).track

    def counted(carrier, awbs):
        calls.append(len(awbs))
        return original(carrier, awbs)

    monkeypatch.setattr(type(services.carrier_for(account)), "track", counted)
    assert services.poll(batch=2) == 3 and calls == [2, 1]
    assert sum(path.endswith("/courier/track/awbs") for _, path in FAKE.calls) == 1  # several at once: POST


def test_no_movement_for_five_days_asks_staff_once(account, pickup, customer):
    [stuck] = parcels(account, customer, 1)
    silent([stuck], 5 * 24 + 1)
    services.poll()
    services.poll()
    exception = ShippingException.objects.get(kind="no_movement")
    assert exception.shipment == stuck and exception.state == "open"


def test_an_open_circuit_waits_for_the_next_run(account, pickup, customer):
    [shipment] = parcels(account, customer, 1)
    silent([shipment], 7)
    account.force_open()
    calls = len(FAKE.calls)
    assert services.poll() == 0 and len(FAKE.calls) == calls


def test_an_unavailable_courier_is_read_again_next_time(account, pickup, customer):
    [shipment] = parcels(account, customer, 1)
    silent([shipment], 7)
    FAKE.fail("/courier/track/awb/", status=502)
    assert services.poll() == 0
    assert services.poll() == 1
