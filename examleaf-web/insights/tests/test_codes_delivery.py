"""Book codes redeemed per batch and district; days in transit per courier and district, and late parcels."""

from datetime import timedelta

import pytest
from django.utils import timezone

from insights.jobs import codes, delivery
from insights.models import CodeActivationStat, DeliveryStat
from learn.models import BookCode
from learn.services import make_codes
from shop.factories import ProductFactory
from shop.models import Shipment

from .helpers import learners, sell

pytestmark = pytest.mark.django_db
approx = pytest.approx


def test_codes_are_counted_per_batch_and_by_the_district_of_the_redeemers_order(physics, directory):
    """Batch PHY-1, 8 codes: five redeemed by buyers in Kamrup Metro (one 10 days ago), one in Jorhat (under 5: other
    districts), one by a student whose only order came after the redemption (unknown), one not redeemed."""
    make_codes(physics, 8, "PHY-1")
    make_codes(None, 2, "ALL-1")
    book, now = ProductFactory(subject=physics), timezone.now()
    people = learners(7)
    for person, pin in zip(people, ["781001"] * 5 + ["785001"], strict=False):
        sell(book, (now - timedelta(days=20)).date(), user=person, pin=pin)
    sell(book, now.date(), user=people[6], pin="781001")  # bought after redeeming: not where the code came from
    phy = list(BookCode.objects.filter(batch="PHY-1"))
    for code, person in zip(phy, people, strict=False):
        days = 10 if person == people[0] else 2
        BookCode.objects.filter(pk=code.pk).update(redeemed_by=person, redeemed_at=now - timedelta(days=days))
    codes.code_activation()
    rows = {(row.batch, row.district): row for row in CodeActivationStat.objects.all()}
    assert {key: (row.printed, row.redeemed, row.redeemed_7d) for key, row in rows.items()} == {
        ("PHY-1", None): (8, 7, 6),
        ("PHY-1", "Kamrup Metro"): (None, 5, 4),
        ("PHY-1", "other districts"): (None, 1, 1),
        ("PHY-1", "unknown"): (None, 1, 1),
        ("ALL-1", None): (2, 0, 0),
    }


def ship(order, courier, days, shipped=None):
    shipped = shipped or timezone.now() - timedelta(days=30)
    delivered = shipped + timedelta(days=days) if days is not None else None
    return Shipment.objects.create(
        order=order, courier=courier, tracking_number="EA1", shipped_at=shipped, delivered_at=delivered
    )


def test_days_in_transit_per_courier_and_district_and_parcels_past_the_p90(physics, directory):
    book, today = ProductFactory(subject=physics), timezone.localdate()
    for days in (2, 3, 4, 5, 10):
        ship(sell(book, today, pin="781001"), "India Post", days)
    for days in (1, 2):
        ship(sell(book, today, pin="785001"), "Delhivery", days)
    ship(sell(book, today, pin="785001"), "Delhivery", -3)  # delivered before it left: a typo, left out
    delivery.delivery_stats()
    rows = {(row.courier, row.district): (row.n, row.median_days, row.p90_days) for row in DeliveryStat.objects.all()}
    assert rows == {
        ("India Post", "Kamrup Metro"): (5, approx(4), approx(5 + 0.6 * 5)),  # P90 at position 3.6 of 2 3 4 5 10
        ("India Post", None): (5, approx(4), approx(8)),
        ("Delhivery", "Jorhat"): (2, approx(1.5), approx(1.9)),
        ("Delhivery", None): (2, approx(1.5), approx(1.9)),
    }
    order = sell(book, today, pin="781001")
    assert delivery.is_late(ship(order, "India Post", None, shipped=timezone.now() - timedelta(days=9)))
    assert not delivery.is_late(ship(order, "India Post", None, shipped=timezone.now() - timedelta(days=7)))
    assert delivery.is_late(ship(order, "India Post", 12))  # delivered, but after 12 days
    assert not delivery.is_late(ship(sell(book, today, pin="785001"), "Delhivery", None))  # 2 deliveries: no basis
