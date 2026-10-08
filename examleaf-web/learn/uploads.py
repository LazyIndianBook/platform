"""Clip videos go straight from the editor's browser to the private bucket (H1). The clip forms of the admin ask
upload_url (staff who may add or change clips; POST) for a PUT link to learn/sources/<uuid>.<ext>, signed for
15 minutes with the file's size and content type; static/learn/upload.js sends the file there with its progress and
puts the signed name it was given into the form (ClipForm.source_key), which is all the form then carries: gunicorn
never reads a video. Without a bucket (development, tests) the video comes with the form, as any upload."""

import uuid
from pathlib import Path
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.urls import reverse

from .models import VIDEO_TYPES, Clip

SALT, LINK_SECONDS, KEY_SECONDS = "learn.upload", 15 * 60, 24 * 3600  # the link; the signed name in the form
CONTENT_TYPES = {
    "mp4": "video/mp4",
    "m4v": "video/x-m4v",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
}


def private():
    """Where clip videos are kept (the private storage: the bucket of MEDIA_BUCKET, or MEDIA_ROOT)."""
    return Clip._meta.get_field("source").storage


def direct():
    """Whether videos go straight to storage: the private storage is a bucket."""
    return not isinstance(private(), FileSystemStorage)


def upload_url(request):
    """POST `name` (the file's own name, for its extension) and `size` (bytes): the PUT `url`, the `headers` to send
    with it, and the signed `key` for the form. 400 with an `error` for anything but a video within LEARN_MAX_UPLOAD_MB.
    ClipAdmin.get_urls serves it to staff who may add or change clips."""
    if not direct():
        raise Http404("Without a bucket the video comes with the form.")
    ext, size = Path(request.POST.get("name", "")).suffix.lower().lstrip("."), request.POST.get("size", "")
    if ext not in VIDEO_TYPES:
        return JsonResponse({"error": f"Choose a video: {', '.join(VIDEO_TYPES)}."}, status=400)
    if not (size.isdigit() and 0 < int(size) <= settings.LEARN_MAX_UPLOAD_MB * 1024 * 1024):
        return JsonResponse({"error": f"At most {settings.LEARN_MAX_UPLOAD_MB} MB (LEARN_MAX_UPLOAD_MB)."}, status=400)
    store, key = private(), f"learn/sources/{uuid.uuid4().hex}.{ext}"
    # Size and type are signed with the link (signed headers): the bucket refuses any other file.
    params = {"Bucket": store.bucket_name, "Key": key, "ContentType": CONTENT_TYPES[ext], "ContentLength": int(size)}
    url = store.connection.meta.client.generate_presigned_url(
        "put_object", Params=params, ExpiresIn=LINK_SECONDS, HttpMethod="PUT"
    )
    headers = {"Content-Type": CONTENT_TYPES[ext]}
    return JsonResponse({"url": url, "headers": headers, "key": signing.dumps(key, salt=SALT)})


class ClipForm(forms.ModelForm):
    """The clip forms of the admin (ClipAdmin and the revision's ClipInline). With a bucket, upload.js puts the signed
    name of the video it sent into source_key and empties the file field before the form goes."""

    source_key = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Clip
        fields = ["revision", "order", "title", "kind", "source", "notes", "is_free_preview", "questions", "tags"]

    class Media:
        js = ["learn/upload.js"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if direct():
            self.fields["source_key"].widget.attrs["data-upload-url"] = reverse("admin:learn_clip_upload_url")

    def clean(self):
        data = super().clean()
        if token := data.get("source_key"):
            try:
                key = signing.loads(token, salt=SALT, max_age=KEY_SECONDS)
            except signing.BadSignature:
                raise ValidationError({"source": "This upload has expired: choose the video again."}) from None
            if not private().exists(key):
                raise ValidationError({"source": "The video did not arrive in storage: choose it again."})
            data["source"] = key  # then checked by the model's validators (type, LEARN_MAX_UPLOAD_MB) as any upload
        return data


def video_changed(form):
    """Whether the form brought a new video, through the form or straight to the bucket."""
    return bool({"source", "source_key"} & set(form.changed_data)) and bool(form.instance.source)


def allow_storage(response, store, *directives):
    """The storage's own origin, as its links name it, added to these CSP directives of this response only (I3): the
    clip pages send videos to the bucket, the staff player fetches from it. Nothing for files on this server."""
    if isinstance(store, FileSystemStorage):
        return response
    link = urlsplit(store.url("learn/csp"))
    origin = f"{link.scheme}://{link.netloc}"
    for attr, setting in (("_csp_config", "SECURE_CSP"), ("_csp_ro_config", "SECURE_CSP_REPORT_ONLY")):
        if policy := getattr(response, attr, None) or getattr(settings, setting, None):
            fallback = policy.get("default-src", [])
            setattr(response, attr, {**policy, **{name: [*policy.get(name, fallback), origin] for name in directives}})
    return response


class LargeBodyGuard:
    """Caddy lets 500 MB through to the clip and revision admin pages (the development fallback, without a bucket):
    only signed-in staff may send a body larger than Django's own limit there. Anyone else's is refused before it is
    read; the CSRF check would read a multipart body (its files to /tmp) before the admin asks who is there (H1).
    After AuthenticationMiddleware (settings.MIDDLEWARE)."""

    PATHS = ("/admin/learn/clip/", "/admin/learn/revision/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path.startswith(self.PATHS):
            size = request.META.get("CONTENT_LENGTH") or ""
            large = not size.isdigit() or int(size) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE
            if large and not (request.user.is_authenticated and request.user.is_staff):
                return HttpResponseForbidden("Log in first.")
        return self.get_response(request)
