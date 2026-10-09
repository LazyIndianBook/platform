"""The base of every task that calls a provider (IntegrationTask), and the integrations' own housekeeping."""

import random
from datetime import timedelta

from celery import shared_task
from celery.exceptions import Ignore
from django.conf import settings
from django.utils import timezone

from examleaf.celery import Task  # a task delivered again after its process died runs a bounded number of times

from .client import CircuitOpen, IntegrationUnavailable
from .models import COOL_OFF, InboundEvent, IntegrationCall, IntegrationFailure
from .services import dead_letter


class IntegrationTask(Task):
    """A task that calls a provider (`@shared_task(base=IntegrationTask, bind=True)`). Its arguments are ids, never
    personal data (the dead-letter list keeps them); it may run more than once, so it looks before it creates. It is
    - retried on IntegrationUnavailable after a delay that grows from 60 s to an hour, jittered, 8 times (about four
      hours in all), as shop.tasks.refund_payment is;
    - put back in the queue without counting a try while the account's circuit is open (CircuitOpen), to run again
      after COOL_OFF and a random minute;
    - written to the dead-letter list once it gives up (dead_letter_created): its retries used up, a refusal
      (IntegrationRejected, IntegrationAuthFailed) or any other error.
    Run inline (the tests, development without a broker) a retry or an open circuit is raised to the caller instead."""

    autoretry_for = (IntegrationUnavailable,)
    dont_autoretry_for = (CircuitOpen,)
    retry_backoff = 60
    retry_backoff_max = 3600
    retry_jitter = True
    max_retries = 8

    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except CircuitOpen:
            if self.request.is_eager or self.request.called_directly:
                raise
            self.apply_async(args, kwargs, countdown=COOL_OFF.total_seconds() + random.randint(0, 60))
            raise Ignore() from None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        dead_letter(self.name, task_id, exc, args, kwargs, attempts=self.request.retries + 1)


class InboundEventTask(IntegrationTask):
    """The processing of an InboundEvent (its id the first argument): one that cannot be processed is marked failed
    (and replayable, InboundEvent.replay) rather than written to the dead-letter list: the event is its own record."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if event := InboundEvent.objects.filter(pk=(args or [kwargs.get("event_id")])[0]).first():
            event.fail(f"{type(exc).__name__}: {exc}")


@shared_task
def purge_old_records():
    """Daily (celery beat): the call log, the inbound events and the dead letters dealt with, older than
    INTEGRATIONS_RETENTION_DAYS. Returns the counts."""
    before = timezone.now() - timedelta(days=settings.INTEGRATIONS_RETENTION_DAYS)
    calls = IntegrationCall.objects.filter(created__lt=before).delete()[0]
    events = InboundEvent.objects.filter(received_at__lt=before).delete()[0]
    closed = IntegrationFailure.objects.exclude(state=IntegrationFailure.State.OPEN)
    failures = closed.filter(resolved_at__lt=before).delete()[0]
    return {"calls": calls, "events": events, "dead_letters": failures}
