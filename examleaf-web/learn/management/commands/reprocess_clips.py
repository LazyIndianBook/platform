from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from learn.models import Clip
from learn.tasks import queue_processing


class Command(BaseCommand):
    help = (
        "Queue clips for ffmpeg again: the given ids, every clip with a video (--all), or by default the failed ones "
        "and those stuck in processing for over an hour (a task lost while the broker was down)."
    )

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="*", type=int)
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, ids, all, **options):
        clips = Clip.objects.exclude(source="")
        if ids:
            clips = clips.filter(pk__in=ids)
        elif not all:
            stuck = Q(processing=Clip.Processing.PROCESSING, modified__lt=timezone.now() - timedelta(hours=1))
            clips = clips.filter(Q(processing=Clip.Processing.FAILED) | stuck)
        for clip in clips:
            queue_processing(clip)
            self.stdout.write(f"queued clip {clip.pk}: {clip.title}")
        self.stdout.write(f"{len(clips)} queued")
