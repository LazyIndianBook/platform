from datetime import timedelta

from django import template
from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from djmoney.money import Money

from insights import metrics
from shop.models import INR, OrderItem, Product, Review

register = template.Library()


@register.filter
def inr(value):
    """₹1,234.50 from a Money or a number."""
    return "" if value is None else str(value if isinstance(value, Money) else Money(value, INR))


@register.simple_tag
def shop_stats():
    """The admin index's shop block: orders and revenue today and in the last 30 days, and what waits for staff. Every
    number is the panel's own (insights/metrics.py: one definition, test-mode orders left out on a live site): orders
    paid online or placed with cash on delivery and not cancelled or refunded; revenue the money in less the money back
    (payments captured less refunds processed, a cash-on-delivery order when its parcel is delivered)."""
    today, month = metrics.last_days(1), metrics.last_days(30)
    return {
        "rows": [
            ("Orders", metrics.orders_placed(None, today).value, metrics.orders_placed(None, month).value),
            ("Revenue", inr(metrics.net_revenue(None, today).value), inr(metrics.net_revenue(None, month).value)),
        ],
        "to_pack": metrics.orders_to_pack(None).value,
        "to_deliver": metrics.orders_on_the_way(None).value,
        **store_stats(timezone.now() - timedelta(days=30)),
    }


def store_stats(since):
    """The store's section: orders and their value by day (two weeks), the books most sold in `since`, books running
    out (below SHOP_LOW_STOCK), reviews and quotation requests waiting for staff (test-mode orders left out)."""
    counted = metrics.live_orders()
    by_day = (
        counted.filter(placed_at__gte=timezone.now() - timedelta(days=14))
        .annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(orders=Count("pk"), value=Sum("total"))
        .order_by("-day")
    )
    top = (
        OrderItem.objects.filter(order__in=counted.filter(placed_at__gte=since))
        .values("title")
        .annotate(copies=Sum("quantity"))
        .order_by("-copies", "title")[:5]
    )
    low = Product.objects.filter(is_active=True, stock__lt=settings.SHOP_LOW_STOCK)
    return {
        "by_day": [(row["day"], row["orders"], inr(row["value"])) for row in by_day],
        "top_products": list(top),
        "low_stock": low.exclude(kind__in=[Product.Kind.BUNDLE, Product.Kind.DIGITAL]).order_by("stock", "title")[:10],
        "reviews_waiting": Review.objects.filter(status=Review.Status.PENDING).count(),
        "quotes_waiting": metrics.quotes_open(None, None).value,
    }
