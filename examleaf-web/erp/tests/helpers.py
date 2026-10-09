"""What the erp tests do over and over: orders through the shop's own flows, the relay, time passing."""

import json
from datetime import timedelta

from django.utils import timezone

from erp import contract, tasks
from erp.fake import FAKE
from erp.models import ErpOutbox
from shipping import services as shipping
from shop import services as shop
from shop import tasks as shop_tasks
from shop.factories import captured, make_order
from shop.models import Cart, Order

WEBHOOK_SECRET = "erp-webhook-secret-for-the-tests-0123456789"
PERSONAL = ["rahul", "das", "98640", "9864012345", "house 4", "zoo road", "example.com"]  # shop.factories.ADDRESS


def ordered(*lines, **kwargs):
    order = make_order(*lines, **kwargs)
    Cart.objects.filter(user=kwargs.get("user")).delete()  # as the checkout does: the next order has a cart again
    return order


def invoiced(order):
    """The order's invoice made, as the task after its payment (or its dispatch) does."""
    shop_tasks.generate_invoice(order.pk)
    return Order.objects.get(pk=order.pk)


def pay_online(order):
    """Razorpay's capture of the order's payment (as its webhook), then the invoice."""
    shop.record_capture(captured(order))
    return invoiced(order)


def pay_offline(order, reference="NEFT UTR 401234567890 from Rahul Das"):
    shop.record_offline_payment(order, reference)
    return invoiced(order)


def ship_by_hand(order, number="EA123456789IN"):
    shipping.ship_by_hand(shop.pack_order(order), "India Post", number)
    return Order.objects.get(pk=order.pk)


def refund(order, amount=None, reason="Damaged in transit: Rahul Das called from 98640 12345"):
    """A Razorpay refund processed (its credit note made, as the task does)."""
    made = shop.start_refund(order, reason, amount=amount)
    shop.refund_processed(made.pk, f"rfnd_{made.pk}")
    shop_tasks.generate_credit_note(made.pk)
    made.refresh_from_db()
    return made


def relay():
    return tasks.relay()


def relay_all():
    """The relay until nothing is due (time passing between runs)."""
    for _ in range(10):
        due_now()
        if not tasks.due().exists():
            return
        relay()


def due_now():
    """Time passes: every row waiting is due."""
    waiting = ErpOutbox.objects.exclude(state__in=[ErpOutbox.State.SENT, ErpOutbox.State.DISCARDED])
    waiting.update(next_at=timezone.now() - timedelta(seconds=1))


def rows(**filters):
    return list(ErpOutbox.objects.filter(**filters).order_by("pk"))


def row(event, **filters):
    return ErpOutbox.objects.get(event=event, **filters)


def code(product):
    return contract.item_code(product)


def stock_in(product, copies, batch="PR-2026-1"):
    """Copies received in ERPNext from the printer (its item made first)."""
    FAKE.receive(code(product), copies, batch=batch)


def no_personal_data(payload):
    text = json.dumps(payload).lower()
    return [word for word in PERSONAL if word in text]
