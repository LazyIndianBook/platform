import json
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import media
from .models import Clip, Device

logger = logging.getLogger(__name__)


def queue_processing(clip):
    """Mark the clip as processing and hand it to the media worker once the transaction is saved. If the broker is
    down the clip stays "processing": manage.py reprocess_clips queues it again (RUNBOOK.md)."""
    clip.start()
    clip.save(update_fields=["processing", "processing_error", "modified"])
    transaction.on_commit(lambda: process_clip.delay(clip.pk), robust=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=120, time_limit=3600, soft_time_limit=3500)
def process_clip(self, clip_id):
    """ffmpeg on the "media" queue (settings.CELERY_TASK_ROUTES): the clip becomes ready, or failed with the end of
    ffmpeg's messages. A bad video fails at once; anything else (the storage unreachable) is tried again 3 times."""
    clip = Clip.objects.filter(pk=clip_id).first()
    if clip is None or not clip.source:
        return
    old = clip.hls_path
    try:
        made = media.process(clip)
    except media.MediaError as error:
        clip.fail(str(error))
        clip.save(update_fields=["processing", "processing_error", "modified"])
        return
    except Exception as error:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=error) from error
        clip.fail(f"{type(error).__name__}: {error}")
        clip.save(update_fields=["processing", "processing_error", "modified"])
        raise
    clip.finish(*made)
    clip.save(update_fields=["processing", "hls_path", "poster", "duration", "modified"])
    if old != clip.hls_path:
        media.delete_files(old)


def firebase():
    """The Firebase app made from FCM_SERVICE_ACCOUNT_JSON (the JSON itself, or the path of the file)."""
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app("examleaf")
    except ValueError:
        account = settings.FCM_SERVICE_ACCOUNT_JSON
        info = json.loads(account) if account.lstrip().startswith("{") else account
        return firebase_admin.initialize_app(credentials.Certificate(info), name="examleaf")


def reminder(learner, today):
    if learner.exam_date and learner.exam_date > today:
        return f"{(learner.exam_date - today).days} days to your exam. Today's revision is ready."
    return "Today's revision is ready: a few minutes, a few more marks."


@shared_task
def send_reminders():
    """Daily (celery beat): the revision reminder, through Firebase Cloud Messaging (HTTP v1, firebase-admin), to the
    devices of students who turned it on in the app. Nothing without FCM_SERVICE_ACCOUNT_JSON. Tokens that Firebase
    no longer knows (the app was removed) are deleted. Returns the number sent."""
    if not settings.FCM_SERVICE_ACCOUNT_JSON:
        return 0
    from firebase_admin import messaging

    today, sent = timezone.localdate(), 0
    devices = list(  # in id order: the batches of 500 are the same on every database
        Device.objects.filter(user__learner__reminders=True, user__is_active=True)
        .select_related("user__learner")
        .order_by("pk")
    )
    for start in range(0, len(devices), 500):  # send_each takes at most 500
        batch = devices[start : start + 500]
        notes = [
            messaging.Message(
                fid=device.token,  # FCM's installation ID (firebase-admin 7.7 deprecates token=)
                notification=messaging.Notification(
                    title="ExamLeaf revision", body=reminder(device.user.learner, today)
                ),
            )
            for device in batch
        ]
        answers = messaging.send_each(notes, app=firebase()).responses
        gone = (messaging.UnregisteredError, messaging.SenderIdMismatchError)
        unknown = [d.pk for d, a in zip(batch, answers, strict=True) if isinstance(a.exception, gone)]
        Device.objects.filter(pk__in=unknown).delete()
        sent += sum(answer.success for answer in answers)
    logger.info("revision reminders sent: %s of %s", sent, len(devices))
    return sent
