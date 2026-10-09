import json
import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from examleaf.celery import single_run
from ops.tasks import queue_text_email

from .models import DeletionRequest

logger = logging.getLogger(__name__)


@shared_task
@single_run(300)
def purge_due_deletions():
    """Daily (celery beat): carry out the account deletions whose waiting period is over, but those something holds
    (a legal hold on the account, a student under 18 whose parent has not confirmed: they wait, with an inbox item
    once their day has passed); and erase the registration details the intermediary rule kept, once their 180 days are
    over. Each person gets the confirmation with what stays and the contact block. Returns how many were erased."""
    from staff.models import InboxItem
    from staff.privacy import erasure_confirmation
    from staff.signals import open_item

    due = DeletionRequest.objects.filter(status=DeletionRequest.Status.PENDING, due_at__lte=timezone.now())
    erased = 0
    for deletion in due.select_related("user"):
        subject, body = erasure_confirmation(deletion.user)
        try:
            email = deletion.complete()
        except DeletionRequest.Held as held:  # its items close with it (staff.signals.deletion_waits)
            open_item(
                InboxItem.Kind.COMPLIANCE,
                deletion,
                f"Account deletion {deletion.pk} waits: {held.reasons[0]}",
                "staff.handle_data_request",
                reasons=held.reasons,
            )
            continue
        if email:
            queue_text_email(email, subject, body)
            erased += 1
    finished = DeletionRequest.objects.filter(
        status=DeletionRequest.Status.DONE, registration_until__lte=timezone.now()
    )
    for deletion in finished.select_related("user"):
        deletion.forget_registration()
    return erased


def ledger_line(deletion):
    return {
        "user": deletion.user_id,
        "subject_hash": deletion.subject_hash,
        "erased_at": deletion.closed_at.isoformat() if deletion.closed_at else None,
        "registration_until": deletion.registration_until.isoformat() if deletion.registration_until else None,
    }


LEDGER_PREFIX = "erasures/"


@shared_task(autoretry_for=(OSError,), retry_backoff=60, max_retries=5)
def copy_erasure_ledger(deletion_id=None):
    """The erasure ledger copied off the server, a line per erasure (`erasures/<id>.json` in the backups' bucket), so
    that an erasure made after the last backup is known again even if the database is lost (manage.py
    reapply_erasures reads them). With an id: that erasure's line (queued when it is done); without: every one not
    copied yet (nightly). Without a backups bucket (BACKUP_BUCKET) nothing is copied. A line there already is left as
    it is. Returns how many were copied."""
    from staff.audit import backups_storage

    storage = backups_storage()
    if storage is None:
        return 0
    rows = DeletionRequest.objects.filter(status=DeletionRequest.Status.DONE, ledger_copied_at=None)
    rows = rows.exclude(subject_hash="")
    if deletion_id is not None:
        rows = rows.filter(pk=deletion_id)
    copied = 0
    for deletion in rows:
        name = f"{LEDGER_PREFIX}{deletion.pk}.json"
        if not storage.exists(name):
            storage.save(name, ContentFile(json.dumps(ledger_line(deletion), sort_keys=True).encode()))
        DeletionRequest.objects.filter(pk=deletion.pk).update(ledger_copied_at=timezone.now())
        copied += 1
    return copied
