import signal
import socket
import threading

import pytest
from django.core.cache import cache
from django.db.backends.signals import connection_created
from pwned_passwords_django import api as pwned_passwords

from examleaf.cache import SoftRedisCache
from examleaf.celery import app as celery_app
from examleaf.views import HealthView


def audit_maintenance(sender, connection, **kwargs):
    """PostgreSQL: the audit log refuses DELETE and TRUNCATE (staff migration 0002) unless this is on, and the tests
    that use threads end by truncating every table. staff/tests/test_audit.py switches it off to test the trigger."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET examleaf.audit_maintenance = 'on'")


connection_created.connect(audit_maintenance)


@pytest.hookimpl(trylast=True)  # after pytest-django's order: the transactional tests last
def pytest_collection_modifyitems(items):
    """The transactional tests that restore the database from its snapshot (serialized_rollback) run before the other
    transactional ones. Those end with a flush whose post_migrate makes the content types, permissions and role groups
    again under new ids (PostgreSQL keeps its sequences), and the snapshot's rows then collide with them."""

    def serialized(item):
        marker = item.get_closest_marker("django_db")
        return bool(marker and marker.kwargs.get("serialized_rollback"))

    def transactional(item):
        marker = item.get_closest_marker("django_db")
        fixtures = getattr(item, "fixturenames", ())
        return bool(marker and marker.kwargs.get("transaction")) or "transactional_db" in fixtures

    starts = [index for index, item in enumerate(items) if transactional(item)]
    if starts:
        items[starts[0] :] = sorted(items[starts[0] :], key=lambda item: not serialized(item))  # (a stable sort)


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()  # allauth's rate limits and axes live in the cache
    HealthView.results_by_path.clear()  # the health checks' results, kept 20 s in the process
    SoftRedisCache.down_until = 0.0  # a test's Redis outage is not the next one's


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


@pytest.fixture
def half_open_port():
    """A local port whose server takes every connection and never says a word (a dependency that hangs): only a
    client's own timeout gets it out."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(50)
    held = []

    def accept():
        try:
            while True:
                held.append(server.accept()[0])
        except OSError:  # closed at the end of the test
            pass

    threading.Thread(target=accept, daemon=True).start()
    yield server.getsockname()[1]
    server.close()
    for connection in held:
        connection.close()


class Hung(BaseException):  # not an Exception: no `except Exception` in the code under test can swallow it
    pass


@pytest.fixture
def within():
    """within(seconds, call): whether `call` returned or raised within `seconds`; a hang fails the test instead of
    hanging the run (a timer signal interrupts it, in this thread: the test's database connection stays usable).
    The call's exception, if any, is in within.error."""

    def alarm(signum, frame):
        raise Hung

    def run(seconds, call):
        run.error = None
        previous = signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            call()
        except Hung:
            return False
        except Exception as error:  # kept for the test to look at
            run.error = error
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        return True

    return run
