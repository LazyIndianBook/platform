from datetime import timedelta

from django import template
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from djmoney.money import Money

from shop.models import INR, Order, OrderItem, Product, QuoteRequest, Refund, Review

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
        **store_stats(since),
    }


def store_stats(since):
    """The store's section: orders and their value by day (two weeks), the books most sold in `since`, books running
    out (below SHOP_LOW_STOCK), reviews and quotation requests waiting for staff."""
    counted = Order.objects.counted()
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
        "quotes_waiting": QuoteRequest.objects.filter(status=QuoteRequest.Status.NEW).count(),
    }
