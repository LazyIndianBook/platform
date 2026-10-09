"""An account's erasure reaches its tickets: once accounts.DeletionRequest.complete() has erased the account, its
tickets keep only what the grievance register needs (services.forget_requester). A failure is logged and the
erasure stands: staff can run it again (`manage.py shell`, RUNBOOK.md)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import DeletionRequest
from staff.signals import quietly


@receiver(post_save, sender=DeletionRequest)
@quietly
def account_erased(sender, instance, **kwargs):
    if instance.status == DeletionRequest.Status.DONE:
        from .services import forget_requester

        forget_requester(instance.user)
