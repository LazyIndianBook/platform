"""Clip videos straight to the bucket (H1, learn/uploads.py): the signed PUT link, the form that carries only the
signed name of what was sent, the bucket's origin in the clip pages' CSP, and the guard on large bodies."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import Group
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from storages.backends.s3 import S3Storage

from accounts import roles
from accounts.factories import UserFactory

from . import uploads
from .models import Clip
from .tests import make_course

pytestmark = pytest.mark.django_db
UPLOAD = "/admin/learn/clip/upload-url/"


@pytest.fixture
def editor(client):
    user = UserFactory(is_staff=True)
    user.groups.set([Group.objects.get(name=roles.CONTENT_EDITOR)])
    client.force_login(user)
    return user


@pytest.fixture
def bucket(monkeypatch):
    """A bucket on AWS (links are signed here, nothing is sent): videos go straight to it."""
    store = S3Storage(
        bucket_name="examleaf-private", access_key="AKIATEST", secret_key="test", region_name="ap-south-1"
    )
    monkeypatch.setattr(uploads, "private", lambda: store)
    return store


def test_editors_get_a_put_link_signed_with_the_size_and_type(client, editor, bucket):
    answer = client.post(UPLOAD, {"name": "Lecture 3.MOV", "size": "1048576"}).json()
    link = urlsplit(answer["url"])
    assert link.netloc == "examleaf-private.s3.amazonaws.com" and link.path.startswith("/learn/sources/")
    assert link.path.endswith(".mov") and answer["headers"] == {"Content-Type": "video/quicktime"}
    query = parse_qs(link.query)
    assert query["X-Amz-SignedHeaders"] == ["content-length;content-type;host"] and query["X-Amz-Expires"] == ["900"]
    assert signing.loads(answer["key"], salt=uploads.SALT) == link.path.lstrip("/")
    assert client.post(UPLOAD, {"name": "notes.pdf", "size": "10"}).json()["error"].startswith("Choose a video")
    too_big = str(500 * 1024 * 1024 + 1)
    assert client.post(UPLOAD, {"name": "a.mp4", "size": too_big}).status_code == 400
    assert client.post(UPLOAD, {"name": "a.mp4", "size": "-5"}).status_code == 400
    assert client.get(UPLOAD).status_code == 405


def test_only_staff_who_may_change_clips_get_links_and_none_without_a_bucket(client, bucket):
    client.force_login(UserFactory())
    assert client.post(UPLOAD, {"name": "a.mp4", "size": "10"}).status_code == 302  # the admin's log-in
    sales = UserFactory(is_staff=True)
    sales.groups.set([Group.objects.get(name=roles.SALES)])
    client.force_login(sales)
    assert client.post(UPLOAD, {"name": "a.mp4", "size": "10"}).status_code == 403


def test_without_a_bucket_the_endpoint_is_not_there(client, editor):
    assert client.post(UPLOAD, {"name": "a.mp4", "size": "10"}).status_code == 404


def test_the_form_carries_the_signed_name_and_the_clip_is_processed(client, editor, monkeypatch):
    make_course(chapters=1, clips=1)
    clip = Clip.objects.get()
    queued = []
    monkeypatch.setattr("learn.tasks.queue_processing", queued.append)
    key = "learn/sources/" + "a" * 32 + ".mp4"
    default_storage.save(key, ContentFile(b"video"))  # what the browser sent to the bucket
    change = reverse("admin:learn_clip_change", args=[clip.pk])
    fields = {"revision": clip.revision_id, "order": 1, "title": "Ohm's law", "kind": "concept", "tags": ""}
    page = client.post(change, {**fields, "source_key": "learn/sources/forged.mp4"})
    assert "This upload has expired" in page.content.decode() and not queued  # not signed by us
    missing = signing.dumps("learn/sources/" + "b" * 32 + ".mp4", salt=uploads.SALT)
    assert "did not arrive" in client.post(change, {**fields, "source_key": missing}).content.decode()
    client.post(change, {**fields, "source_key": signing.dumps(key, salt=uploads.SALT)})
    clip.refresh_from_db()
    assert clip.source.name == key and [c.pk for c in queued] == [clip.pk]


def csp(response):
    policy = response.headers.get("Content-Security-Policy") or response.headers["Content-Security-Policy-Report-Only"]
    return dict(part.strip().split(" ", 1) for part in policy.split(";"))


def test_the_clip_pages_and_the_player_allow_the_buckets_own_origin_only(client, editor, bucket, monkeypatch):
    make_course(chapters=1, clips=1)
    clip = Clip.objects.get()
    monkeypatch.setattr(uploads, "direct", lambda: True)
    page = client.get(reverse("admin:learn_clip_change", args=[clip.pk]))
    assert csp(page)["connect-src"] == "'self' https://examleaf-private.s3.amazonaws.com"
    assert f'data-upload-url="{UPLOAD}"' in page.content.decode() and "learn/upload.js" in page.content.decode()
    assert "connect-src" not in csp(client.get("/")) and "amazonaws" not in csp(client.get("/"))["media-src"]
    monkeypatch.setattr("learn.views.media.storage", lambda: bucket)
    policy = csp(client.get(reverse("learn:preview", args=[clip.pk])))
    assert policy["media-src"] == "'self' blob: https://examleaf-private.s3.amazonaws.com"
    assert policy["img-src"].endswith(" https://examleaf-private.s3.amazonaws.com")
    assert policy["connect-src"] == "'self' https://examleaf-private.s3.amazonaws.com"


def test_only_signed_in_staff_may_send_a_large_body_to_the_clip_pages(client, editor):
    def video():
        return {"title": "x", "source": SimpleUploadedFile("a.mp4", b"0" * (1024 * 1024 + 10), "video/mp4")}

    anonymous = client.__class__()
    assert anonymous.post("/admin/learn/clip/add/", video()).status_code == 403  # refused before it is read
    assert anonymous.post("/admin/learn/revision/1/change/", video()).status_code == 403
    assert anonymous.post("/admin/learn/clip/add/", {"title": "small"}).status_code == 302  # the log-in, as before
    assert client.post("/admin/learn/clip/add/", video()).status_code == 200  # the form, with its errors
