"""Cart and coupon maths: paise, rounding, discounts, shipping zones, and the coupon rules."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from djmoney.money import Money

from accounts.factories import UserFactory
from shop.cart import totals
from shop.factories import CouponFactory, ProductFactory, ShippingRateFactory, make_cart, make_order
from shop.models import Coupon, Order, ShippingRate, financial_year, paise, rupees
from shop.services import cancel_order


def test_rupees_round_half_up_and_paise_are_whole():
    assert rupees("0.125") == Decimal("0.13") and rupees("2.675") == Decimal("2.68")
    assert paise(Money("299", "INR")) == 29900 and paise(Decimal("10.005")) == 1001 and paise("309.1") == 30910


def test_coupon_discounts_round_to_the_paisa_and_never_exceed_the_books():
    ten, fifteen = Coupon(kind="percent", value=10), Coupon(kind="percent", value=Decimal("15"))
    assert ten.discount_on(Decimal("1097.00")) == Decimal("109.70")
    assert fifteen.discount_on(Decimal("333.33")) == Decimal("50.00")  # 49.9995
    assert Coupon(kind="fixed", value=500).discount_on(Decimal("299.00")) == Decimal("299.00")


def test_financial_year_turns_in_april():
    assert financial_year(timezone.datetime(2027, 3, 31).date()) == "2026-27"
    assert financial_year(timezone.datetime(2027, 4, 1).date()) == "2027-28"


@pytest.mark.django_db
def test_cart_totals_shipping_by_zone_free_above_the_threshold_after_discount():
    ShippingRateFactory(name="Assam", states=["AS"], fee=40, free_above=499)
    ShippingRateFactory(name="Rest of India", states=[], fee=80, free_above=None)
    papers, solutions = ProductFactory(price=299), ProductFactory(price=249)
    cart = make_cart((papers, 1), (solutions, 1))
    assert totals(cart, state="AS").shipping == 0  # 548 ≥ 499
    assert totals(cart, state="DL").shipping == 80  # no rate names Delhi: the catch-all one
    cart.coupon = CouponFactory(value=10)
    result = totals(cart, state="AS")  # 548 − 54.80 = 493.20 < 499: shipping is charged again
    assert (result.subtotal, result.discount, result.shipping, result.total) == (
        Decimal("548.00"),
        Decimal("54.80"),
        Decimal("40.00"),
        Decimal("533.20"),
    )
    assert ShippingRate.fee_for("AS", Decimal(1)) == 40 and totals(None).total == 0


@pytest.mark.django_db
def test_coupon_rules():
    now, user = timezone.now(), UserFactory()
    assert CouponFactory(is_active=False).problem(Decimal(500)) == "This coupon code is not valid."
    assert CouponFactory(valid_from=now + timedelta(days=1)).problem(Decimal(500)) == "This coupon code is not valid."
    assert CouponFactory(valid_until=now - timedelta(minutes=1)).problem(Decimal(500)) == "This coupon has expired."
    assert "at least ₹299.00" in CouponFactory(min_order=299).problem(Decimal("298.99"))

    once = CouponFactory(max_uses=1, max_uses_per_customer=None)
    order = make_order((ProductFactory(), 1), coupon=once)
    assert once.problem(Decimal(500)) is None  # an unpaid order is not a use
    Order.objects.filter(pk=order.pk).update(placed_at=now)
    assert once.problem(Decimal(500)) == "This coupon has been used up."
    cancel_order(order, "test")  # a cancelled order gives the use back
    assert once.problem(Decimal(500)) is None

    mine = CouponFactory(max_uses_per_customer=1)
    placed = make_order((ProductFactory(), 1), coupon=mine, email=user.email.upper())  # as a guest, same address
    Order.objects.filter(pk=placed.pk).update(placed_at=now)
    assert mine.problem(Decimal(500), user=user) == "You have already used this coupon."
    assert mine.problem(Decimal(500), email="someone.else@example.com") is None


@pytest.mark.django_db
def test_coupon_code_is_case_insensitive_and_explains_refusals(client):
    product = ProductFactory()
    client.post("/api/v1/cart/items/", {"product": product.slug}, "application/json")  # the website's cart
    CouponFactory(code="Welcome10")
    assert Coupon.objects.get().code == "WELCOME10"
    cart = client.post("/api/v1/cart/coupon/", {"code": " welcome10 "}, "application/json").json()
    assert (cart["coupon"], cart["discount"]) == ("WELCOME10", "29.90")
    assert client.delete("/api/v1/cart/coupon/").json()["coupon"] is None
    response = client.post("/api/v1/cart/coupon/", {"code": "NOPE"}, "application/json")
    assert response.status_code == 400 and "This code cannot be applied to this cart." in response.text
    assert client.get("/api/v1/cart/").json()["discount"] == "0.00"
