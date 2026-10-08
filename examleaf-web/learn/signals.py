"""Receivers: the course data of a deleted account, and a clip's files when the clip is deleted."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from . import media
from .models import Clip


@receiver(post_delete, sender=Clip)
def delete_clip_files(sender, instance, **kwargs):
    """The uploaded video and the HLS files of a deleted clip, once the deletion is saved."""

    def delete():
        if instance.source:
            instance.source.delete(save=False)
        media.delete_files(instance.hls_path)

    transaction.on_commit(delete, robust=True)
