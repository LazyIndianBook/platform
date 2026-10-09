"""The SMS gateway (ops/sms.py): backends, the daily cap in the database, the log without whole numbers, order SMS."""

from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from examleaf import sentry
from ops import sms
from ops.models import SmsLog

pytestmark = pytest.mark.django_db
PHONE = "+919864012345"


def test_console_sends_and_the_log_keeps_a_hash_and_the_last_four_digits(capsys):
    sms.queue_sms("otp", PHONE, {"otp": "483920"})
    assert "SMS otp to +919864012345: {'otp': '483920'}" in capsys.readouterr().out
    log = SmsLog.objects.get()
    assert (log.kind, log.status, log.phone_last4) == ("otp", SmsLog.Status.SENT, "2345")
    assert log.phone_hash == sms.phone_hash(PHONE) and "9864012345" not in log.phone_hash


def test_the_daily_cap_holds_back_sends_and_old_rows_go(settings, capsys):
    settings.SMS_DAILY_CAP = 1
    old = SmsLog.objects.create(kind="otp", phone_hash="x", phone_last4="0000", status=SmsLog.Status.SENT)
    SmsLog.objects.filter(pk=old.pk).update(created=timezone.now() - timedelta(days=91))  # not counted, then deleted
    sms.queue_sms("otp", PHONE, {"otp": "111111"})
    sms.queue_sms("otp", PHONE, {"otp": "222222"})
    out = capsys.readouterr().out
    assert "111111" in out and "222222" not in out
    assert list(SmsLog.objects.values_list("status", flat=True)) == [SmsLog.Status.CAPPED, SmsLog.Status.SENT]


def test_sentry_sees_no_number_code_name_or_token_of_an_sms():
    job = {"task_name": "ops.sms.send_sms", "args": ["parent_consent", PHONE, {"var1": "Rahul", "var2": "1f.ab.c"}]}
    filtered = {"var1": "[Filtered]", "var2": "[Filtered]"}
    assert sentry.scrub({"celery-job": job})["celery-job"]["args"] == ["parent_consent", "[Filtered]", filtered]
    assert sentry.scrub({"otp": "483920"}) == {"otp": "[Filtered]"}


def test_nothing_goes_out_while_sms_are_off(settings, capsys):
    settings.SMS_ENABLED = False
    sms.queue_sms("otp", PHONE, {"otp": "483920"})
    assert capsys.readouterr().out == "" and not SmsLog.objects.exists()


def msg91_answers(monkeypatch, *answers):
    """MSG91 stand-in: each call takes the next answer (an httpx.Response, or an exception to raise)."""
    calls, answers = [], list(answers)

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(sms.httpx, "post", post)
    return calls


@pytest.fixture
def msg91(settings):
    settings.SMS_BACKEND, settings.MSG91_AUTHKEY = "msg91", "test-authkey"
    settings.MSG91_TEMPLATES = {kind: f"tpl-{kind}" for kind in settings.SMS_KINDS}


def test_msg91_otp_and_flow_requests_and_a_refusal_in_a_200(msg91, monkeypatch):
    calls = msg91_answers(
        monkeypatch,
        httpx.Response(200, json={"type": "success", "request_id": "3466abc"}),
        httpx.Response(200, json={"type": "error", "message": "Template not approved"}),
    )
    sms.queue_sms("otp", PHONE, {"otp": "483920"})
    sms.queue_sms("order_placed", PHONE, {"var1": "EL-2026-000012"})
    otp, flow = calls
    assert otp["url"].endswith("/api/v5/otp") and otp["headers"] == {"authkey": "test-authkey"}
    assert otp["params"] == {"template_id": "tpl-otp", "mobile": "919864012345", "otp": "483920"}
    assert otp["timeout"] == sms.TIMEOUT and flow["url"].endswith("/api/v5/flow")
    assert flow["json"] == {
        "template_id": "tpl-order_placed",
        "short_url": "0",
        "recipients": [{"mobiles": "919864012345", "var1": "EL-2026-000012"}],
    }
    failed, sent = SmsLog.objects.all()
    assert (sent.status, sent.provider_id, failed.status) == (SmsLog.Status.SENT, "3466abc", SmsLog.Status.FAILED)


def test_msg91_network_failures_are_tried_again(msg91, monkeypatch):
    calls = msg91_answers(
        monkeypatch, httpx.ConnectTimeout("slow"), httpx.Response(200, json={"type": "success", "request_id": "1"})
    )
    sms.send_sms.apply(args=("otp", PHONE, {"otp": "483920"}), throw=False)  # as a worker runs it (retries)
    assert len(calls) == 2 and SmsLog.objects.get().status == SmsLog.Status.SENT


def test_order_sms_only_to_a_confirmed_number_that_asked_for_them(capsys):
    shipment = SimpleNamespace(courier="Delhivery", tracking_number="1234567")
    order = SimpleNamespace(number="EL-2026-000012", user=None, shipments=SimpleNamespace(first=lambda: shipment))
    sms.send_order_sms(order, "confirmation")  # a guest's order
    order.user = UserFactory(login_phone=PHONE, login_phone_verified=True)
    sms.send_order_sms(order, "shipped")  # did not ask for them
    order.user.sms_updates = True
    sms.send_order_sms(order, "cancelled")  # no SMS of this kind
    assert capsys.readouterr().out == ""
    sms.send_order_sms(order, "shipped")
    assert "order_shipped to +919864012345: {'var1': 'EL-2026-000012', 'var2': 'Delhivery 1234567'}" in (
        capsys.readouterr().out
    )
