"""Days in transit (delivered − shipped) per courier and destination district over the last year, as the median and
the P90 (research-b2b-predictive.md 4.9); `is_late` marks a parcel past its route's P90, the time to chase the
courier. The median is what checkout could show as the expected delivery."""

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from shop.models import Shipment

from .. import stats
from ..models import DeliveryStat
from . import district, districts_of, save_stats

WINDOW = timedelta(days=365)
MIN_PARCELS = 5  # deliveries on a route before its own P90 counts; else the courier's to every district


def days_between(start, end):
    return (end - start).total_seconds() / 86400


@transaction.atomic
def delivery_stats(today=None):
    """A row per courier and district delivered to in the last year, and one per courier for every district."""
    now = timezone.now()
    delivered = Shipment.objects.filter(delivered_at__gte=now - WINDOW)
    rows = list(delivered.values_list("courier", "shipped_at", "delivered_at", "order__shipping_address"))
    known = districts_of(address for *_, address in rows)
    transit = defaultdict(list)
    for courier, shipped_at, delivered_at, address in rows:
        if (days := days_between(shipped_at, delivered_at)) >= 0:  # a delivery dated before its dispatch: a typo
            transit[courier, None].append(days)
            transit[courier, district(address, known)].append(days)
    stat_rows = []
    for (courier, where), days in transit.items():
        median, p90 = stats.quantile(days, 0.5), stats.quantile(days, 0.9)
        route = {"courier": courier, "district": where, "n": len(days), "computed_at": now}
        stat_rows.append(DeliveryStat(**route, median_days=median, p90_days=p90))
    return save_stats(DeliveryStat, stat_rows, now)


def is_late(shipment, now=None):
    """Whether a parcel is past the P90 of its route (its courier to its district, else its courier to anywhere, each
    with MIN_PARCELS deliveries): still on its way after longer, or delivered after longer. False without history."""
    newest = DeliveryStat.objects.aggregate(newest=Max("computed_at"))["newest"]
    address = shipment.order.shipping_address
    routes = DeliveryStat.objects.filter(computed_at=newest, courier=shipment.courier, n__gte=MIN_PARCELS)
    here = district(address, districts_of([address]))
    route = routes.filter(district=here).first() or routes.filter(district=None).first()
    if route is None:
        return False
    return days_between(shipment.shipped_at, shipment.delivered_at or now or timezone.now()) > route.p90_days
