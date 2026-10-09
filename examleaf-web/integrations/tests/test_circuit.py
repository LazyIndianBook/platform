"""The circuit breaker of an account: open after 5 failures in 5 minutes, one trial after 5 minutes (half open),
closed on success, held open or reset by staff; the signals the staff inbox will listen to."""

from datetime import timedelta

import pytest
from django.utils import timezone

from integrations import signals
from integrations.models import COOL_OFF, IntegrationAccount

pytestmark = pytest.mark.django_db
Circuit = IntegrationAccount.Circuit


@pytest.fixture
def heard():
    """The signals sent (after the commit, as in production), by name."""
    caught = []

    def receiver_of(name):
        return lambda sender, **kw: caught.append(name)

    receivers = {name: receiver_of(name) for name in ("integration_failed", "integration_recovered")}
    for name, receiver in receivers.items():
        getattr(signals, name).connect(receiver)
    yield caught
    for name, receiver in receivers.items():
        getattr(signals, name).disconnect(receiver)


def fail(account, times, at):
    for _ in range(times):
        account.record_failure("HTTP 503", now=at)


def test_five_failures_within_five_minutes_open_it_once(account, heard, django_capture_on_commit_callbacks):
    now = timezone.now()
    with django_capture_on_commit_callbacks(execute=True):
        fail(account, 4, now)
        assert account.circuit_state == Circuit.CLOSED and account.allows_call()
        fail(account, 1, now + timedelta(minutes=4))
    account.refresh_from_db()
    assert account.circuit_state == Circuit.OPEN and account.opened_at == now + timedelta(minutes=4)
    assert account.last_error == "HTTP 503" and heard == ["integration_failed"]
    assert not account.allows_call(now=now + timedelta(minutes=5))


def test_failures_further_apart_than_the_window_start_a_new_count(account):
    now = timezone.now()
    fail(account, 4, now)
    fail(account, 4, now + timedelta(minutes=6))
    account.refresh_from_db()
    assert account.circuit_state == Circuit.CLOSED and account.failure_count == 4


def test_after_the_cool_off_one_trial_goes_and_a_success_closes_it(account, heard, django_capture_on_commit_callbacks):
    opened = timezone.now() - COOL_OFF - timedelta(seconds=1)
    fail(account, 5, opened)
    other = IntegrationAccount.objects.get(pk=account.pk)  # another worker's copy
    assert account.allows_call() and account.circuit_state == Circuit.HALF_OPEN  # the trial
    assert not other.allows_call()  # the others wait for it
    with django_capture_on_commit_callbacks(execute=True):
        account.record_success()
    assert other.allows_call() and heard == ["integration_recovered"]
    account.refresh_from_db()
    assert account.opened_at is None and account.failure_count == 0 and account.last_success_at


def test_a_failed_trial_opens_it_for_another_cool_off(account):
    opened = timezone.now() - COOL_OFF - timedelta(seconds=1)
    fail(account, 5, opened)
    assert account.allows_call()
    failed_at = timezone.now()
    account.record_failure("timed out", now=failed_at)
    account.refresh_from_db()
    assert account.circuit_state == Circuit.OPEN and account.opened_at == opened  # unavailable since the first time
    assert not account.allows_call(now=failed_at + COOL_OFF - timedelta(seconds=1))
    assert account.allows_call(now=failed_at + COOL_OFF + timedelta(seconds=1))


def test_a_trial_whose_caller_never_reported_is_given_to_another_caller(account):
    fail(account, 5, timezone.now() - 3 * COOL_OFF)
    assert account.allows_call(now=timezone.now() - COOL_OFF - timedelta(seconds=5))  # claimed, then the worker died
    assert IntegrationAccount.objects.get(pk=account.pk).allows_call()


def test_staff_hold_it_open_until_they_reset_it(account):
    account.force_open()
    assert not account.allows_call(now=timezone.now() + 10 * COOL_OFF)
    account.record_success()  # a call that was already under way: still held
    assert IntegrationAccount.objects.get(pk=account.pk).circuit_state == Circuit.OPEN
    account.reset()
    assert account.allows_call() and account.circuit_state == Circuit.CLOSED


def test_a_disabled_account_makes_no_call(account):
    IntegrationAccount.objects.filter(pk=account.pk).update(enabled=False)
    assert not account.allows_call()


def test_a_refusal_proves_the_provider_is_up_but_is_no_success(account):
    fail(account, 5, timezone.now() - COOL_OFF - timedelta(seconds=1))
    assert account.allows_call()
    account.record_success(answered_only=True)
    account.refresh_from_db()
    assert account.circuit_state == Circuit.CLOSED and account.last_success_at is None
