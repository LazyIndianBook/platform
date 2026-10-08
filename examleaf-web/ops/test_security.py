"""Security review fixes at the site level (SECURITY_REVIEW.md): Sentry, health checks, start-up checks, headers,
sessions, supply chain."""

import importlib
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest
import sentry_sdk
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from health_check.checks import Database
from health_check.exceptions import ServiceUnavailable

from api.tests import add_paper
from content.models import Paper
from content.tests import make_paper
from examleaf import api_settings, sentry
from ops.tasks import clear_sessions

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.django_db


def test_sentry_gets_no_stack_variables_and_no_email_text(monkeypatch):  # M4
    calls = []
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    importlib.reload(importlib.import_module("examleaf.settings"))
    assert calls[0]["include_local_variables"] is False
    link = "https://examleaf.in/account/password/reset/key/7-cf3a1b-9a8f2e/"
    event = {
        "extra": {"message": {"body": f"Reset: {link}", "alternatives": [(f'<a href="{link}">', "text/html")]}},
        "logentry": {"message": f"could not send {link}"},
    }
    assert "reset/key" not in str(sentry.before_send(event, {}))


def test_health_results_are_kept_20_seconds_and_the_api_has_no_health_endpoint(client, monkeypatch):  # H1
    assert client.get(reverse("health_web"), HTTP_ACCEPT="application/json").status_code == 200

    def down(check):
        raise ServiceUnavailable("down")

    monkeypatch.setattr(Database, "run", down)
    assert client.get(reverse("health_web"), HTTP_ACCEPT="application/json").status_code == 200  # not run again
    later = time.monotonic() + 21
    monkeypatch.setattr(time, "monotonic", lambda: later)
    response = client.get(reverse("health_web"), HTTP_ACCEPT="application/json")
    assert response.status_code == 500 and response.json()["Database(alias='default')"] == "Unavailable: down"
    assert client.get("/api/v1/health/").status_code == 404


def test_expired_sessions_are_cleared_daily(settings):  # M10
    assert settings.CELERY_BEAT_SCHEDULE["clear-expired-sessions"]["task"] == "ops.tasks.clear_sessions"
    old, new = SessionStore(), SessionStore()
    old.create(), new.create()
    Session.objects.filter(session_key=old.session_key).update(expire_date=timezone.now() - timedelta(days=1))
    clear_sessions()
    assert list(Session.objects.values_list("session_key", flat=True)) == [new.session_key]


def test_the_backup_script_parses():  # M10: it encrypts the off-site copy with age when BACKUP_AGE_RECIPIENT is set
    script = ROOT / "scripts" / "backup.sh"
    assert subprocess.run(["sh", "-n", script]).returncode == 0 and "age --recipient" in script.read_text()


@pytest.mark.parametrize(
    "env, error",
    [
        ({"DEBUG": "1", "ALLOWED_HOSTS": "examleaf.in"}, "DEBUG=1 with ALLOWED_HOSTS=examleaf.in"),
        ({"DEBUG": "0", "SECRET_KEY": "dev-only-change-me"}, "SECRET_KEY is the development one"),
        ({"DEBUG": "0", "SECRET_KEY": "x" * 49}, "shorter than 50 characters"),
    ],
)
def test_development_settings_refuse_to_start_on_a_server(env, error):  # I1
    command = [sys.executable, ROOT / "manage.py", "check"]
    run = subprocess.run(command, env={**os.environ, **env}, capture_output=True, text=True)
    assert run.returncode == 1 and error in run.stderr


def test_the_image_installs_no_test_or_lint_tools():  # L10
    runtime, dev = (ROOT / "requirements.txt").read_text().lower(), (ROOT / "requirements-dev.txt").read_text()
    for tool in ["pytest", "factory_boy", "faker", "ruff", "coverage", "django-debug-toolbar"]:
        assert f"\n{tool}" not in runtime and tool in dev.lower(), tool
    assert "-r requirements.txt" in dev
    assert "permissions:\n  contents: read" in (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text()


def test_qr_images_are_for_published_papers_and_drawn_once_a_day(client, monkeypatch):  # I3
    add_paper(make_paper().book, "PHY-M02", published=False)
    drawn, draw = [], Paper.qr_image
    monkeypatch.setattr(Paper, "qr_image", lambda paper, kind: drawn.append(paper.code) or draw(paper, kind))
    assert client.get("/qr/PHY-M02.png").status_code == 404  # an unpublished code is not confirmed
    for _ in range(2):
        response = client.get("/qr/PHY-E01.png")
        assert response.status_code == 200 and "max-age=86400" in response["Cache-Control"]
    assert drawn == ["PHY-E01"]


def test_jwts_can_have_their_own_signing_key(monkeypatch):  # I5
    monkeypatch.setenv("JWT_SIGNING_KEY", "k" * 64)
    assert importlib.reload(api_settings).SIMPLE_JWT["SIGNING_KEY"] == "k" * 64
    monkeypatch.delenv("JWT_SIGNING_KEY")
    assert "SIGNING_KEY" not in importlib.reload(api_settings).SIMPLE_JWT  # then SECRET_KEY, simplejwt's default


def test_unused_browser_features_are_switched_off(client):  # I6
    for url in ["/", "/api/v1/boards/"]:
        policy = client.get(url)["Permissions-Policy"]
        assert policy == "camera=(), microphone=(), geolocation=(), payment=(self)", url
