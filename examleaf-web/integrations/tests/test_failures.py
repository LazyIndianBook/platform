"""Tasks that call a provider: retried, put back while the circuit is open, and written to the dead-letter list once
they give up; staff replay or discard a dead letter."""

from unittest import mock

import pytest
from celery import shared_task
from celery.exceptions import Ignore, Retry

from integrations import signals
from integrations.client import CircuitOpen, IntegrationRejected, IntegrationUnavailable
from integrations.models import IntegrationFailure
from integrations.tasks import IntegrationTask

pytestmark = pytest.mark.django_db
RAN = []


@shared_task(base=IntegrationTask, bind=True)
def refused(self, shipment_id, note=""):
    RAN.append(shipment_id)
    raise IntegrationRejected("Shiprocket (test) book: HTTP 422: pickup location missing")


@shared_task(base=IntegrationTask, bind=True)
def unavailable(self, shipment_id):
    RAN.append(shipment_id)
    raise IntegrationUnavailable("Shiprocket (test) track: HTTP 503")


@shared_task(base=IntegrationTask, bind=True)
def circuit_open(self, shipment_id):
    raise CircuitOpen("Shiprocket (test): no call made (open: calls wait)")


@pytest.fixture(autouse=True)
def fresh():
    RAN.clear()


def test_a_refusal_gives_up_at_once_into_the_dead_letter_list(account, django_capture_on_commit_callbacks):
    heard = []
    signals.dead_letter_created.connect(receiver := lambda sender, failure, **kw: heard.append(failure))
    try:
        with django_capture_on_commit_callbacks(execute=True):
            result = refused.apply(args=(7,), kwargs={"note": "call 9864012345"}, throw=False)
    finally:
        signals.dead_letter_created.disconnect(receiver)
    assert result.state == "FAILURE" and RAN == [7]
    failure = IntegrationFailure.objects.get()
    assert failure.task_name == "integrations.tests.test_failures.refused" and failure.operation == "refused"
    assert failure.args == {"args": [7], "kwargs": {"note": "call ******2345"}}  # redacted
    assert failure.attempts == 1 and "HTTP 422" in failure.last_error and heard == [failure]
    refused.on_failure(IntegrationRejected("again"), result.id, (7,), {}, None)  # once per task run
    assert IntegrationFailure.objects.count() == 1


def test_an_unavailable_provider_is_retried_then_given_up_after_eight_retries():
    with pytest.raises(Retry):  # inline (tests): the retry comes back to the caller
        unavailable.delay(3)
    assert not IntegrationFailure.objects.exists()
    result = unavailable.apply(args=(3,), retries=8, throw=False)  # the last try
    assert result.state == "FAILURE"
    assert IntegrationFailure.objects.get().attempts == 9


def test_an_open_circuit_puts_the_task_back_without_a_try_or_a_dead_letter():
    with pytest.raises(CircuitOpen):  # inline: raised, nothing to wait in
        circuit_open.delay(5)
    with mock.patch.object(circuit_open, "apply_async") as again:
        circuit_open.push_request(is_eager=False, called_directly=False, retries=0)
        try:
            with pytest.raises(Ignore):
                circuit_open(5)
        finally:
            circuit_open.pop_request()
    assert again.call_args.args == ((5,), {}) and 300 <= again.call_args.kwargs["countdown"] <= 360
    assert not IntegrationFailure.objects.exists()


def test_a_dead_letter_is_replayed_once_or_discarded_with_a_reason(account, django_capture_on_commit_callbacks):
    refused.apply(args=(9,), throw=False)
    failure = IntegrationFailure.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        assert failure.replay()
    assert RAN == [9, 9] and failure.state == IntegrationFailure.State.REPLAYED and failure.resolved_at
    assert not failure.replay()  # once
    refused.apply(args=(10,), throw=False)
    again = IntegrationFailure.objects.get(state="open")
    with pytest.raises(ValueError):
        again.discard("  ")
    assert again.discard("Booked by hand in Shiprocket's panel.")
    again.refresh_from_db()
    assert again.state == "discarded" and again.discard_reason.startswith("Booked by hand")
