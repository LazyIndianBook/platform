from datetime import timedelta

from django import template
from django.db.models import Count, Q, Sum
from django.utils import timezone
from djmoney.money import Money

from shop.models import INR, Order, Refund

register = template.Library()


@register.filter
def inr(value):
    """₹1,234.50 from a Money or a number."""
    return "" if value is None else str(value if isinstance(value, Money) else Money(value, INR))


@register.simple_tag
def shop_stats():
    """The admin index's shop block: orders (paid online, or placed with cash on delivery; not cancelled or refunded)
    and revenue (the same orders and the part-refunded ones, net of what was refunded) today and in the last 30 days,
    and the orders waiting for staff."""
    today, since = timezone.localdate(), timezone.now() - timedelta(days=30)
    sales = Order.objects.counted().aggregate(
        orders_today=Count("pk", filter=Q(placed_at__date=today)),
        orders_month=Count("pk", filter=Q(placed_at__gte=since)),
    )
    # revenue is what was kept: refused parcel refunded less the shipping (the order then reads "refunded") still
    # brings in the shipping, and a refunded order brings in nothing
    kept = Order.objects.filter(placed_at__isnull=False).exclude(status=Order.Status.CANCELLED)
    revenue = kept.aggregate(
        today=Sum("total", filter=Q(placed_at__date=today), default=0),
        month=Sum("total", filter=Q(placed_at__gte=since), default=0),
    )
    refunded = Refund.objects.filter(status=Refund.Status.PROCESSED, order__in=kept).aggregate(
        today=Sum("amount", filter=Q(order__placed_at__date=today), default=0),
        month=Sum("amount", filter=Q(order__placed_at__gte=since), default=0),
    )
    waiting = Order.objects.aggregate(
        to_pack=Count(
            "pk", filter=Q(status=Order.Status.PAID) | Q(status=Order.Status.PENDING, placed_at__isnull=False)
        ),
        to_deliver=Count("pk", filter=Q(status=Order.Status.SHIPPED)),
    )
    return {
        "rows": [
            ("Orders", sales["orders_today"], sales["orders_month"]),
            ("Revenue", inr(revenue["today"] - refunded["today"]), inr(revenue["month"] - refunded["month"])),
        ],
        **waiting,
    }
