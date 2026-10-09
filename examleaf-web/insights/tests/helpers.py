"""Helpers of the insights tests: days of a season's weeks, sales on given days, learners made quickly (no password)."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from accounts.models import User
from insights.jobs import week_start
from shop.factories import ADDRESS
from shop.models import Order, OrderItem

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
