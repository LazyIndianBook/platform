"""The shop in the REST API v1: products, the cart, addresses, checkout, payment through the mobile SDK, cancellation,
invoices and credit notes, ownership, and the guests' lookup and its limit. Razorpay's network calls are mocked
(conftest.rzp); signatures are checked for real."""

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from shop import services
from shop.factories import (
    ADDRESS,
    KEY,
    SECRET,
    CouponFactory,
    ProductFactory,
    ShippingRateFactory,
    captured,
    make_order,
    picture,
    sign,
)
from shop.models import Address, BundleItem, Cart, CreditNote, Order, Payment, Product, ProductImage

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]


def customer(api, verified=True):
    user = UserFactory()
    EmailAddress.objects.create(user=user, email=user.email, verified=verified, primary=True)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user


@pytest.fixture
def api():
    return APIClient()


def test_products_are_public_with_prices_pictures_and_stock_state_only(api, django_assert_max_num_queries):
    book = ProductFactory(title="Physics Sample Papers", slug="physics", stock=3)
    solutions = ProductFactory(slug="physics-solutions", kind=Product.Kind.SOLUTIONS, stock=0)
    bundle = ProductFactory(slug="physics-bundle", kind=Product.Kind.BUNDLE, price=499, mrp=598, stock=0)
    BundleItem.objects.create(bundle=bundle, product=book)
    BundleItem.objects.create(bundle=bundle, product=solutions)
    ProductImage.objects.create(product=book, image=picture("products/inside.jpg"), alt="A page")
    ProductFactory(slug="old", is_active=False)
    with django_assert_max_num_queries(8):  # count, products, pictures, categories, related, bundle items, attributes
        listed = api.get("/api/v1/products/").json()
    assert [p["slug"] for p in listed["results"]] == ["physics-bundle", "physics", "physics-solutions"]
    data = api.get("/api/v1/products/physics/").json()
    assert (data["price"], data["mrp"], data["saving_percent"], data["in_stock"]) == ("299.00", "349.00", 14, True)
    inside = "http://testserver/shop/media/products/inside"  # its AVIF and WebP sizes by width, then the original
    widths = (100, 200, 300, 400)
    sizes = {f"image/{kind}": {str(w): f"{inside}/{w}w.{kind}" for w in widths} for kind in ("avif", "webp")}
    assert "stock" not in data and data["images"] == [
        {"sources": sizes, "src": f"{inside}.jpg", "width": 400, "height": 600, "alt": "A page"}
    ]
    assert data["web_url"] == "http://testserver/shop/physics/" and data["cover"] is None
    assert (data["meta_title"], data["meta_description"], data["og_image"]) == ("", "", None)  # none written or made
    bundle_data = api.get("/api/v1/products/physics-bundle/").json()
    assert not bundle_data["in_stock"]  # the solutions are out of stock
    assert [(i["product"], i["quantity"]) for i in bundle_data["bundle_items"]] == [
        ("physics", 1),
        ("physics-solutions", 1),
    ]
    assert api.get("/api/v1/products/old/").status_code == 404
    assert api.get("/api/v1/products/?kind=bundle").json()["count"] == 1


def test_the_cart_belongs_to_a_confirmed_account_and_keeps_the_website_rules(api):
    book, sold_out = ProductFactory(slug="physics", price=299, stock=5), ProductFactory(slug="gone", stock=0)
    CouponFactory(code="WELCOME10")
    ShippingRateFactory()  # Assam: ₹40 below ₹499
    assert api.get("/api/v1/cart/").json()["items"] == []  # a visitor's: shop/test_api_guest.py
    customer(api, verified=False)
    assert api.get("/api/v1/cart/").json() == {"detail": "Confirm your email address first."}
    user = customer(api)
    assert api.get("/api/v1/cart/").json()["items"] == []
    cart = api.post("/api/v1/cart/items/", {"product": "physics", "quantity": 2}).json()
    assert cart["items"] == [
        {"product": "physics", "title": book.title, "price": "299.00", "quantity": 2, "total": "598.00"}
    ]
    assert api.post("/api/v1/cart/items/", {"product": "physics"}).json()["count"] == 3  # added to the copies
    assert api.post("/api/v1/cart/items/", {"product": "gone"}).json() == {"product": [f"{sold_out} is out of stock."]}
    assert api.post("/api/v1/cart/items/", {"product": "nothing"}).status_code == 400
    assert api.patch("/api/v1/cart/items/physics/", {"quantity": 1}).json()["subtotal"] == "299.00"
    refused = {"code": ["This code cannot be applied to this cart."]}  # whatever the reason
    assert api.post("/api/v1/cart/coupon/", {"code": "nope"}).json() == refused
    cart = api.post("/api/v1/cart/coupon/?state=AS", {"code": "welcome10"}).json()
    assert (cart["coupon"], cart["discount"], cart["shipping"], cart["total"]) == (
        "WELCOME10",
        "29.90",
        "40.00",
        "309.10",
    )
    assert api.get("/api/v1/cart/?state=XX").json() == {"state": ["Unknown state code."]}
    assert api.delete("/api/v1/cart/coupon/").json()["coupon"] is None
    assert api.delete("/api/v1/cart/items/physics/").json()["items"] == []
    assert api.delete("/api/v1/cart/items/physics/").status_code == 404
    assert Cart.objects.get().user == user  # the account's cart, the same as on the website


def test_addresses_are_the_customers_own_with_a_pin_code_and_an_indian_mobile(api):
    other = Address.objects.create(user=UserFactory(), **{**ADDRESS, "phone": "+919864012345"})
    customer(api)
    bad = api.post("/api/v1/addresses/", {**ADDRESS, "pin": "012345", "phone": "+14155552671", "state": "ZZ"}).json()
    assert set(bad) == {"pin", "phone", "state"} and bad["phone"] == ["Enter a 10-digit Indian mobile number."]
    created = api.post("/api/v1/addresses/", {**ADDRESS, "phone": "98640 12345", "is_default": True})
    assert created.status_code == 201 and created.json()["phone"] == "+919864012345"
    url = f"/api/v1/addresses/{created.json()['id']}/"
    assert api.patch(url, {"city": "Jorhat"}).json()["city"] == "Jorhat"
    assert [a["city"] for a in api.get("/api/v1/addresses/").json()["results"]] == ["Jorhat"]
    for method in (api.get, api.delete):
        assert method(f"/api/v1/addresses/{other.pk}/").status_code == 404  # someone else's
    assert api.delete(url).status_code == 204 and Address.objects.count() == 1


def checkout(api, method="razorpay"):
    address = api.post("/api/v1/addresses/", {**ADDRESS, "phone": "98640 12345"}).json()
    return api.post("/api/v1/orders/", {"address": address["id"], "payment_method": method})


def test_checkout_payment_through_the_sdk_and_cancellation(api, rzp, commit):
    product = ProductFactory(slug="physics", price=299, stock=5)
    user = customer(api)
    assert checkout(api).json() == {"non_field_errors": ["Your cart is empty."]}
    api.post("/api/v1/cart/items/", {"product": "physics", "quantity": 2})
    response = checkout(api)
    assert response.status_code == 201
    order = response.json()
    assert (order["status"], order["status_label"], order["total"], order["can_pay"]) == (
        "pending",
        "awaiting payment",
        "598.00",
        True,
    )
    assert order["items"][0]["unit_price"] == "299.00" and order["shipping_address"]["pin"] == "781001"
    url = f"/api/v1/orders/{order['number']}/"
    start = api.post(url + "payment/").json()
    assert (start["key"], start["amount"], start["currency"], start["test_mode"]) == (KEY, 59800, "INR", True)
    assert api.post(url + "payment/").json()["order_id"] == start["order_id"]  # the same Razorpay order
    paid = {"razorpay_order_id": start["order_id"], "razorpay_payment_id": "pay_1"}
    refused = api.post(url + "payment/confirm/", {**paid, "razorpay_signature": "0" * 64})
    assert refused.status_code == 400 and "could not confirm" in refused.json()["non_field_errors"][0]
    assert Payment.objects.get().status == Payment.Status.CREATED and Cart.objects.filter(user=user).exists()
    rzp.payment.fetch.return_value = {**captured(Order.objects.get()), "id": "pay_1"}
    with commit():
        signature = sign(f"{start['order_id']}|pay_1", SECRET)
        order = api.post(url + "payment/confirm/", {**paid, "razorpay_signature": signature}).json()
    assert order["status"] == "paid" and not order["can_pay"] and not Cart.objects.filter(user=user).exists()
    order = api.get(url).json()  # the invoice is made once the payment is committed
    assert order["invoice"]["url"] == f"http://testserver{url}invoice/"
    pdf = api.get(url + "invoice/", HTTP_ACCEPT="application/pdf")
    assert pdf["Content-Type"] == "application/pdf" and b"".join(pdf.streaming_content).startswith(b"%PDF")
    assert [e["status"] for e in api.get("/api/v1/orders/").json()["results"]] == ["paid"]
    with commit():
        assert api.post(url + "cancel/").json()["status"] == "cancelled"
    order = api.get(url).json()  # Razorpay's refund, then the credit note, follow the commit
    product.refresh_from_db()
    assert order["status"] == "refunded" and order["refunds"][0]["amount"] == "598.00" and product.stock == 5
    note = CreditNote.objects.get()
    assert order["credit_notes"][0]["number"] == note.number and order["credit_notes"][0]["amount"] == "598.00"
    assert api.get(f"{url}credit-notes/{note.pk}/")["Content-Type"] == "application/pdf"
    assert api.post(url + "cancel/").json() == {
        "non_field_errors": ["This order can no longer be cancelled; see the Refund Policy."]
    }
    assert api.post(url + "payment/").json() == {
        "non_field_errors": ["This order is not waiting for an online payment."]
    }
    assert [m.subject for m in mail.outbox][-1] == f"[ExamLeaf] Refund for order {order['number']}"


def test_checkout_takes_online_payment_or_cash_on_delivery_only(api, rzp):
    """ "offline" is a method staff record (services.record_offline_payment): chosen by a customer it made an order
    whose payment page failed with a server error."""
    ProductFactory(slug="physics", price=299, stock=5)
    customer(api)
    api.post("/api/v1/cart/items/", {"product": "physics", "quantity": 1})
    refused = checkout(api, method="offline")
    assert refused.status_code == 400 and "not a valid choice" in refused.json()["payment_method"][0]
    assert not Order.objects.exists()
    with pytest.raises(services.ShopError, match="online payment or cash on delivery"):
        services.create_order(Cart.objects.get(), user=None, email="a@example.com", address=ADDRESS, method="offline")


def test_orders_of_other_customers_are_not_found(api, rzp):
    theirs = make_order((ProductFactory(), 1), user=UserFactory())
    Order.objects.filter(pk=theirs.pk).update(status=Order.Status.PAID)
    customer(api)
    url = f"/api/v1/orders/{theirs.number}/"
    for response in [
        api.get(url),
        api.post(url + "cancel/"),
        api.post(url + "payment/"),
        api.post(
            url + "payment/confirm/", {"razorpay_order_id": "x", "razorpay_payment_id": "y", "razorpay_signature": "z"}
        ),
        api.get(url + "invoice/"),
    ]:
        assert response.status_code == 404 and response.json() == {"detail": "No Order matches the given query."}
    assert api.get("/api/v1/orders/").json()["count"] == 0
    theirs.refresh_from_db()
    assert theirs.status == Order.Status.PAID


def test_cash_on_delivery_is_placed_at_once_when_offered(api, settings, commit):
    product = ProductFactory(slug="physics", stock=2)
    user = customer(api)
    api.post("/api/v1/cart/items/", {"product": "physics"})
    assert checkout(api, "cod").json() == {"non_field_errors": ["Cash on delivery is not available."]}
    settings.SHOP_COD_ENABLED = True
    with commit():
        order = checkout(api, "cod").json()
    product.refresh_from_db()
    assert order["status_label"] == "placed (pay on delivery)" and product.stock == 1 and not order["can_pay"]
    assert not Cart.objects.filter(user=user).exists() and "confirmed" in mail.outbox[-1].subject


def test_guests_ask_for_their_orders_link_by_email_with_a_limit(api, monkeypatch, commit):
    order = make_order((ProductFactory(), 1), email="guest@example.com")
    api.credentials(HTTP_AUTHORIZATION="Bearer expired.or.stale")  # ignored here, as on the log-in endpoints
    with commit():
        found = api.post("/api/v1/orders/lookup/", {"number": order.number.lower(), "email": "GUEST@example.com"})
        wrong = api.post("/api/v1/orders/lookup/", {"number": order.number, "email": "other@example.com"})
    sent = {"detail": "If an order matches, we have emailed you a link."}  # the same either way: nothing to learn
    assert found.status_code == wrong.status_code == 200 and found.json() == wrong.json() == sent
    assert [m.to for m in mail.outbox] == [["guest@example.com"]] and order.get_link_url() in mail.outbox[0].body
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "order_lookup", "3/hour")
    tries = [api.post("/api/v1/orders/lookup/", {"number": order.number, "email": "x@example.com"}) for _ in range(2)]
    assert [r.status_code for r in tries] == [200, 429] and int(tries[-1]["Retry-After"]) > 0  # 3 an hour, per address
    other = APIClient(REMOTE_ADDR="10.0.0.2")
    assert (
        other.post("/api/v1/orders/lookup/", {"number": order.number, "email": "guest@example.com"}).status_code == 200
    )
