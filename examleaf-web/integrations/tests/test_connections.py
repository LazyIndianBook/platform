"""The connections page (integrations/connections.py, integrations/api.py): one card per integration that says whether
it works without showing a secret; a connection test through each provider's client with the network answered here,
its result kept; credentials replaced only after their own test passes, masked everywhere (the audit's changes too);
the panel taking Razorpay over from the environment without stopping it; the mode, the circuit, the webhook tokens
(the previous one accepted for 24 hours); events and dead letters replayed and discarded; Razorpay's silence watched."""

import json
from datetime import timedelta
from types import SimpleNamespace

import boto3
import httpx
import pytest
from botocore.stub import Stubber
from django.core import mail
from django.utils import timezone

from accounts import roles
from erp.models import ErpOutbox
from integrations import connections as c
from integrations.models import InboundEvent, IntegrationAccount, IntegrationCall, IntegrationFailure
from integrations.services import panel_keys
from shop.models import Payment, razorpay_keys
from staff.models import AuditEvent, InboxItem
from staff.tests.conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
CONNECTIONS = STAFF + "connections/"
LIVE_ID, LIVE_SECRET = "rzp_live_AbCdEfGh1234", "live-secret-0123456789abcd"
TEST_ID, TEST_SECRET = "rzp_test_ZyXwVuTs9876", "test-secret-9876543210wxyz"


@pytest.fixture
def owner(settings):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    return make_staff(roles.OWNER)


@pytest.fixture
def answers(monkeypatch):
    """The providers' HTTP APIs answered here: set `answers.status` and `answers.body` (JSON, or text for a str);
    `answers.sent` keeps what they were asked."""
    state = SimpleNamespace(status=200, body={"entity": "collection", "count": 1, "items": [{"id": "pay_1"}]}, sent=[])

    def handler(request):
        state.sent.append(request)
        if isinstance(state.body, str):
            return httpx.Response(state.status, text=state.body)
        return httpx.Response(state.status, json=state.body)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(c, "transport_for", lambda provider: transport)
    return state


@pytest.fixture
def live_razorpay(settings):
    settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET = LIVE_ID, LIVE_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET, settings.RAZORPAY_WEBHOOK_SECRET_TEST = "env-live-webhook-secret", ""


def cards(client):
    return {card["provider"]: card for card in client.get(CONNECTIONS).json()}


def test_one_card_per_integration_says_whether_it_works_and_never_shows_a_secret(owner, live_razorpay):
    shiprocket = IntegrationAccount.objects.create(provider="shiprocket", mode="live", enabled=True)
    shiprocket.set_credentials({"email": "api@examleaf.in", "password": "sr-password-123456"})
    shiprocket.save()
    for error in ["", "", "", "HTTP 503", "HTTP 503"]:  # 2 of 5 failed today: a fifth or more, degraded
        IntegrationCall.objects.create(account=shiprocket, operation="track", method="GET", path="/x", error=error)
    response = signed_in(owner).get(CONNECTIONS)
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    found = {card["provider"]: card for card in response.json()}
    assert list(found) == [spec.key for spec in c.PROVIDERS]
    razorpay = found["razorpay"]
    assert (razorpay["status"], razorpay["mode"], razorpay["source"]) == ("connected", "live", "environment")
    assert razorpay["held"] == {"key_id": "…1234", "key_secret": "…abcd"}
    assert found["shiprocket"]["status"] == "degraded" and found["shiprocket"]["calls"]["day_errors"] == 2
    assert found["shiprocket"]["accounts"][0]["held"] == {"email": "…f.in", "password": "…3456"}
    assert found["shiprocket"]["accounts"][0]["rotate_in_days"] == 90
    assert found["whatsapp"]["status"] == "disabled" and found["whatsapp"]["extra"] == {"phase": "D"}
    assert found["manual"]["status"] == "connected" and found["ses"]["status"] == "not_configured"
    assert found["erpnext"]["extra"]["erp"]["key_present"] is False
    for secret in [LIVE_ID, LIVE_SECRET, "sr-password-123456", "api@examleaf.in"]:
        assert secret not in response.content.decode()


def test_the_cards_are_read_in_a_bounded_number_of_queries(owner):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = signed_in(owner)

    def queries(calls):
        IntegrationCall.objects.all().delete()
        for provider in ["shiprocket", "erpnext", "msg91"]:
            account, _ = IntegrationAccount.objects.get_or_create(provider=provider, mode="live")
            IntegrationCall.objects.bulk_create(
                IntegrationCall(account=account, operation="x", method="GET", path="/", duration_ms=n)
                for n in range(calls)
            )
        cards(client)  # the session's own first reads
        with CaptureQueriesContext(connection) as captured:
            assert len(cards(client)) == len(c.PROVIDERS)
        return len(captured)

    assert queries(1) == queries(30)  # as many queries for 90 calls as for 3: none read row by row
    assert cards(client)["shiprocket"]["calls"]["p90_ms"] == 26  # the nearest rank of 30 durations 0 … 29


def test_a_razorpay_test_reads_one_payment_through_the_client_and_keeps_its_result(owner, live_razorpay, answers):
    client = signed_in(owner)
    response = client.post(CONNECTIONS + "razorpay/test/")
    assert response.status_code == 200 and response.json()["ok"] is True
    assert "live keys" in response.json()["message"]
    [request] = answers.sent
    assert request.url.path == "/v1/payments" and request.url.params["count"] == "1"
    assert request.headers["Authorization"].startswith("Basic ")
    account = IntegrationAccount.objects.get(provider="razorpay", mode="live")
    assert account.last_test_ok and not account.credentials and not account.enabled  # the environment stays in force
    assert IntegrationCall.objects.get(account=account).operation == "payments"
    assert AuditEvent.objects.get(action="connection.tested").details == {"provider": "razorpay", "mode": "live",
                                                                         "ok": True}  # fmt: skip
    answers.status, answers.body = 401, {"error": {"description": "The api key provided is invalid"}}
    failed = client.post(CONNECTIONS + "razorpay/test/").json()
    assert failed["ok"] is False and failed["card"]["status"] == "expired"
    assert AuditEvent.objects.filter(action="connection.tested", outcome="failed").exists()


def test_a_test_needs_a_recent_reauthentication_and_the_permission(live_razorpay, answers):
    stale = signed_in(make_staff(roles.OWNER), reauth=False).post(CONNECTIONS + "razorpay/test/")
    assert stale.status_code == 403 and stale.json()["code"] == "reauthentication_required"
    assert signed_in(make_staff(roles.FINANCE)).post(CONNECTIONS + "razorpay/test/").status_code == 403
    assert signed_in(make_staff(roles.FINANCE)).get(CONNECTIONS).status_code == 200  # FINANCE reads the cards
    assert not answers.sent


def test_msg91s_test_reads_the_balance_and_its_key_never_reaches_the_log(owner, settings, answers):
    settings.SMS_BACKEND, settings.MSG91_AUTHKEY = "msg91", "msg91-authkey-0123456789"
    answers.body = "1234.5"
    assert signed_in(owner).post(CONNECTIONS + "msg91/test/").json()["ok"] is True
    call = IntegrationCall.objects.get()
    assert call.path == "/balance.php" and "msg91-authkey" not in call.excerpt + call.path
    assert answers.sent[0].url.params["authkey"] == "msg91-authkey-0123456789"
    answers.body = "Authentication failure"
    result = signed_in(owner).post(CONNECTIONS + "msg91/test/").json()
    assert result["ok"] is False and "Authentication failure" in result["message"]


def test_ses_and_the_buckets_are_tested_with_logged_boto3_calls(owner, monkeypatch):
    real = c.environment
    monkeypatch.setattr(c, "environment", lambda key: {"configured": True, "mode": "live", "held": {}} if key in (
        "ses", "storage") else real(key))  # fmt: skip
    ses = boto3.client("sesv2", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="y")
    quota = {"Max24HourSend": 50000.0, "MaxSendRate": 14.0, "SentLast24Hours": 120.0}
    with Stubber(ses) as stub:
        stub.add_response("get_account", {"SendQuota": quota, "ProductionAccessEnabled": True})
        stub.add_client_error("get_account", "AccessDeniedException", http_status_code=403)
        monkeypatch.setattr(c, "ses_client", lambda: ses)
        result = signed_in(owner).post(CONNECTIONS + "ses/test/").json()
        assert result["ok"] and "in production: 120 of 50,000" in result["message"]
        refused = signed_in(owner).post(CONNECTIONS + "ses/test/").json()
        assert refused["ok"] is False and refused["card"]["status"] == "expired"
    s3 = boto3.client("s3", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="y")
    storage = SimpleNamespace(connection=SimpleNamespace(meta=SimpleNamespace(client=s3)))
    monkeypatch.setattr(c, "_s3_storages", lambda: [("default", "examleaf-media", storage)])
    with Stubber(s3) as stub:
        stub.add_response("head_bucket", {}, {"Bucket": "examleaf-media"})
        assert signed_in(owner).post(CONNECTIONS + "storage/test/").json()["ok"]
    operations = list(IntegrationCall.objects.order_by("pk").values_list("operation", "status_code"))
    assert operations == [("get_account", 200), ("get_account", 403), ("head_bucket default", 200)]


def test_google_and_the_error_tracker_are_checked_for_their_settings(owner, settings):
    settings.STAFF_GOOGLE_CLIENT_ID, settings.STAFF_GOOGLE_CLIENT_SECRET = "staff-client.apps.example", "secret"
    settings.STAFF_GOOGLE_DOMAIN, settings.SENTRY_DSN = "examleaf.in", "https://key@errors.example.in/2"
    google = signed_in(owner).post(CONNECTIONS + "google/test/").json()
    assert google["ok"] and "the staff's client" in google["message"] and "@examleaf.in" in google["message"]
    assert "errors.example.in" in signed_in(owner).post(CONNECTIONS + "error_tracker/test/").json()["message"]
    assert signed_in(owner).post(CONNECTIONS + "manual/test/").status_code == 400
    assert signed_in(owner).post(CONNECTIONS + "nowhere/test/").status_code == 404


def test_new_credentials_are_kept_only_after_their_own_test_passes_and_are_masked_everywhere(owner, answers, settings):
    settings.RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_SECRET = ""  # no environment keys: the panel's first
    client = signed_in(owner)
    url, keys = CONNECTIONS + "razorpay/credentials/", {"key_id": TEST_ID, "key_secret": TEST_SECRET}
    answers.status, answers.body = 401, {"error": {"description": "Authentication failed"}}
    refused = client.post(url, {"mode": "test", "credentials": keys, "reason": "New keys"}, format="json")
    assert refused.status_code == 400 and "did not pass the test" in refused.json()["credentials"][0]
    assert not IntegrationAccount.objects.exclude(credentials="").exists()  # nothing kept
    assert panel_keys("razorpay") is None  # the environment's still (none)
    wrong = client.post(url, {"mode": "live", "credentials": keys, "reason": "x"}, format="json")
    assert wrong.json()["credentials"]["key_id"] == ["A live key starts rzp_live_."]
    answers.status, answers.body = 200, {"entity": "collection", "count": 0, "items": []}
    mail.outbox.clear()
    with_commit = client.post(url, {"mode": "test", "credentials": keys, "reason": "New keys"}, format="json")
    assert with_commit.status_code == 200
    account = IntegrationAccount.objects.get(provider="razorpay", mode="test")
    assert account.get_credentials() == keys and account.credentials_updated_by == owner and account.rotate_by
    assert not account.enabled  # no environment keys were in force: switched on by the mode, later
    event = AuditEvent.objects.get(action="connection.credentials_replaced")
    assert event.changes == {"credentials": [{}, {"key_id": "…9876", "key_secret": "…wxyz"}]}
    text = json.dumps([event.changes, event.details, with_commit.json()])
    assert TEST_ID not in text and TEST_SECRET not in text
    assert AuditEvent.objects.get(action="connection.credentials_refused").outcome == "failed"


def test_the_panel_takes_razorpay_over_from_the_environment_without_stopping_it(owner, live_razorpay, answers):
    client = signed_in(owner)
    url = CONNECTIONS + "razorpay/credentials/"
    test_keys = {"mode": "test", "credentials": {"key_id": TEST_ID, "key_secret": TEST_SECRET}, "reason": "x"}
    assert client.post(url, test_keys, format="json").json()["mode"][0].startswith("The environment's live keys")
    assert razorpay_keys().key_id == LIVE_ID  # untouched
    new = {"key_id": "rzp_live_NewNewNew5678", "key_secret": "new-live-secret-00005678"}
    assert client.post(url, {"mode": "live", "credentials": new, "reason": "Rotated"}, format="json").status_code == 200
    keys = razorpay_keys()
    assert (keys.key_id, keys.key_secret) == (new["key_id"], new["key_secret"])
    assert keys.webhook_secrets == ["env-live-webhook-secret"]  # carried over: Razorpay's webhook still verifies
    card = cards(client)["razorpay"]
    assert (card["source"], card["mode"], card["status"]) == ("panel", "live", "connected")
    assert client.post(url, test_keys, format="json").status_code == 200  # now the test keys may come too
    assert razorpay_keys().key_id == new["key_id"]  # and wait for the mode switch


def test_the_mode_switches_the_account_in_use_and_off_stops_razorpay(owner, answers, settings, commit):
    settings.RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_SECRET = ""
    client = signed_in(owner)
    for mode, key_id in [("test", TEST_ID), ("live", "rzp_live_Second1234567")]:
        credentials = {"key_id": key_id, "key_secret": f"{mode}-secret-0123456789"}
        client.post(CONNECTIONS + "razorpay/credentials/", {"mode": mode, "credentials": credentials, "reason": "x"},
                    format="json")  # fmt: skip
    assert razorpay_keys().key_id == ""  # held, none switched on: off
    url = CONNECTIONS + "razorpay/mode/"
    mail.outbox.clear()
    with commit():
        assert client.post(url, {"mode": "test", "reason": "Test keys"}, format="json").json()["mode"] == "test"
        assert razorpay_keys().key_id == TEST_ID
        assert client.post(url, {"mode": "live", "reason": "Launch"}, format="json").json()["mode"] == "live"
        assert razorpay_keys().key_id == "rzp_live_Second1234567"
        assert client.post(url, {"mode": "off", "reason": "Fraud"}, format="json").json()["status"] == "disabled"
        assert razorpay_keys().key_id == "" and not IntegrationAccount.objects.filter(enabled=True).exists()
    switched = AuditEvent.objects.filter(action="connection.mode_changed").order_by("id")
    assert list(switched.values_list("changes", flat=True)) == [
        {"mode": ["off", "test"]},
        {"mode": ["test", "live"]},
        {"mode": ["live", "off"]},
    ]
    assert sum("switched to" in message.subject for message in mail.outbox) == 3


def test_the_circuit_is_held_open_then_reset_and_its_inbox_item_done(owner):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="live", enabled=True)
    account.set_credentials({"email": "api@examleaf.in", "password": "sr-password-123456"})
    account.save()
    target = {"target_type": "integrations.integrationaccount", "target_id": str(account.pk)}
    item = InboxItem.objects.create(kind="integration_down", title="Shiprocket unavailable", permission="x", **target)
    client, url = signed_in(owner), CONNECTIONS + "shiprocket/circuit/"
    held = client.post(url, {"action": "open", "reason": "Shiprocket's outage notice"}, format="json").json()
    assert held["circuit"]["held_open"] and held["status"] == "degraded"
    account.refresh_from_db()
    assert not account.allows_call()
    reset = client.post(url, {"action": "reset", "reason": "It is back"}, format="json").json()
    assert reset["circuit"] == {"state": "closed", "held_open": False, "opened_at": None, "failures": 0}
    item.refresh_from_db()
    assert item.done_at is not None
    refused = client.post(CONNECTIONS + "razorpay/circuit/", {"action": "open", "reason": "x"}, format="json")
    assert refused.status_code == 400  # its calls do not go through the circuit breaker


def test_a_webhook_token_is_answered_once_and_the_previous_one_works_for_a_day(owner):
    client, url = signed_in(owner), CONNECTIONS + "msg91/webhooks/rotate/"
    first = client.post(url, {"reason": "Setting up the delivery reports"}, format="json").json()["token"]
    second = client.post(url, {"reason": "Rotation"}, format="json").json()
    account = IntegrationAccount.objects.get(provider="msg91")
    assert account.webhook_token_matches(first) and account.webhook_token_matches(second["token"])
    assert not account.webhook_token_matches(first, now=timezone.now() + timedelta(hours=25))
    info = client.get(CONNECTIONS + "msg91/webhooks/").json()
    assert info["token"] == f"…{second['token'][-4:]}" and info["previous_valid_until"]
    assert info["url"].endswith("/api/hooks/sms-events/") and info["header"] == "X-Webhook-Token"
    assert first not in json.dumps(list(AuditEvent.objects.values_list("details", flat=True)))
    assert client.post(CONNECTIONS + "ses/webhooks/rotate/", {"reason": "x"}, format="json").status_code == 400
    assert client.post(CONNECTIONS + "razorpay/webhooks/rotate/", {"reason": "x"}, format="json").status_code == 400


def test_events_are_listed_redacted_and_processed_again(owner, monkeypatch):
    queued = []
    monkeypatch.setattr(InboundEvent, "process_later", lambda self: queued.append(self.pk))
    body = json.dumps({"awb": "123", "phone": "9864012345"})
    failed = InboundEvent.objects.create(provider="shiprocket", body=body, sha256="1" * 64, state="failed")
    rejected = InboundEvent.objects.create(provider="shiprocket", sha256="2" * 64, state="rejected")
    client = signed_in(owner)
    listed = client.get(CONNECTIONS + "shiprocket/events/?state=failed").json()["results"]
    assert [row["id"] for row in listed] == [failed.pk] and "9864012345" not in listed[0]["body_excerpt"]
    assert client.post(f"{CONNECTIONS}shiprocket/events/{failed.pk}/replay/").json()["state"] == "accepted"
    assert client.post(f"{CONNECTIONS}shiprocket/events/{rejected.pk}/replay/").status_code == 400
    assert client.post(f"{CONNECTIONS}msg91/events/{failed.pk}/replay/").status_code == 404  # another provider's
    failed.state = "failed"
    failed.save()
    since = (timezone.now() - timedelta(hours=1)).isoformat()
    answer = client.post(CONNECTIONS + "shiprocket/events/replay-failed/", {"since": since}, format="json").json()
    assert answer == {"replayed": 1, "more": False} and queued == [failed.pk, failed.pk]


def test_dead_letters_are_replayed_or_discarded_and_erpnexts_through_the_sync(owner, monkeypatch, settings):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="live")
    task = {"task_name": "integrations.tasks.purge_old_records", "last_error": "IntegrationUnavailable: HTTP 503"}
    failure = IntegrationFailure.objects.create(account=account, operation="track", task_id="t-1", **task)
    orphan = IntegrationFailure.objects.create(operation="book", task_id="t-2", **{**task, "task_name":
                                               "shipping.tasks.process_inbound_event"})  # fmt: skip
    client = signed_in(owner)
    listed = [row["id"] for row in client.get(CONNECTIONS + "shiprocket/failures/").json()["results"]]
    assert set(listed) == {failure.pk, orphan.pk}  # its account's, and its app's tasks' without one
    assert client.post(f"{CONNECTIONS}shiprocket/failures/{failure.pk}/replay/").json()["state"] == "replayed"
    assert client.post(f"{CONNECTIONS}shiprocket/failures/{failure.pk}/replay/").status_code == 400
    discarded = client.post(f"{CONNECTIONS}shiprocket/failures/{orphan.pk}/discard/", {"reason": "Booked by hand"},
                            format="json").json()  # fmt: skip
    assert (discarded["state"], discarded["discard_reason"]) == ("discarded", "Booked by hand")
    erp = IntegrationAccount.objects.create(provider="erpnext", mode="live")
    dead = IntegrationFailure.objects.create(account=erp, operation="post_invoice", task_id="t-3", **task)
    row = ErpOutbox.objects.create(aggregate_type="order", aggregate_id="EL-1", sequence=1, event="invoice.posted",
                                   examleaf_ref="invoice:EL-1", payload={}, state="dead", failure=dead)  # fmt: skip
    answer = client.post(f"{CONNECTIONS}erpnext/failures/{dead.pk}/discard/", {"reason": "Entered by hand"},
                         format="json").json()  # fmt: skip
    assert answer["state"] == "discarded" and answer["erp_outbox"] == row.pk
    row.refresh_from_db()
    assert row.state == "discarded" and AuditEvent.objects.filter(action="erp.discard").exists()
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"connection.dead_letter_replayed", "connection.dead_letter_discarded"} <= actions


def test_calls_are_listed_newest_first_with_their_failures(owner):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="live")
    ok = IntegrationCall.objects.create(account=account, operation="track", method="GET", path="/track")
    failed = IntegrationCall.objects.create(account=account, operation="book", method="POST", path="/book",
                                            status_code=422, error="HTTP 422: Invalid pincode")  # fmt: skip
    client = signed_in(owner)
    assert [row["id"] for row in client.get(CONNECTIONS + "shiprocket/calls/").json()["results"]] == [failed.pk, ok.pk]
    assert [row["id"] for row in client.get(CONNECTIONS + "shiprocket/calls/?failed=true").json()["results"]] == [
        failed.pk
    ]
    assert client.get(CONNECTIONS + "razorpay/calls/").json()["results"] == []


def test_razorpays_silence_while_payments_come_in_opens_one_inbox_item(live_razorpay, settings, rzp):
    from shop.factories import ProductFactory, make_order
    from shop.models import WebhookEvent

    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    assert c.watch_webhooks() is False
    order = make_order((ProductFactory(stock=5), 1))
    Payment.objects.filter(order=order).update(status="captured", livemode=True)  # paid, and no webhook came
    assert c.watch_webhooks() is True and c.watch_webhooks() is True
    item = InboxItem.objects.get(kind="webhook_silent")
    assert item.permission == "staff.manage_connections" and "1 payments" in item.title
    WebhookEvent.objects.create(event_id="evt_1", digest="d" * 64, name="payment.captured")
    assert c.watch_webhooks() is False
    item.refresh_from_db()
    assert item.done_at is not None
