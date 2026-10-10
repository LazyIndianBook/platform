"""The shop's flows. Each one locks the rows it changes (select_for_update), runs the state-machine transitions and,
once the transaction is committed, sends the emails and queues the follow-up tasks. Views, admin actions, webhooks
and tasks all go through these functions (the REST API should too)."""

import logging
import re
import secrets
from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal

from allauth.account.utils import has_verified_email
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone
from django_fsm import can_proceed

from accounts.roles import SALES
from ops.tasks import queue_email, queue_text_email
from staff.config import site_setting

from . import invoices, signals, tasks, tax
from .cart import price
from .cart import totals as cart_totals
from .models import (
    INR,
    Coupon,
    CouponCode,
    CreditNote,
    Invoice,
    Offer,
    Order,
    OrderDiscount,
    OrderItem,
    OrderMessage,
    OrderNote,
    Payment,
    PinCode,
    Product,
    QuoteRequest,
    Refund,
    ReturnRequest,
    Shipment,
    live_mode,
    paise,
    rupees,
)

logger = logging.getLogger(__name__)
UNPAID_ORDERS_EXPIRE = timedelta(days=2)
STAFF_ORDERS_EXPIRE = timedelta(days=16)  # a day after their payment link (payments.LINK_DAYS)


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


class OfferUsedUp(ShopError):
    advice = "Please check your cart again: an offer has ended."
    while_paying = "an offer in the order was used up"


SUBJECTS = {
    "confirmation": "Order {} confirmed",
    "shipped": "Order {} is on its way",
    "delivered": "Order {} has been delivered",
    "cancelled": "Order {} cancelled",
    "refunded": "Refund for order {}",
    "link": "Your link to order {}",
    "payment_link": "Pay for order {}",
    "delivery_failed": "Order {} could not be delivered",  # a courier's news (shipping/messages.py)
    "returning": "Order {} is coming back to us",
    # Phase B: orders
    "packed": "Order {} is packed",
    "refund_started": "Your refund for order {} is on its way",
    "return_requested": "Your return request for order {}",
    "return_approved": "Your return for order {} is approved",
    "return_declined": "About your return for order {}",
    "return_label": "How to send back the books of order {}",
    "return_received": "The books of order {} are back with us",
    "invoice": "The invoice of order {}",
}


HTML_EMAILS = {"confirmation", "shipped", "payment_link"}  # with the order's lines: <kind>.html, the drawn layout


def sms_wanted(order, kind):
    """Whether this news goes by SMS too: a kind with an SMS (ops.sms.ORDER_SMS) whose DLT template is registered, to
    an account with a confirmed mobile number that asked for order updates by SMS."""
    from ops.sms import ORDER_SMS

    user = order.user
    if kind not in ORDER_SMS or not (user and user.login_phone_verified and user.sms_updates):
        return False
    return settings.SMS_BACKEND != "msg91" or bool(settings.MSG91_TEMPLATES.get(ORDER_SMS[kind]))


def notify(order, kind, sms=True, **context):
    """Email the customer (templates/shop/email/<kind>.txt) once the transaction is committed, and an SMS for the
    kinds ops.sms.send_order_sms sends (confirmation, shipped, delivered) to accounts that asked for them, unless
    `sms` is off (the shipping app sends a courier's news by SMS itself, never at night). The kinds in HTML_EMAILS
    have an HTML part of their own; the others get the one queue_email makes from the text. Each is an OrderMessage
    (the order's timeline); an SMS between 21:00 and 08:00 (India time) waits there for the morning (tasks.
    send_held_sms), as the shipping app's do."""
    from ops.sms import ORDER_SMS
    from shipping.messages import quiet  # (shipping.messages imports this module)

    wanted = sms and sms_wanted(order, kind)
    held = wanted and quiet()
    state = OrderMessage.Sms.HELD if held else OrderMessage.Sms.SENT if wanted else OrderMessage.Sms.NONE
    OrderMessage.objects.create(order=order, kind=kind, sms=state)
    sms = sms and kind in ORDER_SMS and not held  # ops.sms.send_order_sms checks the account's choice again

    def send():
        context_ = {"order": order, "site_url": settings.SITE_URL, "seller": settings.SHOP_SELLER, **context}
        if back := context.get("back"):  # a return's books, by title
            titles = dict(order.items.values_list("pk", "title"))
            context_["lines"] = [
                {"title": titles.get(line["item"], ""), "quantity": line["quantity"]} for line in back.lines
            ]
        context_["days"] = settings.SHOP_BANK_REFUND_DAYS
        body, subject = render_to_string(f"shop/email/{kind}.txt", context_), SUBJECTS[kind].format(order.number)
        if kind in HTML_EMAILS:
            html = render_to_string(f"shop/email/{kind}.html", {**context_, "title": subject})
            message = EmailMultiAlternatives(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX + subject, body, to=[order.email])
            message.attach_alternative(html, "text/html")
            queue_email(message)
        else:
            queue_text_email(order.email, subject, body)
        if not sms:
            return
        try:
            from ops.sms import send_order_sms
        except ImportError:  # the SMS gateway (work package A) not installed
            return
        send_order_sms(order, kind)

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


def claim_offers(order):
    """The usage limits of the order's automatic offers, checked again when it is placed, under a lock on each offer
    (in id order), as claim_coupon does for the coupon (M4): orders awaiting payment do not count as uses, so every
    order made before the first one is paid would otherwise keep the offer. Changes nothing; raises OfferUsedUp."""
    ids = order.discount_lines.exclude(offer=None).values_list("offer_id", flat=True)
    for offer in Offer.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
        if problem := offer.limit_problem(user=order.user, email=order.email):
            raise OfferUsedUp(f"The offer “{offer.name}” is {problem}.")


def release_stock(order):
    if order.stock_reserved:
        for pk, count in sorted(_stock_needed(order).items()):
            Product.objects.filter(pk=pk).update(stock=F("stock") + count)
        order.stock_reserved = False


COD_OPEN_ORDERS = 2  # placed with cash on delivery and not yet delivered, per account
CUSTOMER_METHODS = (Order.Method.RAZORPAY, Order.Method.COD)  # what a customer may choose at checkout
CUSTOMER_METHOD_CHOICES = [(method.value, method.label) for method in CUSTOMER_METHODS]


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


def create_order(cart, *, user, email, address, method, billing_state=""):
    """A pending order made from the cart at today's prices, with its payment. `address` is an Address snapshot;
    `billing_state` (a state code) is the place of supply of a cart of courses alone (shop/tax.py `billing_state`).
    Raises ShopError with what the customer must change first."""
    if method not in CUSTOMER_METHODS:  # "offline" is recorded by staff (record_offline_payment), never chosen
        raise ShopError("Choose online payment or cash on delivery.")
    if method == Order.Method.COD and not site_setting("SHOP_COD_ENABLED"):  # the panel may switch it
        raise ShopError("Cash on delivery is not available.")
    if method == Order.Method.COD and (problem := cod_problem(user)):
        raise ShopError(problem)
    if problem := PinCode.state_problem(address["pin"], address["state"]):  # a saved address older than the directory
        raise ShopError(f"{problem} Correct the delivery address.")
    result = cart_totals(cart, state=address["state"], user=user, email=email)
    if not result.lines:
        raise ShopError("Your cart is empty.")
    if problems := result.problems():
        raise ShopError(" ".join(problems))
    if any(line.product.has_digital for line in result.lines):
        if method == Order.Method.COD:
            raise ShopError("Cash on delivery is for printed books: please pay online for the course.")
        if user is None:
            raise ShopError("Please log in first: the course opens in your account.")
    if result.coupon_problem:
        raise ShopError(f"{result.coupon_problem} Remove the coupon to go on.")
    if method == Order.Method.COD and result.total > settings.SHOP_COD_MAX_VALUE:
        limit = f"₹{settings.SHOP_COD_MAX_VALUE:,}"
        raise ShopError(f"Cash on delivery is for orders up to {limit}: please pay this one online.")
    goods = any(not line.product.digital_only for line in result.lines)
    if billing_state and goods and billing_state != address.get("state"):
        raise ShopError("Books are taxed in the state they are delivered to: the billing state is for courses alone.")
    return save_order(
        result, user=user, email=email, shipping_address=address, payment_method=method, billing_state=billing_state
    )


def create_staff_order(lines, *, by, email, address, user=None, discount=0, shipping=None):
    """A phone or school order made by staff in the admin: `lines` (cart.Line) at today's prices with the offers, a
    staff discount in rupees and the shipping of the rates (or `shipping` rupees), waiting for a Razorpay Payment Link
    (payments.send_payment_link) or a payment recorded offline (record_offline_payment). Raises ShopError."""
    if problem := PinCode.state_problem(address["pin"], address["state"]):
        raise ShopError(f"{problem} Correct the delivery address.")
    result = price(lines, state=address["state"], user=user, email=email, staff_discount=discount)
    if shipping is not None:
        result.shipping = shipping
    if problems := result.problems():
        raise ShopError(" ".join(problems))
    if user is None and any(line.product.has_digital for line in lines):
        raise ShopError("A course opens in an account: give the email address of the customer's account.")
    if user is not None and user.consent_pending:  # as the website and the API refuse such a student's orders (L11)
        raise ShopError("This student's parent has not confirmed the account yet: no order until they do.")
    return save_order(result, user=user, email=email, shipping_address=address, created_by=by)


def save_order(result, billing_state="", **fields):
    """The order, its lines, its discounts and its payment, from cart.Totals. Each line keeps its tax as the HSN and
    SAC master gives it today (a bundle by its treatment), and the order its place of supply (shop/tax.py)."""
    today = timezone.localdate()
    taxes = [tax.order_line(line.product, today) for line in result.lines]
    state = tax.billing_state(result.lines, fields.get("shipping_address"), billing_state)
    code = result.coupon_code  # a single-use code (Phase B: catalogue): the order's alone, from this transaction
    with transaction.atomic():
        order = Order.objects.create(
            subtotal=result.subtotal,
            discount=result.discount,
            shipping_fee=result.shipping,
            total=result.total,
            coupon=result.coupon,
            coupon_code=code.code if code else result.coupon.code if result.coupon else "",
            livemode=live_mode(),  # online: set again from the keys that make its Razorpay order (payments)
            billing_state=state,
            **fields,
        )
        if code is not None:  # one order a code: another that took it meanwhile leaves this one unmade
            free = CouponCode.objects.filter(pk=code.pk, order=None)  # (a cancelled order frees it: models.py)
            if not free.update(order=order, used_by=fields.get("user"), used_at=timezone.now()):
                raise CouponUsedUp("This code has been used. Remove it to go on.")
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                product=line.product,
                title=line.product.title,
                mrp=line.product.mrp,
                unit_price=line.product.price,
                quantity=line.quantity,
                discount=line.discount,
                **taxed,
            )
            for line, taxed in zip(result.lines, taxes, strict=True)
        )
        OrderDiscount.objects.bulk_create(
            OrderDiscount(order=order, offer=saving.offer, label=saving.label, amount=saving.amount)
            for saving in result.savings
        )
        Payment.objects.create(order=order, method=order.payment_method, amount=order.total, livemode=order.livemode)
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
            claim_offers(order)
            reserve_stock(order)
            order.placed_at = timezone.now()
            assess_risk(order)
            order.save()
            notify(order, "confirmation")
            if order.held_at:
                held(order)
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
                mark_paid(order)
            except (OutOfStock, CouponUsedUp, OfferUsedUp) as error:
                order.cancel()
                order.save()
                why = error.while_paying
                refund = start_refund(order, f"{why.capitalize()} while the payment was made.", payment=payment)
                notify(order, "cancelled", reason=f"{why} while you were paying", refund=refund)
    return order


def mark_paid(order):
    """A pending order (locked) has been paid, online or offline: its coupon and offers claimed and its copies taken
    (raising CouponUsedUp, OfferUsedUp or OutOfStock before anything changes), then paid, its digital products opened
    (and an order of digital products only delivered at once), the customer emailed and the invoice queued."""
    claim_coupon(order)  # first: they change nothing, so a book sold out after them leaves no trace
    claim_offers(order)
    reserve_stock(order)
    order.pay()
    order.save()
    if order.has_digital:
        grant_course(order)
        if order.is_digital:
            order.deliver_digital()
            order.save()
    notify(order, "confirmation")
    transaction.on_commit(lambda: tasks.generate_invoice.delay(order.pk), robust=True)


def grant_course(order):
    """The `learn` app's entitlement for a paid order with a digital product (Phase 6 D), in the payment's transaction:
    if it fails, the payment is recorded again on Razorpay's retry. Skipped while the app is not installed."""
    try:
        from learn.services import grant_for_order
    except ImportError:
        logger.error("Order %s has a digital product but learn.services.grant_for_order is missing", order.number)
        return
    grant_for_order(order)


def revoke_course(order):
    """What a paid order with a digital product opened closes once it is cancelled or refunded in full
    (learn.services.revoke_for_order). Skipped while the app is not installed."""
    try:
        from learn.services import revoke_for_order
    except ImportError:
        return
    revoke_for_order(order)


def record_link_payment(link_id, entity, payload=None):
    """A payment made through one of our Razorpay Payment Links (the payment_link.paid webhook, or reconcile): the
    Razorpay order the link made is noted on the link's Payment, then the payment is recorded as any other
    (record_capture: amount checked, order paid once, refunded if it can no longer be paid). Other links: None."""
    payment = Payment.objects.filter(razorpay_payment_link_id=link_id).first()
    if payment is None or not same_mode(payment, "payment_link.paid"):
        return None
    Payment.objects.filter(pk=payment.pk, razorpay_order_id=None).update(razorpay_order_id=entity["order_id"])
    return record_capture(entity, payload)


def record_offline_payment(order, reference):
    """Staff record a payment received outside Razorpay (NEFT, IMPS or UPI to the bank account, e.g. for a school's
    quotation): a captured Payment with its reference (printed on the invoice), and the order paid (mark_paid).
    Raises ShopError when the order is not waiting for a payment, OutOfStock, CouponUsedUp or OfferUsedUp (nothing
    recorded)."""
    with transaction.atomic():
        order = _lock(order)
        if order.status != Order.Status.PENDING or order.placed_at or order.is_cod:
            raise ShopError(f"Order {order.number} is not waiting for a payment.")
        payment = Payment.objects.create(
            order=order, method=Order.Method.OFFLINE, amount=order.total, reference=reference, livemode=order.livemode
        )
        payment.capture()
        payment.save()
        order.payment_method = Order.Method.OFFLINE
        mark_paid(order)
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


PAID = [Payment.Status.CAPTURED, Payment.Status.REFUNDED]  # money came in (a payment refunded in part reads refunded)


def refundable(payment):
    """What is left to refund of a payment: what it took, less its refunds under way or made (a failed one gives
    nothing back). Several partial refunds may be made of one payment (Razorpay allows them too), never more."""
    if payment.status not in PAID:
        return Decimal("0.00")
    given = sum((r.amount.amount for r in payment.refunds.exclude(status=Refund.Status.FAILED)), Decimal("0.00"))
    return max(payment.amount.amount - given, Decimal("0.00"))


def online_payment(order):
    """The order's online payment that has something left to refund, or None."""
    online = order.payments.filter(method=Order.Method.RAZORPAY, status__in=PAID).order_by("pk")
    return next((payment for payment in online if refundable(payment) > 0), None)


def start_refund(order, reason, payment=None, by=None, amount=None, **fields):
    """Refund a captured online payment: what is left of it (all of it at first), or `amount` rupees (what Razorpay
    actually took; at most what is left), through Razorpay (tasks.refund_payment). Returns the Refund, or None when
    there is nothing to refund (unpaid, cash on delivery, refunded already: a refund under way counts). `fields`: the
    panel's details of the refund (its lines, shipping, speed …)."""
    payment = payment or online_payment(order)
    if payment is None or (left := refundable(payment)) <= 0:
        return None
    amount = left if amount is None else min(amount, left)
    refund = Refund.objects.create(order=order, payment=payment, amount=amount, reason=reason, created_by=by, **fields)
    transaction.on_commit(lambda: tasks.refund_payment.delay(refund.pk), robust=True)
    return refund


def refund_processed(refund_id, razorpay_refund_id=None, arn=""):
    """Razorpay has refunded (the API's answer or the refund.processed webhook), or FINANCE has transferred a refund
    by bank (mark_bank_refund_paid): payment refunded, order refunded unless another captured payment still pays it,
    customer told, the credit note made. Once."""
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status == Refund.Status.PROCESSED:
            return refund
        refund.status, refund.processed_at, refund.error = Refund.Status.PROCESSED, timezone.now(), ""
        refund.razorpay_refund_id = refund.razorpay_refund_id or razorpay_refund_id
        refund.arn = refund.arn or str(arn or "")[:40]  # the bank's reference: what a customer's bank asks for
        refund.save()
        payment = Payment.objects.select_for_update().get(pk=refund.payment_id)
        if can_proceed(payment.refund):
            payment.refund()
            payment.save()
        order = _lock(refund.order)
        if can_proceed(order.mark_refunded) and not order.payments.filter(status=Payment.Status.CAPTURED).exists():
            order.mark_refunded()
            order.save()
            if order.has_digital and refunded_in_full(order):  # a goodwill part-refund leaves the course open
                revoke_course(order)
        notify(order, "refunded", refund=refund)
        transaction.on_commit(lambda: tasks.generate_credit_note.delay(refund.pk), robust=True)  # if invoiced
    return refund


def refunded_in_full(order):
    """Whether the processed refunds of the order add up to what it cost (a refused parcel refunded less the shipping,
    or a goodwill part-refund, is not)."""
    refunded = sum(
        (refund.amount.amount for refund in order.refunds.filter(status=Refund.Status.PROCESSED)), Decimal(0)
    )
    return refunded >= order.total.amount


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
        cancelled(order)
        refund = start_refund(order, reason, by=by)
        if email:
            notify(order, "cancelled", reason=reason, refund=refund)
    return order


def cancelled(order):
    """The cancellation itself, of a locked order not yet shipped: the transition, its stock back, its course closed,
    a cash-on-delivery payment that will never come marked failed. Raises TransitionNotAllowed."""
    order.cancel()
    release_stock(order)
    order.save()
    if order.placed_at and order.has_digital:  # paid: its course was opened
        revoke_course(order)
    for payment in order.payments.select_for_update().filter(method=Order.Method.COD):
        if can_proceed(payment.fail):
            payment.fail("Order cancelled.")
            payment.save()


def pack_order(order):
    """Packed (paid, or placed to pay on delivery; not a test order, not on hold): the customer is told."""
    with transaction.atomic():
        order = _lock(order)
        order.pack()
        order.save()
        notify(order, "packed")
    return order


def ship_order(order, courier, tracking_number, tracking_url=""):
    """Shipped: the customer gets the courier, the number and a tracking link (the courier's page when staff leave
    `tracking_url` empty: Shipment.tracking_url_for)."""
    with transaction.atomic():
        order = _lock(order)
        order.ship()
        order.save()
        tracking_url = tracking_url or Shipment.tracking_url_for(courier, tracking_number)
        shipment = Shipment.objects.create(
            order=order, courier=courier, tracking_number=tracking_number, tracking_url=tracking_url
        )
        shipped(order, shipment)
    return order


def shipped(order, shipment, sms=True, email=True):
    """What follows order.ship(), in its transaction: the customer is told (the courier, the number, the link) and a
    cash-on-delivery order's bill is made, as it travels with the parcel. Also the shipping app's, when a courier's
    first scan says its parcel has left (it sends that SMS itself, `sms` off)."""
    if email:
        notify(order, "shipped", sms=sms, shipment=shipment)
    if order.is_cod:  # the bill travels with the parcel
        transaction.on_commit(lambda: tasks.generate_invoice.delay(order.pk), robust=True)
    signals.order_shipped.send(sender=Order, order=order, shipment=shipment)  # the erp app's delivery note


def deliver_order(order, sms=True):
    """Delivered: a cash-on-delivery payment is captured (the courier collected the cash) and the customer is told
    (the SMS unless `sms` is off: the shipping app sends a courier's news by SMS itself)."""
    with transaction.atomic():
        order = _lock(order)
        order.deliver()
        order.save()
        order.shipments.filter(delivered_at=None).update(delivered_at=timezone.now())
        for payment in order.payments.select_for_update().filter(method=Order.Method.COD):
            if can_proceed(payment.capture):  # the courier collected the cash
                payment.capture()
                payment.save()
        notify(order, "delivered", sms=sms)
    return order


def refund_order(order, reason, by=None, amount=None):
    """Staff's refund (admin): an order not yet shipped is cancelled (stock back) and refunded in full; a shipped or
    delivered one (damaged, refused, never arrived) is refunded in full or by `amount` rupees (at most what was
    paid). Returns the Refund or None."""
    if can_proceed(order.cancel):
        return cancel_order(order, reason, by=by).refunds.exclude(status=Refund.Status.FAILED).first()
    with transaction.atomic():
        order = _lock(order)
        return start_refund(order, reason, by=by, amount=amount or None)  # at most what is left of the payment


DELETED = "deleted"
FORGET_UNSOLD_AFTER = timedelta(days=30)  # after the cancellation of an order that was never paid or placed


def forget_orders(orders, today=None):
    """The customer's details leave these orders and their history: name, phone and address lines, and the email
    address, become "deleted" (town, district, state and PIN code stay, for the books), and staff's notes on them go.
    The orders themselves stay.
    Used by the daily clean-up for orders never paid or placed, and once a year by hand for invoiced orders past their
    eight years (RUNBOOK.md). An order whose tax documents must still be kept (72 months after its year's annual
    return: shop/tax.py `held_orders`, judged on `today`) is left as it is, whoever asks. Returns how many."""
    from django.core.files.storage import default_storage

    pks = list(orders.exclude(email=DELETED).values_list("pk", flat=True))
    held = tax.held_orders(pks, today)
    pks = [pk for pk in pks if pk not in held]
    for order in Order.objects.filter(pk__in=pks).only("shipping_address"):
        address = {**order.shipping_address, **dict.fromkeys(["name", "phone", "line1", "line2"], DELETED)}
        Order.objects.filter(pk=order.pk).update(email=DELETED, shipping_address=address)
    Order.history.filter(id__in=pks).update(email=DELETED)
    OrderNote.history.filter(order_id__in=pks).delete()  # staff's notes may name the customer
    OrderNote.objects.filter(order__in=pks).delete()
    returns = ReturnRequest.objects.filter(order__in=pks)
    for names in returns.exclude(photos=[]).values_list("photos", flat=True):  # the inspection's photographs
        for name in names:
            default_storage.delete(name)
    returns.update(note="", photos=[])  # the customer's words (their history keeps none), the evidence
    return len(pks)


def expire_unpaid_orders(reconcile=None):
    """Orders never paid (online) or placed (cash on delivery) within UNPAID_ORDERS_EXPIRE are cancelled (a payment
    arriving later is refunded), so an old checkout page cannot be paid at an old price and abandoned review pages do
    not pile up in the admin. `reconcile(order)` asks Razorpay first (payments.reconcile): an order whose payment was
    made but never reported is paid, not cancelled, and one that Razorpay could not be asked about waits for the next
    run. Returns how many were cancelled."""
    stale = Order.objects.filter(
        status=Order.Status.PENDING, placed_at__isnull=True, created__lt=timezone.now() - UNPAID_ORDERS_EXPIRE
    ).exclude(created_by__isnull=False, created__gte=timezone.now() - STAFF_ORDERS_EXPIRE)  # their links live longer
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


def staff_emails(role=SALES):
    """The addresses of the role's active members, or of the superusers while the role has none."""
    users = get_user_model().objects.filter(is_active=True)
    return list(users.filter(groups__name=role).values_list("email", flat=True)) or list(
        users.filter(is_superuser=True).values_list("email", flat=True)
    )


def email_staff(subject, template, context, role=SALES):
    """A text email (templates/<template>) to the role's members, once the transaction is committed."""

    def send():
        body = render_to_string(template, {"site_url": settings.SITE_URL, **context})
        for address in staff_emails(role):
            queue_text_email(address, subject, body)

    transaction.on_commit(send, robust=True)


def make_quotation(quote):
    """The quotation PDF at today's prices (invoices.quotation_context), valid QuoteRequest.VALID_DAYS days from now,
    in the private storage; it replaces an earlier one."""
    old = quote.quotation.name
    quote.quoted_at = timezone.now()
    quote.quotation.save(f"{quote.number}.pdf", ContentFile(invoices.render_pdf(quote)), save=False)
    if quote.status == QuoteRequest.Status.NEW:
        quote.status = QuoteRequest.Status.QUOTED
    quote.save()
    if old:
        quote.quotation.storage.delete(old)
    return quote


# Phase B: orders. The staff panel's flows (shop/staff_orders.py, shop/README.md): holds and tags, refunds by line and
# by bank, returns, a cash-on-delivery parcel back undelivered, a COD order's risk. Each writes its audit event in the
# caller's transaction (staff.audit.record: the request's member of staff, or the site itself).

HOLD_RISK = "payment check"  # the hold a high COD risk puts on an order (plan 5.3)
HOLDABLE = [Order.Status.PENDING, Order.Status.PAID, Order.Status.PACKED]  # not sent yet
TAG = re.compile(r"[\w][\w \-]{0,39}")
MAX_TAGS = 10
MAX_RETURN_PHOTOS = 5


def record(action, order, request=None, by=None, **kwargs):
    """An audit event about an order, by the request's member of staff, `by`, or the site itself."""
    from staff.audit import ActorType
    from staff.audit import record as audit

    system = by is None and request is None
    actor_type = ActorType.SYSTEM if system else None
    return audit(action, request=request, actor=by, actor_type=actor_type, target=order, **kwargs)


def assess_risk(order):
    """A cash-on-delivery order's risk of coming back unpaid (insights.jobs.risk.rto_risk over the shipping app's
    outcomes), kept on the order with its strongest three reasons; a high one puts it on hold ("payment check") while
    SHOP_COD_HIGH_RISK_HOLD is on, for staff to confirm with the customer first (plan 5.3). It never stops a checkout:
    a failure is logged and the order goes on unscored."""
    if not order.is_cod:
        return
    from insights.jobs.risk import history_for, rto_risk

    try:
        with transaction.atomic():  # a savepoint: a failed query leaves the checkout's own transaction usable
            risk = rto_risk(order, history_for(order))
    except Exception:
        logger.exception("Order %s: its COD risk could not be scored", order.number)
        return
    order.risk_bucket, order.risk_reasons = risk.bucket, risk.reasons[:3]
    if risk.bucket == Order.Risk.HIGH and site_setting("SHOP_COD_HIGH_RISK_HOLD"):
        order.held_at, order.held_by, order.hold_reason = timezone.now(), None, HOLD_RISK


def held(order, by=None, request=None):
    """What follows a hold, in its transaction: an inbox item for whoever changes orders, and the audit event."""
    from staff.models import InboxItem
    from staff.signals import open_item

    open_item(InboxItem.Kind.ORDER_HOLD, order, f"Order {order.number} is on hold", "shop.change_order")
    record("order.held", order, request, by, reason=order.hold_reason)


def hold(order, reason, by=None, request=None):
    """Hold an order not yet sent (an address to check, a payment to confirm): it leaves the packing queue and cannot
    be packed until released. Raises ShopError."""
    reason = " ".join(str(reason or "").split())[:200]
    if not reason:
        raise ShopError("Say why it waits: an address to check, a payment to confirm.")
    with transaction.atomic():
        order = _lock(order)
        if order.held_at:
            raise ShopError(f"Order {order.number} is on hold already ({order.hold_reason}).")
        if order.status not in HOLDABLE:
            raise ShopError(f"Order {order.number} is {order.get_status_display()}: only an order not yet sent waits.")
        order.held_at, order.held_by, order.hold_reason = timezone.now(), by, reason
        order.save()
        held(order, by, request)
    return order


def release(order, by=None, request=None):
    """Release a held order: it is back in the packing queue. Raises ShopError."""
    from staff.models import InboxItem
    from staff.signals import close_items

    with transaction.atomic():
        order = _lock(order)
        if not order.held_at:
            raise ShopError(f"Order {order.number} is not on hold.")
        reason = order.hold_reason
        order.held_at, order.held_by, order.hold_reason = None, None, ""
        order.save()
        close_items(order, InboxItem.Kind.ORDER_HOLD)
        record("order.released", order, request, by, reason=f"Was held: {reason}")
    return order


def set_tags(order, add=(), remove=(), by=None, request=None):
    """Add and remove an order's tags (words: "school", "awaiting reprint"; lower case, 40 characters at most, ten at
    most). Returns its tags. Raises ShopError."""

    def clean(names):
        return sorted({" ".join(str(name).split()).lower() for name in names if str(name).strip()})

    add, remove = clean(add), clean(remove)
    if bad := [name for name in add if not TAG.fullmatch(name)]:
        raise ShopError(f"A tag is a word or a few (letters, digits, spaces, hyphens; 40 at most): {', '.join(bad)}.")
    with transaction.atomic():
        order = _lock(order)
        before = sorted(order.tags.names())
        after = sorted((set(before) | set(add)) - set(remove))
        if len(after) > MAX_TAGS:
            raise ShopError(f"At most {MAX_TAGS} tags on an order.")
        if add:
            order.tags.add(*add)
        if remove:
            order.tags.remove(*remove)
        if before != after:
            record("order.tagged", order, request, by, changes={"tags": [before, after]})
    return after


# Refunds by line, with the shipping, to the source or by bank (staff.approvals "order.refund" runs them)


def refund_lines(order):
    """{item id: {item, value, refunded, given}} of an order: each line's invoiced value (its total less its share of
    the discounts, as its invoice prints it), the copies refunded of it already and the rupees given for them (refunds
    under way or made)."""
    items = list(order.items.select_related("product"))
    lines = {
        item.pk: {"item": item, "value": item.line_total.amount - share, "refunded": 0, "given": Decimal("0.00")}
        for item, share in zip(items, invoices.discount_shares(order, items), strict=True)
    }
    for refund in order.refunds.exclude(status=Refund.Status.FAILED).exclude(method=Refund.Method.NONE):
        for line in refund.lines:
            if entry := lines.get(int(line["item"])):
                entry["refunded"] += int(line["quantity"])
                entry["given"] += Decimal(str(line["amount"]))
    return lines


def price_lines(order, asked):
    """The lines asked for ([{item, quantity}], quantities from 0: a line left at 0 is not refunded) checked against
    the order and what was refunded of it, each with its amount: its invoiced value per copy, the last copies taking
    what is left of the line to the paisa. Raises ShopError."""
    known, priced, seen = refund_lines(order), [], set()
    for row in asked or []:
        try:
            pk, quantity = int(row["item"]), int(row["quantity"])
        except (KeyError, TypeError, ValueError) as error:
            raise ShopError("Each line: one of the order's items and its copies.") from error
        entry = known.get(pk)
        if entry is None or pk in seen:
            raise ShopError("Each line: one of the order's items, once.")
        seen.add(pk)
        if quantity == 0:
            continue
        left, item = entry["item"].quantity - entry["refunded"], entry["item"]
        if not 0 < quantity <= left:
            raise ShopError(f"{item.title}: {left} of {item.quantity} copies are left to refund.")
        if quantity == left:
            value = entry["value"] - entry["given"]
        else:
            value = rupees(entry["value"] * quantity / item.quantity)
        priced.append({"item": pk, "quantity": quantity, "amount": str(value)})
    return priced


def shipping_left(order):
    """The shipping not refunded yet."""
    given = sum((r.shipping_amount.amount for r in order.refunds.exclude(status=Refund.Status.FAILED)), Decimal(0))
    return max(order.shipping_fee.amount - given, Decimal("0.00"))


def refundable_payment(order):
    """The payment a refund of the order goes against, with something left of it: online first (refunded through
    Razorpay), else one by cash on delivery or recorded offline (refunded by bank or UPI). None: nothing to refund."""
    if payment := online_payment(order):
        return payment
    others = order.payments.filter(method__in=[Order.Method.COD, Order.Method.OFFLINE], status__in=PAID).order_by("pk")
    return next((payment for payment in others if refundable(payment) > 0), None)


def restock_lines(order, lines, reason, by=None, request=None):
    """The copies of these lines ([{item, quantity}]) back into stock (a bundle's books; a course has none), with the
    reason in the audit log (a return inspected, a refund's restock). Returns {product id: copies}."""
    items = {item.pk: item for item in order.items.select_related("product")}
    need = Counter()
    for line in lines:
        need.update(items[int(line["item"])].product.stock_lines(int(line["quantity"])))
    for pk, count in sorted(need.items()):
        Product.objects.filter(pk=pk).update(stock=F("stock") + count)
    record("order.restocked", order, request, by, reason=reason[:500], details={"copies": dict(need)})
    return need


def refund_with_details(order, payment, *, amount, reason, method, by=None, request=None, cancel=False, **details):
    """The panel's refund (staff.approvals "order.refund" with its details), in one transaction: an order not yet
    sent is cancelled first (its stock back) and refunded in full; then to the way it was paid (Razorpay: the task)
    or by bank or UPI to the account the customer gave (FINANCE transfers it and marks it paid: an inbox item due in
    SHOP_BANK_REFUND_DAYS); the copies refunded back into stock if asked; a return refunded; the customer told.
    `details`: lines, shipping, restock, speed, payee and payee_masked (encrypted already), change_request, key,
    back (the ReturnRequest). Returns the Refund. Raises ShopError."""
    from staff.models import InboxItem
    from staff.signals import open_item

    lines, back = details.get("lines") or [], details.get("back")
    fields = {
        "lines": lines,
        "shipping_amount": details.get("shipping") or Decimal("0.00"),
        "restock": bool(details.get("restock")),
        "speed": details.get("speed") or Refund.Speed.NORMAL,
        "change_request": details.get("change_request"),
        "idempotency_key": str(details.get("key") or "")[:80],
    }
    with transaction.atomic():
        order = _lock(order)
        if cancel:
            cancelled(order)
        if method == Refund.Method.SOURCE:
            refund = start_refund(order, reason, payment=payment, by=by, amount=amount, method=method, **fields)
            if refund is None:
                raise ShopError("Nothing was refunded: the payment has nothing left to refund.")
        else:
            if amount > refundable(payment):
                raise ShopError("Nothing was refunded: the payment has less left to refund.")
            refund = Refund.objects.create(
                order=order,
                payment=payment,
                amount=amount,
                reason=reason,
                created_by=by,
                method=method,
                payee=details.get("payee", ""),
                payee_masked=details.get("payee_masked", ""),
                **fields,
            )
            due = timezone.now() + timedelta(days=settings.SHOP_BANK_REFUND_DAYS)
            title = f"Refund #{refund.pk} of {order.number}: transfer it by bank or UPI"
            open_item(InboxItem.Kind.BANK_REFUND, order, title, "staff.approve_refund", due)  # one per order
        if fields["restock"] and lines:
            restock_lines(order, lines, f"Refund #{refund.pk}: {reason}", by, request)
        if back is not None:
            back = ReturnRequest.objects.select_for_update().get(pk=back.pk)
            back.refund = refund
            back.mark_refunded()
            back.save()
        if cancel:
            notify(order, "cancelled", reason=reason, refund=refund)
        elif method == Refund.Method.BANK:  # Razorpay's is told once it is made ("refunded"), within seconds
            notify(order, "refund_started", refund=refund)
    return refund


def mark_bank_refund_paid(refund, utr, by=None, request=None):
    """FINANCE transferred a refund by bank or UPI: its UTR kept, the refund processed (refund_processed: the payment
    and the order refunded, the customer told, the credit note made, once), the inbox item done. Raises ShopError."""
    from staff.models import InboxItem
    from staff.signals import close_items

    utr = " ".join(str(utr or "").split())
    if not 4 <= len(utr) <= 60:
        raise ShopError("The transfer's UTR or UPI reference (4 to 60 characters).")
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        if refund.method != Refund.Method.BANK:
            raise ShopError(f"Refund #{refund.pk} is not one by bank or UPI: Razorpay makes it.")
        if refund.status == Refund.Status.PROCESSED:
            raise ShopError(f"Refund #{refund.pk} was marked paid already (UTR {refund.utr}).")
        refund.utr, refund.paid_by = utr, by
        refund.save(update_fields=["utr", "paid_by", "modified"])
        refund_processed(refund.pk)
        waiting = Refund.objects.filter(order=refund.order_id, method=Refund.Method.BANK, status=Refund.Status.PENDING)
        if not waiting.exists():  # another transfer still due keeps the order's item open
            close_items(refund.order, InboxItem.Kind.BANK_REFUND)
        details = {"refund": refund.pk, "amount": refund.amount.amount, "utr": utr}
        record("refund.paid", refund.order, request, by, details=details)
    return Refund.objects.get(pk=refund.pk)


def cancel_returned(order, reason, by=None, restock=True, request=None):
    """A cash-on-delivery parcel back with us undelivered (RTO; decision 10.1): the order cancelled with the reason,
    nothing having been collected; its copies back into stock unless the parcel came back damaged; its invoice (made
    at dispatch) credited in full by a credit note that moves no money (Refund.Method.NONE); the parcel's RTO
    exception settled; the customer told. Raises TransitionNotAllowed for any other order."""
    from shipping.models import ShipmentDetail, ShippingException
    from shipping.services import close_exceptions

    with transaction.atomic():
        order = _lock(order)
        order.cancel_returned()
        if restock:
            release_stock(order)
        else:
            order.stock_reserved = False  # the copies came back damaged: none go back for sale
        order.save()
        for payment in order.payments.select_for_update().filter(method=Order.Method.COD):
            if can_proceed(payment.fail):
                payment.fail("Came back undelivered.")
                payment.save()
        if Invoice.objects.filter(order=order).exists():
            payment = order.payments.filter(method=Order.Method.COD).order_by("pk").first()
            if payment is None:
                logger.error("Order %s came back undelivered and has no COD payment: no credit note", order.number)
            else:
                note = Refund.objects.create(
                    order=order,
                    payment=payment,
                    amount=order.total.amount,
                    reason=reason[:200],
                    created_by=by,
                    status=Refund.Status.PROCESSED,
                    processed_at=timezone.now(),
                    method=Refund.Method.NONE,
                    restock=restock,
                )
                transaction.on_commit(lambda: tasks.generate_credit_note.delay(note.pk), robust=True)
        returned = ShipmentDetail.objects.filter(shipment__order=order, status="returned").select_related("shipment")
        for detail in returned:
            close_exceptions(detail.shipment, [ShippingException.Kind.RTO], "Order cancelled: came back undelivered.")
        notify(order, "cancelled", reason=reason, refund=None)
        record("order.cancelled", order, request, by, reason=reason, details={"returned": True, "restock": restock})
    return order


# Returns (RMA)


def delivered_on(order):
    """When the order was delivered: its parcels' latest delivery, else when its status turned delivered."""
    parcels = order.shipments.exclude(delivered_at=None).order_by("-delivered_at")
    when = parcels.values_list("delivered_at", flat=True).first()
    if when is None:
        rows = order.history.filter(status=Order.Status.DELIVERED).order_by("history_date")
        when = rows.values_list("history_date", flat=True).first()
    return when


def return_deadline(order):
    """The last moment a customer may ask for a return on the website (SHOP_RETURN_DAYS after delivery), or None."""
    when = delivered_on(order)
    return when + timedelta(days=settings.SHOP_RETURN_DAYS) if when else None


def returnable(order):
    """{item id: copies not yet asked back} of the order's books (returns declined do not count)."""
    left = {item.pk: item.quantity for item in order.items.select_related("product") if not item.product.digital_only}
    for back in order.returns.exclude(status=ReturnRequest.Status.DECLINED):
        for line in back.lines:
            if int(line["item"]) in left:
                left[int(line["item"])] -= int(line["quantity"])
    return left


def request_return(order, lines, reason, note="", by=None, by_customer=False, request=None):
    """A return asked for: by the customer on the website (a delivered order, within SHOP_RETURN_DAYS of delivery), or
    by staff for them (the window is the website's, not the law's: Rule 7(4) has none). Its books and copies, a reason
    code, the customer's words; an inbox item for whoever handles returns, due in 48 hours; the customer told.
    Raises ShopError with what to change."""
    from staff.models import InboxItem
    from staff.signals import open_item

    if reason not in ReturnRequest.Reason.values:
        raise ShopError("Choose a reason from the list.")
    with transaction.atomic():
        order = _lock(order)
        if order.status != Order.Status.DELIVERED:
            status = order.get_status_display()
            raise ShopError(f"Order {order.number} is {status}: only a delivered order is sent back.")
        if order.is_digital:
            raise ShopError("A course is not sent back: write to us about it through the contact page.")
        if by_customer and ((deadline := return_deadline(order)) is None or timezone.now() > deadline):
            days = settings.SHOP_RETURN_DAYS
            raise ShopError(f"A return is asked for within {days} days of delivery: write to us on the contact page.")
        if order.returns.filter(status__in=ReturnRequest.OPEN).exists():
            raise ShopError(f"A return of order {order.number} is under way already.")
        left, clean, seen = returnable(order), [], set()
        for row in lines or []:
            try:
                pk, quantity = int(row["item"]), int(row["quantity"])
            except (KeyError, TypeError, ValueError) as error:
                raise ShopError("Each line: one of the order's books and its copies.") from error
            if pk not in left or pk in seen:
                raise ShopError("Each line: one of the order's books, once.")
            seen.add(pk)
            if quantity and not 0 < quantity <= left[pk]:
                raise ShopError(f"At most {max(left[pk], 0)} copies of that book can be sent back.")
            if quantity:
                clean.append({"item": pk, "quantity": quantity})
        if not clean:
            raise ShopError("Choose the books to send back, and how many copies.")
        back = ReturnRequest.objects.create(
            order=order,
            lines=clean,
            reason=reason,
            note=str(note or "").strip()[:1000],
            by_customer=by_customer,
            requested_by=by if getattr(by, "pk", None) else None,
        )
        title = f"Return {back.number} of order {order.number}"
        due = timezone.now() + timedelta(hours=48)
        open_item(InboxItem.Kind.RETURN_REQUEST, back, title, "staff.handle_return", due)
        details = {"return": back.pk, "reason": reason, "lines": clean, "by_customer": by_customer}
        record("order.return_requested", order, request, by, details=details)
        notify(order, "return_requested", back=back)
    return back


def _locked_return(back):
    return ReturnRequest.objects.select_for_update().select_related("order").get(pk=back.pk)


def decide_return(back, approve, note="", by=None, request=None):
    """Approve a return (the customer is told how to send it back) or decline it, saying why (the customer is told
    the reason). Raises TransitionNotAllowed once decided, ShopError without a reason to decline."""
    from staff.models import InboxItem
    from staff.signals import close_items

    note = " ".join(str(note or "").split())[:300]
    if not approve and not note:
        raise ShopError("Say why it is declined: the customer is told.")
    with transaction.atomic():
        back = _locked_return(back)
        if approve:
            back.approve()
        else:
            back.decline()
        back.decision_note = note
        back.save()
        close_items(back, InboxItem.Kind.RETURN_REQUEST)
        verb = "approved" if approve else "declined"
        record(f"order.return_{verb}", back.order, request, by, reason=note, details={"return": back.pk})
        notify(back.order, f"return_{verb}", back=back)
    return back


def send_return_label(back, courier, awb, by=None, request=None):
    """The return label sent: the courier and the AWB the customer hands the parcel over with (the customer told).
    Raises TransitionNotAllowed, ShopError."""
    courier, awb = " ".join(str(courier or "").split())[:80], str(awb or "").strip()[:80]
    if not courier or not awb:
        raise ShopError("The courier and the return parcel's AWB.")
    with transaction.atomic():
        back = _locked_return(back)
        back.return_courier, back.return_awb = courier, awb
        back.send_label()
        back.save()
        record("order.return_label_sent", back.order, request, by, details={"return": back.pk, "courier": courier})
        notify(back.order, "return_label", back=back)
    return back


def receive_return(back, by=None, request=None):
    """The parcel sent back has arrived (with our label or the customer's own): the customer is told."""
    with transaction.atomic():
        back = _locked_return(back)
        back.receive()
        back.save()
        record("order.return_received", back.order, request, by, details={"return": back.pk})
        notify(back.order, "return_received", back=back)
    return back


def inspect_return(back, restock, by=None, request=None):
    """The parcel inspected: its copies back into stock (with the return as the reason), or kept apart as damaged.
    Its refund follows (staff.approvals "order.refund" naming the return). Raises TransitionNotAllowed."""
    with transaction.atomic():
        back = _locked_return(back)
        if restock:
            back.restock()
        else:
            back.mark_damaged()
        back.save()
        if restock:
            restock_lines(back.order, back.lines, f"Return {back.number}", by, request)
        outcome = "restocked" if restock else "damaged"
        record("order.return_inspected", back.order, request, by, details={"return": back.pk, "outcome": outcome})
    return back


def add_return_photo(back, upload, by=None, request=None):
    """A photograph of what came back (the inspection's evidence), in the private storage. Raises ShopError."""
    from django.core.files.storage import default_storage

    if len(back.photos) >= MAX_RETURN_PHOTOS:
        raise ShopError(f"At most {MAX_RETURN_PHOTOS} photographs of a return.")
    kinds = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    if getattr(upload, "content_type", "") not in kinds or upload.size > 5 * 1024 * 1024:
        raise ShopError("A photograph: a JPEG, PNG or WebP image of 5 MB at most.")
    name = default_storage.save(f"shop/returns/{back.pk}/{secrets.token_hex(8)}.{kinds[upload.content_type]}", upload)
    with transaction.atomic():
        back = _locked_return(back)
        back.photos = [*back.photos, name]
        ReturnRequest.objects.filter(pk=back.pk).update(photos=back.photos, modified=timezone.now())
        record("order.return_photo_added", back.order, request, by, details={"return": back.pk})
    return back


# The owners' weekly list of what staff gave away (tasks.weekly_staff_grants; inventory I6)


def staff_grants(start, end):
    """What was given away between two days (India time, the end excluded), for the owners' weekly email: orders made
    with a staff discount (its rupees and its share of the books after the offers), payments recorded offline, and
    orders of ₹0, each with who gave it. Test orders are left out on the live site."""
    from staff.models import AuditEvent

    tz = timezone.get_current_timezone()
    since, until = (timezone.make_aware(datetime.combine(day, time.min), tz) for day in (start, end))
    live = {"livemode": True} if live_mode() else {}
    orders = Order.objects.filter(created__gte=since, created__lt=until, **live).select_related("created_by")

    def who(user):
        return (user.full_name or user.email) if user else "a customer"

    discounts = []
    staff_lines = OrderDiscount.objects.filter(order__in=orders, offer=None, label="Discount")
    for line in staff_lines.select_related("order__created_by").order_by("pk"):
        order = line.order
        base = order.subtotal.amount - (order.discount.amount - line.amount.amount)  # the books after the offers
        share = (line.amount.amount * 100 / base).quantize(Decimal("0.1")) if base else Decimal(100)
        discounts.append(
            {"order": order.number, "by": who(order.created_by), "amount": line.amount.amount, "percent": share}
        )
    free = [{"order": order.number, "by": who(order.created_by)} for order in orders.filter(total=0).order_by("pk")]
    events = AuditEvent.objects.filter(action="payment.offline_recorded", ts__gte=since, ts__lt=until).order_by("id")
    events = list(events)
    counted = Order.objects.filter(pk__in={event.target_id for event in events}, **live)
    counted = {str(pk) for pk in counted.values_list("pk", flat=True)}
    staff = get_user_model().objects.filter(pk__in={event.actor_id for event in events})
    staff = {user.pk: user for user in staff}
    offline = [
        {"order": event.target_label, "by": who(staff.get(event.actor_id)), "amount": event.details.get("amount", "")}
        for event in events
        if event.target_id in counted
    ]
    return {"discounts": discounts, "offline": offline, "free": free}


# Documents and messages again (the panel's buttons for RUNBOOK's shell steps)


def invoiceable(order):
    """Whether the order has an invoice, or is to have one: paid (online or offline) from payment on, a cash-on-
    delivery order from its dispatch (the bill travels with the parcel)."""
    S = Order.Status
    if Invoice.objects.filter(order=order).exists():
        return True
    if order.is_cod:
        return order.status in (S.SHIPPED, S.DELIVERED, S.REFUNDED)
    return order.status in (S.PAID, S.PACKED, S.SHIPPED, S.DELIVERED, S.REFUNDED)


def regenerate_documents(order):
    """What is missing of the order's invoice and credit notes, queued for the worker (tasks.generate_invoice and
    generate_credit_note: numbered once, the PDF made once). Returns what was queued, in words. Raises ShopError when
    there is no invoice to make yet, nothing is missing, or the seller's details still hold a placeholder."""
    if not invoiceable(order):
        when = "once it is sent" if order.is_cod else "once it is paid"
        raise ShopError(f"Order {order.number} has no invoice yet: it is made {when}.")
    try:
        invoices.check_seller(order.livemode)
    except ImproperlyConfigured as error:
        raise ShopError(f"{error}: no invoice is numbered until then.") from error
    invoice, made = Invoice.objects.filter(order=order).first(), []
    if invoice is None or not invoice.pdf:
        made.append("the invoice")
        transaction.on_commit(lambda: tasks.generate_invoice.delay(order.pk), robust=True)  # its credit notes after it
    else:
        for refund in order.refunds.filter(status=Refund.Status.PROCESSED):
            note = CreditNote.objects.filter(refund=refund).first()
            if note is None or not note.pdf:
                made.append(f"the credit note of refund #{refund.pk}")
                transaction.on_commit(lambda pk=refund.pk: tasks.generate_credit_note.delay(pk), robust=True)
    if not made:
        raise ShopError(f"Nothing to make: order {order.number}'s invoice and credit notes exist.")
    return made


def renotify(order, kind):
    """A status message sent again (the email, and the SMS where the customer asked for them), only while what it says
    is true: placed or paid, packed, shipped (with the latest parcel), delivered, cancelled, refunded (the latest refund
    made). Returns what was sent, in words. Raises ShopError."""
    S = Order.Status
    latest = order.shipments.order_by("-shipped_at", "-pk").first()
    if kind in ("placed", "paid"):
        if order.placed_at is None or order.status in (S.CANCELLED, S.REFUNDED):
            raise ShopError(f"Order {order.number} is {order.get_status_display()}: no confirmation to send.")
        notify(order, "confirmation")
        return "the confirmation"
    true = {
        "packed": order.status in (S.PACKED, S.SHIPPED, S.DELIVERED),
        "shipped": order.status in (S.SHIPPED, S.DELIVERED) and latest is not None,
        "delivered": order.status == S.DELIVERED,
        "cancelled": order.status == S.CANCELLED,
        "refunded": order.refunds.filter(status=Refund.Status.PROCESSED).exclude(method=Refund.Method.NONE).exists(),
    }
    if not true[kind]:
        raise ShopError(f"Order {order.number} is {order.get_status_display()}: that message would not be true.")
    if kind == "shipped":
        notify(order, "shipped", shipment=latest)
    elif kind == "cancelled":
        refund = order.refunds.exclude(status=Refund.Status.FAILED).exclude(method=Refund.Method.NONE).first()
        notify(order, "cancelled", reason="", refund=refund)
    elif kind == "refunded":
        refund = order.refunds.filter(status=Refund.Status.PROCESSED).exclude(method=Refund.Method.NONE).first()
        notify(order, "refunded", refund=refund)
    else:
        notify(order, kind)
    return f"the {kind} message"
