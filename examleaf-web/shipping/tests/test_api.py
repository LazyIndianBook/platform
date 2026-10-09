"""The staff API under /api/v1/shipping/ (the staff app's permissions, deny by default: staff/tests/test_matrix.py has
every role; the admin host only; every change in the audit log) and the customer's order page, which shows a parcel
booked with a courier only once it has left."""

import io

import pytest
from django.core.management import call_command
from PIL import Image

from accounts import roles
from accounts.factories import UserFactory
from shipping import services
from shipping.carriers.fake import FAKE
from shipping.models import PickupLocation, ShipmentDetail, ShipmentEvent, ShippingException
from shipping.status import Status
from staff.models import AuditEvent
from staff.tests.conftest import make_staff, signed_in

pytestmark = pytest.mark.django_db
BASE = "/api/v1/shipping"


def logged():
    return list(
        AuditEvent.objects.filter(action__startswith="shipping.").order_by("id").values_list("action", flat=True)
    )


@pytest.fixture
def parcel(account, pickup, prepaid):
    return services.book(services.prepare(prepaid, account=account, courier_company_id=51))


def move(parcel, *codes):
    FAKE.move(parcel.tracking_number, *codes)
    read = services.carrier_for(parcel.detail.account).track([parcel.tracking_number])[parcel.tracking_number]
    services.apply_events(parcel, read, ShipmentEvent.Source.POLL)


def test_staff_only(client, parcel):
    assert client.get(f"{BASE}/shipments/").status_code in (401, 403)  # signed out
    client.force_login(UserFactory())  # a student
    assert client.get(f"{BASE}/shipments/").status_code == 403
    assert client.get(f"{BASE}/orders/{parcel.order.number}/quote/").status_code == 403
    assert client.post("/api/v1/shipping/manifest/", {"shipments": [parcel.pk]}, "application/json").status_code == 403
    client.force_login(UserFactory(is_staff=True, totp=False))  # staff without an authenticator app
    assert client.get(f"{BASE}/shipments/").json()["code"] == "mfa_setup_required"


def test_the_quote_and_booking_with_a_courier(
    staff_client, account, pickup, prepaid, django_capture_on_commit_callbacks
):
    quote = staff_client.get(f"{BASE}/orders/{prepaid.number}/quote/").json()
    assert [c["courier_name"] for c in quote["couriers"]][:1] == ["Amazon Shipping 1kg"] and not quote["stale"]
    chosen = quote["couriers"][0]
    body = {"order": prepaid.number, "courier_company_id": chosen["courier_company_id"], "weight_g": 420}
    body.update(courier_name=chosen["courier_name"], quoted_rate=chosen["rate"])
    with django_capture_on_commit_callbacks(execute=True):
        response = staff_client.post(f"{BASE}/shipments/", body, "application/json")
    assert response.status_code == 202 and response.json()["detail"]["status"] is None  # booked by a task
    shipment = prepaid.shipments.get()
    detail = shipment.detail
    assert detail.status == Status.BOOKED and detail.weight_g == 420 and str(detail.quoted_rate) == chosen["rate"]
    page = staff_client.get(f"{BASE}/shipments/{shipment.pk}/").json()
    assert page["tracking_number"] == shipment.tracking_number and page["events"][0]["carrier_label"] == "AWB assigned"
    assert page["detail"]["has_label"] and page["cod_remittance"] is None
    assert staff_client.post(f"{BASE}/shipments/", body, "application/json").json() == {
        "non_field_errors": [f"Order {prepaid.number} has a parcel booked or on its way already."]
    }
    listed = staff_client.get(f"{BASE}/shipments/?status=booked&search={shipment.tracking_number}").json()
    assert listed["count"] == 1 and staff_client.get(f"{BASE}/shipments/?status=delivered").json()["count"] == 0
    booked = AuditEvent.objects.get(action="shipping.booked")  # once: the refused second booking left none
    assert (booked.target_type, booked.target_label) == ("shop.order", prepaid.number)
    assert booked.details == {"shipment": shipment.pk, "courier_company_id": chosen["courier_company_id"],
                              "courier_name": chosen["courier_name"], "weight_g": 420}  # fmt: skip


def test_booking_needs_a_courier_and_one_sent_by_hand_ships_at_once(staff_client, prepaid):
    refused = staff_client.post(f"{BASE}/shipments/", {"order": prepaid.number}, "application/json")
    assert refused.status_code == 400 and "courier_company_id" in refused.json()
    body = {"order": prepaid.number, "courier": "India Post", "tracking_number": "EA123456789IN"}
    response = staff_client.post(f"{BASE}/shipments/", body, "application/json")
    assert response.status_code == 201 and response.json()["detail"]["carrier"] == "manual"
    assert staff_client.post(f"{BASE}/shipments/", body, "application/json").status_code == 400  # shipped already
    assert logged() == ["shipping.shipped_by_hand"]


def test_label_pickup_manifest_events_and_photo(staff_client, parcel, django_capture_on_commit_callbacks):
    url = f"{BASE}/shipments/{parcel.pk}"
    assert staff_client.get(f"{url}/label/").status_code == 404  # not fetched yet (no commit in this test)
    with django_capture_on_commit_callbacks(execute=True):
        assert staff_client.post(f"{url}/label/").status_code == 202
    label = staff_client.get(f"{url}/label/", HTTP_ACCEPT="application/pdf")
    assert label.status_code == 200 and b"".join(label.streaming_content).startswith(b"%PDF")
    pickup = staff_client.post(f"{url}/pickup/", {}, "application/json")
    assert pickup.status_code == 200 and pickup.json()["pickup_date"]
    manifest = staff_client.post(f"{BASE}/manifest/", {"shipments": [parcel.pk]}, "application/json")
    assert manifest.json()["url"].endswith("manifest.pdf")
    assert [e["carrier_label"] for e in staff_client.get(f"{url}/events/").json()][0] == "AWB assigned"
    picture = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(picture, "JPEG")
    picture.name = "scale.jpg"
    picture.seek(0)
    response = staff_client.post(f"{url}/photo/", {"photo": picture})  # multipart
    assert response.status_code == 200, response.json()
    assert response.json()["detail"]["has_photo"]
    assert ShipmentDetail.objects.get(shipment=parcel).parcel_photo.name.endswith(".jpg")
    assert logged() == ["shipping.label_requested", "shipping.pickup_scheduled", "shipping.manifested",
                        "shipping.photo_added"]  # fmt: skip


def test_cancel_ndr_action_and_an_unreachable_courier(staff_client, parcel):
    url = f"{BASE}/shipments/{parcel.pk}"
    assert staff_client.post(
        f"{url}/ndr-action/", {"action": "re-attempt", "comments": "x"}, "application/json"
    ).json() == {"non_field_errors": [f"{parcel.detail.reference}: no failed delivery to act on."]}
    FAKE.fail("/courier/generate/pickup", status=503)
    assert staff_client.post(f"{url}/pickup/", {}, "application/json").status_code == 503
    move(parcel, 42, 18, 21)
    action = {"action": "re-attempt", "comments": "Customer home after 5 pm", "phone": "9864099999"}
    response = staff_client.post(f"{url}/ndr-action/", {**action, "deferred_date": "2026-10-15"}, "application/json")
    assert response.status_code == 200
    taken = response.json()["data"]["actions"][0]
    assert taken["action"] == "re-attempt" and taken["changed"] == ["deferred_date", "phone"]
    assert "9864099999" not in str(response.json())  # what changed, not the new details
    cancelled = staff_client.post(f"{url}/cancel/").json()
    assert "can no longer be cancelled" in cancelled["non_field_errors"][0]  # picked up
    [ndr] = AuditEvent.objects.filter(action__startswith="shipping.")  # the refusals left none
    assert ndr.action == "shipping.ndr_action" and ndr.details["changed"] == ["deferred_date", "phone"]
    assert "9864099999" not in str(ndr.details)


def test_the_parcels_answer_on_the_admin_host_only_and_a_packer_sees_its_queue(settings, parcel):
    settings.ALLOWED_HOSTS = ["examleaf.in", "admin.examleaf.in", "testserver"]
    settings.ADMIN_HOSTS = ["admin.examleaf.in"]
    packer = signed_in(make_staff(roles.PACKER))
    for path in ["shipments/", f"orders/{parcel.order.number}/quote/", "cod/", "exceptions/"]:
        assert packer.get(f"{BASE}/{path}", HTTP_HOST="examleaf.in").status_code == 404, path
    assert packer.get("/api/v1/insights/forecasts/", HTTP_HOST="examleaf.in").status_code == 404
    assert packer.get(f"{BASE}/", HTTP_HOST="examleaf.in").status_code == 200  # the checkout's delivery rates
    assert packer.get(f"{BASE}/quote/", HTTP_HOST="examleaf.in").status_code != 404
    on_admin = packer.get(f"{BASE}/shipments/", HTTP_HOST="admin.examleaf.in").json()
    assert [row["id"] for row in on_admin["results"]] == [parcel.pk]
    services.ship(parcel)
    services.deliver(parcel)  # delivered: out of the packing room's scope (paid, packed and shipped orders)
    assert packer.get(f"{BASE}/shipments/{parcel.pk}/", HTTP_HOST="admin.examleaf.in").status_code == 404
    sales = signed_in(make_staff(roles.SALES))
    assert sales.get(f"{BASE}/shipments/{parcel.pk}/", HTTP_HOST="admin.examleaf.in").status_code == 200


def test_exceptions_cod_charges_and_pickup_locations(staff_client, account, parcel):
    move(parcel, 42, 18, 21)
    exceptions = staff_client.get(f"{BASE}/exceptions/?state=open&kind=ndr").json()
    assert exceptions["count"] == 1 and exceptions["results"][0]["order"] == parcel.order.number
    pk = exceptions["results"][0]["id"]
    resolved = staff_client.post(
        f"{BASE}/exceptions/{pk}/resolve/", {"resolution": "Called, re-attempt."}, "application/json"
    )
    assert resolved.json()["state"] == "resolved" and ShippingException.objects.get(pk=pk).resolved_by
    assert (
        staff_client.post(f"{BASE}/exceptions/{pk}/resolve/", {"resolution": "x"}, "application/json").status_code
        == 400
    )
    services.sync_statement(account)
    assert staff_client.get(f"{BASE}/charges/?kind=freight").json()["count"] == 1
    assert staff_client.get(f"{BASE}/cod/").json()["count"] == 0
    synced = staff_client.post(f"{BASE}/pickup-locations/sync/").json()
    assert [place["nickname"] for place in synced] == ["Primary"]
    second = {"nickname": "Store 2", "pin_code": "781001", "is_default": True}
    created = staff_client.post(f"{BASE}/pickup-locations/", second, "application/json")
    assert created.status_code == 201, created.json()
    assert PickupLocation.default().nickname == "Store 2"  # one default at a time


def test_the_customer_sees_a_courier_s_parcel_only_once_it_has_left(client, parcel, customer):
    client.force_login(customer)
    order = parcel.order
    assert client.get(f"/api/v1/orders/{order.number}/").json()["shipments"] == []  # booked, waiting for its pickup
    move(parcel, 42, 18)
    [shown] = client.get(f"/api/v1/orders/{order.number}/").json()["shipments"]
    assert shown["tracking_number"] == parcel.tracking_number
    assert client.get(f"/api/v1/orders/t/{order.token}/").json()["shipments"] == [shown]  # the email's link too


def test_the_schema_has_the_staff_endpoints(tmp_path):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", tmp_path / "schema.yml")
    schema = (tmp_path / "schema.yml").read_text()
    for path in ["/api/v1/shipping/shipments/{id}/ndr-action/", "/api/v1/shipping/orders/{number}/quote/"]:
        assert path in schema
    assert "/api/hooks/parcel-events/" not in schema and "shipping (staff)" in schema
