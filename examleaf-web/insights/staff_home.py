"""Home, for the panel (API.md "Home and reports (staff)"): `GET /api/v1/staff/home/` answers the cards of the person's
roles, each a number with its definition, when it was worked out and the list or report it links to, already filtered.
Any member of staff may ask: the permissions decide the cards (insights/metrics.py: a card needs the permissions of its
data, and is for certain roles), so a packer is given the orders to pack and a finance member the refunds to approve,
and an owner the money. Totals (net revenue, orders, codes redeemed, active learners) carry the previous period of the
same length; a queue (orders to pack, tickets, reports) is the figure of this moment. Test mode is kept out of every
number (`test_orders_left_out` says how many test orders were left out; on a site on test keys `test_mode` is true).

The cards fail one by one: a number that cannot be worked out (a source that does not answer) is a card with an `error`
and no value, never a Home that does not open. A card whose source is not installed (Finance, Course, Support not
merged yet) is left out."""

import logging
from decimal import Decimal

from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from api.schema import AutoSchema
from shop.models import Order, live_mode
from staff.api import StaffView
from staff.permissions import ANY_STAFF

from . import metrics

logger = logging.getLogger(__name__)

PERIODS = {"today": (1, "Today"), "week": (7, "The last 7 days"), "month": (30, "The last 30 days")}
DEFAULT_PERIOD = "week"
FAILED = "This number could not be worked out just now."


class HomeSchema(AutoSchema):
    def get_tags(self):
        return ["home (staff)"]


class HomeSpanSerializer(serializers.Serializer):
    start = serializers.DateField(help_text="the first day (India's calendar)")
    end = serializers.DateField(help_text="the last day, included")
    days = serializers.IntegerField()


class HomePeriodSerializer(HomeSpanSerializer):
    key = serializers.CharField(help_text="today, week or month")
    label = serializers.CharField()


class HomeComparisonSerializer(serializers.Serializer):
    previous = serializers.CharField(help_text="the same figure for the period before, of the same length")
    difference = serializers.CharField(help_text="this period's less the previous one's, signed")
    percent = serializers.CharField(
        allow_null=True, help_text="the difference as a signed percent of the previous; null from 0"
    )
    period = HomeSpanSerializer()


class HomeCardSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    group = serializers.CharField(help_text="measure (a total) or queue (what waits for a person)")
    unit = serializers.CharField(help_text="inr (rupees, two places) or count")
    value = serializers.CharField(
        allow_null=True, help_text="a decimal string for rupees, a whole number else; null with an error"
    )
    definition = serializers.CharField(
        help_text="how it is counted, in words (shown on hover and in 'How this is counted')"
    )
    as_of = serializers.DateTimeField(help_text="when it was worked out")
    period = HomeSpanSerializer(allow_null=True, help_text="the days a total covers; null for a queue")
    href = serializers.CharField(help_text="the console's list or report it counts, already filtered")
    test_mode = serializers.BooleanField(help_text="made of test-mode rows (the site runs on test keys)")
    comparison = HomeComparisonSerializer(allow_null=True)
    error = serializers.CharField(allow_blank=True)


class HomeSerializer(serializers.Serializer):
    as_of = serializers.DateTimeField()
    period = HomePeriodSerializer(help_text="the period of the totals")
    test_mode = serializers.BooleanField(help_text="the site runs on test keys: every number is of test-mode rows")
    test_orders_left_out = serializers.IntegerField(
        help_text="orders placed in the periods shown that were made with test keys on the live site, left out"
    )
    cards = HomeCardSerializer(many=True)


def figure(unit, value):
    """A value as the API writes it: rupees with two places, a count as a whole number."""
    return f"{Decimal(value):.2f}" if unit == "inr" else str(int(value))


def span(period):
    return {"start": period.start, "end": period.end, "days": period.days} if period else None


def comparison(unit, now, before):
    """The previous period beside this one: its figure, the signed difference and the percent it is of it."""
    now, then = Decimal(now), Decimal(before.value)
    difference = now - then
    sign = f"{difference:+.2f}" if unit == "inr" else f"{int(difference):+d}"
    percent = None if then == 0 else f"{difference / then * 100:+.1f}"
    return {"previous": figure(unit, then), "difference": sign, "percent": percent, "period": span(before.period)}


def card(spec, user, period):
    """One card of Home, or None when its source is not installed."""
    window = metrics.last_days(spec.days) if spec.days else period
    href = spec.href.replace("{period}", f"?from={window.start}&to={window.end}")
    try:
        found = spec.run(user, window)
        before = spec.run(user, window.previous()) if spec.compares else None
    except metrics.Absent:
        return None
    except Exception:  # one number failing is a card with an error, not a Home that does not open
        logger.exception("Home: the card %s could not be worked out", spec.key)
        return {
            "key": spec.key,
            "label": spec.label,
            "group": spec.group,
            "unit": spec.unit,
            "value": None,
            "definition": spec.definition,
            "as_of": timezone.now(),
            "period": span(window if spec.compares else None),
            "href": href,
            "test_mode": False,
            "comparison": None,
            "error": FAILED,
        }
    return {
        "key": spec.key,
        "label": spec.label,
        "group": spec.group,
        "unit": spec.unit,
        "value": figure(spec.unit, found.value),
        "definition": found.definition,
        "as_of": found.as_of,
        "period": span(found.period),
        "href": href,
        "test_mode": found.test_mode,
        "comparison": comparison(spec.unit, found.value, before) if before else None,
        "error": "",
    }


def test_orders_left_out(user, period):
    """Test-mode orders placed in the period shown or the one before it, which a live site leaves out of its numbers
    (0 where the person may not read orders, or the site runs on test keys: nothing is left out there)."""
    if not live_mode() or not user.has_perm("shop.view_order"):
        return 0
    placed = metrics.rows(Order.objects.filter(livemode=False), user, "shop.view_order")
    return placed.filter(placed_at__gte=period.previous().since, placed_at__lt=period.until).count()


class HomeView(StaffView, generics.GenericAPIView):
    """Home's cards for the person who asks: the totals over `?period=` (today, week or month; week by default), the
    queues as they stand now."""

    schema = HomeSchema()
    permissions = {"GET": ANY_STAFF}
    pagination_class = None
    filter_backends = []
    serializer_class = HomeSerializer

    @extend_schema(
        parameters=[OpenApiParameter("period", str, enum=list(PERIODS), description="the totals' period (week)")],
        responses=HomeSerializer,
    )
    def get(self, request, *args, **kwargs):
        key = request.query_params.get("period") or DEFAULT_PERIOD
        if key not in PERIODS:
            raise serializers.ValidationError({"period": [f"One of {', '.join(PERIODS)}."]})
        days, label = PERIODS[key]
        period = metrics.last_days(days)
        user = request.user
        cards = [each for each in (card(spec, user, period) for spec in metrics.visible(user)) if each]
        answer = {
            "as_of": timezone.now(),
            "period": {**span(period), "key": key, "label": label},
            "test_mode": not live_mode(),
            "test_orders_left_out": test_orders_left_out(user, period),
            "cards": cards,
        }
        return Response(HomeSerializer(answer).data)


urlpatterns = [path("", HomeView.as_view(), name="home")]  # under /api/v1/staff/home/ (staff/urls.py)
