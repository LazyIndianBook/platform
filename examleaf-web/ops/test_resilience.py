"""Redis half-open (takes connections, never answers), the email provider failing on top of it, the health ping."""

import socket
import threading

import pytest
from django.core import mail
from django.core.mail import EmailMessage

from examleaf.urls import WEB_CHECKS, health_checks
from ops import tasks

pytestmark = pytest.mark.django_db


@pytest.fixture
def half_open_broker(broker):
    """A server that takes connections and says nothing, set up as the Celery broker (real, not inline)."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(10)
    held = []

    def accept():
        try:
            while True:
                held.append(server.accept()[0])
        except OSError:  # closed at the end of the test
            pass

    threading.Thread(target=accept, daemon=True).start()
    broker(f"redis://127.0.0.1:{server.getsockname()[1]}/0")
    yield
    server.close()
    for connection in held:
        connection.close()


def queue_within(seconds, message):
    """queue_email in a thread: a hang fails the test after `seconds` instead of hanging the whole run."""
    done = threading.Thread(target=tasks.queue_email, args=(message,), daemon=True)
    done.start()
    done.join(seconds)
    return not done.is_alive()


def test_a_broker_that_never_answers_costs_seconds_not_the_request(half_open_broker):
    assert queue_within(30, EmailMessage("Your code", "ABCD-EFGH", to=["a@example.com"]))
    assert [m.subject for m in mail.outbox] == ["Your code"]  # sent from the web process instead


def test_the_provider_failing_too_does_not_fail_the_page(half_open_broker, monkeypatch, caplog):
    def provider_down(self, *args, **kwargs):
        raise ConnectionError("the email provider is down")

    monkeypatch.setattr(EmailMessage, "send", provider_down)
    assert queue_within(30, EmailMessage("Your code", "ABCD-EFGH", to=["a@example.com"]))  # no exception reaches it
    assert "could not be sent here either" in caplog.text and not mail.outbox


def test_the_health_ping_returns_with_the_first_worker_instead_of_waiting_out_its_timeout():
    assert health_checks(eager=True) == WEB_CHECKS  # inline tasks: no worker to ask
    [*web, (ping, options)] = health_checks(eager=False)
    assert web == WEB_CHECKS and ping == "health_check.contrib.celery.Ping" and options["limit"] == 1
