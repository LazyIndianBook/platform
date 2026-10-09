"""The shipping admin: every page opens with rows behind it, money is read-only, the parcel actions work, and the
order's page keeps a parcel booked with a courier as it is while staff save notes."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from shipping import services
from shipping.carriers.fake import FAKE
from shipping.models import (
    CodRemittance,
    PickupLocation,
    PinServiceability,
    PostalTariff,
    ShipmentCharge,
    ShipmentDetail,
    ShipmentEvent,
    ShippingException,
)
from shop.models import OrderNote, Shipment

pytestmark = pytest.mark.django_db
MODELS = [Shipment, ShippingException, ShipmentCharge, CodRemittance, PickupLocation, PinServiceability, PostalTariff]
EDITABLE = {PickupLocation, PostalTariff}


@pytest.fixture
def admin_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


@pytest.fixture
def parcel(account, pickup, cod):
    shipment = services.book(services.prepare(cod, account=account, courier_company_id=51))
    services.open_exception(shipment, "ndr", data={"attempts": 1})
    ShipmentCharge.objects.create(
        shipment=shipment,
        account=account,
        kind="freight",
        amount=Decimal("63.25"),
        statement_line_id="x",
        charged_at=timezone.now(),
    )
    CodRemittance.objects.create(shipment=shipment, expected_amount=598, expected_on=timezone.localdate())
    PinServiceability.objects.create(pin="781024", courier_company_id=51, courier_name="Xpressbees Surface")
    PostalTariff.objects.create(service="book_post", weight_to_g=50, price=4, effective_from=timezone.localdate())
    return shipment


def test_every_page_opens_and_money_is_read_only(admin_client, parcel):
    for model in MODELS:
        base = f"admin:{model._meta.app_label}_{model._meta.model_name}"
        row = model.objects.first()
        for url, expected in [
            (reverse(f"{base}_changelist"), 200),
            (reverse(f"{base}_changelist") + "?q=a&o=1", 200),
            (reverse(f"{base}_add"), 200 if model in EDITABLE else 403),
            (reverse(f"{base}_change", args=[row.pk]), 200),
            (reverse(f"{base}_history", args=[row.pk]), 200),
            (reverse(f"{base}_delete", args=[row.pk]), 200 if model in EDITABLE else 403),
        ]:
            assert admin_client.get(url).status_code == expected, url
    listed = admin_client.get(reverse("admin:shop_shipment_changelist") + "?detail__status__exact=booked")
    assert parcel.tracking_number in listed.content.decode()
    page = admin_client.get(reverse("admin:shop_shipment_change", args=[parcel.pk])).content.decode()
    assert "AWB assigned" in page and "delivery failed (NDR)" in page and "63.25" in page


def act(client, model, action, objects, **data):
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
    return client.post(url, {"action": action, "_selected_action": [o.pk for o in objects], **data}, follow=True)


def test_parcel_actions_read_the_tracking_and_cancel(admin_client, parcel):
    FAKE.move(parcel.tracking_number, 19)
    assert "Tracking read for 1 parcel(s)." in act(admin_client, Shipment, "read_tracking", [parcel]).content.decode()
    assert parcel.events.filter(carrier_code="19").exists()
    page = act(admin_client, Shipment, "cancel_bookings", [parcel]).content.decode()
    assert "can no longer be cancelled" in page  # the courier is out to collect it


def test_exceptions_are_resolved_with_what_was_done(admin_client, parcel):
    exception = ShippingException.objects.get()
    assert "Resolve exceptions" in act(admin_client, ShippingException, "resolve", [exception]).content.decode()
    act(admin_client, ShippingException, "resolve", [exception], apply="1", resolution="Called the customer.")
    exception.refresh_from_db()
    assert exception.state == "resolved" and exception.resolution == "Called the customer."


def test_the_order_page_keeps_a_courier_s_parcel_while_notes_are_saved(admin_client, parcel):
    order = parcel.order
    url = reverse("admin:shop_order_change", args=[order.pk])
    page = admin_client.get(url).content.decode()
    shipments = page[page.find('id="shipments-group"') :][:6000]
    assert parcel.tracking_number in shipments, shipments
    assert "booked" in shipments and "disabled" in shipments
    prefixes = ["items", "discount_lines", "payments", "shipments", "refunds", "notes"]
    data = {f"{prefix}-{name}": "0" for prefix in prefixes for name in ("TOTAL_FORMS", "INITIAL_FORMS")}
    data.update({"shipments-TOTAL_FORMS": "1", "shipments-INITIAL_FORMS": "1", "shipments-0-id": parcel.pk})
    data.update({"shipments-0-order": order.pk, "shipments-0-tracking_number": "TAMPERED"})
    data.update({"notes-TOTAL_FORMS": "1", "notes-0-text": "Courier booked.", "notes-0-order": order.pk})
    ShipmentDetail.objects.filter(shipment=parcel).update(status=None)  # being booked: no AWB checks then
    Shipment.objects.filter(pk=parcel.pk).update(tracking_number="")
    response = admin_client.post(url, data)
    assert response.status_code == 302, response.content.decode()[:3000]
    assert OrderNote.objects.filter(text="Courier booked.").exists()
    assert Shipment.objects.get(pk=parcel.pk).tracking_number == ""  # the courier's, not the form's
    assert ShipmentEvent.objects.filter(shipment=parcel).exists()
