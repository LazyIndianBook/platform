"""The shop's flows. Each one locks the rows it changes (select_for_update), runs the state-machine transitions and,
once the transaction is committed, sends the emails and queues the follow-up tasks. Views, admin actions, webhooks
and tasks all go through these functions (the REST API should too)."""

import logging
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from allauth.account.utils import has_verified_email
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone
from django_fsm import can_proceed

from ops.tasks import queue_text_email

from . import tasks
from .cart import totals as cart_totals
from .models import INR, Coupon, Order, OrderItem, Payment, Product, Refund, Shipment, live_mode, paise

logger = logging.getLogger(__name__)
UNPAID_ORDERS_EXPIRE = timedelta(days=2)


class ShopError(Exception):
    """Something the customer must fix (shown to them as it is)."""

    advice = ""  # what to do about it, for the pages that send the customer back to the cart
    while_paying = ""  # how it reads in the email of an order cancelled because of it ("… while you were paying")


class OutOfStock(ShopError):
    advice = "Please change your cart."
    while_paying = "the books sold out"


class CouponUsedUp(ShopError):
    advice = "Please remove the coupon from your cart."
    while_paying = "the coupon was used up"


SUBJECTS = {
    "confirmation": "Order {} confirmed",
    "shipped": "Order {} is on its way",
    "delivered": "Order {} has been delivered",
    "cancelled": "Order {} cancelled",
    "refunded": "Refund for order {}",
    "link": "Your link to order {}",
}


def notify(order, kind, **context):
    """Email the customer (templates/shop/email/<kind>.txt) once the transaction is committed."""

    def send():
        body = render_to_string(f"shop/email/{kind}.txt", {"order": order, "site_url": settings.SITE_URL, **context})
        queue_text_email(order.email, SUBJECTS[kind].format(order.number), body)

    transaction.on_commit(send, robust=True)


LINK_SENT = "If an order matches, we have emailed you a link."
COUPON_REFUSED = "This code cannot be applied to this cart."  # unknown, expired, used up or too small a cart alike


def email_order_link(number, email):
    """Guests' lookup: the link of the guest order with this number and email address (if there is one) is emailed to
    that address. Orders of accounts are left out: their owners log in."""
    if order := Order.objects.filter(number=number, email__iexact=email, user__isnull=True).first():
        notify(order, "link")


def _stock_needed(order):
    need = Counter()
    for item in order.items.select_related("product"):
        need.update(item.product.stock_lines(item.quantity))
    return need


def reserve_stock(order):
    """Take the order's copies from stock: on payment, or when a cash-on-delivery order is placed. The product rows
    are locked in id order (no deadlock between two checkouts) and checked first, so the last copy sells once."""
    need = _stock_needed(order)
    products = Product.objects.select_for_update().filter(pk__in=need).order_by("pk")
    if short := [product.title for product in products if product.stock < need[product.pk]]:
        raise OutOfStock(f"Sold out: {', '.join(short)}.")
    for pk, count in need.items():
        Product.objects.filter(pk=pk).update(stock=F("stock") - count)
    order.stock_reserved = True


def coupon_problem(order):
    """Why the order's coupon can no longer be used for it (a limit reached since the order was made), or None."""
    if order.coupon_id and (coupon := Coupon.objects.filter(pk=order.coupon_id).first()):
        return coupon.limit_problem(user=order.user, email=order.email)
    return None


def claim_coupon(order):
    """The coupon's limits, checked again when the order is placed, under a lock on the coupon: the check at checkout
    cannot stop several pending orders from each taking the last use (or one customer's second use), and only orders
    placed count as uses. Changes nothing; raises CouponUsedUp."""
    if order.coupon_id:
        Coupon.objects.select_for_update().filter(pk=order.coupon_id).first()  # one placement at a time per coupon
        if problem := coupon_problem(order):
            raise CouponUsedUp(problem)


def release_stock(order):
    if order.stock_reserved:
        for pk, count in sorted(_stock_needed(order).items()):
            Product.objects.filter(pk=pk).update(stock=F("stock") + count)
        order.stock_reserved = False


COD_OPEN_ORDERS = 2  # placed with cash on delivery and not yet delivered, per account


def cod_problem(user):
    """Why this customer may not order with cash on delivery now, or None. A cash-on-delivery order holds stock and
    sends a parcel before anything is paid: only accounts with a confirmed email address, COD_OPEN_ORDERS at a time."""
    if user is None or not has_verified_email(user):
        return "Cash on delivery is for accounts with a confirmed email address: log in, or pay online."
    on_the_way = [Order.Status.PENDING, Order.Status.PACKED, Order.Status.SHIPPED]
    placed = user.orders.filter(payment_method=Order.Method.COD, placed_at__isnull=False, status__in=on_the_way)
    if placed.count() >= COD_OPEN_ORDERS:
        return f"You have {COD_OPEN_ORDERS} cash-on-delivery orders on their way already: please pay this one online."
    return None


def create_order(cart, *, user, email, address, method):
    """A pending order made from the cart at today's prices, with its payment. `address` is an Address snapshot.
    Raises ShopError with what the customer must change first."""
    if method == Order.Method.COD and not settings.SHOP_COD_ENABLED:
        raise ShopError("Cash on delivery is not available.")
    if method == Order.Method.COD and (problem := cod_problem(user)):
        raise ShopError(problem)
    result = cart_totals(cart, state=address["state"], user=user, email=email)
    if not result.lines:
        raise ShopError("Your cart is empty.")
    if problems := result.problems():
        raise ShopError(" ".join(problems))
    if result.coupon_problem:
        raise ShopError(f"{result.coupon_problem} Remove the coupon to go on.")
    if method == Order.Method.COD and result.total > settings.SHOP_COD_MAX_VALUE:
        limit = f"₹{settings.SHOP_COD_MAX_VALUE:,}"
        raise ShopError(f"Cash on delivery is for orders up to {limit}: please pay this one online.")
    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            email=email,
            shipping_address=address,
            payment_method=method,
            subtotal=result.subtotal,
            discount=result.discount,
            shipping_fee=result.shipping,
            total=result.total,
            coupon=result.coupon,
            coupon_code=result.coupon.code if result.coupon else "",
            livemode=live_mode(),  # online: set again from the keys that make its Razorpay order (payments)
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                product=line.product,
                title=line.product.title,
                hsn_code=line.product.hsn_code,
                gst_rate=line.product.gst_rate,
                mrp=line.product.mrp,
                unit_price=line.product.price,
                quantity=line.quantity,
            )
            for line in result.lines
        )
        Payment.objects.create(order=order, method=method, amount=order.total, livemode=order.livemode)
    return order


def _lock(order):
    return Order.objects.select_for_update().get(pk=order.pk)


def place_cod(order):
    """Cash on delivery: the order is placed now (stock taken, confirmation sent) and paid when delivered."""
    with transaction.atomic():
        order = _lock(order)
        if order.placed_at is None and order.is_cod and order.status == Order.Status.PENDING:
            get_user_model().objects.select_for_update().filter(pk=order.user_id).first()  # one placement at a time
            if problem := cod_problem(order.user):  # checked again: several orders may wait to be placed
                raise ShopError(problem)
            claim_coupon(order)
            reserve_stock(order)
            order.placed_at = timezone.now()
            order.save()
            notify(order, "confirmation")
    return order


def same_mode(payment, what):
    """Whether the payment was made with keys of the mode (test or live) the site runs on now. Anything from the other
    mode is logged and ignored: a test payment never pays, refunds or completes an order on the live site."""
    if payment.livemode == live_mode():
        return True
    mode = "live" if payment.livemode else "test"
    logger.warning("Razorpay %s for payment #%s (%s mode) ignored: the site's keys are not", what, payment.pk, mode)
    return False


def _lock_payment(entity, payload):
    payment = Payment.objects.select_for_update().get(razorpay_order_id=entity["order_id"])
    if payload is not None:  # from a webhook: its payment's allowed fields; an update, so a repeat adds no history
        payment.raw_payload = {name: entity[name] for name in Payment.PAYLOAD_FIELDS if name in entity}
        Payment.objects.filter(pk=payment.pk).update(raw_payload=payment.raw_payload)
    return payment


def record_capture(entity, payload=None):
    """A captured Razorpay payment (`entity` from the API or a webhook): the payment is marked captured and the order
    paid, once. Calling it again (a repeated webhook; the webhook and the return page both arriving, in either order)
    changes nothing. A payment that cannot pay its order (wrong amount, order cancelled meanwhile, books sold out) is
    refunded in full."""
    with transaction.atomic():
        payment = _lock_payment(entity, payload)
        if not same_mode(payment, "capture"):
            return payment.order
        if payment.status in (Payment.Status.CAPTURED, Payment.Status.REFUNDED):
            if entity["id"] != payment.razorpay_payment_id:
                _refund_second_payment(payment, entity)
            return payment.order
        payment.razorpay_payment_id = entity["id"]
        payment.capture()
        payment.save()
        order = _lock(payment.order)
        if entity["amount"] != paise(payment.amount) or entity["currency"] != INR:
            logger.error("Razorpay payment %s does not match order %s; refunding it", entity["id"], order.number)
            taken = Decimal(entity["amount"]) / 100
            start_refund(order, "The amount paid did not match the order.", payment=payment, amount=taken)
        elif order.status != Order.Status.PENDING:
            start_refund(order, f"Paid while the order was {order.get_status_display()}.", payment=payment)
        else:
            try:
                claim_coupon(order)  # first: it changes nothing, so a book sold out after it leaves no trace
                reserve_stock(order)
            except (OutOfStock, CouponUsedUp) as error:
                order.cancel()
                order.save()
                why = error.while_paying
                refund = start_refund(order, f"{why.capitalize()} while the payment was made.", payment=payment)
                notify(order, "cancelled", reason=f"{why} while you were paying", refund=refund)
            else:
                order.pay()
                order.save()
                notify(order, "confirmation")
                transaction.on_commit(lambda: tasks.generate_invoice.delay(order.pk), robust=True)
    return order


def _refund_second_payment(first, entity):
    """A captured payment of a Razorpay order that another payment has paid already (a late or repeated UPI payment):
    recorded as a Payment of its own and refunded in full, once."""
    if Payment.objects.filter(razorpay_payment_id=entity["id"]).exists():
        return  # recorded before
    order = first.order
    logger.error("Razorpay payment %s is a second payment for order %s; refunding it", entity["id"], order.number)
    second = Payment.objects.create(
        order=order,
        method=Order.Method.RAZORPAY,
        amount=Decimal(entity["amount"]) / 100,
        razorpay_payment_id=entity["id"],
        livemode=first.livemode,
    )
    second.capture()
    second.save()
    start_refund(order, "Paid twice: the second payment is refunded.", payment=second)


def record_failure(entity, payload=None):
    """A failed Razorpay payment attempt. The order stays pending: Checkout lets the customer try again."""
    with transaction.atomic():
        payment = _lock_payment(entity, payload)
        if can_proceed(payment.fail):  # never after a capture (a late webhook of an earlier, failed attempt)
            payment.fail(entity.get("error_description") or "The payment failed.")
            payment.save()


def start_refund(order, reason, payment=None, by=None, amount=None):
    """Refund a captured online payment in full (or `amount` rupees: what Razorpay actually took), through Razorpay
    (tasks.refund_payment), unless a refund of it is already under way. Returns the Refund, or None when there is
    nothing to refund (unpaid, cash on delivery)."""
    captured = order.payments.filter(method=Order.Method.RAZORPAY, status=Payment.Status.CAPTURED)
    payment = payment or captured.exclude(refunds__status__in=[Refund.Status.PENDING, Refund.Status.PROCESSED]).first()
    if (
        payment is None
        or payment.status != Payment.Status.CAPTURED
        or payment.refunds.exclude(status=Refund.Status.FAILED).exists()
    ):
        return None
    amount = payment.amount if amount is None else amount
    refund = Refund.objects.create(order=order, payment=payment, amount=amount, reason=reason, created_by=by)
    transaction.on_commit(lambda: tasks.refund_payment.delay(refund.pk), robust=True)
    return refund


def refund_processed(refund_id, razorpay_refund_id=None):
    """Razorpay has refunded (the API's answer or the refund.processed webhook): payment refunded, order refunded
    unless another captured payment still pays it, customer told. Once."""
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status == Refund.Status.PROCESSED:
            return refund
        refund.status, refund.processed_at, refund.error = Refund.Status.PROCESSED, timezone.now(), ""
        refund.razorpay_refund_id = refund.razorpay_refund_id or razorpay_refund_id
        refund.save()
        payment = Payment.objects.select_for_update().get(pk=refund.payment_id)
        if can_proceed(payment.refund):
            payment.refund()
            payment.save()
        order = _lock(refund.order)
        if can_proceed(order.mark_refunded) and not order.payments.filter(status=Payment.Status.CAPTURED).exists():
            order.mark_refunded()
            order.save()
        notify(order, "refunded", refund=refund)
        transaction.on_commit(lambda: tasks.generate_credit_note.delay(refund.pk), robust=True)  # if invoiced
    return refund


def refund_failed(refund_id, error):
    Refund.objects.filter(pk=refund_id).exclude(status=Refund.Status.PROCESSED).update(
        status=Refund.Status.FAILED, error=error[:255]
    )
    logger.error("Razorpay refused refund %s: %s", refund_id, error)


def cancel_order(order, reason, by=None, email=True):
    """Cancel an order that has not left (pending, paid or packed): its stock goes back and an online payment is
    refunded in full. Raises django_fsm.TransitionNotAllowed once the order has been shipped."""
    with transaction.atomic():
        order = _lock(order)
        order.cancel()
        release_stock(order)
        order.save()
        for payment in order.payments.select_for_update().filter(method=Order.Method.COD):
            if can_proceed(payment.fail):
                payment.fail("Order cancelled.")
                payment.save()
        refund = start_refund(order, reason, by=by)
        if email:
            notify(order, "cancelled", reason=reason, refund=refund)
    return order


def pack_order(order):
    with transaction.atomic():
        order = _lock(order)
        order.pack()
        order.save()
    return order


def ship_order(order, courier, tracking_number, tracking_url=""):
    with transaction.atomic():
        order = _lock(order)
        order.ship()
        order.save()
        shipment = Shipment.objects.create(
            order=order, courier=courier, tracking_number=tracking_number, tracking_url=tracking_url
        )
        notify(order, "shipped", shipment=shipment)
        if order.is_cod:  # the bill travels with the parcel
            transaction.on_commit(lambda: tasks.generate_invoice.delay(order.pk), robust=True)
    return order


def deliver_order(order):
    with transaction.atomic():
        order = _lock(order)
        order.deliver()
        order.save()
        order.shipments.filter(delivered_at=None).update(delivered_at=timezone.now())
        for payment in order.payments.select_for_update().filter(method=Order.Method.COD):
            if can_proceed(payment.capture):  # the courier collected the cash
                payment.capture()
                payment.save()
        notify(order, "delivered")
    return order


def refund_order(order, reason, by=None, amount=None):
    """Staff's refund (admin): an order not yet shipped is cancelled (stock back) and refunded in full; a shipped or
    delivered one (damaged, refused, never arrived) is refunded in full or by `amount` rupees (at most what was
    paid). Returns the Refund or None."""
    if can_proceed(order.cancel):
        return cancel_order(order, reason, by=by).refunds.exclude(status=Refund.Status.FAILED).first()
    with transaction.atomic():
        order = _lock(order)
        paid = order.payments.filter(status=Payment.Status.CAPTURED).first()
        amount = min(amount, paid.amount.amount) if amount and paid else None
        return start_refund(order, reason, by=by, amount=amount)


DELETED = "deleted"
FORGET_UNSOLD_AFTER = timedelta(days=30)  # after the cancellation of an order that was never paid or placed


def forget_orders(orders):
    """The customer's details leave these orders and their history: name, phone and address lines, and the email
    address, become "deleted" (town, district, state and PIN code stay, for the books). The orders themselves stay.
    Used by the daily clean-up for orders never paid or placed, and once a year by hand for invoiced orders past their
    eight years (RUNBOOK.md). Returns how many."""
    pks = list(orders.exclude(email=DELETED).values_list("pk", flat=True))
    for order in Order.objects.filter(pk__in=pks).only("shipping_address"):
        address = {**order.shipping_address, **dict.fromkeys(["name", "phone", "line1", "line2"], DELETED)}
        Order.objects.filter(pk=order.pk).update(email=DELETED, shipping_address=address)
    Order.history.filter(id__in=pks).update(email=DELETED)
    return len(pks)


def expire_unpaid_orders(reconcile=None):
    """Orders never paid (online) or placed (cash on delivery) within UNPAID_ORDERS_EXPIRE are cancelled (a payment
    arriving later is refunded), so an old checkout page cannot be paid at an old price and abandoned review pages do
    not pile up in the admin. `reconcile(order)` asks Razorpay first (payments.reconcile): an order whose payment was
    made but never reported is paid, not cancelled, and one that Razorpay could not be asked about waits for the next
    run. Returns how many were cancelled."""
    stale = Order.objects.filter(
        status=Order.Status.PENDING, placed_at__isnull=True, created__lt=timezone.now() - UNPAID_ORDERS_EXPIRE
    )
    cancelled = 0
    for order in stale:
        try:
            known = reconcile(order) if reconcile and not order.is_cod else False
        except Exception:  # one order's trouble must not stop the others, or the rest of the daily clean-up
            logger.exception("Reconciling order %s failed", order.number)
            continue
        if known is not False:  # paid, or not known: not cancelled
            continue
        with transaction.atomic():
            locked = _lock(order)
            if locked.status == Order.Status.PENDING and locked.placed_at is None:  # paid meanwhile: leave it
                cancel_order(locked, "Not paid within two days.", email=False)
                cancelled += 1
    return cancelled
