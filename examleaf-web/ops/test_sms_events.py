"""MSG91's delivery reports (ops/webhooks.py, POST /api/hooks/sms-events/): the X-Webhook-Token header compared in
constant time with the current token and, for 24 hours after a rotation, the previous one; a wrong one kept as a
rejected event; a report sent twice processed once (its id: MSG91's request id, the number's last digits, the status);
each report written on its SmsLog row, with MSG91's reason when it failed."""

import hmac
import json
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.models import InboundEvent, IntegrationAccount
from ops.models import SmsLog
from ops.webhooks import delivery_of, reports_of

pytestmark = pytest.mark.django_db
HOOK = "/api/hooks/sms-events/"


@pytest.fixture
def token():
    account = IntegrationAccount.objects.create(provider="msg91", mode="live")
    return account.rotate_webhook_token()


def report(request_id="5f1a2b3c4d5e6f7a8b9c0d1e", number="919864012345", status="16", desc="Rejected"):
    return [{"requestId": request_id, "report": [{"number": number, "status": status, "desc": desc,
                                                   "date": "2026-10-09 10:15:00"}]}]  # fmt: skip


def send(body, token, **headers):
    return APIClient().post(HOOK, json.dumps(body), content_type="application/json", HTTP_X_WEBHOOK_TOKEN=token,
                            **headers)  # fmt: skip


def sent(request_id="5f1a2b3c4d5e6f7a8b9c0d1e", last4="2345"):
    return SmsLog.objects.create(kind="order_placed", phone_hash="h", phone_last4=last4, status="sent",
                                 provider_id=request_id)  # fmt: skip


def test_a_wrong_or_missing_token_is_refused_and_kept_without_its_body(token):
    assert send(report(), "wrong").status_code == 403
    assert APIClient().post(HOOK, report(), format="json").status_code == 403
    assert list(InboundEvent.objects.values_list("state", "body")) == [("rejected", ""), ("rejected", "")]


def test_the_token_is_compared_in_constant_time_with_the_current_and_the_previous_one(token, monkeypatch):
    compared = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: compared.append(len(b)) or real(a, b))
    account = IntegrationAccount.objects.get(provider="msg91")
    new = account.rotate_webhook_token()
    assert send(report(status="1", desc="Delivered"), token).status_code == 200  # the previous one, within a day
    assert len(compared) == 2  # both tokens compared, whichever matched
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_rotated_at=timezone.now() - timedelta(hours=25))
    assert send(report(status="2", desc="Failed"), token).status_code == 403  # a day later: no more
    assert send(report(status="2", desc="Failed"), new).status_code == 200


def test_a_report_is_written_on_its_sms_with_the_reason_and_a_repeat_is_ignored(token, commit):
    log = sent()
    with commit():
        assert send(report(desc="Template Id not found on DLT"), token).status_code == 200
    log.refresh_from_db()
    assert (log.delivery, log.delivery_reason) == ("rejected", "Template Id not found on DLT")
    assert log.delivered_at is not None
    event = InboundEvent.objects.get(state="accepted")
    assert event.event_id.startswith("dlr:") and event.processed_at
    again = report(desc="Template Id not found on DLT")
    again[0]["campaign"] = "the same report, another body"
    with commit():
        assert send(again, token).status_code == 200
    assert InboundEvent.objects.exclude(state="rejected").count() == 1  # the same report: one event


def test_a_final_report_is_never_replaced_by_a_late_pending_one(token, commit):
    log = sent()
    with commit():
        send(report(status="1", desc="Delivered"), token)
        send(report(status="5", desc="Pending"), token)
    log.refresh_from_db()
    assert (log.delivery, log.delivery_reason) == ("delivered", "")


def test_a_flow_to_several_numbers_reports_each_and_a_form_body_is_read(token, commit):
    first, second = sent(last4="2345"), sent(last4="9999")
    body = [{"requestId": "5f1a2b3c4d5e6f7a8b9c0d1e", "report": [
        {"number": "919864012345", "status": "1", "desc": "DELIVERED"},
        {"number": "919800009999", "status": "9", "desc": "NDNC"}]}]  # fmt: skip
    with commit():
        response = APIClient().post(HOOK, urlencode({"data": json.dumps(body)}), HTTP_X_WEBHOOK_TOKEN=token,
                                    content_type="application/x-www-form-urlencoded")  # fmt: skip
    assert response.status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.delivery, second.delivery, second.delivery_reason) == ("delivered", "rejected", "NDNC")


def test_a_body_without_a_report_is_refused_and_a_report_of_no_sms_of_ours_is_said(token, commit):
    assert send({"nothing": "here"}, token).status_code == 400
    with commit():
        assert send(report(request_id="someone-elses"), token).status_code == 200
    event = InboundEvent.objects.get(state="duplicate")
    assert event.error == "No SMS of ours waits for this report."


def test_the_reports_words_decide_before_their_codes():
    def state(status, desc=""):
        return delivery_of({"status": status, "description": desc})

    assert [state("1"), state("2"), state("9"), state("5"), state("42")] == [
        "delivered",
        "failed",
        "rejected",
        "pending",
        "pending",
    ]
    assert state("1", "Not delivered") == "failed" and state("", "Template Id not found on DLT") == "rejected"
    rows = reports_of([{"request_id": "r1", "number": "+91 98640 12345", "status": "1"}, {"report": []}, "junk"])
    assert rows == [{"request_id": "r1", "last4": "2345", "status": "1", "description": "", "date": ""}]
