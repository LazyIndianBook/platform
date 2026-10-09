"""RESILIENCE.md's settings, as settings.py makes them: the timeouts of every client of another service, the
database's limits by role, Celery's acknowledgements and limits; and the health checks each prober gets."""

import importlib
import json
import sys
from importlib.util import find_spec

import pytest
from anymail.backends.amazon_ses import _get_anymail_boto3_params
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache.backends.base import BaseCache
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from health_check.exceptions import ServiceUnavailable
from storages.backends.s3 import S3Storage

from examleaf.health import Migrations
from examleaf.storage import PublicS3Storage

postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL's own limits")


@pytest.fixture
def reload_settings(monkeypatch):
    """The settings module run again with the environment (and program name) a test sets."""
    module = importlib.import_module("examleaf.settings")
    yield lambda: importlib.reload(module)
    monkeypatch.undo()
    importlib.reload(module)


def run_as(monkeypatch, program):
    monkeypatch.setattr(sys, "argv", [f"/usr/local/bin/{program}", "examleaf.wsgi"])


def test_the_buckets_give_up_within_seconds_and_retry_a_bounded_number_of_times(monkeypatch, reload_settings, settings):
    for name, value in {
        "MEDIA_BUCKET": "examleaf-private",
        "PUBLIC_MEDIA_BUCKET": "examleaf-public",
        "PUBLIC_MEDIA_DOMAIN": "media.examleaf.in",
        "BACKUP_BUCKET": "examleaf-backups",
        "S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        "S3_ACCESS_KEY_ID": "key",
        "S3_SECRET_ACCESS_KEY": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    made = reload_settings()
    settings.STORAGES = made.STORAGES  # PublicS3Storage reads its options there
    storages = [S3Storage(**made.STORAGES[name]["OPTIONS"]) for name in ("default", "backups")]
    for storage in [*storages, PublicS3Storage()]:
        config = storage.connection.meta.client.meta.config  # boto3's client, as each request uses it
        assert (config.connect_timeout, config.read_timeout) == (3, 20)
        assert config.retries == {"mode": "standard", "total_max_attempts": 3}  # the first try and two more
    assert PublicS3Storage().deconstruct() == ("examleaf.storage.PublicS3Storage", (), {})  # no options to Celery


def test_email_through_ses_or_an_http_provider_gives_up_within_seconds(settings):
    _, client_params = _get_anymail_boto3_params()  # what anymail's SES backend (and its webhook) give boto3
    config = client_params["config"]
    assert (config.connect_timeout, config.read_timeout, config.retries["mode"]) == (3, 10, "standard")
    assert settings.ANYMAIL["REQUESTS_TIMEOUT"] == (3, 10)


@pytest.mark.parametrize(
    "program, options",
    [
        ("gunicorn", "-c statement_timeout=15000 -c idle_in_transaction_session_timeout=60000"),
        ("celery", "-c statement_timeout=600000 -c idle_in_transaction_session_timeout=600000"),
        ("manage.py", None),  # migrations, imports and reports: no limit
    ],
)
def test_statements_have_a_time_limit_by_role(program, options, monkeypatch, reload_settings):
    monkeypatch.setenv("DATABASE_URL", "postgres://examleaf:secret@db:5432/examleaf?sslmode=require")
    run_as(monkeypatch, program)
    database = reload_settings().DATABASES["default"]
    assert database["OPTIONS"].get("options") == options
    assert database["OPTIONS"]["connect_timeout"] == 5 and database["OPTIONS"]["sslmode"] == "require"
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT", "0")  # an operator's override
    assert "statement_timeout" not in reload_settings().DATABASES["default"]["OPTIONS"].get("options", "")


@postgres_only
@pytest.mark.django_db
def test_postgresql_ends_a_statement_over_the_limit(monkeypatch, reload_settings):
    from django.db.backends.postgresql.base import DatabaseWrapper
    from django.db.utils import OperationalError

    monkeypatch.setenv("DB_STATEMENT_TIMEOUT", "1")
    run_as(monkeypatch, "gunicorn")
    options = reload_settings().DATABASES["default"]["OPTIONS"]
    web = DatabaseWrapper({**connection.settings_dict, "OPTIONS": options})  # a connection as the web makes one
    try:
        with web.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone() == ("1s",)
            with pytest.raises(OperationalError, match="statement timeout"):
                cursor.execute("SELECT pg_sleep(3)")
    finally:
        web.close()


def test_firebase_calls_wait_twenty_seconds_not_two_minutes(settings):
    import firebase_admin

    from learn import tasks

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    settings.FCM_SERVICE_ACCOUNT_JSON = json.dumps(
        {
            "type": "service_account",
            "project_id": "examleaf-test",
            "private_key_id": "1",
            "private_key": pem.decode(),
            "client_email": "fcm@examleaf-test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    app = tasks.firebase()
    try:
        assert app.options.get("httpTimeout") == tasks.FCM_TIMEOUT == 20
    finally:
        firebase_admin.delete_app(app)


def test_tasks_are_acknowledged_once_run_and_none_outlives_the_brokers_visibility_timeout():
    from django.apps import apps

    from examleaf.celery import app
    from integrations.models import COOL_OFF

    for config in apps.get_app_configs():  # every app's tasks.py, as the worker's autodiscovery imports them
        if find_spec(f"{config.name}.tasks"):
            importlib.import_module(f"{config.name}.tasks")
    conf = app.conf
    assert conf.task_acks_late and not conf.task_reject_on_worker_lost and conf.worker_prefetch_multiplier == 1
    assert conf.broker_connection_retry_on_startup and conf.result_expires
    assert conf.worker_max_tasks_per_child == 200 and conf.worker_max_memory_per_child == 300 * 1024
    visibility = conf.broker_transport_options["visibility_timeout"]
    ours = [task for name, task in app.tasks.items() if not name.startswith("celery.")]
    assert len(ours) > 30
    for task in ours:  # a task still running (or waiting for its retry) past it would be given to a second worker
        soft, hard = task.soft_time_limit or conf.task_soft_time_limit, task.time_limit or conf.task_time_limit
        assert soft < hard < visibility, task.name
        backoff = getattr(task, "retry_backoff", False)
        countdown = getattr(task, "retry_backoff_max", 600) if backoff else task.default_retry_delay
        assert countdown < visibility, task.name
    assert COOL_OFF.total_seconds() + 60 < visibility  # IntegrationTask's wait while a circuit is open
    assert app.tasks["learn.tasks.send_reminders"].acks_late is False  # run twice, it would remind everybody twice


class Untouchable(BaseCache):
    """A cache any use of which fails the test (BaseCache's methods raise NotImplementedError)."""

    def __init__(self, location, params):
        super().__init__(params)


def test_liveness_answers_without_the_database_or_redis(client, settings):  # no django_db: a query would raise
    settings.CACHES = {"default": {"BACKEND": "examleaf.test_resilience.Untouchable"}}
    response = client.get("/health/live/", HTTP_X_FORWARDED_PROTO="https")
    assert response.status_code == 200 and response.content == b"OK"


@pytest.mark.django_db
def test_readiness_fails_while_a_migration_of_this_code_is_waiting():
    Migrations().run()  # all applied: ready
    newest = MigrationRecorder.Migration.objects.filter(app="ops").latest("id")
    newest.delete()  # as a pod of a new release finds the database before its migrate has run
    with pytest.raises(ServiceUnavailable, match="migrations not applied"):
        Migrations().run()
