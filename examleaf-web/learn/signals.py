"""Receivers: the course data of a deleted account, and a clip's files when the clip is deleted."""

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import DeletionRequest

from . import media
from .models import CardReview, Clip, Device, Entitlement, Learner, Progress, QuizAttempt


@receiver(post_delete, sender=Clip)
def delete_clip_files(sender, instance, **kwargs):
    """The uploaded video and the HLS files of a deleted clip, once the deletion is saved."""

    def delete():
        if instance.source:
            instance.source.delete(save=False)
        media.delete_files(instance.hls_path)

    transaction.on_commit(delete, robust=True)


@receiver(post_save, sender=DeletionRequest)
def forget_course_data(sender, instance, **kwargs):
    """Account deletion (accounts.DeletionRequest.complete): progress, quiz answers, card reviews, settings, the app's
    devices (no more reminders) and entitlements go, with the entitlements' history (their notes are staff's words
    about the person). Redeemed book codes stay used (by the anonymised account)."""
    if instance.status == DeletionRequest.Status.DONE:
        for model in (Progress, QuizAttempt, CardReview, Learner, Device, Entitlement):
            model.objects.filter(user=instance.user_id).delete()
        Entitlement.history.filter(user_id=instance.user_id).delete()
