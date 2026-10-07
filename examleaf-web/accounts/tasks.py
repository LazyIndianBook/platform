from celery import shared_task
from django.utils import timezone

from ops.tasks import queue_text_email

from .models import DeletionRequest


@shared_task
def purge_due_deletions():
    """Daily (celery beat): carry out the account deletions whose waiting period is over."""
    due = list(
        DeletionRequest.objects.filter(
            status=DeletionRequest.Status.PENDING, due_at__lte=timezone.now()
        ).select_related("user")
    )
    for deletion in due:
        email = deletion.complete()
        queue_text_email(
            email,
            "Your account has been deleted",
            "Your ExamLeaf account and the personal details in it have been deleted, as you asked.\n\n"
            "Thank you for using ExamLeaf.",
        )
    return len(due)
