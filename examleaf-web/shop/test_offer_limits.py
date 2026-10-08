"""Offer limits with several pending orders (SECURITY_REVIEW_PHASE5_6.md M4): each order made before the first is paid
carries the offer, so the limits are checked again, under a lock, when an order is placed, as for coupons."""

from decimal import Decimal

import pytest

from shop import services
from shop.factories import ProductFactory, captured, make_order
from shop.models import Offer, Order, Refund

pytestmark = pytest.mark.django_db


@pytest.fixture
def first_order_offer():
    return Offer.objects.create(
        name="₹100 off your first order", kind="fixed", value=Decimal("100"), max_uses_per_customer=1
    )


def test_a_second_pending_order_with_a_once_per_customer_offer_is_refunded_when_paid(first_order_offer, rzp, commit):
    book = ProductFactory(price=Decimal("299.00"), stock=10)
    first, second = make_order((book, 1)), make_order((book, 1))
    assert first.discount.amount == second.discount.amount == Decimal("100.00")  # made while neither was paid
    with commit():
        services.record_capture(captured(first))
        services.record_capture(captured(second))
    first.refresh_from_db(), second.refresh_from_db()
    assert (first.status, second.status) == (Order.Status.PAID, Order.Status.REFUNDED)  # cancelled, then refunded
    refund = Refund.objects.get(order=second)
    assert refund.amount == second.total and "offer" in refund.reason


def test_the_last_use_of_an_offer_goes_to_one_cash_on_delivery_order_only(first_order_offer, settings):
    settings.SHOP_COD_ENABLED = True
    first_order_offer.max_uses_per_customer, first_order_offer.max_uses = None, 1
    first_order_offer.save()
    book = ProductFactory(price=Decimal("299.00"), stock=10)
    first = make_order((book, 1), method="cod", email="a@example.com")
    second = make_order((book, 1), method="cod", email="b@example.com")
    services.place_cod(first)
    with pytest.raises(services.OfferUsedUp, match="used up"):
        services.place_cod(second)
    second.refresh_from_db()
    assert second.placed_at is None and book.__class__.objects.get(pk=book.pk).stock == 9
