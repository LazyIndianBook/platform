"""A clip's HLS files behind a signed link (the app's player and the staff player), the staff preview page, and the
course's page on the website (/revision/)."""

import re
from datetime import timedelta

from allauth.account.utils import has_verified_email
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from . import media, services
from .models import Chapter, Clip, Revision
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


class CodeForm(forms.Form):
    code = forms.CharField(
        label="Book code",
        max_length=40,
        help_text="Printed in your ExamLeaf book, like 7KQM-3XPA-9TRW.",
        error_messages={"required": "Type the code printed in your book."},
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters", "spellcheck": "false"}),
    )


def code_try_allowed(request):
    """One more book code tried, within the app's limits (api.learn.RedeemView: learn_redeem an hour per account and
    learn_redeem_address per client address), counted together with the app's tries."""
    from rest_framework.throttling import ScopedRateThrottle

    from api.learn import PerAddress, RedeemView  # (api.learn imports this module)

    view = RedeemView()
    return all(throttle.allow_request(request, view) for throttle in (ScopedRateThrottle(), PerAddress()))


def free_clips():
    """{chapter id: its free clips that are ready to play}: the first clip of each published revision and any marked
    as a free preview, while LEARN_FREE_PREVIEW is on (services.is_free_clip, as the app shows them)."""
    free, firsts = {}, {}
    clips = Clip.objects.filter(revision__status=Revision.Status.PUBLISHED).select_related("revision")
    for clip in clips.order_by("revision", "order", "pk"):
        first = firsts.setdefault(clip.revision_id, clip.pk)
        if clip.processing == Clip.Processing.READY and services.is_free_clip(clip, first=first):
            free.setdefault(clip.revision.chapter_id, []).append(clip)
    return free


def redeem(request, form):
    """The code of the form, with the app's rules (api.learn.STUDENT): a confirmed address, a parent's consent where
    it is needed. Returns the success message, or None with the reason on the form."""
    user = request.user
    try:
        if not has_verified_email(user):
            raise services.CodeError("Confirm your email address first, with the code we emailed you.")
        if user.consent_pending:
            raise services.CodeError("Your parent or guardian has not confirmed your account yet: see My account.")
        entitlement = services.redeem(user, form.cleaned_data["code"])
    except services.CodeError as error:
        form.add_error("code", str(error))
        return None
    if entitlement is None:  # the student's own code, whose entitlement staff removed
        return "You have used this code already."
    what = entitlement.subject.name if entitlement.subject else "Every subject"
    return f"Code accepted. {what} is open in the app until {date_format(entitlement.valid_until, 'j F Y')}."


@never_cache  # it shows the student's own course and the form's CSRF token
def revision(request):
    """/revision/: the revision course on the website (the course itself is in the app): what it is, each subject's
    chapters with the Board's marks, the free clips, how to get the app; for a signed-in student, what is open and the
    book code form."""
    user, form = request.user, None
    if not user.is_authenticated and request.method == "POST":
        return redirect_to_login(reverse("revision"))
    if user.is_authenticated:
        form = CodeForm(request.POST or None)
        if request.method == "POST" and not code_try_allowed(request):
            return render(request, "429.html", status=429)
        if request.method == "POST" and form.is_valid() and (message := redeem(request, form)):
            messages.success(request, message)
            return redirect("revision")
    free, subjects = free_clips(), {}
    for chapter in Chapter.objects.select_related("subject").order_by("subject_id", "number"):
        chapter.free_clips = free.get(chapter.pk, [])
        subjects.setdefault(chapter.subject, []).append(chapter)
    context = {
        "subjects": subjects.items(),
        "has_free_clips": bool(free),
        "free_preview": settings.LEARN_FREE_PREVIEW,
        "access_days": settings.LEARN_ACCESS_DAYS,
        "form": form,
        "entitlements": user.entitlements.select_related("subject") if user.is_authenticated else None,
        "today": timezone.localdate(),
    }
    return render(request, "learn/revision.html", context)
