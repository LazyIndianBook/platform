"""The staff app's tasks (celery beat, settings.CELERY_BEAT_SCHEDULE): the audit chain verified nightly and copied off
the server daily."""

import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from . import audit
from .models import InboxItem

logger = logging.getLogger(__name__)


@shared_task
def verify_audit_chain():
    """Nightly: recompute both chains; a break alerts the owners and files an inbox item (research 3.3)."""
    problems = audit.verify()
    action = "audit.chain_broken" if problems else "audit.verified"
    details = {"problems": problems[:20], "count": len(problems), "heads": audit.heads()}
    with transaction.atomic():
        audit.record(
            action,
            actor_type=audit.ActorType.SYSTEM,
            outcome=audit.Outcome.FAILED if problems else audit.Outcome.SUCCESS,
            details=details,
        )
        if problems:
            day = timezone.localdate().isoformat()
            InboxItem.objects.get_or_create(
                kind=InboxItem.Kind.INCIDENT,
                target_type="audit.chain",
                target_id=day,
                done_at=None,
                defaults={
                    "title": "The audit log's chain is broken",
                    "permission": "staff.view_auditlog",
                    "data": {"problems": problems[:20]},
                },
            )
            audit.alert("The audit log's chain is broken", "\n".join(problems[:20]))
    return len(problems)


@shared_task
def export_audit_log(days=7):
    """Daily: each of the last `days` UTC days not yet in the backups' bucket, as JSON lines with the chains' heads
    (audit.export_day). A failure alerts the owners."""
    today = datetime.now(UTC).date()
    written = []
    try:
        for back in range(days, 0, -1):
            if name := audit.export_day(today - timedelta(days=back)):
                written.append(name)
    except Exception as error:
        logger.exception("The audit log's export failed")
        audit.alert("The audit log's export failed", f"{type(error).__name__}: {error}")
        raise
    return written
