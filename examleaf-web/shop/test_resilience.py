"""When Razorpay hangs (RESILIENCE.md): the real SDK and requests against a local server that takes the connection and
never answers, so that only the client's own timeout ends the wait. A refund another worker is making. Periodic jobs
that overlap, and the quotation PDF made by the worker."""

import threading

import pytest
import razorpay
import requests
from django.core import mail
from django.core.cache import cache
from django.db import connection, connections, transaction
from django.urls import reverse
from kombu.exceptions import OperationalError

from accounts.factories import UserFactory
from shop import payments, tasks
from shop.factories import KEY, SECRET, ProductFactory, make_order
from shop.models import Order, Payment, QuoteRequest, Refund, StockAlert
from shop.test_commerce import QUOTE

REAL_REQUEST = requests.Session.request  # before shop/conftest.py's no_network fixture refuses every call
postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs row locks (select_for_update)")


def pending_refund():
    order = make_order((ProductFactory(), 1))
    payment = order.payments.get()
    Payment.objects.filter(pk=payment.pk).update(razorpay_payment_id="pay_1", status=Payment.Status.CAPTURED)
    return Refund.objects.create(order=order, payment=payment, amount=payment.amount, reason="test")


def hanging_razorpay(monkeypatch, port):
    monkeypatch.setattr(requests.Session, "request", REAL_REQUEST)
    monkeypatch.setattr(payments, "TIMEOUT", (1, 1))  # the shape of the production pair, shorter for the test
    hung = razorpay.Client(auth=(KEY, SECRET), base_url=f"http://127.0.0.1:{port}/v1")
    monkeypatch.setattr(payments, "client", lambda: hung)


def test_a_razorpay_that_never_answers_costs_the_timeout_and_the_honest_answer(
    client, monkeypatch, half_open_port, within, db
):
    order = make_order((ProductFactory(), 1))
    Payment.objects.filter(order=order).update(razorpay_order_id=None)  # the Razorpay order is made on this call
    hanging_razorpay(monkeypatch, half_open_port)
    answers = []
    assert within(10, lambda: answers.append(client.post(f"/api/v1/orders/t/{order.token}/payment/")))
    assert answers[0].status_code == 503 and "could not be reached" in answers[0].json()["detail"]
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING  # nothing lost: the customer tries again


def test_a_refund_task_meeting_a_silent_razorpay_gives_up_its_try_and_is_retried(
    rzp, monkeypatch, half_open_port, within, db
):
    refund = pending_refund()
    hanging_razorpay(monkeypatch, half_open_port)
    assert within(10, lambda: tasks.refund_payment.run(refund.pk))  # run(): the try itself, not Celery's retries
    assert isinstance(within.error, requests.Timeout)  # retried by autoretry_for (requests.RequestException)
    refund.refresh_from_db()
    assert refund.status == Refund.Status.PENDING and refund.razorpay_refund_id is None


@postgres_only
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_refund_another_worker_is_making_is_left_to_it_at_once(rzp, within):
    refund = pending_refund()
    held, release = threading.Event(), threading.Event()

    def other_worker():  # holds the refund's row as refund_payment does during its Razorpay calls
        with transaction.atomic():
            Refund.objects.select_for_update().get(pk=refund.pk)
            held.set()
            release.wait(10)
        connections.close_all()

    holder = threading.Thread(target=other_worker)
    holder.start()
    assert held.wait(5)
    try:
        assert within(3, lambda: tasks.refund_payment.run(refund.pk)) and within.error is None
    finally:
        release.set()
        holder.join()
    assert not rzp.payment.refund.called  # nothing sent twice; the first worker finishes it
    tasks.refund_payment.run(refund.pk)  # once free, the row is the task's again
    assert Refund.objects.get(pk=refund.pk).status == Refund.Status.PROCESSED


def test_two_overlapping_stock_alert_runs_email_each_address_once(monkeypatch, db):
    product = ProductFactory(stock=3)
    for email in ("ann@example.com", "bob@example.com"):
        StockAlert.objects.create(product=product, email=email)
    unlocked = tasks.send_stock_alerts.run.__wrapped__  # the job without its lock, as while Redis is down
    sent = []

    def queue(to, subject, body):
        sent.append(to)
        if len(sent) == 1:
            unlocked()  # a second run starts while the first sends

    monkeypatch.setattr(tasks, "queue_text_email", queue)
    unlocked()
    assert sorted(sent) == ["ann@example.com", "bob@example.com"] and not StockAlert.objects.exists()


def test_a_periodic_job_that_finds_itself_running_does_nothing(commit, db):
    UserFactory(is_superuser=True, email="sales@example.com")  # the SALES role's stand-in while it has no members
    ProductFactory(stock=1)
    lock = "single-run:shop.tasks.low_stock_report"
    cache.add(lock, "running", 300)  # another run holds it
    with commit():
        tasks.low_stock_report()
    assert not mail.outbox
    cache.delete(lock)
    with commit():
        tasks.low_stock_report()
    assert [m.subject for m in mail.outbox] == ["[ExamLeaf] Books running out"] and cache.get(lock) is None


def test_the_quotation_pdf_is_made_by_the_worker_or_here_while_the_queue_is_down(client, monkeypatch, db):
    ProductFactory(slug="physics")
    quote = QuoteRequest.objects.create(**QUOTE, items=[{"product": "physics", "title": "Physics", "quantity": 40}])
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    queued = []
    monkeypatch.setattr(tasks.make_quotation, "delay", queued.append)  # a broker: the worker makes it
    action = {"action": "make_quotation", "_selected_action": [quote.pk]}
    client.post(reverse("admin:shop_quoterequest_changelist"), action)
    quote.refresh_from_db()
    assert queued == [quote.pk] and not quote.quotation  # nothing rendered in the request

    def broker_down(pk):
        raise OperationalError("Connection refused")

    monkeypatch.setattr(tasks.make_quotation, "delay", broker_down)
    client.post(reverse("admin:shop_quoterequest_changelist"), action)
    quote.refresh_from_db()
    assert quote.quotation.name.startswith("quotations/QT-")
