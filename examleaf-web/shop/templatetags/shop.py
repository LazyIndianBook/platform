from datetime import timedelta

from django import template
from django.db.models import Count, Q, Sum
from django.utils import timezone
from djmoney.money import Money

from shop.models import INR, Order

register = template.Library()


@register.filter
def inr(value):
    """₹1,234.50 from a Money or a number."""
    return "" if value is None else str(value if isinstance(value, Money) else Money(value, INR))


@register.simple_tag
def shop_stats():
    """The admin index's shop block: orders and revenue today and in the last 30 days (paid online, or placed with
    cash on delivery; cancelled and refunded ones left out), and the orders waiting for staff. Two queries."""
    today, since = timezone.localdate(), timezone.now() - timedelta(days=30)
    sales = Order.objects.counted().aggregate(
        orders_today=Count("pk", filter=Q(placed_at__date=today)),
        orders_month=Count("pk", filter=Q(placed_at__gte=since)),
        revenue_today=Sum("total", filter=Q(placed_at__date=today), default=0),
        revenue_month=Sum("total", filter=Q(placed_at__gte=since), default=0),
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
            ("Revenue", inr(sales["revenue_today"]), inr(sales["revenue_month"])),
        ],
        **waiting,
    }
