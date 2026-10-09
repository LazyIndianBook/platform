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
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django_fsm import can_proceed
from razorpay.errors import BadRequestError, GatewayError, ServerError, SignatureVerificationError

from examleaf.bulkhead import Bulkhead

from . import services
from .models import (
    INR,
    InvoicePaymentLink,
    Order,
    Payment,
    Refund,
    WebhookEvent,
    live_mode,
    paise,
    razorpay_keys,
    rupees,
)

logger = logging.getLogger(__name__)
# Seconds per Razorpay call, to connect and then for each read of the answer (requests' pair): an unreachable or a
# silent Razorpay costs a checkout 3 or 10 seconds and the "could not be reached" answer, never a hung thread. The
# SDK's own retries stay off (Client.enable_retry): a page retries by the customer's click, a task by Celery.
TIMEOUT = (3, 10)
# Razorpay's calls share the providers' half of a process's threads (examleaf/bulkhead.py): over it, a call answers
# "could not be reached" at once instead of holding a thread every other page needs.
CALLS = Bulkhead(requests.ConnectionError, "Half of this process's threads are waiting on providers already")
WEBHOOK_MAX_AGE = timedelta(days=7)  # Razorpay retries a webhook for 24 hours; older signed events are replays
LINK_DAYS = 15  # a payment link's life, as a quotation's (QuoteRequest.VALID_DAYS)
API_ERRORS = (requests.RequestException, BadRequestError, GatewayError, ServerError)


class Unavailable(Exception):
    """Razorpay is not set up or could not be reached; the order stays pending and the page offers a retry."""


class Session(requests.Session):
    """The SDK's HTTP session: every call it makes goes through the bulkhead (CALLS)."""

    def request(self, *args, **kwargs):
        with CALLS:
            return super().request(*args, **kwargs)


def client():
    keys = razorpay_keys()  # the environment's, or the panel's once it holds some (models.razorpay_keys)
    return razorpay.Client(session=Session(), auth=(keys.key_id, keys.key_secret))


def configured():
    keys = razorpay_keys()
    return bool(keys.key_id and keys.key_secret)


def test_mode():
    return not live_mode()


def razorpay_order_id(payment):
    """The Razorpay order Checkout pays, created on first use (and again on a retry after Razorpay was unreachable).
    Its amount is the order's total in paise, fixed when the order was made."""
    if payment.razorpay_order_id:
        return payment.razorpay_order_id
    if not configured():
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
        "key": razorpay_keys().key_id,
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
    links = order.payments.exclude(razorpay_payment_link_id=None).exclude(status=Payment.Status.FAILED)
    payment = links.first()  # a link cancelled (cancel_payment_link) is never sent again: a new one is made
    if payment is None:
        if not configured():
            raise Unavailable("Online payment is not set up yet.")
        address = order.shipping_address
        made = order.payments.exclude(razorpay_payment_link_id=None).count()  # Razorpay takes a reference id once
        try:
            data = client().payment_link.create(
                {
                    "amount": paise(order.total),
                    "currency": INR,
                    "accept_partial": False,
                    "reference_id": f"{order.number}-{made + 1}" if made else order.number,
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


def awaiting_payment(older_than=10):
    """The online orders of the keys' mode still awaiting their payment, made more than `older_than` minutes ago (a
    customer may be paying right now), that reached Razorpay (its checkout opened, or a staff order's link made):
    those Razorpay may know a payment of (reconcile)."""
    reached = Payment.objects.filter(order=OuterRef("pk"), method=Order.Method.RAZORPAY).filter(
        Q(razorpay_order_id__isnull=False) | Q(razorpay_payment_link_id__isnull=False)
    )
    return Order.objects.filter(
        status=Order.Status.PENDING,
        placed_at__isnull=True,
        payment_method=Order.Method.RAZORPAY,
        livemode=live_mode(),
        created__lt=timezone.now() - timedelta(minutes=older_than),
    ).filter(Exists(reached))


def handle_webhook(body, signature, event_id=""):
    """A Razorpay webhook. Returns False if the signature (HMAC of the raw body with the webhook secret) is wrong or
    no secret is set. Each event is handled once, in one transaction with its record (WebhookEvent: its id and the hash
    of the body, so a replay under another id is caught too); events older than WEBHOOK_MAX_AGE and events for unknown
    orders (another integration on the same account) are acknowledged and ignored. The secret is the keys' mode's from
    the environment, or the panel's (with the previous one for 24 hours after a rotation: models.razorpay_keys)."""
    secrets = razorpay_keys().webhook_secrets
    if not secrets or not signature:
        return False
    try:
        text = body.decode()
        verified = False
        for secret in secrets:
            try:
                client().utility.verify_webhook_signature(text, signature, secret)
                verified = True
                break
            except SignatureVerificationError:
                continue
        if not verified:
            return False
        event = json.loads(body)
    except UnicodeDecodeError, ValueError:
        return False
    digest = hashlib.sha256(body).hexdigest()
    created = event.get("created_at")
    if isinstance(created, int) and created < time.time() - WEBHOOK_MAX_AGE.total_seconds():
        logger.warning("Razorpay webhook %s from %s ignored: too old", event_id or digest, created)
        return True
    with transaction.atomic():  # the record goes with the changes: an event that fails is handled again on retry
        try:
            with transaction.atomic():
                row = WebhookEvent.objects.create(
                    event_id=event_id[:64] or digest, digest=digest, name=event.get("event", "")[:40]
                )
        except IntegrityError:
            return True  # handled before
        if (payment := _dispatch(event)) is not None:  # the panel's payment record lists its webhooks
            WebhookEvent.objects.filter(pk=row.pk).update(payment=payment)
    return True


def _dispatch(event):
    """Handle one webhook. Returns the Payment it was about, or None."""
    name, payload = event.get("event", ""), event.get("payload", {})
    if name in ("payment.captured", "order.paid", "payment.failed"):
        entity = payload["payment"]["entity"]
        payment = Payment.objects.filter(razorpay_order_id=entity.get("order_id") or None).first()
        if payment is not None and services.same_mode(payment, name):
            if name == "payment.failed":
                services.record_failure(entity, payload=event)
            else:
                services.record_capture(entity, payload=event)
        return payment
    if name == "payment_link.paid":
        link_id, entity = payload["payment_link"]["entity"].get("id"), payload["payment"]["entity"]
        if services.record_link_payment(link_id, entity, event) is None:  # not an order's: a B2B invoice's?
            record_invoice_link_payment(link_id, entity)
        return Payment.objects.filter(razorpay_payment_link_id=link_id or None).first()
    refund = None
    if name in ("refund.processed", "refund.failed"):
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
                arn = (entity.get("acquirer_data") or {}).get("arn") or ""  # the bank's reference
                services.refund_processed(refund.pk, razorpay_refund_id=entity["id"], arn=arn)
            else:
                services.refund_failed(refund.pk, (entity.get("error_description") or "refund failed"))
    return refund.payment if refund else None


def cancel_payment_link(order):
    """Cancel a staff order's Razorpay Payment Link that is still open (a wrong amount, the customer paid otherwise):
    Razorpay first, then its Payment marked failed, so the next send_payment_link makes a new one. Returns the payment;
    raises Unavailable (Razorpay could not be asked: nothing changed) or ValueError (no open link)."""
    payment = order.payments.exclude(razorpay_payment_link_id=None).exclude(status=Payment.Status.FAILED).first()
    if payment is None or payment.status != Payment.Status.CREATED:
        raise ValueError(f"Order {order.number} has no payment link waiting to be paid.")
    try:
        client().payment_link.cancel(payment.razorpay_payment_link_id, timeout=TIMEOUT)
    except API_ERRORS as error:
        logger.warning("Razorpay payment link of %s not cancelled: %s", order.number, error)
        raise Unavailable("The payment service could not be reached.") from error
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if can_proceed(locked.fail):
            locked.fail("Payment link cancelled by staff.")
            locked.save()
    return locked


# Phase B: finance. Payment links for ERPNext's B2B invoices (InvoicePaymentLink): made by the platform, because
# Razorpay stays here (plan 5.8); their payment recorded here and posted in ERPNext by FINANCE, by hand.

UNREACHABLE = (requests.RequestException, GatewayError, ServerError)  # BadRequestError: Razorpay answered and refused
Link = InvoicePaymentLink


def b2b_invoice(name):
    """A B2B invoice of ERPNext's that a link may be made for: in the platform's read-only copy (erp.ErpMirror, while
    ERP_PULL_B2B keeps them), submitted, not a credit note, with something outstanding. Returns (its name, what is
    outstanding in rupees); raises ValueError saying why not."""
    from erp.models import ErpMirror

    name = str(name or "").strip()
    mirror = ErpMirror.objects.filter(doctype="Sales Invoice", name=name).first() if name else None
    if mirror is None:
        raise ValueError(f"No B2B invoice {name} in the platform's copy of ERPNext (ERP_PULL_B2B keeps them).")
    data = mirror.data if isinstance(mirror.data, dict) else {}
    if data.get("docstatus") != 1:
        raise ValueError(f"Invoice {mirror.name} is not submitted in ERPNext, or it was cancelled there.")
    if data.get("is_return"):
        raise ValueError(f"{mirror.name} is a credit note: there is nothing to pay.")
    try:
        outstanding = rupees(Decimal(str(data.get("outstanding_amount") or 0)))
    except ArithmeticError, ValueError:
        outstanding = Decimal(0)
    if outstanding <= 0:
        raise ValueError(f"Invoice {mirror.name} has nothing outstanding.")
    return mirror.name, outstanding


def send_invoice_link(name, by=None, request=None):
    """A Razorpay Payment Link for what a B2B invoice has outstanding, valid LINK_DAYS: made once while it is open
    (asking again answers the same link), its address for staff to send the customer (no contact of a B2B customer is
    kept on the platform, so Razorpay sends nothing either). Audited. Returns (the link, whether it was made now);
    raises Unavailable or ValueError."""
    from staff.audit import record

    now = timezone.now()
    Link.objects.filter(invoice=str(name).strip(), status=Link.Status.SENT, expires_at__lte=now).update(
        status=Link.Status.EXPIRED
    )
    if (open_link := Link.objects.filter(invoice=str(name).strip(), status=Link.Status.SENT).first()) is not None:
        return open_link, False
    invoice, amount = b2b_invoice(name)
    if not configured():
        raise Unavailable("Online payment is not set up yet.")
    made = Link.objects.filter(invoice=invoice).count()
    try:
        data = client().payment_link.create(
            {
                "amount": paise(amount),
                "currency": INR,
                "accept_partial": False,
                "reference_id": f"{invoice}/{made + 1}"[:40],  # Razorpay takes a reference id once
                "description": f"ExamLeaf invoice {invoice}"[:200],
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
                "expire_by": int(time.time() + LINK_DAYS * 86400),
                "notes": {"invoice": invoice},
            },
            timeout=TIMEOUT,
        )
    except BadRequestError as error:
        raise ValueError(f"Razorpay refused the link: {error}") from error
    except UNREACHABLE as error:
        logger.warning("Razorpay payment link for invoice %s not made: %s", invoice, error)
        raise Unavailable("The payment service could not be reached.") from error
    try:
        with transaction.atomic():
            link = Link.objects.create(
                invoice=invoice,
                amount=amount,
                razorpay_payment_link_id=data["id"],
                url=data.get("short_url", ""),
                expires_at=now + timedelta(days=LINK_DAYS),
                livemode=live_mode(),
                created_by=by,
            )
            details = {"invoice": invoice, "amount": amount, "link": data["id"]}
            record("payment.link_made", request=request, actor=by, target=link, details=details)
    except IntegrityError:  # another person made one at the same moment: theirs stands, this one is cancelled
        try:
            client().payment_link.cancel(data["id"], timeout=TIMEOUT)
        except API_ERRORS as error:  # it expires by itself, unpaid: nobody has its address
            logger.warning("Razorpay payment link %s made twice and not cancelled: %s", data["id"], error)
        return Link.objects.get(invoice=invoice, status=Link.Status.SENT), False
    return link, True


def cancel_invoice_link(link, by=None, request=None):
    """Cancel a B2B invoice's link that is still open: Razorpay first (a link paid meanwhile is refused there, and its
    payment is recorded by its webhook), then the link. Audited. Returns the link; raises Unavailable (Razorpay could
    not be asked: nothing changed) or ValueError (not open)."""
    from staff.audit import record

    if link.status != Link.Status.SENT or link.expires_at <= timezone.now():
        raise ValueError(f"The link for {link.invoice} is not open: it is {link.get_status_display()} or expired.")
    try:
        client().payment_link.cancel(link.razorpay_payment_link_id, timeout=TIMEOUT)
    except BadRequestError as error:
        raise ValueError(f"Razorpay refused to cancel the link (paid meanwhile?): {error}") from error
    except UNREACHABLE as error:
        logger.warning("Razorpay payment link for invoice %s not cancelled: %s", link.invoice, error)
        raise Unavailable("The payment service could not be reached.") from error
    with transaction.atomic():
        locked = Link.objects.select_for_update().get(pk=link.pk)
        if locked.status == Link.Status.SENT:
            locked.status, locked.cancelled_by = Link.Status.CANCELLED, by
            locked.save(update_fields=["status", "cancelled_by", "modified"])
            details = {"invoice": locked.invoice, "link": locked.razorpay_payment_link_id}
            record("payment.link_cancelled", request=request, actor=by, target=locked, details=details)
    return locked


def record_invoice_link_payment(link_id, entity):
    """A payment made through one of our B2B invoices' links (the payment_link.paid webhook, or asked again): the link
    paid, once, and FINANCE told to post its Payment Entry in ERPNext by hand (ERPNext's create_payment_entry takes
    only the platform's own invoices). A link of the other mode's keys is ignored. Returns the link, or None for a
    link that is not one of these."""
    from staff.audit import plain, record
    from staff.models import InboxItem
    from staff.signals import open_item

    with transaction.atomic():
        link = Link.objects.select_for_update().filter(razorpay_payment_link_id=link_id or None).first()
        if link is None or link.status == Link.Status.PAID or entity.get("status") != "captured":
            return link
        if link.livemode != live_mode():
            logger.warning("Razorpay payment for B2B link #%s (the other mode's keys) ignored", link.pk)
            return link
        link.status, link.razorpay_payment_id, link.paid_at = Link.Status.PAID, entity["id"], timezone.now()
        link.save(update_fields=["status", "razorpay_payment_id", "paid_at", "modified"])
        taken = rupees(Decimal(entity.get("amount") or 0) / 100)
        details = {"invoice": link.invoice, "amount": taken, "payment": entity["id"]}
        record("payment.link_paid", target=link, details=details)
        differs = "" if taken == link.amount.amount else f", not the ₹{link.amount.amount} asked"
        title = f"Post by hand in ERPNext: invoice {link.invoice} paid ₹{taken}{differs} ({entity['id']})"
        open_item(InboxItem.Kind.B2B_PAYMENT, link, title, "staff.reconcile_settlements", **plain(details))
    return link


def reconcile_invoice_link(link):
    """Ask Razorpay what became of a B2B invoice's link (its webhook lost): a paid one is recorded; one Razorpay
    expired or cancelled is marked so. Returns True (paid), False (not paid), or None (Razorpay could not be asked)."""
    if link.status == Link.Status.PAID:
        return True
    if link.livemode != live_mode():
        return False  # these keys see nothing of the other mode's links
    try:
        data = client().payment_link.fetch(link.razorpay_payment_link_id, timeout=TIMEOUT)
        paid = (data.get("payments") or []) if data.get("status") == "paid" else []
        for entity in (client().payment.fetch(item["payment_id"], timeout=TIMEOUT) for item in paid):
            if entity.get("status") == "captured":
                record_invoice_link_payment(link.razorpay_payment_link_id, entity)
                return True
    except API_ERRORS as error:
        logger.warning("Razorpay could not be asked about the link of invoice %s: %s", link.invoice, error)
        return None
    gone = {"expired": Link.Status.EXPIRED, "cancelled": Link.Status.CANCELLED}.get(data.get("status"))
    if gone:
        Link.objects.filter(pk=link.pk, status=Link.Status.SENT).update(status=gone)
    return False
