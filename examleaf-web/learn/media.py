"""Clip videos to HLS for low-end phones with ffmpeg (run as a subprocess; `ffmpeg` and `ffprobe` must be on PATH: the
Dockerfile installs them, `brew install ffmpeg` on a Mac): two vertical 9:16 renditions, 480x854 at about 700 kbps and
720x1280 at about 1.5 Mbps (a landscape video is letterboxed), AAC sound at 64 kbps, 4-second segments, a master
playlist, and a poster from the first second. Files go to the private storage, or the public one with
LEARN_PUBLIC_VIDEO=1, under learn/hls/<clip>/<new folder per run>/."""

import json
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages

RENDITIONS = [("480p", 480, 854, 700), ("720p", 720, 1280, 1500)]  # name, width, height, video kbps
SEGMENT_SECONDS = 4
TIMEOUT = 3000  # seconds for one ffmpeg run (the task's own limit is an hour)


class MediaError(Exception):
    """ffmpeg or ffprobe could not do it: the message ends with the end of their error output."""


def storage():
    return storages["public" if settings.LEARN_PUBLIC_VIDEO else "default"]


def run(args):
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except FileNotFoundError:
        raise MediaError(f"{args[0]} is not installed (Dockerfile; on a Mac: brew install ffmpeg).") from None
    except subprocess.TimeoutExpired:
        raise MediaError(f"{args[0]} took more than {TIMEOUT} seconds.") from None
    if done.returncode:
        raise MediaError(f"{args[0]} failed ({done.returncode}): {done.stderr[-1500:]}")
    return done.stdout


def probe(path):
    """(whole seconds, has sound) of a video file."""
    info = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]))
    kinds = {stream.get("codec_type") for stream in info.get("streams", [])}
    if "video" not in kinds:
        raise MediaError("The file has no video.")
    return round(float(info.get("format", {}).get("duration", 0))), "audio" in kinds


def hls_command(source, out, audio):
    """One ffmpeg run for every rendition: scaled and padded to 9:16, key frames every segment, one playlist each."""
    count = len(RENDITIONS)
    scale = [
        f"[v{i}]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[out{i}]"
        for i, (_, w, h, _) in enumerate(RENDITIONS)
    ]
    split = f"[0:v]split={count}" + "".join(f"[v{i}]" for i in range(count))
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", source, "-filter_complex", ";".join([split, *scale])]
    for i, (_, _, _, kbps) in enumerate(RENDITIONS):
        args += ["-map", f"[out{i}]", f"-c:v:{i}", "libx264", f"-b:v:{i}", f"{kbps}k"]
        args += [f"-maxrate:v:{i}", f"{kbps * 11 // 10}k", f"-bufsize:v:{i}", f"{kbps * 2}k"]
        args += ["-map", "0:a:0"] if audio else []
    args += ["-preset", "veryfast", "-profile:v", "main", "-pix_fmt", "yuv420p"]
    args += ["-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})"]
    args += ["-c:a", "aac", "-b:a", "64k", "-ac", "1"] if audio else []
    streams = [f"v:{i},a:{i},name:{name}" if audio else f"v:{i},name:{name}" for i, (name, *_) in enumerate(RENDITIONS)]
    args += ["-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod"]
    args += ["-hls_flags", "independent_segments", "-hls_segment_filename", f"{out}/%v/seg_%03d.ts"]
    args += ["-master_pl_name", "master.m3u8", "-var_stream_map", " ".join(streams), f"{out}/%v/index.m3u8"]
    return args


def poster_command(source, poster, seconds):
    _, w, h, _ = RENDITIONS[-1]
    at = "1" if seconds > 1 else "0"
    scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    return ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", at, "-i", source, "-frames:v", "1", "-vf", scale, poster]


def process(clip):
    """Make the clip's HLS files and poster from its uploaded video; returns (master playlist, poster, seconds), names
    in storage(). A new folder each run: the files of an earlier run stay until the task deletes them."""
    store, folder = storage(), f"learn/hls/{clip.pk}/{secrets.token_hex(4)}"
    with tempfile.TemporaryDirectory() as tmp:
        source, out = Path(tmp) / f"source{Path(clip.source.name).suffix}", Path(tmp) / "hls"
        with clip.source.open("rb") as uploaded, source.open("wb") as copy:
            shutil.copyfileobj(uploaded, copy)
        seconds, audio = probe(str(source))
        for name, *_ in RENDITIONS:
            (out / name).mkdir(parents=True)
        run(hls_command(str(source), out, audio))
        run(poster_command(str(source), str(out / "poster.jpg"), seconds))
        for path in sorted(p for p in out.rglob("*") if p.is_file()):
            with path.open("rb") as file:
                store.save(f"{folder}/{path.relative_to(out).as_posix()}", File(file))
    return f"{folder}/master.m3u8", f"{folder}/poster.jpg", seconds


def delete_files(master):
    """Delete the folder of an HLS master playlist (name in storage()) with everything in it."""
    if not master:
        return
    store = storage()

    def remove(folder):
        folders, files = store.listdir(folder)
        for name in files:
            store.delete(f"{folder}/{name}")
        for name in folders:
            remove(f"{folder}/{name}")

    try:
        remove(master.rsplit("/", 1)[0])
    except FileNotFoundError:  # gone already
        pass
