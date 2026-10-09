"""Razorpay (official SDK): the client, the Razorpay order behind a checkout, the check of what Checkout returns, and
the webhooks. Signatures are HMAC-SHA256, checked locally by the SDK; every network call has a timeout. Tests replace
the network calls of `client()`."""

import hashlib
import json
import logging
import time
from datetime import timedelta
from decimal import Decimal

import razorpay
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django_fsm import can_proceed
from razorpay.errors import BadRequestError, GatewayError, ServerError, SignatureVerificationError

from . import services
from .models import INR, Order, Payment, Refund, WebhookEvent, live_mode, paise

logger = logging.getLogger(__name__)
# Seconds per Razorpay call, to connect and then for each read of the answer (requests' pair): an unreachable or a
# silent Razorpay costs a checkout 3 or 10 seconds and the "could not be reached" answer, never a hung thread. The
# SDK's own retries stay off (Client.enable_retry): a page retries by the customer's click, a task by Celery.
TIMEOUT = (3, 10)
WEBHOOK_MAX_AGE = timedelta(days=7)  # Razorpay retries a webhook for 24 hours; older signed events are replays
LINK_DAYS = 15  # a payment link's life, as a quotation's (QuoteRequest.VALID_DAYS)
API_ERRORS = (requests.RequestException, BadRequestError, GatewayError, ServerError)


class Unavailable(Exception):
    """Razorpay is not set up or could not be reached; the order stays pending and the page offers a retry."""


def client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def test_mode():
    return not live_mode()


def razorpay_order_id(payment):
    """The Razorpay order Checkout pays, created on first use (and again on a retry after Razorpay was unreachable).
    Its amount is the order's total in paise, fixed when the order was made."""
    if payment.razorpay_order_id:
        return payment.razorpay_order_id
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        raise Unavailable("Online payment is not set up yet.")
    number = payment.order.number
    try:
        data = client().order.create(
            {"amount": paise(payment.amount), "currency": INR, "receipt": number, "notes": {"order": number}},
            timeout=TIMEOUT,
        )
    except API_ERRORS as error:
        logger.warning("Razorpay order for %s not created: %s", number, error)
        raise Unavailable("The payment service could not be reached.") from error
    live = live_mode()  # the mode of the keys that made the Razorpay order is the payment's, and its order's
    first = Payment.objects.filter(pk=payment.pk, razorpay_order_id=None)
    if first.update(razorpay_order_id=data["id"], livemode=live):
        Order.objects.filter(pk=payment.order_id).update(livemode=live)
    return Payment.objects.values_list("razorpay_order_id", flat=True).get(pk=payment.pk)  # another tab's, if first


def checkout_options(order):
    """What Razorpay Checkout (the payment page) or the mobile SDK (the API) needs to pay an online order. Raises
    Unavailable."""
    payment = order.payments.filter(method=Order.Method.RAZORPAY, razorpay_payment_link_id=None).first()
    address = order.shipping_address
    return {
        "key": settings.RAZORPAY_KEY_ID,
        "order_id": razorpay_order_id(payment),
        "amount": paise(payment.amount),
        "currency": INR,
        "name": "ExamLeaf",
        "description": f"Order {order.number}",
        "prefill": {"name": address["name"], "email": order.email, "contact": address["phone"]},
        "notes": {"order": order.number},
        "theme": {"color": "#0b2a5b"},
    }


def send_payment_link(order):
    """A Razorpay Payment Link for a pending order made by staff, made once (later calls email the same link again)
    and emailed to the customer by us (services.notify; ops.sms has no template for it, so no SMS), valid LINK_DAYS.
    It gets a Payment of its own, apart from the website's checkout. Raises Unavailable."""
    payment = order.payments.exclude(razorpay_payment_link_id=None).first()
    if payment is None:
        if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
            raise Unavailable("Online payment is not set up yet.")
        address = order.shipping_address
        try:
            data = client().payment_link.create(
                {
                    "amount": paise(order.total),
                    "currency": INR,
                    "accept_partial": False,
                    "reference_id": order.number,
                    "description": f"ExamLeaf order {order.number}",
                    "customer": {"name": address["name"], "email": order.email, "contact": address["phone"]},
                    "notify": {"sms": False, "email": False},  # we email it
                    "reminder_enable": False,
                    "expire_by": int(time.time() + LINK_DAYS * 86400),
                    "notes": {"order": order.number},
                },
                timeout=TIMEOUT,
            )
        except API_ERRORS as error:
            logger.warning("Razorpay payment link for %s not created: %s", order.number, error)
            raise Unavailable("The payment service could not be reached.") from error
        payment = Payment.objects.create(
            order=order,
            method=Order.Method.RAZORPAY,
            amount=order.total,
            livemode=live_mode(),
            razorpay_payment_link_id=data["id"],
            payment_link_url=data["short_url"],
        )
    services.notify(order, "payment_link", url=payment.payment_link_url)
    return payment


def confirm_return(payment, data):
    """Checkout's success callback (`data`: razorpay_order_id, razorpay_payment_id, razorpay_signature). Returns False
    if the signature is wrong. Otherwise the payment is authorized, then Razorpay is asked for it and it is recorded
    if captured (capturing it first if the account does not capture by itself). If Razorpay cannot be asked now, the
    payment.captured webhook completes the order."""
    params = {name: data.get(name, "") for name in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")}
    if not payment.razorpay_order_id or params["razorpay_order_id"] != payment.razorpay_order_id:
        return False
    try:
        client().utility.verify_payment_signature(params)
    except SignatureVerificationError:
        logger.warning("Wrong Checkout signature for order %s", payment.order.number)
        return False
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        locked.razorpay_signature = params["razorpay_signature"]
        if can_proceed(locked.authorize):
            locked.razorpay_payment_id = params["razorpay_payment_id"]
            locked.authorize()
        locked.save()
    try:
        entity = client().payment.fetch(params["razorpay_payment_id"], timeout=TIMEOUT)
        if entity["status"] == "authorized" and entity["amount"] == paise(payment.amount):
            entity = client().payment.capture(entity["id"], entity["amount"], {"currency": INR}, timeout=TIMEOUT)
    except API_ERRORS as error:
        logger.warning("Razorpay payment %s not confirmed now (%s); waiting for the webhook", params, error)
        return True
    if entity.get("status") == "captured" and entity.get("order_id") == payment.razorpay_order_id:
        services.record_capture(entity)
    return True


def reconcile(order):
    """For an online order still awaiting payment: ask Razorpay what became of the payment (the customer may have paid
    and never come back, and the webhook may have been lost) and record a captured one, capturing an authorized one
    first. Returns True if the order has been paid, False if Razorpay has no payment for it, None if Razorpay could not
    be asked (nothing is known then)."""
    link = order.payments.exclude(razorpay_payment_link_id=None).filter(razorpay_order_id=None).first()
    if link is not None and link.livemode == live_mode():  # a staff order's link, paid with its webhook lost?
        try:
            data = client().payment_link.fetch(link.razorpay_payment_link_id, timeout=TIMEOUT)
            paid = (data.get("payments") or []) if data.get("status") == "paid" else []
            for entity in (client().payment.fetch(item["payment_id"], timeout=TIMEOUT) for item in paid):
                if entity.get("status") == "captured":
                    services.record_link_payment(link.razorpay_payment_link_id, entity)
                    return True
        except API_ERRORS as error:
            logger.warning("Razorpay could not be asked about the link of order %s: %s", order.number, error)
            return None
    payment = order.payments.filter(method=Order.Method.RAZORPAY).exclude(razorpay_order_id=None).first()
    if payment is None or payment.livemode != live_mode():
        return False  # never reached the payment page, or made with the other mode's keys: these keys see no payment
    try:
        for entity in client().order.payments(payment.razorpay_order_id, timeout=TIMEOUT).get("items", []):
            if entity.get("status") == "authorized" and entity.get("amount") == paise(payment.amount):
                entity = client().payment.capture(entity["id"], entity["amount"], {"currency": INR}, timeout=TIMEOUT)
            if entity.get("status") == "captured" and entity.get("order_id") == payment.razorpay_order_id:
                services.record_capture(entity)
                return True
    except API_ERRORS as error:
        logger.warning("Razorpay could not be asked about order %s: %s", order.number, error)
        return None
    return False


def handle_webhook(body, signature, event_id=""):
    """A Razorpay webhook. Returns False if the signature (HMAC of the raw body with the webhook secret) is wrong or
    no secret is set. Each event is handled once, in one transaction with its record (WebhookEvent: its id and the hash
    of the body, so a replay under another id is caught too); events older than WEBHOOK_MAX_AGE and events for unknown
    orders (another integration on the same account) are acknowledged and ignored."""
    secret = settings.RAZORPAY_WEBHOOK_SECRET if live_mode() else settings.RAZORPAY_WEBHOOK_SECRET_TEST
    if not secret or not signature:
        return False
    try:
        client().utility.verify_webhook_signature(body.decode(), signature, secret)
        event = json.loads(body)
    except SignatureVerificationError, UnicodeDecodeError, ValueError:
        return False
    digest = hashlib.sha256(body).hexdigest()
    created = event.get("created_at")
    if isinstance(created, int) and created < time.time() - WEBHOOK_MAX_AGE.total_seconds():
        logger.warning("Razorpay webhook %s from %s ignored: too old", event_id or digest, created)
        return True
    with transaction.atomic():  # the record goes with the changes: an event that fails is handled again on retry
        try:
            with transaction.atomic():
                WebhookEvent.objects.create(
                    event_id=event_id[:64] or digest, digest=digest, name=event.get("event", "")[:40]
                )
        except IntegrityError:
            return True  # handled before
        _dispatch(event)
    return True


def _dispatch(event):
    name, payload = event.get("event", ""), event.get("payload", {})
    if name in ("payment.captured", "order.paid", "payment.failed"):
        entity = payload["payment"]["entity"]
        payment = Payment.objects.filter(razorpay_order_id=entity.get("order_id") or None).first()
        if payment is not None and services.same_mode(payment, name):
            if name == "payment.failed":
                services.record_failure(entity, payload=event)
            else:
                services.record_capture(entity, payload=event)
    elif name == "payment_link.paid":
        services.record_link_payment(payload["payment_link"]["entity"].get("id"), payload["payment"]["entity"], event)
    elif name in ("refund.processed", "refund.failed"):
        entity = payload["refund"]["entity"]
        notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}  # Razorpay sends [] when empty
        ours = Q(razorpay_refund_id=entity["id"])
        if str(notes.get("refund_id", "")).isdigit():
            ours |= Q(pk=int(notes["refund_id"]), razorpay_refund_id=None)  # webhook before the API's answer
        refund = Refund.objects.filter(ours).first()
        if refund is None and name == "refund.processed":
            payment = Payment.objects.filter(razorpay_payment_id=entity.get("payment_id") or None).first()
            if payment is not None and services.same_mode(payment, name):  # made in the Razorpay dashboard: recorded
                refund = Refund.objects.create(
                    order=payment.order,
                    payment=payment,
                    amount=Decimal(entity["amount"]) / 100,
                    reason="Refunded in the Razorpay dashboard.",
                    razorpay_refund_id=entity["id"],
                )
        if refund and services.same_mode(refund.payment, name):
            if name == "refund.processed":
                services.refund_processed(refund.pk, razorpay_refund_id=entity["id"])
            else:
                services.refund_failed(refund.pk, (entity.get("error_description") or "refund failed"))
