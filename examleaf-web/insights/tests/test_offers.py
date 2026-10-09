"""What a coupon or an offer did while it ran, beside the same weeks last season: never a winner."""

import math
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from insights.jobs import offers
from insights.models import OfferStat
from shop.factories import CouponFactory, ProductFactory
from shop.models import Offer, Order, OrderDiscount

from .helpers import at_noon, sell

pytestmark = pytest.mark.django_db
approx = pytest.approx


@pytest.fixture
def book(physics):
    return ProductFactory(subject=physics, price=Decimal(200))


def orders(book, count, day, coupon=None, off=None, old_discount=None):
    """`count` orders on `day`; `off`: the coupon's discount line on each; `old_discount`: an order's discount without
    lines, as orders made before the lines were kept have it."""
    for _ in range(count):
        order = sell(book, day, coupon=coupon)
        if off is not None:
            OrderDiscount.objects.create(order=order, label=f"Coupon {coupon.code}", amount=off)
        if old_discount is not None:
            Order.objects.filter(pk=order.pk).update(discount=old_discount)


def test_a_coupon_used_a_few_times_is_not_conclusive(book):
    today = timezone.localdate()
    coupon = CouponFactory(code="WELCOME10", valid_from=at_noon(today - timedelta(days=20)))
    orders(book, 3, today - timedelta(days=5), coupon=coupon, off=Decimal(20))
    orders(book, 2, today - timedelta(days=5))  # without it, the same days
    offers.offer_effectiveness()
    stat = OfferStat.objects.get()
    assert (stat.coupon, stat.orders, stat.revenue, stat.discount_cost) == (coupon, 3, Decimal(600), Decimal(60))
    assert (stat.period_start, stat.period_end, stat.period_orders, stat.baseline_orders) == (
        today - timedelta(days=20), today, 5, 0,
    )  # fmt: skip
    assert (stat.interval_low, stat.interval_high) == (None, None)
    assert stat.note == "Not conclusive: 3 orders used it, 0 in those weeks last season (needs 30 each)."


def test_with_enough_orders_it_gives_an_interval_and_still_names_no_winner(book):
    today = timezone.localdate()
    coupon = CouponFactory(code="BOARD2027", valid_from=at_noon(today - timedelta(days=13)))
    orders(book, 40, today - timedelta(days=3), coupon=coupon)  # 40 orders while it ran ...
    orders(book, 30, today - timedelta(weeks=52, days=3))  # ... and 30 in those days a year before
    offers.offer_effectiveness()
    stat = OfferStat.objects.get()
    half = 1.959964 * math.sqrt(1 / 40 + 1 / 30)
    assert (stat.interval_low, stat.interval_high) == (approx(4 / 3 * math.exp(-half)), approx(4 / 3 * math.exp(half)))
    assert stat.note == "Not conclusive: orders while it ran were 0.83 to 2.14 times last season's (95 %)."
    orders(book, 80, today - timedelta(days=3), coupon=coupon, old_discount=Decimal(20))  # 120 against 30
    offers.offer_effectiveness()
    stat = OfferStat.objects.latest("computed_at")
    assert stat.note == (
        "Orders while it ran were 2.68 to 5.97 times last season's (95 %); other changes may explain it."
    )  # above 1 whatever the noise, and still no claim that the coupon did it
    assert stat.discount_cost == 80 * Decimal(20)  # orders older than the discount lines: their whole discount


def test_an_offer_counts_its_own_discount_lines_and_says_when_it_ran_last_season_too(book):
    today = timezone.localdate()
    offer = Offer.objects.create(name="Board 2027 offer", value=10, valid_from=at_noon(today - timedelta(weeks=60)))
    for _ in range(31):
        order = sell(book, today - timedelta(days=2))
        OrderDiscount.objects.create(order=order, offer=offer, label=offer.name, amount=Decimal(20))
    orders(book, 31, today - timedelta(weeks=52, days=2))
    offers.offer_effectiveness()
    stat = OfferStat.objects.get()
    assert (stat.offer, stat.orders, stat.discount_cost) == (offer, 31, Decimal(620))
    assert stat.note == "Not conclusive: it ran in the same weeks last season too."
