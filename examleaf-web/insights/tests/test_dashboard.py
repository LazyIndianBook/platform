"""The Django admin's dashboard on the metrics: its numbers are Home's (one definition each), the "Waiting" line
leaves out test-mode orders and shows each item only to whoever may open the list it links to."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from accounts import roles
from insights import metrics
from shop.factories import ProductFactory
from shop.models import Order
from shop.templatetags.shop import shop_stats, store_stats
from staff.tests.conftest import make_staff

from .helpers import as_test, pay, sell

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live: test-mode orders are then left out


def test_the_shop_block_counts_what_home_counts_and_leaves_out_the_test_orders():
    book = ProductFactory(price=Decimal("300.00"))
    today = timezone.localdate()
    pay(sell(book, today))
    pay(as_test(sell(book, today)))  # made with test keys on the live site
    sell(book, today, method="cod")
    stats = shop_stats()
    assert stats["rows"][0] == ("Orders", 2, 2)  # the same count as Home's orders
    assert stats["rows"][1] == ("Revenue", "₹300.00", "₹300.00")  # ... and its net revenue: the money in
    assert stats["rows"][0][1] == metrics.orders_placed(None, metrics.last_days(1)).value
    assert (stats["to_pack"], stats["to_deliver"]) == (2, 0)  # the test order is not waiting to be packed
    Order.objects.filter(pk=sell(book, today).pk).update(status="shipped")
    as_test(sell(book, today))
    Order.objects.filter(placed_at__isnull=False, livemode=False).update(status="shipped")
    assert shop_stats()["to_deliver"] == 1


def test_the_stores_days_and_most_sold_books_leave_out_the_test_orders_too():
    book = ProductFactory(title="Physics Sample Papers", price=Decimal("300.00"))
    sell(book, timezone.localdate(), copies=2)
    as_test(sell(book, timezone.localdate(), copies=5))
    found = store_stats(timezone.now() - timedelta(days=30))
    assert [(orders, value) for _, orders, value in found["by_day"]] == [(1, "₹600.00")]
    assert [(row["title"], row["copies"]) for row in found["top_products"]] == [("Physics Sample Papers", 2)]


def test_each_waiting_item_is_shown_only_to_whoever_may_open_its_list(client):
    orders_only = make_staff()
    orders_only.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="view_order"))
    client.force_login(orders_only)
    page = client.get(reverse("admin:index")).content.decode()
    assert "to pack" in page and "on the way" in page
    assert "to read" not in page and "quotation request" not in page  # no review or quotation permission
    assert "teacher request" not in page and "account deletion" not in page  # none of the people's lists
    client.force_login(make_staff(roles.SUPPORT))
    page = client.get(reverse("admin:index")).content.decode()
    assert "teacher request" in page and "account deletion" in page and "to read" in page
    editor = make_staff(roles.CONTENT_EDITOR)  # content, not people nor orders
    client.force_login(editor)
    page = client.get(reverse("admin:index")).content.decode()
    assert "teacher request" not in page and "account deletion" not in page and "to pack" not in page
