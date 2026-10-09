"""The catalogue's rules apart from its API: the dark-pattern phrases (shop/copy_rules.py), the EAN-13 barcode
(shop/barcode.py), the courier's data and its migration (shop/catalogue.py), coupons that name products and
categories, a first order's coupon, stacking, single-use codes taken by an order and freed by its cancellation, and
what the storefront guarantees: copies counted from real stock, nothing added that was not asked for, every fee in the
cart before checkout."""

from decimal import Decimal

import pytest
from django.apps import apps
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from shop import barcode, catalogue, copy_rules, services
from shop.cart import totals
from shop.factories import (
    ADDRESS,
    CouponFactory,
    ProductFactory,
    ShippingRateFactory,
    captured,
    make_cart,
    make_order,
    verified_user,
)
from shop.models import BundleItem, Category, Coupon, CouponCode, Offer, Order, Product

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
D = Decimal


# ---- The phrases (shop/copy_rules.py) ----


def test_the_dark_pattern_phrases_are_found_whatever_their_case_and_apostrophes():
    assert copy_rules.normal("Don’t  MISS") == "do not miss"
    assert [pattern for _, pattern in copy_rules.found("Hurry! Only fools wait.")] == [
        "confirm_shaming",
        "false_urgency",
    ]
    assert copy_rules.found("DON'T MISS the Board offer")[0][1] == "false_urgency"
    assert copy_rules.found("You'll regret it") == [("you will regret", "confirm_shaming")]
    assert copy_rules.found("Hurrying home") == [] and copy_rules.found("A Diwali offer on every book") == []
    assert copy_rules.found("Limited time: until 31 December") == []  # a date beside it: true
    assert copy_rules.found("Limited time", dated=True) == [] and copy_rules.found("limited time")
    with pytest.raises(Exception) as refused:
        copy_rules.check("Last chance!")
    assert "false urgency" in str(refused.value) and "the day it ends" in str(refused.value)


def test_the_phrases_come_from_the_setting(settings):
    settings.SHOP_DARK_PATTERN_PHRASES = {"act now": "false_urgency"}
    assert copy_rules.found("Act now!") and not copy_rules.found("Hurry!")


# ---- The barcode (shop/barcode.py) ----


def test_an_ean13_is_drawn_from_the_standards_patterns():
    # 5 901234 123457, the standard's own example: first digit 5 (parity LGGLLG), then the R patterns
    expected = "101" + "0001011" + "0100111" + "0110011" + "0010011" + "0111101" + "0011101" + "01010"
    expected += "1100110" + "1101100" + "1000010" + "1011100" + "1001110" + "1000100" + "101"
    assert barcode.modules("5901234123457") == expected and len(expected) == 95
    assert barcode.check_digit("978030640615") == "7"
    for wrong in ("5901234123458", "590123412345", "97803064061x7"):
        with pytest.raises(ValueError):
            barcode.modules(wrong)
    drawing = barcode.svg("9780306406157")
    assert drawing.startswith("<svg") and 'width="37.29mm"' in drawing and "9780306406157" in drawing


# ---- The courier's data (shop/catalogue.py) and the migration ----


def test_the_courier_rule_in_the_database_and_in_python_agree():
    books = {
        "weighed": ProductFactory(weight_grams=300, packaging="flyer"),
        "weightless": ProductFactory(weight_grams=0, packaging="flyer"),
        "unpacked": ProductFactory(weight_grams=300, packaging=""),
        "sized": ProductFactory(weight_grams=300, packaging="", length_cm=30, width_cm=21, height_cm=3),
        "box": ProductFactory(weight_grams=300, packaging="box"),
        "course": ProductFactory(kind=Product.Kind.DIGITAL, weight_grams=0, packaging=""),
    }
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, weight_grams=0, packaging="flyer")
    BundleItem.objects.create(bundle=bundle, product=books["weighed"])
    heavy = ProductFactory(kind=Product.Kind.BUNDLE, weight_grams=0, packaging="flyer")
    BundleItem.objects.create(bundle=heavy, product=books["weightless"])
    found = set(catalogue.incomplete(Product.objects.all()).values_list("pk", flat=True))
    problems = {
        product.pk
        for product in Product.objects.all()
        if catalogue.courier_problem(product, list(product.bundle_items.select_related("product")))
    }
    assert found == problems == {books["weightless"].pk, books["unpacked"].pk, books["box"].pk, heavy.pk}


def test_the_migration_packs_the_goods_in_a_flyer_and_writes_each_records_first_version():
    from importlib import import_module

    migration = import_module("shop.migrations.0023_phase_b_catalogue")
    goods, course = ProductFactory(packaging=""), ProductFactory(kind=Product.Kind.DIGITAL, packaging="")
    offer = Offer.objects.create(name="Board offer", value=D("10"), scope=Offer.Scope.PRODUCTS)
    offer.products.add(goods)
    coupon = CouponFactory()
    for model in (Product, Offer, Coupon):
        model.history.all().delete()
    migration.physical_and_history(apps, None)
    goods.refresh_from_db()
    course.refresh_from_db()
    assert (goods.packaging, course.packaging, goods.weight_grams) == ("flyer", "", 0)  # weight left to fix
    assert goods.history.count() == 1 and coupon.history.get().history_change_reason == "When its history began"
    first = offer.history.get()
    assert list(first.products.values_list("product_id", flat=True)) == [goods.pk]  # what it covered then


# ---- Coupons at the cart ----


def shelf(slug):
    return Category.objects.add_root({"name": slug.title(), "slug": slug})


def test_a_coupon_applies_to_the_products_and_categories_it_names_and_not_to_those_it_leaves_out():
    science = shelf("science")
    physics, chemistry, maths = (ProductFactory(price=D("300.00")) for _ in range(3))
    physics.categories.add(science)
    chemistry.categories.add(science)
    coupon = CouponFactory(value=D("10"))
    coupon.include_categories.add(science)
    coupon.exclude_products.add(chemistry)
    result = totals(make_cart((physics, 1), (chemistry, 1), (maths, 1), coupon=coupon))
    assert [line.discount for line in result.lines] == [D("30.00"), D("0.00"), D("0.00")]
    picky = CouponFactory(value=D("10"), min_order=D("500"))
    picky.include_products.add(physics)
    assert totals(make_cart((physics, 1), (maths, 2), coupon=picky)).coupon_problem.startswith("This coupon needs")
    elsewhere = CouponFactory()
    elsewhere.include_products.add(chemistry)
    problem = totals(make_cart((physics, 1), coupon=elsewhere)).coupon_problem
    assert problem == "This coupon is not for the books in your cart."


def test_a_first_orders_coupon_is_refused_after_an_order(rzp):
    user = verified_user("rahul@example.com")
    coupon = CouponFactory(first_order_only=True)
    assert totals(make_cart((ProductFactory(), 1), coupon=coupon), user=user, email=user.email).coupon is not None
    order = make_order((ProductFactory(), 1), user=user)
    services.record_capture(captured(order))  # an order placed: paid
    later = totals(make_cart((ProductFactory(), 1), coupon=coupon), user=user, email=user.email)
    assert later.coupon_problem == "This coupon is for a first order."


def test_a_coupon_that_does_not_stack_takes_no_offer_beside_it():
    physics = ProductFactory(price=D("300.00"))
    Offer.objects.create(name="Board offer", value=D("10"))
    plain = totals(make_cart((physics, 1), coupon=CouponFactory(value=D("5"))))
    assert [s.label for s in plain.savings][1:] == ["Board offer"]
    alone = totals(make_cart((physics, 1), coupon=CouponFactory(value=D("5"), stackable=False)))
    assert len(alone.savings) == 1 and alone.savings[0].label.startswith("Coupon")


def api(user=None):
    client = APIClient()
    if user:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def test_a_single_use_code_is_one_orders_and_a_cancellation_frees_it(rzp):
    school = CouponFactory(code="SCHOOL10", value=D("10"), single_use=True, max_uses_per_customer=None)
    code = CouponCode.objects.create(coupon=school, code="CCHS-ABCDEFGH", note="Cotton Collegiate")
    physics = ProductFactory(price=D("300.00"), stock=10)
    first, second = verified_user("anita@example.com"), verified_user("rahul@example.com")
    for user in (first, second):
        api(user).post("/api/v1/cart/items/", {"product": physics.slug}, format="json")
    own = api(first).post("/api/v1/cart/coupon/", {"code": "school10"}, format="json")
    assert own.status_code == 400  # a codes-only coupon's own code is not for the cart
    applied = api(first).post("/api/v1/cart/coupon/", {"code": "cchs-abcdefgh"}, format="json").json()
    assert applied["coupon"] == "CCHS-ABCDEFGH" and applied["savings"][0]["label"] == "Coupon CCHS-ABCDEFGH"
    assert api(second).post("/api/v1/cart/coupon/", {"code": "CCHS-ABCDEFGH"}, format="json").status_code == 200
    address = first.addresses.create(**{k: v for k, v in ADDRESS.items()})
    order = api(first).post("/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay"}, format="json")
    assert order.status_code == 201, order.content
    code.refresh_from_db()
    made = Order.objects.get(number=order.json()["number"])
    assert (code.order_id, code.used_by_id) == (made.pk, first.pk)
    assert (made.coupon_code, made.coupon_id) == (code.code, school.pk)
    late = second.addresses.create(**{k: v for k, v in ADDRESS.items()})
    refused = api(second).post("/api/v1/orders/", {"address": late.pk, "payment_method": "razorpay"}, format="json")
    assert refused.status_code == 400 and "This code has been used" in str(refused.json())
    assert api(second).post("/api/v1/cart/coupon/", {"code": "CCHS-ABCDEFGH"}, format="json").status_code == 400
    services.cancel_order(made, "Not wanted")
    code.refresh_from_db()
    assert code.order_id is None and code.used_at is None  # free again for another order
    assert api(second).post("/api/v1/cart/coupon/", {"code": "CCHS-ABCDEFGH"}, format="json").status_code == 200


# ---- What the storefront guarantees (plan 5.5's dark-pattern guardrails) ----


def test_only_n_left_is_counted_from_real_stock():
    physics = ProductFactory(title="Physics", stock=2)
    result = totals(make_cart((physics, 3)))
    assert result.problems() == ["Only 2 copies of Physics left."]
    physics.stock = 0
    physics.save()
    assert totals(make_cart((physics, 1))).problems() == ["Physics is out of stock. Please remove it."]
    typed = {field.name for field in Product._meta.get_fields()} | {field.name for field in Offer._meta.get_fields()}
    assert not [name for name in typed if "left" in name or "scarcity" in name]  # no number typed to show instead


def test_the_cart_adds_nothing_the_customer_did_not_ask_for():
    user = verified_user("rahul@example.com")
    physics, related = ProductFactory(), ProductFactory()
    physics.related.add(related)
    bundle = ProductFactory(kind=Product.Kind.BUNDLE)
    BundleItem.objects.create(bundle=bundle, product=physics)
    Offer.objects.create(name="Board offer", value=D("10"))
    cart = api(user).post("/api/v1/cart/items/", {"product": physics.slug, "quantity": 1}, format="json").json()
    assert [(line["product"], line["quantity"]) for line in cart["items"]] == [(physics.slug, 1)]


def test_every_fee_is_in_the_cart_before_checkout_and_the_order_charges_no_other(settings):
    settings.SHOP_COD_ENABLED = True
    user = verified_user("rahul@example.com")
    ShippingRateFactory(fee=D("40.00"), free_above=D("999.00"))
    physics = ProductFactory(price=D("300.00"), stock=10)
    api(user).post("/api/v1/cart/items/", {"product": physics.slug}, format="json")
    cart = api(user).get("/api/v1/cart/?state=AS").json()
    assert (cart["subtotal"], cart["shipping"], cart["total"]) == ("300.00", "40.00", "340.00")
    address = user.addresses.create(**{k: v for k, v in ADDRESS.items()})
    order = api(user).post("/api/v1/orders/", {"address": address.pk, "payment_method": "cod"}, format="json").json()
    assert order["total"] == cart["total"] and order["shipping_fee"] == cart["shipping"]  # cash on delivery: no fee
    shipping = api().get("/api/v1/shipping/").json()
    assert (shipping["fee_from"], shipping["free_above"]) == ("40.00", "999.00")  # shown before any cart


def test_codes_are_drawn_once_each_and_never_a_coupons_code():
    school = CouponFactory(code="SCHOOL", single_use=True)
    made = catalogue.make_codes(school, 50, "CCHS", note="Cotton Collegiate")
    assert len(set(made)) == 50 and all(code.startswith("CCHS-") and len(code) == 13 for code in made)
    assert CouponCode.objects.filter(coupon=school).count() == 50
    assert all(set(code[5:]) <= set(catalogue.CODE_LETTERS) for code in made)  # no 0, O, 1, I or L to misread
