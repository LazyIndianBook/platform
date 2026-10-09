"""What each coupon and offer did while it ran, beside the same weeks last season (research-b2b-predictive.md 4.11):
the orders that used it, their revenue, the discount given, and a 95 % interval for all orders while it ran ÷ those
of the same weeks a year before. Small numbers are called inconclusive, and no offer is ever named the winner:
stopping as soon as a test looks good turns a 5 % false-positive rate into 26 % (Evan Miller)."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shop.models import Coupon, Offer

from .. import stats
from ..models import OfferStat
from . import counted_orders, save_stats

MIN_ORDERS = 30  # orders that used it, and orders in the baseline, before an interval means anything
YEAR = timedelta(weeks=52)  # "the same weeks last season": 52 weeks before, the same weekdays


def period(item, today):
    """The days a coupon or offer could be used within the last year: (first, last), or None."""
    start = max(timezone.localdate(item.valid_from), today - YEAR + timedelta(days=1))
    end = min(timezone.localdate(item.valid_until), today) if item.valid_until else today
    return (start, end) if start <= end else None


def given(item, orders):
    """What the coupon or offer took off these orders (an order older than the discount lines: its whole discount,
    which was the coupon's)."""
    total = Decimal(0)
    for order in orders:
        lines = list(order.discount_lines.all())
        if isinstance(item, Offer):
            total += sum((line.amount.amount for line in lines if line.offer_id == item.pk), Decimal(0))
        elif lines:
            total += sum((line.amount.amount for line in lines if line.label == f"Coupon {item.code}"), Decimal(0))
        else:
            total += order.discount.amount
    return total


def note(used, baseline, ran_before, interval):
    """What the numbers allow one to say; never that the coupon or offer worked."""
    if used < MIN_ORDERS or baseline < MIN_ORDERS:
        return (
            f"Not conclusive: {used} orders used it, {baseline} in those weeks last season (needs {MIN_ORDERS} each)."
        )
    if ran_before:
        return "Not conclusive: it ran in the same weeks last season too."
    low, high = interval
    if low <= 1 <= high:
        return f"Not conclusive: orders while it ran were {low:.2f} to {high:.2f} times last season's (95 %)."
    return f"Orders while it ran were {low:.2f} to {high:.2f} times last season's (95 %); other changes may explain it."


def effect(item, used, today, now):
    """The OfferStat of a coupon or offer: `used` is every counted order that used it."""
    start, end = period(item, today)
    orders = counted_orders()
    mine = list(used.filter(placed_at__date__gte=start, placed_at__date__lte=end).prefetch_related("discount_lines"))
    period_orders = orders.filter(placed_at__date__gte=start, placed_at__date__lte=end).count()
    baseline = list(orders.filter(placed_at__date__gte=start - YEAR, placed_at__date__lte=end - YEAR))
    ran_before = timezone.localdate(item.valid_from) <= end - YEAR and (
        item.valid_until is None or timezone.localdate(item.valid_until) >= start - YEAR
    )
    interval = stats.ratio_interval(period_orders, len(baseline))
    return OfferStat(
        coupon=item if isinstance(item, Coupon) else None,
        offer=item if isinstance(item, Offer) else None,
        period_start=start,
        period_end=end,
        orders=len(mine),
        revenue=sum((order.total.amount for order in mine), Decimal(0)),
        discount_cost=given(item, mine),
        period_orders=period_orders,
        baseline_orders=len(baseline),
        baseline_revenue=sum((order.total.amount for order in baseline), Decimal(0)),
        interval_low=interval[0] if interval else None,
        interval_high=interval[1] if interval else None,
        note=note(len(mine), len(baseline), ran_before, interval or (0, 0)),
        computed_at=now,
    )


@transaction.atomic
def offer_effectiveness(today=None):
    """An OfferStat for each coupon and offer used in the last year."""
    now = timezone.now()
    today = today or timezone.localdate(now)
    orders, rows, year_ago = counted_orders(), [], today - YEAR
    for coupon in Coupon.objects.filter(orders__placed_at__date__gt=year_ago).distinct():
        if period(coupon, today):
            rows.append(effect(coupon, orders.filter(coupon=coupon), today, now))
    for offer in Offer.objects.filter(order_lines__order__placed_at__date__gt=year_ago).distinct():
        if period(offer, today):
            rows.append(effect(offer, orders.filter(discount_lines__offer=offer).distinct(), today, now))
    return save_stats(OfferStat, rows, now)
