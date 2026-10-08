"""Razorpay: the return from Checkout (signature), the webhooks (signature, duplicates, order of arrival), the
automatic refunds, and an unreachable Razorpay. The SDK's network calls are mocked (conftest.rzp)."""

import time

import pytest
import requests
from django.core import mail
from django.urls import reverse

from shop import payments
from shop.factories import SECRET, ProductFactory, captured, make_order, post_webhook, sign
from shop.models import Order, Payment, Refund, WebhookEvent
from shop.services import cancel_order
from shop.views import ORDERS_KEY

pytestmark = pytest.mark.django_db


def as_customer(client, order):
    session = client.session
    session[ORDERS_KEY] = [order.number]
    session.save()


def return_from_checkout(client, order, signature=None, payment_id=None):
    payment = order.payments.get()
    payment_id = payment_id or f"pay_{order.pk}"
    data = {
        "razorpay_order_id": payment.razorpay_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature or sign(f"{payment.razorpay_order_id}|{payment_id}", SECRET),
    }
    return client.post(reverse("shop:pay_verify", args=[order.number]), data)


def test_return_with_a_good_signature_pays_the_order_once(client, rzp, commit):
    product = ProductFactory(stock=5)
    order = make_order((product, 2))
    as_customer(client, order)
    rzp.payment.fetch.return_value = captured(order)
    with commit():
        response = return_from_checkout(client, order)
    assert response.url == reverse("shop:done", args=[order.number])
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.PAID and order.placed_at and product.stock == 3
    assert order.payments.get().status == Payment.Status.CAPTURED and order.invoice.pdf
    assert [m.subject for m in mail.outbox] == [f"[ExamLeaf] Order {order.number} confirmed"]
    with commit():  # the webhook for the same payment changes nothing
        assert post_webhook(client, "payment.captured", captured(order)).status_code == 200
        assert post_webhook(client, "order.paid", captured(order)).status_code == 200
    product.refresh_from_db()
    assert product.stock == 3 and len(mail.outbox) == 1
    assert order.payments.get().raw_payload == captured(order)  # the webhook's payment, allowed fields only


def test_a_wrong_signature_is_refused(client, rzp):
    order = make_order((ProductFactory(), 1))
    as_customer(client, order)
    response = return_from_checkout(client, order, signature="0" * 64)
    assert response.url == reverse("shop:pay", args=[order.number])
    assert order.payments.get().status == Payment.Status.CREATED and not rzp.payment.fetch.called
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_webhooks_need_the_right_signature_and_a_secret(client, rzp, settings):
    order = make_order((ProductFactory(), 1))
    assert post_webhook(client, "payment.captured", captured(order), secret="guess").status_code == 400
    settings.RAZORPAY_WEBHOOK_SECRET_TEST = ""  # the test keys' webhook secret
    assert post_webhook(client, "payment.captured", captured(order), secret="").status_code == 400
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_webhook_before_the_redirect(client, rzp, commit):
    product = ProductFactory(stock=1)
    order = make_order((product, 1))
    as_customer(client, order)
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    rzp.payment.fetch.return_value = captured(order)
    with commit():  # the customer's browser comes back afterwards
        assert return_from_checkout(client, order).url == reverse("shop:done", args=[order.number])
    product.refresh_from_db()
    assert product.stock == 0 and len(mail.outbox) == 1 and not Refund.objects.exists()


def test_redirect_waits_for_the_webhook_when_razorpay_cannot_be_asked(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    as_customer(client, order)
    rzp.payment.fetch.side_effect = requests.ConnectionError
    response = return_from_checkout(client, order)
    assert response.url == reverse("shop:done", args=[order.number])
    assert "We are confirming your payment" in client.get(response.url).content.decode()
    assert order.payments.get().status == Payment.Status.AUTHORIZED
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


def test_an_authorized_payment_is_captured_on_return(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    as_customer(client, order)
    rzp.payment.fetch.return_value = captured(order, status="authorized")
    rzp.payment.capture.return_value = captured(order)
    with commit():
        return_from_checkout(client, order)
    amount = order.payments.get().amount
    rzp.payment.capture.assert_called_once_with(
        f"pay_{order.pk}", int(amount.amount * 100), {"currency": "INR"}, timeout=10
    )
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


def test_failed_attempt_then_success_and_late_failures_are_ignored(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    post_webhook(client, "payment.failed", captured(order, id="pay_a", status="failed", error_description="Declined"))
    payment = order.payments.get()
    assert payment.status == Payment.Status.FAILED and payment.error == "Declined"
    with commit():
        post_webhook(client, "payment.captured", captured(order, id="pay_b"))
    post_webhook(client, "payment.failed", captured(order, id="pay_a", status="failed"))  # late, out of order
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED and payment.razorpay_payment_id == "pay_b"


def test_payment_for_a_cancelled_order_is_refunded(client, rzp, commit):
    product = ProductFactory(stock=3)
    order = make_order((product, 1))
    with commit():
        cancel_order(order, "Changed my mind.")
        post_webhook(client, "payment.captured", captured(order))  # paid in another tab meanwhile
    order.refresh_from_db()
    product.refresh_from_db()
    refund = order.refunds.get()
    assert refund.status == Refund.Status.PROCESSED and refund.razorpay_refund_id == f"rfnd_{refund.pk}"
    assert order.status == Order.Status.REFUNDED and product.stock == 3
    assert rzp.payment.refund.call_args.args[1]["amount"] == 29900


def test_books_sold_out_while_paying_cancels_and_refunds(client, rzp, commit):
    product = ProductFactory(stock=1)
    first, second = make_order((product, 1)), make_order((product, 1))
    with commit():
        post_webhook(client, "payment.captured", captured(first))
        post_webhook(client, "payment.captured", captured(second))
    first.refresh_from_db()
    second.refresh_from_db()
    product.refresh_from_db()
    assert first.status == Order.Status.PAID and product.stock == 0
    assert second.status == Order.Status.REFUNDED and second.refunds.get().status == Refund.Status.PROCESSED
    assert any("sold out" in m.body for m in mail.outbox if second.number in m.subject)


def test_wrong_amount_is_refunded_not_accepted(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        post_webhook(client, "payment.captured", captured(order, amount=100))
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING and order.refunds.get().amount.amount == 1


def test_refund_finished_by_the_webhook(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    rzp.payment.refund.side_effect = None
    rzp.payment.refund.return_value = {"id": "rfnd_X", "status": "pending"}
    with commit():
        cancel_order(order, "Cancelled by the customer.")
    refund = order.refunds.get()
    assert refund.status == Refund.Status.PENDING and refund.razorpay_refund_id == "rfnd_X"
    with commit():
        post_webhook(client, "refund.processed", {"id": "rfnd_X", "notes": []}, kind="refund")
        post_webhook(client, "refund.processed", {"id": "rfnd_X", "notes": []}, kind="refund")  # repeated
    refund.refresh_from_db()
    order.refresh_from_db()
    assert refund.status == Refund.Status.PROCESSED and order.status == Order.Status.REFUNDED
    assert sum(f"Refund for order {order.number}" in m.subject for m in mail.outbox) == 1


def test_unreachable_razorpay_keeps_the_order_and_offers_a_retry(client, rzp):
    order = make_order((ProductFactory(), 1))
    Payment.objects.filter(order=order).update(razorpay_order_id=None)
    as_customer(client, order)
    rzp.order.create.side_effect = requests.Timeout
    page = client.get(reverse("shop:pay", args=[order.number])).content.decode()
    assert "could not be reached" in page and "Try again" in page and 'id="razorpay-options"' not in page
    rzp.order.create.side_effect = lambda data, **kw: {"id": "order_R", **data}
    response = client.get(reverse("shop:pay", args=[order.number]))
    assert response.context["checkout"]["order_id"] == "order_R" == order.payments.get().razorpay_order_id
    assert rzp.order.create.call_args.args[0]["amount"] == 29900


def test_razorpay_is_allowed_by_the_csp_on_the_payment_page_only(client, rzp, settings):
    settings.SECURE_CSP, settings.SECURE_CSP_REPORT_ONLY = settings.CONTENT_SECURITY_POLICY, {}
    order = make_order((ProductFactory(), 1))
    as_customer(client, order)
    response = client.get(reverse("shop:pay", args=[order.number]))
    policy = response.headers["Content-Security-Policy"]
    assert "script-src 'self' https://cdn.jsdelivr.net/npm/katex@0.19.0/dist/ https://checkout.razorpay.com" in policy
    assert "frame-src 'self' https://api.razorpay.com" in policy and "lumberjack.razorpay.com" in policy
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
    assert "razorpay" not in client.get(reverse("shop:catalogue")).headers["Content-Security-Policy"]


def test_each_webhook_is_handled_once_and_old_ones_are_refused(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    now = int(time.time())
    old = now - int(payments.WEBHOOK_MAX_AGE.total_seconds()) - 60
    assert post_webhook(client, "payment.captured", captured(order), created_at=old).status_code == 200  # ignored
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING and not WebhookEvent.objects.exists()
    with commit():
        post_webhook(client, "payment.captured", captured(order), event_id="evt_1", created_at=now)
        post_webhook(client, "order.paid", captured(order), event_id="evt_2", created_at=now)
        for event_id in ["evt_1", "evt_forged"]:  # Razorpay's repeat; a replay of the signed body under another id
            assert (
                post_webhook(client, "payment.captured", captured(order), event_id=event_id, created_at=now).status_code
                == 200
            )
    assert list(WebhookEvent.objects.values_list("event_id", "name")) == [
        ("evt_1", "payment.captured"),
        ("evt_2", "order.paid"),
    ]
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and len(mail.outbox) == 1  # the repeats were not handled again
