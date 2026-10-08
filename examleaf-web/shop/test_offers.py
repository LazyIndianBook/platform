"""Phase 6 E2: automatic offers beside coupons, the discount split kept on order lines, invoices and credit notes."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from shop import invoices, services
from shop.cart import split, totals
from shop.factories import CouponFactory, ProductFactory, captured, make_cart, make_order, verified_user
from shop.models import Category, Collection, CollectionItem, CreditNote, Invoice, Offer, OrderItem, Refund

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
D = Decimal


def test_split_adds_up_exactly_and_never_takes_more_than_a_line():
    assert split(D("10.00"), [D("299.00"), D("299.00"), D("299.00")]) == [D("3.34"), D("3.33"), D("3.33")]
    assert split(D("0.02"), [D("1"), D("1"), D("1")]) == [D("0.01"), D("0.01"), D("0.00")]
    shares = split(D("100.00"), [D("99.99"), D("0.01")])
    assert shares == [D("99.99"), D("0.01")] and sum(split(D("7.77"), [D("5"), D("0")])) == D("7.77")
    assert split(D("5"), [D("0"), D("0")]) == [D("0.00"), D("0.00")]


@pytest.fixture
def science():
    shelf = Category.objects.add_root({"name": "Science", "slug": "science"})
    physics = ProductFactory(title="Physics", price=D("299.00"))
    physics.categories.add(shelf)
    return shelf, physics


def offer(**fields):
    return Offer.objects.create(**{"name": "Board offer", "value": D("10"), **fields})


def test_a_category_offer_takes_its_share_from_its_own_lines_only(science):
    shelf, physics = science
    other = ProductFactory(title="Other", price=D("299.00"))
    offer(scope=Offer.Scope.CATEGORIES).categories.add(shelf)
    result = totals(make_cart((physics, 2), (other, 1)))
    assert [(s.label, s.amount) for s in result.savings] == [("Board offer", D("59.80"))]
    assert [line.discount for line in result.lines] == [D("59.80"), D("0.00")] and result.discount == D("59.80")


def test_the_coupon_comes_first_then_combinable_offers_and_alone_offers_never_with_a_coupon(science):
    shelf, physics = science
    offer(name="Ten off", kind="fixed", value=D("10"))
    offer(name="Alone", value=D("50"), combinable=False)
    cart = make_cart((physics, 1))
    assert [s.label for s in totals(cart).savings] == ["Alone"]  # 149.50 beats 10.00
    cart.coupon = CouponFactory(code="WELCOME10")
    cart.save()
    result = totals(cart)
    assert [(s.label, s.amount) for s in result.savings] == [("Coupon WELCOME10", D("29.90")), ("Ten off", D("10.00"))]
    assert result.total == D("259.10")


def test_an_offer_needs_its_copies_value_dates_and_uses_left(science, rzp, commit):
    _, physics = science
    big = offer(min_quantity=2, min_value=D("500"), max_uses=1, max_uses_per_customer=1)
    assert not totals(make_cart((physics, 1))).savings  # one copy, 299
    assert totals(make_cart((physics, 2))).savings[0].offer == big
    Offer.objects.filter(pk=big.pk).update(valid_from=timezone.now() + timedelta(days=1))
    assert not totals(make_cart((physics, 2))).savings
    Offer.objects.filter(pk=big.pk).update(valid_from=timezone.now() - timedelta(days=2))
    order = make_order((physics, 2))
    assert order.discount_lines.get().offer == big  # made, not placed: not a use yet
    assert totals(make_cart((physics, 2))).savings
    with commit():
        services.record_capture(captured(order))
    assert not totals(make_cart((physics, 2))).savings  # used up
    assert big.limit_problem(email="rahul@example.com") == "used up"


def test_the_order_lines_invoice_and_credit_note_keep_the_split_and_older_orders_theirs(science, rzp, commit):
    shelf, physics = science
    other = ProductFactory(title="Other", price=D("100.00"))
    offer(scope=Offer.Scope.PRODUCTS).products.add(physics)
    coupon = CouponFactory(code="SAVE5", kind="fixed", value=D("5"))
    order = make_order((physics, 1), (other, 1), coupon=coupon)
    shares = list(order.items.values_list("discount", flat=True))
    assert shares == [D("33.28"), D("1.25")] and order.discount.amount == D("34.53")  # coupon 3.75 + offer 29.53
    assert [label for label, _ in order.savings] == ["Coupon SAVE5", "Board offer"]
    with commit():
        services.record_capture(captured(order))
    invoice = Invoice.for_order(order)
    assert [line["discount"] for line in invoices.context(invoice)["lines"]] == shares
    refund = Refund.objects.create(order=order, payment=order.payments.get(), amount=order.total, reason="test")
    note = CreditNote.for_refund(refund, invoice)
    credited = sum(line["amount"] for line in invoices.credit_note_context(note)["lines"])
    assert credited == order.subtotal.amount - D("34.53") and "Board offer  −₹29.53" in mail.outbox[-1].body
    Offer.objects.update(is_active=False)
    three = [(ProductFactory(price=D("100.00")), 1) for _ in range(3)]
    old = make_order(*three, coupon=CouponFactory(kind="fixed", value=D("10")))
    assert list(old.items.values_list("discount", flat=True)) == [D("3.34"), D("3.33"), D("3.33")]  # split()
    OrderItem.objects.filter(order=old).update(discount=None)  # as if made before the split was kept
    old.discount_lines.all().delete()
    old_lines = invoices.context(Invoice(order=old))["lines"]
    assert [line["discount"] for line in old_lines] == [D("3.33"), D("3.33"), D("3.34")]  # as their invoices were
    assert old.savings == [(f"Coupon {old.coupon_code}", old.discount)]


def test_a_collection_offer_shows_in_the_cart_page_and_the_api(science):
    _, physics = science
    essentials = Collection.objects.create(name="Essentials", slug="essentials")
    CollectionItem.objects.create(collection=essentials, product=physics)
    offer(name="Essentials offer", scope=Offer.Scope.COLLECTIONS).collections.add(essentials)
    user = verified_user("rahul@example.com")
    make_cart((physics, 1), user=user)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    data = api.get("/api/v1/cart/").json()
    assert data["savings"] == [{"label": "Essentials offer", "amount": "29.90"}] and data["discount"] == "29.90"
    assert data["total"] == "269.10"
