from datetime import timedelta

import requests
from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from razorpay.errors import BadRequestError, GatewayError, ServerError

from . import invoices, payments, services
from .models import Cart, Invoice, Order, Refund, paise


@shared_task(
    autoretry_for=(requests.RequestException, GatewayError, ServerError),
    retry_backoff=60,
    retry_backoff_max=3600,
    max_retries=8,
)
def refund_payment(refund_id):
    """Ask Razorpay to refund a payment in full. Razorpay unreachable or failing: retried for about four hours.
    Refused (a bad request): the refund is marked failed for staff (admin, Refunds). The row stays locked during the
    call, so a task queued twice cannot refund twice."""
    with transaction.atomic():
        refund = Refund.objects.select_for_update().select_related("payment", "order").get(pk=refund_id)
        if refund.status != Refund.Status.PENDING or refund.razorpay_refund_id:
            return
        try:
            result = payments.client().payment.refund(
                refund.payment.razorpay_payment_id,
                {
                    "amount": paise(refund.amount),
                    "speed": "normal",
                    "receipt": f"refund-{refund.pk}",
                    "notes": {"order": refund.order.number, "refund_id": str(refund.pk)},
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
    invoice = Invoice.for_order(Order.objects.get(pk=order_id))
    if not invoice.pdf:
        invoice.pdf.save(f"{invoice.number.replace('/', '-')}.pdf", ContentFile(invoices.render_pdf(invoice)))


@shared_task
def clean_up():
    """Daily (celery beat): cancel online orders left unpaid; queue again the refunds and invoices whose task was lost
    (broker down when queued, retries used up); delete guest carts untouched for 30 days."""
    services.expire_unpaid_orders()
    hour_ago = timezone.now() - timedelta(hours=1)
    lost_refunds = Refund.objects.filter(status=Refund.Status.PENDING, razorpay_refund_id=None, created__lt=hour_ago)
    for pk in lost_refunds.values_list("pk", flat=True):
        refund_payment.delay(pk)
    S = Order.Status
    no_invoice = (
        Order.objects.filter(status__in=[S.PAID, S.PACKED, S.SHIPPED, S.DELIVERED], modified__lt=hour_ago)
        .filter(Q(invoice__isnull=True) | Q(invoice__pdf=""))
        .exclude(payment_method=Order.Method.COD, status__in=[S.PAID, S.PACKED])  # cash on delivery: at dispatch
    )
    for pk in no_invoice.values_list("pk", flat=True):
        generate_invoice.delay(pk)
    Cart.objects.filter(user=None, modified__lt=timezone.now() - timedelta(days=30)).delete()
