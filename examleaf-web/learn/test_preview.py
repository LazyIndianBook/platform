"""The staff player: who opens it, what it shows (a ready clip's signed links, a failed clip's ffmpeg messages), the
self-hosted hls.js and the CSP that lets it play."""

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.factories import UserFactory

from .models import Clip
from .tests import make_course

pytestmark = pytest.mark.django_db


@pytest.fixture
def clip():
    make_course(chapters=1, clips=1)
    return Clip.objects.get()


def test_editors_see_the_clip_as_the_app_plays_it(client, clip):
    editor = UserFactory(is_staff=True)
    editor.user_permissions.add(Permission.objects.get(codename="view_clip"))
    client.force_login(editor)
    page = client.get(reverse("learn:preview", args=[clip.pk]))
    html = page.content.decode()
    assert 'data-src="/learn/hls/' in html and "/master.m3u8" in html and "learn/hls.min.js" in html
    policy = page.headers.get("Content-Security-Policy") or page.headers["Content-Security-Policy-Report-Only"]
    assert "media-src 'self' blob:" in policy  # hls.js plays from blob: URLs
    assert (settings.BASE_DIR / "static/learn/hls.min.js").exists()
    assert "Apache" in (settings.BASE_DIR / "static/learn/hls.js-LICENSE.txt").read_text()

    Clip.objects.update(processing="failed", processing_error="moov atom not found")
    assert "moov atom not found" in client.get(reverse("learn:preview", args=[clip.pk])).content.decode()


def test_only_staff_who_may_view_clips(client, clip):
    preview = reverse("learn:preview", args=[clip.pk])
    client.force_login(UserFactory())
    assert client.get(preview).status_code == 302  # to the admin's log-in
    client.force_login(UserFactory(is_staff=True))
    assert client.get(preview).status_code == 403


def test_the_admin_links_to_it(client, clip):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:learn_clip_change", args=[clip.pk])).content.decode()
    assert reverse("learn:preview", args=[clip.pk]) in page
