"""The ffmpeg pipeline: the commands, a run with ffmpeg mocked (ready, failed, files replaced), the clean-up, the
reprocess command, and one real run when ffmpeg is installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from celery.exceptions import Retry
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from . import media
from .models import Clip
from .tasks import process_clip, queue_processing
from .tests import make_course

pytestmark = pytest.mark.django_db


def fake_ffmpeg(audio=True, fail=None):
    """subprocess.run as ffprobe and ffmpeg would answer, writing the files ffmpeg would write."""

    def run(args, **kwargs):
        if args[0] == fail:
            return subprocess.CompletedProcess(args, 1, "", "lots of output\nInvalid data found when processing input")
        if args[0] == "ffprobe":
            streams = [{"codec_type": "video"}, *([{"codec_type": "audio"}] if audio else [])]
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"streams": streams, "format": {"duration": "61.6"}})
            )
        if "-master_pl_name" in args:
            out = Path(args[-1]).parent.parent
            (out / "master.m3u8").write_text("#EXTM3U\n480p/index.m3u8\n720p/index.m3u8\n")
            for name, *_ in media.RENDITIONS:
                (out / name / "index.m3u8").write_text("#EXTM3U\nseg_000.ts\n")
                (out / name / "seg_000.ts").write_bytes(b"ts")
        else:
            Path(args[-1]).write_bytes(b"jpg")
        return subprocess.CompletedProcess(args, 0, "", "")

    return run


@pytest.fixture
def clip():
    make_course(chapters=1, clips=1)
    clip = Clip.objects.get()
    clip.source.save("phone video.MP4", ContentFile(b"video"), save=True)
    return clip


def test_the_command_makes_two_vertical_renditions_with_sound():
    args = " ".join(media.hls_command("in.mp4", "out", audio=True))
    for part in ["scale=480:854", "scale=720:1280", "-b:v:0 700k", "-b:v:1 1500k", "-b:a 64k", "-hls_time 4"]:
        assert part in args
    assert "v:0,a:0,name:480p v:1,a:1,name:720p" in args and "-hls_playlist_type vod" in args
    assert "0:a:0" not in " ".join(media.hls_command("in.mp4", "out", audio=False))
    assert media.poster_command("in.mp4", "p.jpg", 61)[4:6] == ["-ss", "1"]


def test_a_processed_clip_is_ready_and_a_new_run_replaces_its_files(
    clip, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(media.subprocess, "run", fake_ffmpeg())
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(clip)
    clip.refresh_from_db()
    assert (clip.processing, clip.duration, clip.source.name.startswith("learn/sources/")) == ("ready", 62, True)
    first = clip.hls_path
    assert default_storage.exists(first) and default_storage.exists(first.replace("master.m3u8", "720p/seg_000.ts"))

    with django_capture_on_commit_callbacks(execute=True):
        call_command("reprocess_clips", clip.pk, stdout=open("/dev/null", "w"))
    clip.refresh_from_db()
    assert clip.hls_path != first and default_storage.exists(clip.hls_path) and not default_storage.exists(first)

    files = [clip.hls_path, clip.source.name]
    with django_capture_on_commit_callbacks(execute=True):
        clip.delete()
    assert not any(default_storage.exists(name) for name in files)


def test_a_bad_video_fails_with_the_end_of_ffmpegs_messages(clip, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(media.subprocess, "run", fake_ffmpeg(fail="ffmpeg"))
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(clip)
    clip.refresh_from_db()
    assert clip.processing == "failed" and clip.processing_error.endswith("Invalid data found when processing input")
    assert clip.hls_path.startswith("learn/hls/")  # the earlier files (make_course's names) are kept

    monkeypatch.setattr(media.subprocess, "run", fake_ffmpeg())
    with django_capture_on_commit_callbacks(execute=True):
        call_command("reprocess_clips", stdout=open("/dev/null", "w"))  # by default: the failed ones
    clip.refresh_from_db()
    assert clip.processing == "ready" and clip.processing_error == ""


def test_storage_trouble_is_tried_again_then_fails(clip, monkeypatch):
    monkeypatch.setattr(media, "process", lambda clip: (_ for _ in ()).throw(OSError("bucket unreachable")))
    clip.start()
    clip.save()
    with pytest.raises(Retry):
        process_clip.apply(args=[clip.pk], throw=True)
    clip.refresh_from_db()
    assert clip.processing == "processing"
    with pytest.raises(OSError):
        process_clip.apply(args=[clip.pk], retries=3, throw=True)  # the last try
    clip.refresh_from_db()
    assert clip.processing == "failed" and "bucket unreachable" in clip.processing_error


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed (brew install ffmpeg)")
def test_a_real_ffmpeg_run(clip, tmp_path, django_capture_on_commit_callbacks):
    video = tmp_path / "test.mp4"
    media.run(["ffmpeg", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=6", "-f", "lavfi", "-i",
               "sine=duration=6", "-shortest", "-pix_fmt", "yuv420p", str(video)])  # fmt: skip
    clip.source.save("test.mp4", ContentFile(video.read_bytes()), save=True)
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(clip)
    clip.refresh_from_db()
    assert clip.processing == "ready", clip.processing_error
    master = default_storage.open(clip.hls_path).read().decode()
    assert "RESOLUTION=480x854" in master and "RESOLUTION=720x1280" in master and clip.duration == 6
    assert default_storage.exists(clip.poster)
