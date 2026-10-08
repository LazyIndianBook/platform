"""A clip's HLS files behind a signed link (the app's player and the staff player), and the staff preview page."""

import re
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from . import media
from .models import Clip

SIGNER = signing.TimestampSigner(salt="learn.hls")
NAMES = "|".join(name for name, *_ in media.RENDITIONS)
FILE = re.compile(rf"master\.m3u8|poster\.jpg|(?:{NAMES})/(?:index\.m3u8|seg_\d{{3,5}}\.ts)")
TYPES = {"m3u8": "application/vnd.apple.mpegurl", "ts": "video/mp2t", "jpg": "image/jpeg"}


def playback(clip):
    """The links of a processed clip's master playlist and poster, and when they stop working (None: never, for
    public files with LEARN_PUBLIC_VIDEO=1 and a bucket)."""
    store = media.storage()
    if settings.LEARN_PUBLIC_VIDEO and not isinstance(store, FileSystemStorage):
        return {"hls_url": store.url(clip.hls_path), "poster_url": store.url(clip.poster), "expires_at": None}
    token = SIGNER.sign_object(clip.pk)
    return {
        "hls_url": settings.SITE_URL + reverse("learn:hls", args=[token, "master.m3u8"]),
        "poster_url": settings.SITE_URL + reverse("learn:hls", args=[token, "poster.jpg"]),
        "expires_at": timezone.now() + timedelta(seconds=settings.LEARN_URL_SECONDS),
    }


@require_GET
def hls(request, token, name):
    """/learn/hls/<token>/<file>: the master playlist and poster for LEARN_URL_SECONDS after the link was made; the
    renditions' playlists and segments that long again plus the clip's length, so that a clip started in time plays
    to the end. Files in a bucket: playlists are read here (they are small), segments and the poster are a redirect
    to the bucket's own link, signed for LEARN_URL_SECONDS."""
    if not FILE.fullmatch(name):
        raise Http404
    try:
        clip = Clip.objects.filter(pk=SIGNER.unsign_object(token), processing=Clip.Processing.READY).first()
        if clip is None:
            raise Http404
        late = name not in ("master.m3u8", "poster.jpg")
        SIGNER.unsign_object(token, max_age=settings.LEARN_URL_SECONDS * (2 if late else 1) + clip.duration * late)
    except signing.BadSignature:  # also an expired one
        return HttpResponseForbidden("This link has expired: ask the app for the clip again.")
    store, path = media.storage(), f"{clip.hls_path.rsplit('/', 1)[0]}/{name}"
    kind = TYPES[name.rsplit(".", 1)[1]]
    if not kind == TYPES["m3u8"] and not isinstance(store, FileSystemStorage):
        return HttpResponseRedirect(store.url(path, expire=settings.LEARN_URL_SECONDS))
    try:
        if kind == TYPES["m3u8"]:
            with store.open(path) as playlist:
                response = HttpResponse(playlist.read(), content_type=kind)
        else:
            response = FileResponse(store.open(path), content_type=kind)
    except FileNotFoundError:
        raise Http404 from None
    response["Cache-Control"] = f"private, max-age={settings.LEARN_URL_SECONDS}"
    return response
