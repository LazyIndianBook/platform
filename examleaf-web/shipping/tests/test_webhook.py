"""POST /api/hooks/parcel-events/: the token (current, previous for 24 hours, wrong, missing, none set), the raw body
kept once, the scans applied once, a claim of delivery read again first, and the processing's failures."""

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from integrations.models import InboundEvent, IntegrationAccount
from shipping import services
from shipping.carriers.fake import FAKE
from shipping.models import ShipmentEvent
from shipping.status import Status
from shipping.tasks import process_inbound_event
from shop.models import Order

from .conftest import WEBHOOK_TOKEN

pytestmark = pytest.mark.django_db
URL = "/api/hooks/parcel-events/"


def post(client, body, token=WEBHOOK_TOKEN):
    headers = {} if token is None else {"HTTP_X_API_KEY": token}
    data = body if isinstance(body, str | bytes) else json.dumps(body)
    return client.post(URL, data, content_type="application/json", **headers)


@pytest.fixture
def parcel(account, pickup, prepaid):
    return services.book(services.prepare(prepaid, account=account, courier_company_id=51))


def test_the_address_has_none_of_the_words_shiprocket_refuses():
    assert reverse("parcel-events") == URL
    assert not any(word in URL for word in ["shiprocket", "kartrocket", "sr", "kr"])


def test_the_current_token_is_accepted_and_the_body_kept_once(client, parcel, django_capture_on_commit_callbacks):
    FAKE.move(parcel.tracking_number, 42, 18)
    body = FAKE.webhook(parcel.tracking_number)
    with django_capture_on_commit_callbacks(execute=True):
        response = post(client, body)
    assert response.status_code == 200 and response.json() == {"detail": "Received."}
    event = InboundEvent.objects.get()
    assert event.state == "accepted" and event.processed_at and json.loads(event.body) == body
    assert "X-Api-Key" not in event.headers and event.account_id == parcel.detail.account_id
    assert post(client, body).status_code == 200  # Shiprocket sends it again: answered, not kept again
    assert InboundEvent.objects.count() == 1
    parcel.order.refresh_from_db()
    assert parcel.order.status == Order.Status.SHIPPED
    assert services.parcel(parcel).detail.status == Status.IN_TRANSIT


def test_the_previous_token_works_for_24_hours_after_a_rotation(client, parcel, account):
    new = account.rotate_webhook_token()
    assert post(client, {"awb": "1"}, token=new).status_code == 200
    assert post(client, {"awb": "2"}, token=WEBHOOK_TOKEN).status_code == 200  # the previous one, still
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_rotated_at=timezone.now() - timedelta(hours=25))
    assert post(client, {"awb": "3"}, token=WEBHOOK_TOKEN).status_code == 403
    assert post(client, {"awb": "4"}, token=new).status_code == 200


def test_a_wrong_or_missing_token_is_refused_and_kept_without_the_body(client, parcel):
    assert post(client, {"awb": parcel.tracking_number}, token="wrong").status_code == 403
    assert post(client, {"awb": parcel.tracking_number}, token=None).status_code == 403
    assert post(client, {"awb": parcel.tracking_number}, token="").status_code == 403
    rejected = InboundEvent.objects.filter(state="rejected")
    assert rejected.count() == 3 and not rejected.exclude(body="").exists()
    assert post(client, {"awb": parcel.tracking_number}).status_code == 200  # the same body, the right token: kept


def test_no_token_set_or_a_disabled_account_refuses_everything(client, account):
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_token="")
    assert post(client, {"awb": "1"}).status_code == 403
    assert post(client, {"awb": "1"}, token=None).status_code == 403
    account.refresh_from_db()
    token = account.rotate_webhook_token()
    IntegrationAccount.objects.filter(pk=account.pk).update(enabled=False)
    assert post(client, {"awb": "1"}, token=token).status_code == 403


def test_a_claim_of_delivery_is_read_again_before_it_counts(client, parcel, django_capture_on_commit_callbacks):
    awb = parcel.tracking_number
    FAKE.move(awb, 42, 18)
    forged = FAKE.webhook(awb)  # an unsigned body saying "delivered" while the courier says in transit
    forged.update(shipment_status_id=7, shipment_status="DELIVERED", current_status="DELIVERED")
    forged["scans"].append({**forged["scans"][-1], "sr-status": "7", "sr-status-label": "DELIVERED"})
    with django_capture_on_commit_callbacks(execute=True):
        assert post(client, forged).status_code == 200
    detail = services.parcel(parcel).detail
    assert detail.status == Status.IN_TRANSIT and not parcel.events.filter(status=Status.DELIVERED).exists()
    FAKE.move(awb, 17, 7)  # now it is delivered
    with django_capture_on_commit_callbacks(execute=True):
        post(client, FAKE.webhook(awb))
    assert services.parcel(parcel).detail.status == Status.DELIVERED
    assert parcel.events.get(status=Status.DELIVERED).source == ShipmentEvent.Source.POLL  # from the read
    parcel.order.refresh_from_db()
    assert parcel.order.status == Order.Status.DELIVERED


def test_scans_repeated_in_later_payloads_are_kept_once(client, parcel, django_capture_on_commit_callbacks):
    awb = parcel.tracking_number
    FAKE.move(awb, 42)
    with django_capture_on_commit_callbacks(execute=True):
        post(client, FAKE.webhook(awb))
    FAKE.move(awb, 18)
    with django_capture_on_commit_callbacks(execute=True):
        post(client, FAKE.webhook(awb))  # scans 42 and 18
    again = FAKE.webhook(awb)
    again["current_timestamp"] = "01 01 2027 10:00:00"  # another body, the same scans
    with django_capture_on_commit_callbacks(execute=True):
        post(client, again)
    assert list(parcel.events.exclude(source="manual").values_list("carrier_code", flat=True)) == ["42", "18"]
    assert list(InboundEvent.objects.order_by("pk").values_list("state", flat=True)) == [
        "accepted",
        "accepted",
        "duplicate",
    ]


def test_a_parcel_that_is_not_ours_is_noted(client, account, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        post(client, {**FAKE.webhook("999"), "awb": "999"})
    event = InboundEvent.objects.get()
    assert event.processed_at and event.error == "No parcel of ours has this AWB."


def test_a_body_that_cannot_be_processed_fails_and_is_replayed(client, account):
    post(client, "not json")
    event = InboundEvent.objects.get()
    assert process_inbound_event.apply(args=(event.pk,), throw=False).state == "FAILURE"
    event.refresh_from_db()
    assert event.state == "failed" and "JSONDecodeError" in event.error
    assert event.replay() and InboundEvent.objects.get().state == "accepted"


def test_webhooks_are_throttled_per_client_address(client, account, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "parcel_events", "2/minute")
    assert [post(client, {"awb": str(n)}).status_code for n in range(3)] == [200, 200, 429]
