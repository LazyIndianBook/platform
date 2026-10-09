"""Helpers of the insights tests: days of a season's weeks, sales on given days, learners made quickly (no password)."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from accounts.models import User
from insights.jobs import week_start
from shop.factories import ADDRESS
from shop.models import Order, OrderItem, Payment, Refund

EXAMS = {"2024-25": date(2025, 2, 12), "2025-26": date(2026, 2, 11), "2026-27": date(2027, 2, 17)}


def day_in(season, index, weekday=3):
    """A day of a season's week (0: its first week, 51: the week before the exam)."""
    return week_start(season, index) + timedelta(days=weekday)


def at_noon(day):
    return timezone.make_aware(datetime.combine(day, time(12)))


def sell(product, day, copies=1, method="razorpay", user=None, coupon=None, email="buyer@example.com", **address):
    """A paid order (cash on delivery: placed) of `copies` of the product on `day`, made with live keys."""
    amount = product.price.amount * copies
    order = Order.objects.create(
        user=user,
        email=email,
        shipping_address={**ADDRESS, **address},
        subtotal=amount,
        total=amount,
        status="pending" if method == "cod" else "paid",
        payment_method=method,
        placed_at=at_noon(day),
        livemode=True,
        coupon=coupon,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        title=product.title,
        hsn_code="4901",
        gst_rate=0,
        mrp=product.mrp,
        unit_price=product.price,
        quantity=copies,
    )
    return order


def learners(count, start=0):
    return User.objects.bulk_create(User(email=f"learner{start + n}@example.com", full_name="A") for n in range(count))


def at(day, hour=12, minute=0):
    """A moment of an India day."""
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def as_test(order):
    """The order made with test keys on the live site (livemode off): TEST everywhere, in no number."""
    Order.objects.filter(pk=order.pk).update(livemode=False)
    order.refresh_from_db()
    return order


def pay(order, amount=None, when=None):
    """A captured payment of the order, captured at `when` (its history says when, as the metrics read it)."""
    payment = Payment.objects.create(
        order=order,
        method=order.payment_method,
        amount=order.total.amount if amount is None else amount,
        livemode=order.livemode,
    )
    payment.capture()
    payment.save()
    if when is not None:
        Payment.history.filter(id=payment.pk, status="captured").update(history_date=when)
    return payment


def give_back(payment, amount, when=None, status="processed", method="source"):
    """A refund of the payment, processed at `when` (not yet processed: status="pending")."""
    return Refund.objects.create(
        order=payment.order,
        payment=payment,
        amount=amount,
        reason="Damaged",
        status=status,
        method=method,
        processed_at=when if status == "processed" else None,
    )
