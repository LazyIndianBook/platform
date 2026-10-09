"""When Razorpay hangs (RESILIENCE.md): the real SDK and requests against a local server that takes the connection and
never answers, so that only the client's own timeout ends the wait. A refund another worker is making. Periodic jobs
that overlap, the quotation PDF made by the worker, and the same checkout sent twice at once."""

import threading

import pytest
import razorpay
import requests
from django.core import mail
from django.core.cache import cache
from django.db import connection, connections, transaction
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from examleaf import bulkhead
from shop import payments, tasks
from shop.factories import ADDRESS, KEY, SECRET, ProductFactory, make_cart, make_order, verified_user
from shop.models import Order, Payment, Product, QuoteRequest, Refund, StockAlert
from shop.test_commerce import QUOTE
from shop.test_robustness import at_once

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


def test_a_razorpay_call_over_the_providers_half_of_the_threads_answers_at_once(client, within, db):
    order = make_order((ProductFactory(), 1))
    Payment.objects.filter(order=order).update(razorpay_order_id=None)
    taken = [bulkhead.SLOTS.acquire(blocking=False) for _ in range(8)]  # four calls already waiting on providers
    try:
        assert sum(taken) == 4  # half of gunicorn's eight threads
        answers = []
        assert within(2, lambda: answers.append(client.post(f"/api/v1/orders/t/{order.token}/payment/")))
        assert answers[0].status_code == 503 and "could not be reached" in answers[0].json()["detail"]
    finally:
        for got in taken:
            if got:
                bulkhead.SLOTS.release()
    assert bulkhead.SLOTS.acquire(blocking=False)  # every slot given back
    bulkhead.SLOTS.release()


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
    fields = {**QUOTE, "gstin": "", "delivery_pin": "781001", "phone": "+919864012345"}  # as the form cleans them
    quote = QuoteRequest.objects.create(**fields, items=[{"product": "physics", "title": "Physics", "quantity": 40}])
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


def cod_customer(settings):
    """An account with a confirmed address, one book in its cart and a saved address: (its API client's maker, the
    address's id, the book)."""
    settings.SHOP_COD_ENABLED = True
    user, book = verified_user("rahul@example.com"), ProductFactory(stock=5)
    make_cart((book, 1), user=user)

    def api():
        signed_in = APIClient()
        signed_in.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return signed_in

    address = api().post("/api/v1/addresses/", {**ADDRESS, "phone": "98640 12345"}).json()["id"]
    return api, address, book


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")  # the short development SECRET_KEY
def test_a_cash_on_delivery_checkout_sent_again_places_no_second_order(settings, db):
    api, address, book = cod_customer(settings)
    order = {"address": address, "payment_method": "cod"}
    first, again = api().post("/api/v1/orders/", order), api().post("/api/v1/orders/", order)
    assert first.status_code == 201 and again.json() == {"non_field_errors": ["Your cart is empty."]}
    assert Order.objects.exclude(placed_at=None).count() == 1 and Product.objects.get(pk=book.pk).stock == 4


@postgres_only
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_the_same_cash_on_delivery_checkout_sent_twice_at_once_places_one_order(settings):
    api, address, book = cod_customer(settings)
    order = {"address": address, "payment_method": "cod"}
    answers = at_once(*[lambda: api().post("/api/v1/orders/", order).status_code] * 2)
    assert sorted(answers) == [201, 400]  # the second waited for the first, then found the cart emptied
    assert Order.objects.exclude(placed_at=None).count() == 1 and Product.objects.get(pk=book.pk).stock == 4
