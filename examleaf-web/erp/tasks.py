"""The erp app's Celery tasks (beat entries in settings.py, "erp-…"). The relay sends the outbox; the doorbells and the
pull read ERPNext back (inbound.py); the reconciliation compares each day (reconcile.py).

The relay (every minute, and nudged when a transaction writes a row) sends, per aggregate, its first row not sent
(an earlier row that failed holds the aggregate's later ones, never another aggregate's), only of the flows switched
on, through the ERPNext account's client (its circuit breaker and call log). A row is claimed first (compare-and-set,
with a lease: a worker that died leaves it to be tried again), so two relays never send one; nothing is held in a
transaction during a call. On an answer (a duplicate's too: ERPNext had it already): sent, ERPNext's answer kept and
its ErpLink written. Otherwise:
- the circuit open (no call was made): the row waits COOL_OFF, no try counted; the run stops;
- 429: the row waits what Retry-After says (else the backoff), no try counted; the run stops;
- a refusal that never succeeds unchanged (contract.PERMANENT: a request ERPNext calls invalid, a conflict with what
  it holds, more paid or credited than there is, a key reused with another body ...): dead at once;
- ERPNext unreachable or 5xx, another refusal (a document it does not have yet, stock not received yet, a step the
  sync user may not do), a payload that cannot be built: a try counted, tried again after a delay that doubles from
  a minute to six hours, jittered; after ERP_MAX_ATTEMPTS tries it is dead;
- the token refused (Frappe's 401 or 403): a try counted, and the run stops.
A dead row is a dead letter (IntegrationFailure, dead_letter_created) and holds its aggregate for staff: replay, or
discard with a reason."""

import logging
import random
import time
import uuid
from collections import Counter
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from examleaf.celery import LONG_TASK, single_run
from integrations.client import (
    CircuitOpen,
    IntegrationAuthFailed,
    IntegrationError,
    IntegrationRejected,
    IntegrationUnavailable,
)
from integrations.models import COOL_OFF, InboundEvent, IntegrationAccount, IntegrationFailure
from integrations.services import dead_letter
from integrations.tasks import InboundEventTask, IntegrationTask

from . import contract, inbound, reconcile
from .client import client
from .models import ErpCursor, ErpLink, ErpOutbox, ErpReconciliationRun
from .producers import FLOWS, enabled, enabled_events, nudge, switch

logger = logging.getLogger(__name__)
State = ErpOutbox.State
LEASE = timedelta(minutes=5)  # a claimed row that never reported is tried again after this
BACKOFF, BACKOFF_MAX = 60, 6 * 3600  # seconds: the first retry's delay, and the most it grows to
BATCH = 50
RUN_SECONDS = 240  # a run stops taking rows after this (CELERY_TASK_TIME_LIMIT is 300); the next one goes on
STOP = {"waiting", "rate_limited", "credentials_refused"}


def backoff(attempts):
    """Seconds before the next try: a minute doubling with each try, at most six hours, jittered (half to all)."""
    delay = min(BACKOFF_MAX, BACKOFF * 2 ** max(attempts - 1, 0))
    return delay / 2 + random.uniform(0, delay / 2)


def due(now=None):
    """The rows to send now: due, of a flow switched on, and first of their aggregate not sent (no earlier row of it
    open: pending, sending, failed or dead); a row claimed whose lease ran out counts as due."""
    now = now or timezone.now()
    earlier = ErpOutbox.objects.filter(
        aggregate_type=OuterRef("aggregate_type"),
        aggregate_id=OuterRef("aggregate_id"),
        sequence__lt=OuterRef("sequence"),
        state__in=ErpOutbox.OPEN,
    )
    ready = Q(state__in=[State.PENDING, State.FAILED, State.SENDING], next_at__lte=now)
    rows = ErpOutbox.objects.filter(ready, event__in=enabled_events()).exclude(Exists(earlier))
    return rows.order_by("next_at", "pk")


def _wait(row, error, seconds):
    """Not tried (the circuit open, a 429): back as it was, for `seconds`."""
    state = State.FAILED if row.attempts else State.PENDING
    next_at = timezone.now() + timedelta(seconds=seconds)
    ErpOutbox.objects.filter(pk=row.pk).update(state=state, next_at=next_at, last_error=str(error)[:500])


def _failed(row, error, dead=False):
    """A try that failed: again later, or dead (`dead`, or after ERP_MAX_ATTEMPTS: a dead letter; the aggregate
    waits)."""
    row.attempts += 1
    row.last_error = str(error)[:500]
    if not dead and row.attempts < settings.ERP_MAX_ATTEMPTS:
        row.state, row.next_at = State.FAILED, timezone.now() + timedelta(seconds=backoff(row.attempts))
        row.save(update_fields=["state", "attempts", "next_at", "last_error"])
        return "failed"
    with transaction.atomic():
        run_id = f"erp-outbox-{row.pk}-{uuid.uuid4().hex[:12]}"
        method = contract.EVENTS[row.event].method if row.event in contract.EVENTS else row.event
        row.failure = dead_letter("erp.tasks.replay_row", run_id, error, [row.pk], {}, row.attempts, operation=method)
        row.state = State.DEAD
        row.save(update_fields=["state", "attempts", "last_error", "failure"])
    logger.error("erp: outbox row %s (%s) is dead after %s tries: %s", row.pk, row.event, row.attempts, error)
    return "dead"


def _sent(row, answer):
    answer = answer if isinstance(answer, dict) else {"answer": answer}
    now = timezone.now()
    with transaction.atomic():
        ErpOutbox.objects.filter(pk=row.pk).update(state=State.SENT, sent_at=now, response=answer, last_error="")
        ErpLink.objects.update_or_create(
            examleaf_ref=row.examleaf_ref,
            defaults={
                "model": row.model,
                "object_id": row.object_id,
                "doctype": contract.EVENTS[row.event].doctype,
                "name": str(answer.get("name") or "")[:140],
                "synced_at": now,
            },
        )
    return "sent"


def deliver(erp, row):
    """Send one row (claimed first): what came of it ("sent", "failed", "dead", "busy": another worker has it, or a
    reason to stop the run)."""
    claim = ErpOutbox.objects.filter(pk=row.pk, state=row.state, next_at=row.next_at)
    if not claim.update(state=State.SENDING, next_at=timezone.now() + LEASE):
        return "busy"
    try:
        if row.payload is None:  # its builder failed when it was written
            row.payload = contract.build_again(row.event, row.model, row.object_id)
            ErpOutbox.objects.filter(pk=row.pk).update(payload=row.payload)
        answer = erp.call(contract.EVENTS[row.event].method, contract.request_body(row))
    except CircuitOpen as error:
        _wait(row, error, COOL_OFF.total_seconds())
        return "waiting"
    except IntegrationUnavailable as error:
        if error.status_code == 429:
            _wait(row, error, error.retry_after if error.retry_after is not None else backoff(row.attempts + 1))
            return "rate_limited"
        return _failed(row, error)
    except IntegrationAuthFailed as error:
        if getattr(error, "code", None) == "permission_denied":  # examleaf_erp's: one step refused, not the token
            return _failed(row, error)
        _failed(row, error)
        return "credentials_refused"
    except IntegrationRejected as error:
        return _failed(row, error, dead=contract.permanent(getattr(error, "code", None), getattr(error, "field", None)))
    except Exception as error:  # a payload that cannot be built
        if not isinstance(error, IntegrationError):
            logger.exception("erp: outbox row %s could not be sent", row.pk)
        return _failed(row, error)
    return _sent(row, answer)


@shared_task
def relay():
    """Every minute, and after a transaction that wrote rows: send what is due (module docstring). Returns the
    counts of what came of the rows."""
    if not switch("ERP_ENABLED"):
        return {"skipped": "ERP_ENABLED is off"}
    erp = client()
    if erp is None:
        return {"skipped": "no enabled ERPNext account"}
    discarded = IntegrationFailure.State.DISCARDED  # dead letters discarded in Admin → Integrations: theirs go on
    ErpOutbox.objects.filter(state=State.DEAD, failure__state=discarded).update(state=State.DISCARDED)
    counts, deadline = Counter(), time.monotonic() + RUN_SECONDS
    while time.monotonic() < deadline and (rows := list(due()[:BATCH])):
        progressed = False
        for row in rows:
            outcome = deliver(erp, row)
            counts[outcome] += 1
            if outcome in STOP:
                return dict(counts)
            progressed |= outcome != "busy"
        if not progressed:  # every row of the batch was another relay's
            break
    return dict(counts)


@shared_task
def replay_row(row_id):
    """A dead letter replayed (Admin → Integrations, the API, erp_replay): the row tries again now, from its first
    try. Nothing when it is not dead or failing (replayed already)."""
    rows = ErpOutbox.objects.filter(pk=row_id, state__in=[State.DEAD, State.FAILED])
    with transaction.atomic():
        if rows.update(state=State.PENDING, attempts=0, next_at=timezone.now()):
            nudge()


@shared_task(base=InboundEventTask, bind=True)
def process_inbound_event(self, event_id):
    """A doorbell stored by /api/hooks/erp-events/: the document read again and applied (inbound.ring). Once."""
    event = InboundEvent.objects.get(pk=event_id)
    if event.processed_at or event.state == InboundEvent.State.REJECTED:
        return
    note = inbound.ring(event)
    event.processed_at, event.error = timezone.now(), note[:500]
    event.save(update_fields=["processed_at", "error"])


@shared_task
def pull():
    """Every 15 minutes: what changed in ERPNext since each cursor (the net under lost doorbells)."""
    if not switch("ERP_ENABLED"):
        return {"skipped": "ERP_ENABLED is off"}
    return inbound.pull()


@shared_task
def refresh_stock():
    """A stock doorbell's read (inbound.stock_soon: one for a burst of them)."""
    if switch("ERP_ENABLED") and switch("ERP_PULL_STOCK") and (erp := client()):
        try:
            return len(inbound.refresh_stock(erp))
        except IntegrationError as error:  # the 15-minute pull reads it again
            logger.warning("erp: the stock was not read: %s", error)
    return None


@shared_task(base=IntegrationTask, bind=True, **LONG_TASK)
@single_run(LONG_TASK["time_limit"])  # its differences and their email: once
def reconcile_day(self, day=None):
    """03:30 India time: yesterday's documents and today's stock compared (reconcile.run); retried while ERPNext
    cannot be reached, a dead letter when it gives up."""
    run = reconcile.run(reconcile.parse_day(day))
    return {"run": run.pk, "state": run.state, "differences": run.differences_count} if run else None


def status(now=None):
    """The sync at a glance (erp_status, GET /api/v1/staff/erp/status/): the switches, the account and its circuit, the
    outbox by state with its oldest row waiting, the aggregates a dead row holds, the cursors, the last
    reconciliation."""
    now = now or timezone.now()
    counts = dict(ErpOutbox.objects.order_by().values_list("state").annotate(n=Count("pk")))
    waiting = ErpOutbox.objects.filter(state__in=[State.PENDING, State.FAILED, State.SENDING])
    oldest = waiting.order_by("created").values_list("created", flat=True).first()
    held = ErpOutbox.objects.filter(state=State.DEAD).values("aggregate_type", "aggregate_id").distinct().count()
    account = IntegrationAccount.enabled_for("erpnext")
    run = ErpReconciliationRun.objects.order_by("-started_at", "-pk").first()
    return {
        "enabled": switch("ERP_ENABLED"),
        "mode": settings.ERP_MODE,
        "flows": {flow: enabled(flow) for flow in FLOWS},
        "pull_stock": switch("ERP_PULL_STOCK"),
        "pull_b2b": switch("ERP_PULL_B2B"),
        "stock_projection": switch("ERP_STOCK_PROJECTION"),
        "account": account
        and {
            "id": account.pk,
            "label": str(account),
            "mode": account.mode,
            "circuit": account.circuit_state,
            "last_success_at": account.last_success_at,
            "last_error": account.last_error,
        },
        "outbox": {state: counts.get(state, 0) for state in State.values},
        "oldest_waiting_at": oldest,
        "oldest_waiting_seconds": int((now - oldest).total_seconds()) if oldest else None,
        "held_aggregates": held,
        "cursors": [
            {
                "doctype": c.doctype,
                "modified_after": c.modified_after,
                "last_run_at": c.last_run_at,
                "error": c.last_error,
            }
            for c in ErpCursor.objects.all()
        ],
        "last_reconciliation": run
        and {
            "id": run.pk,
            "date": run.date,
            "state": run.state,
            "differences": run.differences_count,
            "open_differences": run.differences.filter(resolved_at__isnull=True).count(),
            "finished_at": run.finished_at,
        },
    }
