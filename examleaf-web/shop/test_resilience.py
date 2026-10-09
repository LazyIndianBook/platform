"""When Razorpay hangs (RESILIENCE.md): the real SDK and requests against a local server that takes the connection and
never answers, so that only the client's own timeout ends the wait. And a refund another worker is making."""

import threading

import pytest
import razorpay
import requests
from django.db import connection, connections, transaction

from shop import payments, tasks
from shop.factories import KEY, SECRET, ProductFactory, make_order
from shop.models import Order, Payment, Refund

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
