from datetime import timedelta

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

from examleaf.images import og_image
from ops.tasks import queue_text_email

from . import invoices, payments, services
from .models import (
    Cart,
    CreditNote,
    Invoice,
    Order,
    Payment,
    Product,
    Refund,
    StockAlert,
    WebhookEvent,
    paise,
    public_storage,
)


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
        client, payment_id, ours = payments.client(), refund.payment.razorpay_payment_id, str(refund.pk)
        made = client.payment.fetch_multiple_refund(payment_id, timeout=payments.TIMEOUT).get("items", [])
        notes = [r["notes"] if isinstance(r.get("notes"), dict) else {} for r in made]  # Razorpay: [] when empty
        result = next((r for r, n in zip(made, notes, strict=True) if n.get("refund_id") == ours), None)
        try:
            result = result or client.payment.refund(
                payment_id,
                {
                    "amount": paise(refund.amount),
                    "speed": "normal",
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
        services.refund_processed(refund_id)


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=6)
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


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=6)
def generate_credit_note(refund_id):
    """The credit note of a processed refund of an invoiced order (none before the invoice exists: generate_invoice
    comes back here once it does). Numbered on the first try, the PDF made with WeasyPrint; a failure is retried."""
    refund = Refund.objects.get(pk=refund_id)
    invoice = Invoice.objects.filter(order=refund.order_id).first()
    if refund.status != Refund.Status.PROCESSED or invoice is None:
        return
    invoices.check_seller(not invoice.is_test)
    note = CreditNote.for_refund(refund, invoice)
    if not note.pdf:
        note.pdf.save(f"{note.number.replace('/', '-')}.pdf", ContentFile(invoices.render_pdf(note)))


@shared_task
def clean_up():
    """Daily (celery beat): cancel orders left unpaid (after asking Razorpay if they were paid after all); queue again
    the refunds, invoices and credit notes whose task was lost (broker down when queued, retries used up); delete guest
    carts untouched for 30 days, the record of webhooks too old to be accepted again, what was kept of the webhooks
    of payments older than Payment.PAYLOAD_DAYS, and the customer's details from orders never paid or placed, 30 days
    after they were cancelled."""
    services.expire_unpaid_orders(reconcile=payments.reconcile)
    hour_ago = timezone.now() - timedelta(hours=1)
    lost_refunds = Refund.objects.filter(status=Refund.Status.PENDING, razorpay_refund_id=None, created__lt=hour_ago)
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
def send_stock_alerts():
    """Hourly (celery beat): each address waiting for a product that has copies again gets one email, and its alert
    is deleted."""
    for product in Product.objects.filter(is_active=True, stock_alerts__isnull=False).distinct():
        if product.available < 1:
            continue
        alerts = list(product.stock_alerts.all())
        body = render_to_string("shop/email/back_in_stock.txt", {"product": product, "site_url": settings.SITE_URL})
        for alert in alerts:
            queue_text_email(alert.email, f"{product} is back in stock", body)
        StockAlert.objects.filter(pk__in=[alert.pk for alert in alerts]).delete()


@shared_task
def low_stock_report():
    """Daily (celery beat): the SALES role is emailed the books on sale with fewer than SHOP_LOW_STOCK copies (bundles
    have none of their own)."""
    low = Product.objects.filter(is_active=True, stock__lt=settings.SHOP_LOW_STOCK)
    low = low.exclude(kind__in=[Product.Kind.BUNDLE, Product.Kind.DIGITAL])  # no copies of their own
    if products := list(low.order_by("stock", "title")):
        context = {"products": products, "low_stock": settings.SHOP_LOW_STOCK}
        services.email_staff("Books running out", "shop/email/low_stock.txt", context)
