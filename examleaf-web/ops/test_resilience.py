"""Redis half-open (takes connections, never answers), the email provider failing on top of it, MSG91 silent, the
health ping."""

import threading

import httpx
import pytest
from django.core import mail
from django.core.mail import EmailMessage
from health_check.exceptions import ServiceUnavailable

from examleaf.health import WorkerPing
from examleaf.urls import WEB_CHECKS, health_checks
from ops import sms, tasks
from ops.models import SmsLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def half_open_broker(broker, half_open_port):
    """A server that takes connections and says nothing, set up as the Celery broker (real, not inline)."""
    broker(f"redis://127.0.0.1:{half_open_port}/0")


def queue_within(seconds, message):
    """queue_email in a thread: a hang fails the test after `seconds` instead of hanging the whole run."""
    done = threading.Thread(target=tasks.queue_email, args=(message,), daemon=True)
    done.start()
    done.join(seconds)
    return not done.is_alive()


def test_a_broker_that_never_answers_costs_seconds_not_the_request(half_open_broker):
    assert queue_within(30, EmailMessage("Your code", "ABCD-EFGH", to=["a@example.com"]))
    assert [m.subject for m in mail.outbox] == ["Your code"]  # sent from the web process instead


def test_a_silent_msg91_costs_its_timeout_and_the_sms_is_tried_again(settings, monkeypatch, half_open_port, within):
    settings.SMS_BACKEND, settings.MSG91_AUTHKEY = "msg91", "test-authkey"
    settings.MSG91_TEMPLATES = {kind: f"tpl-{kind}" for kind in settings.SMS_KINDS}
    monkeypatch.setattr(sms, "MSG91", f"http://127.0.0.1:{half_open_port}/api/v5/")
    monkeypatch.setattr(sms, "TIMEOUT", httpx.Timeout(1, connect=1))  # the production one's shape, shorter
    assert within(10, lambda: sms.send_sms.run("otp", "+919864012345", {"otp": "483920"}))
    assert isinstance(within.error, httpx.TimeoutException)  # a TransportError: autoretry_for tries it again
    assert not SmsLog.objects.filter(status=SmsLog.Status.SENT).exists()


def test_an_sms_task_run_again_does_not_send_again(capsys):
    log = SmsLog.objects.create(kind="otp", phone_hash=sms.phone_hash("+919864012345"), phone_last4="2345")
    for _ in range(2):  # acks_late: the task given to a second worker after the first died with it
        sms.send_sms.run("otp", "+919864012345", {"otp": "483920"}, log.pk)
    assert capsys.readouterr().out.count("SMS otp to") == 1


def test_the_provider_failing_too_does_not_fail_the_page(half_open_broker, monkeypatch, caplog):
    def provider_down(self, *args, **kwargs):
        raise ConnectionError("the email provider is down")

    monkeypatch.setattr(EmailMessage, "send", provider_down)
    assert queue_within(30, EmailMessage("Your code", "ABCD-EFGH", to=["a@example.com"]))  # no exception reaches it
    assert "could not be sent here either" in caplog.text and not mail.outbox


class FakeCeleryApp:
    """control.inspect(workers).active_queues() answering a fixed table: worker name -> its queues."""

    def __init__(self, active_queues):
        self.active = active_queues
        self.control = self

    def inspect(self, workers):
        return self

    def active_queues(self):
        return self.active


def test_the_health_ping_waits_for_every_worker_and_checks_each_queue_the_platform_uses():
    assert health_checks(eager=True) == WEB_CHECKS  # inline tasks: no worker to ask
    [*web, (ping, options)] = health_checks(eager=False)
    assert web == WEB_CHECKS and ping == "examleaf.health.WorkerPing" and "limit" not in options  # every worker answers
    both = FakeCeleryApp({"celery@web": [{"name": "celery"}], "media@web": [{"name": "media"}]})
    WorkerPing(app=both).check_active_queues("celery@web", "media@web")  # both queues served: no complaint
    with pytest.raises(ServiceUnavailable, match="media"):  # the media worker is down, whichever worker answered first
        WorkerPing(app=FakeCeleryApp({"celery@web": [{"name": "celery"}]})).check_active_queues("celery@web")
    with pytest.raises(ServiceUnavailable, match="celery"):
        WorkerPing(app=FakeCeleryApp({"media@web": [{"name": "media"}]})).check_active_queues("media@web")
