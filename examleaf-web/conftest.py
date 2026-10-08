import socket

import pytest
from django.core.cache import cache
from pwned_passwords_django import api as pwned_passwords

from examleaf.celery import app as celery_app
from examleaf.views import HealthView


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()  # allauth's rate limits and axes live in the cache
    HealthView.results_by_path.clear()  # the health checks' results, kept 20 s in the process


@pytest.fixture(autouse=True)
def no_pwned_passwords_requests(monkeypatch):
    """No password leaves for haveibeenpwned.com from the tests: none is found in a breach, unless a test says so."""
    monkeypatch.setattr(pwned_passwords.default_client, "check_password", lambda password: 0)


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path  # the health check's storage probe and any upload write here


@pytest.fixture
def broker(settings, monkeypatch):
    """Celery as in production, a real queue instead of inline tasks: call it with the broker's address. Celery reads
    its CELERY_* settings from Django's, so those are what is changed (not the app's conf, which ignores it)."""

    def use(url):
        settings.CELERY_TASK_ALWAYS_EAGER = False
        settings.CELERY_BROKER_URL = url
        monkeypatch.setattr(celery_app, "_pool", None)  # connections made for the old address
        monkeypatch.setattr(celery_app.amqp, "_producer_pool", None)

    return use


@pytest.fixture
def closed_port():
    """A local port that nothing listens on (connections are refused at once)."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
