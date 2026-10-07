"""Health endpoint, request IDs, emails through Celery, the admin dashboard."""

import importlib
import uuid
from io import StringIO

import pytest
import redis
import sentry_sdk
from allauth.account.models import EmailAddress
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.urls import reverse
from kombu.exceptions import OperationalError

from accounts.factories import UserFactory
from accounts.models import TeacherProfile
from content.tests import make_paper
from examleaf import sentry
from examleaf.celery import app as celery_app
from ops import tasks

pytestmark = pytest.mark.django_db


def test_health_checks_database_cache_and_storage(client):
    for name in ["health", "health_web"]:  # the same three while tasks run inline (no worker to ping)
        response = client.get(reverse(name), HTTP_ACCEPT="application/json")
        assert response.status_code == 200
        assert response.json() == {
            "Database(alias='default')": "OK",
            "Cache(alias='default')": "OK",
            "Storage(alias='default')": "OK",
        }
        assert "no-cache" in response["Cache-Control"]
    with pytest.raises(SystemExit) as gate:  # the web container's readiness check before gunicorn starts
        call_command("health_check", "health_web", "--no-http", stdout=StringIO())
    assert gate.value.code == 0


def test_the_site_keeps_working_while_redis_is_down(client, settings, monkeypatch):
    def refused(connection):
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(redis.connection.Connection, "_connect", refused)  # Redis stopped: cache and broker
    settings.CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://localhost:6379/1",
            "OPTIONS": settings.REDIS_CACHE_OPTIONS,  # what settings.py gives a redis:// CACHE_URL
        }
    }
    make_paper()
    assert client.get("/api/v1/books/physics-2027/").status_code == 200  # cached page and throttles: a miss
    lookup = {"number": "EL-2026-999999", "email": "x@example.com"}
    assert client.post(reverse("shop:lookup"), lookup).status_code == 200  # its rate limit lets it through
    assert client.get(reverse("account_login")).status_code == 200
    assert client.get(reverse("health_web"), HTTP_ACCEPT="application/json").status_code == 500  # the monitor knows
    with pytest.raises(SystemExit) as gate:  # and a new web container waits for Redis
        call_command("health_check", "health_web", "--no-http", stdout=StringIO())
    assert gate.value.code == 1
    monkeypatch.setattr(celery_app.conf, "task_always_eager", False)  # a real broker, as in production
    monkeypatch.setattr(celery_app.conf, "broker_url", "redis://localhost:6379/0")
    monkeypatch.setattr(celery_app, "_pool", None)
    monkeypatch.setattr(celery_app.amqp, "_producer_pool", None)
    tasks.queue_email(EmailMessage("Your code", "ABCD-EFGH", to=["a@example.com"]))
    assert [m.subject for m in mail.outbox] == ["Your code"]  # sent from the web process instead


def test_the_request_id_from_the_proxy_comes_back_or_a_new_one_is_made(client):
    request_id = uuid.uuid4().hex
    assert client.get(reverse("terms"), HTTP_X_REQUEST_ID=request_id)["X-Request-ID"] == request_id
    assert len(client.get(reverse("terms"))["X-Request-ID"]) == 32


def test_email_is_sent_by_the_task_or_here_when_the_broker_is_down(monkeypatch):
    tasks.queue_email(EmailMessage("Hello", "Body", to=["a@example.com"]))

    def broker_down(*args, **kwargs):
        raise OperationalError("Connection refused")

    monkeypatch.setattr(tasks.send_email, "delay", broker_down)
    tasks.queue_email(EmailMessage("Again", "Body", to=["a@example.com"]))
    assert [m.subject for m in mail.outbox] == ["Hello", "Again"]


def test_admin_dashboard_counts_today_and_the_last_30_days(client):
    confirmed, _ = UserFactory(), UserFactory()
    EmailAddress.objects.create(user=confirmed, email=confirmed.email, verified=True, primary=True)
    TeacherProfile.objects.create(user=confirmed, school_name="S", district="D", subject="Physics")
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    response = client.get(reverse("admin:index"))
    rows = {label: (today, month) for label, today, month in response.context["stats"]["rows"]}
    assert rows == {"Registrations": (3, 3), "… with a confirmed email": (1, 1), "Attempts saved": (0, 0)}
    assert "1 teacher request<" in response.text and "ExamLeaf admin" in response.text


def test_upload_backup_puts_the_dump_in_the_backups_storage(settings, tmp_path, capsys):
    from django.core.management import call_command

    dump = tmp_path / "examleaf-20261008-021500.dump"
    dump.write_bytes(b"PGDMP")
    settings.STORAGES = {
        **settings.STORAGES,
        "backups": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": tmp_path / "bucket"},
        },
    }
    call_command("upload_backup", str(dump))
    assert (tmp_path / "bucket" / "database" / dump.name).read_bytes() == b"PGDMP"


def test_sentry_gets_no_secrets_and_no_personal_data(monkeypatch):
    calls = []
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    importlib.reload(importlib.import_module("examleaf.settings"))  # the settings module's own Sentry set-up
    assert calls[0]["send_default_pii"] is False and calls[0]["before_send"] is sentry.before_send
    event = {
        "event_id": "4111111111111111" + "0" * 16,
        "request": {
            "data": {"password1": "x", "new_password2": "x", "old_password": "x", "code": "ABCD-EFGH", "board": 1},
            "headers": {"X-Razorpay-Signature": "f00d", "Content-Type": "application/json"},
            "query_string": "next=/s/PHY-E01/&email=rahul@example.com",
        },
        "exception": {
            "values": [
                {
                    "value": "rahul@example.com (+91 98640 12345) paid with 4111 1111 1111 1111 for EL-2026-000123",
                    "stacktrace": {"frames": [{"vars": {"refresh": "eyJ", "params": {"razorpay_signature": "ab"}}}]},
                }
            ]
        },
        "extra": {"verification_token": "q3k9", "parent_contact": "9864012345", "card_number": "4111111111111111"},
        "breadcrumbs": {"values": [{"message": "SMS to 9864012345 failed", "data": {"cvv": "987"}}]},
    }
    scrubbed = sentry.before_send(event, {})
    text = str(scrubbed)
    for secret in ["ABCD-EFGH", "f00d", "rahul@", "98640", "9864012345", "4111 1111", "eyJ", "q3k9", "'ab'", "987"]:
        assert secret not in text, secret
    assert scrubbed["event_id"] == event["event_id"] and scrubbed["request"]["data"]["board"] == 1
    assert "EL-2026-000123" in scrubbed["exception"]["values"][0]["value"]  # an order number is not personal
