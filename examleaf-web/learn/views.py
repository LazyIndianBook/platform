"""A clip's HLS files behind a signed link (the app's player and the staff player), and the staff preview page."""

import re
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe

from . import media
from .models import Clip
from .uploads import allow_storage

SIGNER = signing.TimestampSigner(salt="learn.hls")
NAMES = "|".join(name for name, *_ in media.RENDITIONS)
FILE = re.compile(rf"master\.m3u8|poster\.jpg|(?:{NAMES})/(?:index\.m3u8|seg_\d{{3,5}}\.ts)")
TYPES = {"m3u8": "application/vnd.apple.mpegurl", "ts": "video/mp2t", "jpg": "image/jpeg"}


def playback(clip, site=None):
    """The links of a processed clip's master playlist and poster, and when they stop working (None: never, for
    public files with LEARN_PUBLIC_VIDEO=1 and a bucket). site="": links on this site's own origin."""
    store = media.storage()
    if settings.LEARN_PUBLIC_VIDEO and not isinstance(store, FileSystemStorage):
        return {"hls_url": store.url(clip.hls_path), "poster_url": store.url(clip.poster), "expires_at": None}
    token, site = SIGNER.sign_object(clip.pk), settings.SITE_URL if site is None else site
    return {
        "hls_url": site + reverse("learn:hls", args=[token, "master.m3u8"]),
        "poster_url": site + reverse("learn:hls", args=[token, "poster.jpg"]),
        "expires_at": timezone.now() + timedelta(seconds=settings.LEARN_URL_SECONDS),
    }


@require_safe  # GET and HEAD
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
    if kind != TYPES["m3u8"] and not isinstance(store, FileSystemStorage):
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


@staff_member_required
def preview(request, pk):
    """/learn/preview/<clip>/: the clip as the app plays it (hls.js, self-hosted), for staff who may view clips
    (CONTENT_EDITOR, ADMIN), whatever the revision's status. Linked from the clip in the admin."""
    if not request.user.has_perm("learn.view_clip"):
        raise PermissionDenied
    clip = get_object_or_404(Clip.objects.select_related("revision__chapter"), pk=pk)
    ready = clip.processing == Clip.Processing.READY
    context = {**admin.site.each_context(request), "clip": clip, "title": f"Preview: {clip}"}
    page = render(request, "learn/preview.html", {**context, "playback": playback(clip, site="") if ready else None})
    # hls.js fetches the segments, and the poster loads, from the bucket the signed links redirect to (I3)
    return allow_storage(page, media.storage(), "connect-src", "media-src", "img-src")
