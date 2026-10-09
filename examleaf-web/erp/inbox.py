"""The ERPNext sync's items in the staff inbox (staff.InboxItem, through the staff app's own helpers): an outbox row
that died (ERPNext refused it for good, or its tries ran out) waits for those who may replay or discard it
(erp.replay_sync) and is done once replayed or discarded; a reconciliation that found differences waits, one item a
run, for those who may resolve them (erp.resolve_difference) and is done with its last one. Titles name a document's
reference or a day, never a person."""

from django.dispatch import receiver

from integrations.signals import dead_letter_created
from staff.models import InboxItem
from staff.signals import close_items, open_item, quietly

REPLAY_TASK = "erp.tasks.replay_row"  # the dead letters that are the erp app's (IntegrationFailure.task_name)


@receiver(dead_letter_created, dispatch_uid="erp_dead_letter_to_the_inbox")
@quietly
def dead_letter_waits(sender, failure, **kwargs):
    from .models import ErpOutbox

    if failure.task_name != REPLAY_TASK or not (row := ErpOutbox.objects.filter(failure=failure).first()):
        return
    title = f"ERPNext refused {row.examleaf_ref} ({row.event}): replay or discard it"
    open_item(InboxItem.Kind.SYNC_FAILED, row, title, "erp.replay_sync", row=row.pk, error=row.last_error[:200])


def differences_wait(run):
    """A run's differences, one item for them all (in the run's transaction)."""
    title = f"ERPNext reconciliation of {run.date:%d %b %Y}: {run.differences_count} difference(s) to resolve"
    open_item(InboxItem.Kind.RECONCILIATION, run, title, "erp.resolve_difference", run=run.pk)


def done(target):
    """Its open items are done (a row replayed or discarded, a run's last difference resolved)."""
    close_items(target)
