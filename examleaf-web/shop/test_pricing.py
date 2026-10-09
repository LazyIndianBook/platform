"""The prior price (shop/pricing.py): the lowest selling price of the 30 days before a reduction, read from the
product's history, given beside a reduced price from SHOP_PRIOR_PRICE_FROM; the storefront's `prior_price`."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from shop import pricing
from shop.factories import ProductFactory
from shop.models import Product

pytestmark = pytest.mark.django_db
ON = date(2027, 2, 1)  # the rule in force (SHOP_PRIOR_PRICE_FROM: 1 January 2027)
SLUGS = count(1)


def priced(product, price, at):
    """The product's selling price set at `at` (a version of its history dated then)."""
    product.price = Decimal(price)
    product._history_date = at
    product.save()
    return product


def with_history(*steps, mrp="349.00"):
    """A product whose history holds these (price, days ago) steps, oldest first."""
    now = timezone.now()
    first, *rest = steps
    product = Product(title="Physics", slug=f"physics-{next(SLUGS)}", kind="sample-papers", mrp=Decimal(mrp))
    product.price, product._history_date = Decimal(first[0]), now - timedelta(days=first[1])
    product.save()
    for price, days_ago in rest:
        priced(product, price, now - timedelta(days=days_ago))
    return Product.objects.get(pk=product.pk)


def test_the_prior_price_is_the_lowest_price_of_the_30_days_before_the_reduction():
    product = with_history(("300", 50), ("250", 10), ("200", 0))  # 300 for 40 days, 250 for 10, then 200
    assert pricing.prior_price(product, on=ON) == Decimal("250.00")
    assert pricing.prior_price(product, on=date(2026, 12, 31)) is None  # before SHOP_PRIOR_PRICE_FROM
    raised = with_history(("200", 50), ("250", 10), ("300", 0))
    assert pricing.prior_price(raised, on=ON) is None  # not reduced
    level = with_history(("250", 50), ("200", 20), ("250", 0))
    assert pricing.prior_price(level, on=ON) is None  # back up: not below the lowest of the 30 days (200)


def test_a_short_rise_never_makes_the_prior_price_higher():
    # 300 for long, 350 for two days (a rise), then 200: the lowest of the 30 days is 300, never the rise's 350
    product = with_history(("300", 90), ("350", 2), ("200", 0))
    assert pricing.prior_price(product, on=ON) == Decimal("300.00")


def test_saves_that_keep_the_price_do_not_move_the_reduction():
    product = with_history(("300", 60), ("200", 20))
    product.title = "Physics, new cover"
    product.save()  # a version today with the same price: the reduction still began 20 days ago
    window = pricing.changes([product.pk])[product.pk]
    assert [price for _, price in window] == [Decimal("300.00"), Decimal("200.00")]
    assert pricing.prior_price(product, on=ON) == Decimal("300.00")


def test_a_product_newer_than_its_history_has_no_prior_price():
    assert pricing.prior_price(with_history(("199", 3)), on=ON) is None
    out_of_step = with_history(("300", 50))
    Product.objects.filter(pk=out_of_step.pk).update(price=Decimal("250"))  # an update that skipped the history
    assert pricing.prior_price(Product.objects.get(pk=out_of_step.pk), on=ON) == Decimal("300.00")


def test_a_proposed_price_shows_its_prior_price_before_it_is_saved():
    product = with_history(("300", 50), ("280", 5))
    answer = pricing.proposal(product, Decimal("250"), on=ON)
    assert (answer["lowest_in_30_days"], answer["prior_price"], answer["applies"]) == (280, 280, True)
    assert pricing.proposal(product, Decimal("290"), on=ON)["prior_price"] is None  # not below the lowest
    assert Product.objects.get(pk=product.pk).price.amount == Decimal("280.00")  # nothing changed


def test_the_storefront_gives_the_prior_price_from_its_day(settings):
    reduced = with_history(("300", 50), ("250", 10), ("200", 0))
    ProductFactory(slug="plain")
    api = APIClient()
    settings.SHOP_PRIOR_PRICE_FROM = timezone.localdate() + timedelta(days=1)
    assert api.get(f"/api/v1/products/{reduced.slug}/").json()["prior_price"] is None  # not in force yet
    settings.SHOP_PRIOR_PRICE_FROM = timezone.localdate()
    assert api.get(f"/api/v1/products/{reduced.slug}/").json()["prior_price"] == "250.00"
    listed = {row["slug"]: row["prior_price"] for row in api.get("/api/v1/products/").json()["results"]}
    assert listed == {reduced.slug: "250.00", "plain": None}


def test_the_storefront_list_reads_the_prior_prices_at_once(settings):
    settings.SHOP_PRIOR_PRICE_FROM = timezone.localdate()
    with_history(("300", 50), ("200", 0))
    api = APIClient()

    def queries():
        api.get("/api/v1/products/")
        with CaptureQueriesContext(connection) as captured:
            assert api.get("/api/v1/products/").status_code == 200
        return len(captured)

    one = queries()
    for days in (40, 41, 42):
        with_history(("300", days), ("250", 1))
    assert queries() == one
