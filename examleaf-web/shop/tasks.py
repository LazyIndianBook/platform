import logging
from datetime import date, timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from PIL import Image
from razorpay.errors import BadRequestError, GatewayError, ServerError

from examleaf.celery import LONG_TASK, PDF_TASK, single_run
from examleaf.images import og_image
from integrations.client import IntegrationUnavailable
from ops.tasks import queue_text_email

from . import invoices, payments, services, tax
from .models import (
    Cart,
    CreditNote,
    Invoice,
    Order,
    Payment,
    Product,
    QuoteRequest,
    Refund,
    StockAlert,
    WebhookEvent,
    paise,
    public_storage,
)

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(requests.RequestException, GatewayError, ServerError),
    retry_backoff=60,
    retry_backoff_max=3600,
    max_retries=8,
)
def refund_payment(refund_id):
    """Ask Razorpay to refund a payment in full. Razorpay unreachable or failing: retried for about four hours.
    Refused (a bad request): the refund is marked failed for staff (admin, Refunds). The refund's row stays locked
    during the call, so a task queued twice cannot refund twice; a second one finds it locked and leaves it to the
    first at once (skip_locked), rather than wait for its Razorpay calls. Each try first asks Razorpay for the
    payment's refunds and adopts the one that carries this refund's id in its notes: a refund made by a try whose
    answer was lost (a timeout) is never sent again."""
    with transaction.atomic():
        mine = Refund.objects.select_for_update(skip_locked=True, of=("self",)).select_related("payment", "order")
        refund = mine.filter(pk=refund_id).first()  # None: another worker has it (or it is gone)
        if refund is None or refund.status != Refund.Status.PENDING or refund.razorpay_refund_id:
            return
        if refund.method != Refund.Method.SOURCE:  # by bank or UPI (FINANCE transfers it), or no money at all
            return
        client, payment_id, ours = payments.client(), refund.payment.razorpay_payment_id, str(refund.pk)
        made = client.payment.fetch_multiple_refund(payment_id, timeout=payments.TIMEOUT).get("items", [])
        notes = [r["notes"] if isinstance(r.get("notes"), dict) else {} for r in made]  # Razorpay: [] when empty
        result = next((r for r, n in zip(made, notes, strict=True) if n.get("refund_id") == ours), None)
        try:
            result = result or client.payment.refund(
                payment_id,
                {
                    "amount": paise(refund.amount),
                    "speed": refund.speed,  # normal, or optimum (instant where the bank allows)
                    "receipt": f"refund-{refund.pk}",
                    "notes": {"order": refund.order.number, "refund_id": ours},
                },
                timeout=payments.TIMEOUT,
            )
        except BadRequestError as error:
            services.refund_failed(refund.pk, str(error))
            return
        refund.razorpay_refund_id = result["id"]
        refund.save(update_fields=["razorpay_refund_id", "modified"])
    if result.get("status") == "processed":  # otherwise the refund.processed webhook finishes it
        services.refund_processed(refund_id, arn=(result.get("acquirer_data") or {}).get("arn") or "")


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=6, **PDF_TASK)
def generate_invoice(order_id):
    """The order's invoice: numbered on the first try, the PDF made with WeasyPrint. A failure is retried; the order
    page shows the invoice link once the file exists."""
    order = Order.objects.get(pk=order_id)
    invoices.check_seller(order.livemode)
    invoice = Invoice.for_order(order)
    if not invoice.pdf:
        invoice.pdf.save(f"{invoice.number.replace('/', '-')}.pdf", ContentFile(invoices.render_pdf(invoice)))
    refunded = Refund.objects.filter(order=order_id, status=Refund.Status.PROCESSED, credit_note=None)
    for pk in refunded.values_list("pk", flat=True):  # refunded before the invoice was made
        generate_credit_note.delay(pk)


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=6, **PDF_TASK)
def generate_credit_note(refund_id):
    """The credit note of a processed refund of an invoiced order (none before the invoice exists: generate_invoice
    comes back here once it does). Numbered on the first try, the PDF made with WeasyPrint; a failure is retried. None
    against a cancelled invoice or past 30 November after the invoice's year (tax.CreditNoteRefused): the refund has
    gone out regardless, and FINANCE's inbox says which note is missing and why."""
    refund = Refund.objects.select_related("order").get(pk=refund_id)
    invoice = Invoice.objects.filter(order=refund.order_id).first()
    if refund.status != Refund.Status.PROCESSED or invoice is None:
        return
    invoices.check_seller(not invoice.is_test)
    try:
        note = CreditNote.for_refund(refund, invoice)
    except tax.CreditNoteRefused as refused:
        tax.report_missing_credit_note(refund, str(refused))
        return
    if not note.pdf:
        note.pdf.save(f"{note.number.replace('/', '-')}.pdf", ContentFile(invoices.render_pdf(note)))


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=6, **PDF_TASK)
def remake_pdf(model, pk):
    """A document's PDF made again (a cancelled one, marked so: tax.cancel): saved under a new name, the old file
    removed once the new one is in place."""
    document = (Invoice if model == "shop.invoice" else CreditNote).objects.filter(pk=pk).first()
    if document is None:
        return
    old = document.pdf.name
    document.pdf.save(f"{document.number.replace('/', '-')}.pdf", ContentFile(invoices.render_pdf(document)))
    if old and old != document.pdf.name:
        document.pdf.storage.delete(old)


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def watch_tax_thresholds():
    """Nightly (01:45): the threshold monitor's rows for today, and an inbox item for FINANCE when a line is crossed
    (tax.watch_thresholds; a second run the same day changes nothing)."""
    return len(tax.watch_thresholds())


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=3, **PDF_TASK)
def make_quotation(quote_id):
    """The quotation PDF staff asked for in the admin (services.make_quotation), made here rather than in their
    request: WeasyPrint's work, and the upload to the private storage, belong to a worker."""
    services.make_quotation(QuoteRequest.objects.get(pk=quote_id))


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def clean_up():
    """Daily (celery beat): cancel orders left unpaid (after asking Razorpay if they were paid after all); queue again
    the refunds, invoices and credit notes whose task was lost (broker down when queued, retries used up); delete guest
    carts untouched for 30 days, the record of webhooks too old to be accepted again, what was kept of the webhooks
    of payments older than Payment.PAYLOAD_DAYS, and the customer's details from orders never paid or placed, 30 days
    after they were cancelled."""
    services.expire_unpaid_orders(reconcile=payments.reconcile)
    hour_ago = timezone.now() - timedelta(hours=1)
    lost_refunds = Refund.objects.filter(status=Refund.Status.PENDING, razorpay_refund_id=None, created__lt=hour_ago)
    lost_refunds = lost_refunds.filter(method=Refund.Method.SOURCE)  # Razorpay's: a bank refund waits for FINANCE
    for pk in lost_refunds.values_list("pk", flat=True):
        refund_payment.delay(pk)
    S = Order.Status
    no_invoice = (
        Order.objects.filter(status__in=[S.PAID, S.PACKED, S.SHIPPED, S.DELIVERED], modified__lt=hour_ago)
        .filter(Q(invoice__isnull=True) | Q(invoice__pdf=""))
        .exclude(payment_method=Order.Method.COD, status__in=[S.PAID, S.PACKED])  # cash on delivery: at dispatch
        .exclude(email=services.DELETED)  # purged after eight years (RUNBOOK.md): their PDFs are gone for good
    )
    for pk in no_invoice.values_list("pk", flat=True):
        generate_invoice.delay(pk)
    no_note = Refund.objects.filter(status=Refund.Status.PROCESSED, order__invoice__isnull=False, modified__lt=hour_ago)
    no_note = no_note.exclude(order__email=services.DELETED)
    for pk in no_note.filter(Q(credit_note=None) | Q(credit_note__pdf="")).values_list("pk", flat=True):
        generate_credit_note.delay(pk)
    Cart.objects.filter(user=None, modified__lt=timezone.now() - timedelta(days=30)).delete()
    WebhookEvent.objects.filter(received_at__lt=timezone.now() - payments.WEBHOOK_MAX_AGE).delete()
    old_payments = Payment.objects.filter(created__lt=timezone.now() - timedelta(days=Payment.PAYLOAD_DAYS))
    old_payments.filter(raw_payload__isnull=False).update(raw_payload=None)
    StockAlert.objects.filter(created__lt=timezone.now() - timedelta(days=365)).delete()  # a book never back
    unsold = Order.objects.filter(status=S.CANCELLED, placed_at=None)  # no sale: nothing for the tax records
    services.forget_orders(unsold.filter(modified__lt=timezone.now() - services.FORGET_UNSOLD_AFTER))


@shared_task(autoretry_for=(OSError,), retry_backoff=60, max_retries=3)
def make_og_image(product_id):
    """The product's link-preview picture (og:image): its cover and title on the night colour, 1200x630 JPEG, in the
    public storage under a new name each time (the bucket's files are cached as immutable); the old one is deleted."""
    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        return
    covers = []
    if product.cover:
        with public_storage().open(product.cover.name) as file, Image.open(file) as cover:
            covers = [cover.convert("RGB")]
    name = public_storage().save(f"og/{product.slug}.jpg", ContentFile(og_image(covers, product.title)))
    Product.objects.filter(pk=product.pk).update(og_image=name)  # no post_save: nothing queued again
    if product.og_image:
        public_storage().delete(product.og_image.name)


@shared_task
@single_run(300)
def send_stock_alerts():
    """Hourly (celery beat): each address waiting for a product that has copies again gets one email, and its alert
    is deleted, before the email goes: a run that overlaps this one (or this one run again) finds it gone."""
    for product in Product.objects.filter(is_active=True, stock_alerts__isnull=False).distinct():
        if product.available < 1:
            continue
        body = render_to_string("shop/email/back_in_stock.txt", {"product": product, "site_url": settings.SITE_URL})
        for alert in product.stock_alerts.all():
            if StockAlert.objects.filter(pk=alert.pk).delete()[0]:  # taken by this run
                queue_text_email(alert.email, f"{product} is back in stock", body)


@shared_task
@single_run(300)
def low_stock_report():
    """Daily (celery beat): the SALES role is emailed the books on sale with fewer than SHOP_LOW_STOCK copies (bundles
    have none of their own)."""
    low = Product.objects.filter(is_active=True, stock__lt=settings.SHOP_LOW_STOCK)
    low = low.exclude(kind__in=[Product.Kind.BUNDLE, Product.Kind.DIGITAL])  # no copies of their own
    if products := list(low.order_by("stock", "title")):
        context = {"products": products, "low_stock": settings.SHOP_LOW_STOCK}
        services.email_staff("Books running out", "shop/email/low_stock.txt", context)


# Phase B: orders


@shared_task
@single_run(300)
def send_held_sms():
    """At 08:00 (India time): the order SMS held through the night (services.notify: none goes from 21:00 to 08:00),
    each claimed before it goes (a second run, or this one run again, finds it taken) and sent only if still true."""
    from ops.sms import send_order_sms

    from .models import OrderMessage

    still = {  # what each news needs to be still true; the others go as they are
        "confirmation": lambda order: order.status not in (Order.Status.CANCELLED, Order.Status.REFUNDED),
        "shipped": lambda order: order.status == Order.Status.SHIPPED,
        "delivered": lambda order: order.status == Order.Status.DELIVERED,
    }
    sent = 0
    for message in OrderMessage.objects.filter(sms=OrderMessage.Sms.HELD).select_related("order__user"):
        true = still.get(message.kind, lambda order: True)(message.order)
        state = OrderMessage.Sms.SENT if true else OrderMessage.Sms.DROPPED
        if not OrderMessage.objects.filter(pk=message.pk, sms=OrderMessage.Sms.HELD).update(sms=state):
            continue  # taken by another run
        if true:
            send_order_sms(message.order, message.kind)
            sent += 1
    return sent


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def weekly_staff_grants(today=None):
    """Mondays at 08:00 (India time): the owners are emailed last week's staff discounts, payments recorded offline
    and ₹0 orders, by the member of staff who gave them (inventory I6: "one person can give goods away"). Once a week:
    its audit event marks the week sent, so a second run, or this one delivered again, sends nothing."""
    from staff.audit import ActorType, owners_emails, record
    from staff.models import AuditEvent

    from .services import staff_grants

    today = today or timezone.localdate()
    end = today - timedelta(days=today.weekday())  # this Monday: the week before it, Monday to Sunday
    start = end - timedelta(days=7)
    week = start.isoformat()
    if AuditEvent.objects.filter(action="order.grants_emailed", target_id=week).exists():
        return 0
    grants = staff_grants(start, end)
    body = render_to_string(
        "shop/email/staff_grants.txt",
        {**grants, "start": start, "end": end - timedelta(days=1), "site_url": settings.SITE_URL},
    )
    counts = {name: len(grants[name]) for name in ("discounts", "offline", "free")}
    with transaction.atomic():
        target = ("shop.staffgrants", week, f"Week of {week}")
        record("order.grants_emailed", actor_type=ActorType.SYSTEM, target=target, details=counts)
        recipients = owners_emails()
        transaction.on_commit(
            lambda: [
                queue_text_email(address, f"Staff grants, week of {start:%d %b %Y}", body) for address in recipients
            ],
            robust=True,
        )
    return len(recipients)


# Phase B: finance


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def reconcile_payments(older_than=10):
    """Nightly (02:30): every online order still awaiting payment, made more than `older_than` minutes ago, asked of
    Razorpay (a lost webhook; a payment that failed and turned authorised within its 3 days: captured and recorded),
    staff orders' links included, as `manage.py reconcile_payments` does; then the B2B invoices' open links. A second
    run finds the paid ones paid (record_capture is once). Returns {"paid", "unpaid", "unknown"}."""
    from .models import InvoicePaymentLink

    counts = {"paid": 0, "unpaid": 0, "unknown": 0}
    words = {True: "paid", False: "unpaid", None: "unknown"}
    if not payments.configured():
        return counts
    for order in payments.awaiting_payment(older_than):
        try:
            counts[words[payments.reconcile(order)]] += 1
        except Exception:  # one order's trouble does not stop the others
            logger.exception("Reconciling order %s failed", order.number)
            counts["unknown"] += 1
    old = timezone.now() - timedelta(minutes=older_than)
    for link in InvoicePaymentLink.objects.filter(status=InvoicePaymentLink.Status.SENT, created__lt=old):
        try:
            counts[words[payments.reconcile_invoice_link(link)]] += 1
        except Exception:
            logger.exception("Reconciling the link for invoice %s failed", link.invoice)
            counts["unknown"] += 1
    return counts


@shared_task(
    autoretry_for=(IntegrationUnavailable,), retry_backoff=600, retry_backoff_max=3600, max_retries=4, **LONG_TASK
)
@single_run(LONG_TASK["time_limit"])
def fetch_settlements(day=None):
    """Daily (03:15): yesterday's Razorpay settlements (or `day`'s, YYYY-MM-DD) fetched, kept once, matched and
    posted to ERPNext once (shop.settlements), then the matched ones still waiting to be posted (the flow was off).
    Razorpay out of reach or its circuit open: tried again for about three hours. Not set up: nothing. Run twice, the
    same day changes nothing (settlements and lines are kept once each; a settlement posts once)."""
    from . import settlements

    when = date.fromisoformat(day) if day else settlements.yesterday()
    try:
        result = settlements.fetch_day(when)
    except settlements.NotConfigured as error:
        logger.info("Razorpay settlements not fetched: %s", error)
        return {"day": when.isoformat(), "not_configured": True}
    result["posted_waiting"] = settlements.post_waiting()
    return result
