"""Inbound events (kept raw, once per body, rejected ones without their body), their replay and failure, the retention
of the logs, and /health/integrations/."""

from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from health_check.exceptions import ServiceUnavailable

from examleaf.views import HealthView
from integrations import models, services, signals
from integrations.health import Integrations
from integrations.models import InboundEvent, IntegrationAccount, IntegrationCall, IntegrationFailure
from integrations.tasks import purge_old_records

pytestmark = pytest.mark.django_db
BODY = b'{"awb": "19041424751540", "current_status": "IN TRANSIT"}'


@pytest.fixture
def processor(monkeypatch):
    """The provider's processing task, replaced: the events it was given."""
    given = []
    task = mock.Mock(delay=lambda pk: given.append(pk))
    monkeypatch.setitem(models.INBOUND_PROCESSORS, "shiprocket", "integrations.tests.test_events.TASK")
    monkeypatch.setattr("integrations.tests.test_events.TASK", task, raising=False)
    return given


def test_a_body_is_kept_once_per_provider_and_processed_after_the_commit(
    account, processor, monkeypatch, django_capture_on_commit_callbacks
):
    headers = {"Content-Type": "application/json", "X-Api-Key": "secret-token", "User-Agent": "SR"}
    with django_capture_on_commit_callbacks(execute=True):
        event = services.receive_event("shiprocket", BODY, headers, account=account)
        assert services.receive_event("shiprocket", BODY, headers, account=account) is None  # the same body again
    assert processor == [event.pk] and event.body == BODY.decode() and len(event.sha256) == 64
    assert event.headers == {"Content-Type": "application/json", "User-Agent": "SR"}  # never the token
    monkeypatch.setitem(models.INBOUND_PROCESSORS, "erpnext", models.INBOUND_PROCESSORS["shiprocket"])
    assert services.receive_event("erpnext", BODY, {}) is not None  # another provider's own


def test_a_rejected_body_is_kept_without_it_and_never_blocks_the_genuine_one(processor):
    rejected = services.receive_event("shiprocket", BODY, {}, rejected=True)
    assert rejected.state == "rejected" and rejected.body == ""
    assert services.receive_event("shiprocket", BODY, {}, rejected=True).pk != rejected.pk
    assert services.receive_event("shiprocket", BODY, {}).state == "accepted"
    assert not rejected.replay()


def test_a_failed_event_tells_the_inbox_and_is_replayed(account, processor, django_capture_on_commit_callbacks):
    event = services.receive_event("shiprocket", BODY, {}, account=account)
    heard = []
    signals.inbound_event_failed.connect(receiver := lambda sender, event, error, **kw: heard.append(error))
    try:
        with django_capture_on_commit_callbacks(execute=True):
            event.fail("no such parcel 9864012345")
    finally:
        signals.inbound_event_failed.disconnect(receiver)
    assert event.state == "failed" and heard == [event.error]
    with django_capture_on_commit_callbacks(execute=True):
        assert event.replay()
    event.refresh_from_db()
    assert event.state == "accepted" and event.error == "" and processor == [event.pk]


def test_the_logs_go_after_the_retention_days(settings, account):
    settings.INTEGRATIONS_RETENTION_DAYS = 90
    old = timezone.now() - timedelta(days=91)
    IntegrationCall.objects.create(account=account, operation="track", method="GET", path="/x", created=old)
    kept = IntegrationCall.objects.create(account=account, operation="track", method="GET", path="/x")
    InboundEvent.objects.create(provider="shiprocket", sha256="a" * 64, received_at=old)
    IntegrationFailure.objects.create(operation="book", task_name="x", last_error="e", state="open")
    IntegrationFailure.objects.create(
        operation="book", task_name="x", last_error="e", state="replayed", resolved_at=old
    )
    assert purge_old_records() == {"calls": 1, "events": 1, "dead_letters": 1}
    assert list(IntegrationCall.objects.all()) == [kept] and IntegrationFailure.objects.get().state == "open"


def test_the_integrations_check_names_what_waits(account):
    Integrations().run()  # nothing wrong
    IntegrationAccount.objects.filter(pk=account.pk).update(
        circuit_state="half_open", opened_at=timezone.now() - timedelta(minutes=31)
    )
    IntegrationFailure.objects.create(operation="book", task_name="x", last_error="e")
    InboundEvent.objects.create(provider="shiprocket", sha256="c" * 64, state="failed")
    with pytest.raises(ServiceUnavailable) as problem:
        Integrations().run()
    message = str(problem.value)
    assert "Shiprocket (test), tests unavailable since" in message and "1 dead letter(s) waiting" in message
    assert "1 inbound event(s) failed" in message
    IntegrationAccount.objects.filter(pk=account.pk).update(opened_at=timezone.now())  # open, not for long yet
    IntegrationFailure.objects.update(state="discarded")
    InboundEvent.objects.update(state="accepted")
    Integrations().run()


@pytest.mark.django_db(transaction=True)  # the view runs the check in another thread: committed rows only
def test_health_integrations_is_an_address_of_its_own(client):
    url = reverse("health_integrations")
    assert client.get(url, HTTP_ACCEPT="application/json").json() == {"Integrations()": "OK"}
    IntegrationFailure.objects.create(operation="book", task_name="x", last_error="e")
    HealthView.results_by_path.clear()  # results are kept 20 seconds
    assert client.get(url, HTTP_ACCEPT="application/json").status_code == 500
    assert client.get(reverse("health"), HTTP_ACCEPT="application/json").status_code == 200  # the site itself: up
