"""Health endpoint, request IDs, emails through Celery, the admin dashboard."""

import uuid

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.core.mail import EmailMessage
from django.urls import reverse
from kombu.exceptions import OperationalError

from accounts.factories import UserFactory
from accounts.models import TeacherProfile
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
