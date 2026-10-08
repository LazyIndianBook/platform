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


def fake_ffmpeg(audio="aac", fail=None, video="h264", container="mov,mp4,m4a,3gp,3g2,mj2", calls=None):
    """subprocess.run as ffprobe and ffmpeg would answer (codecs and container as ffprobe names them; audio=None: no
    sound), writing the files ffmpeg would write; `calls` collects the commands."""

    def run(args, **kwargs):
        if calls is not None:
            calls.append(args)
        if args[0] == fail:
            return subprocess.CompletedProcess(args, 1, "", "lots of output\nInvalid data found when processing input")
        if args[0] == "ffprobe":
            streams = [{"codec_type": "video", "codec_name": video}]
            streams += [{"codec_type": "audio", "codec_name": audio}] if audio else []
            streams += [{"codec_type": "data", "codec_name": "none"}]  # an iPhone's metadata track: never decoded
            info = {"streams": streams, "format": {"format_name": container, "duration": "61.6"}}
            return subprocess.CompletedProcess(args, 0, json.dumps(info))
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
    poster = media.poster_command("in.mp4", "p.jpg", 61)
    assert poster[poster.index("-ss") + 1] == "1"


def test_ffmpeg_opens_local_mp4_and_matroska_files_with_the_expected_decoders_only():
    """M5: whatever the file claims to be: no network or playlist, no other demuxer or decoder, 2 threads, no stdin."""
    for command in [media.hls_command("in.mp4", "out", audio=True), media.poster_command("in.mp4", "p.jpg", 61)]:
        before_input = " ".join(command[: command.index("-i")])
        assert "-nostdin" in before_input and "-hide_banner" in before_input and "-threads 2" in before_input
        assert "-protocol_whitelist file -format_whitelist matroska,mov -codec_whitelist h264,hevc," in before_input
        assert "-threads 2" in " ".join(command[command.index("-i") :])  # the encoders too


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


@pytest.mark.parametrize(
    "probed, refused",
    [
        ({"container": "avi"}, "container: avi"),
        ({"container": "hls"}, "container: hls"),
        ({"video": "prores"}, "video: prores"),
        ({"audio": "pcm_s16le"}, "audio: pcm_s16le"),
    ],
)
def test_ffprobe_must_find_a_clip_before_ffmpeg_decodes_anything(
    clip, monkeypatch, django_capture_on_commit_callbacks, probed, refused
):
    """M5: the container and codecs ffprobe reports are checked; anything else fails the clip, and ffmpeg never runs."""
    calls = []
    monkeypatch.setattr(media.subprocess, "run", fake_ffmpeg(calls=calls, **probed))
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(clip)
    clip.refresh_from_db()
    assert clip.processing == "failed" and clip.processing_error.startswith("Not a video we take")
    assert refused in clip.processing_error and [args[0] for args in calls] == ["ffprobe"]
    assert "-protocol_whitelist" in calls[0] and "-codec_whitelist" in calls[0]


def test_a_file_too_large_or_not_a_video_by_name_is_not_even_fetched(
    clip, monkeypatch, settings, django_capture_on_commit_callbacks
):
    calls = []
    monkeypatch.setattr(media.subprocess, "run", fake_ffmpeg(calls=calls))
    settings.LEARN_MAX_UPLOAD_MB = 0  # the clip's 5 bytes are over it
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(clip)
    clip.refresh_from_db()
    assert clip.processing == "failed" and "LEARN_MAX_UPLOAD_MB" in clip.processing_error and calls == []
    settings.LEARN_MAX_UPLOAD_MB = 500
    Clip.objects.filter(pk=clip.pk).update(source="learn/sources/" + "c" * 32 + ".m3u8")
    with django_capture_on_commit_callbacks(execute=True):
        queue_processing(Clip.objects.get(pk=clip.pk))
    assert Clip.objects.get(pk=clip.pk).processing_error.startswith("Not a video we take") and calls == []


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
