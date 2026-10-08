"""Visitors shop through the API as on the website: a guest cart held by the session cookie (a browser on the site's
origin, CSRF token on changes) or by X-Cart-Token (POST cart/), coupons and checkout with the website's checks, payment
through the order's link, and the guest cart joining the account's at log-in. Razorpay's network calls are mocked
(conftest.rzp); signatures are checked for real."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import forms as account_forms
from accounts.factories import PASSWORD
from api.tests import student
from shop.factories import ADDRESS, KEY, SECRET, CouponFactory, ProductFactory, ShippingRateFactory, captured, sign
from shop.models import Cart, Order, PinCode, Product

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
GUEST = {
    "email": "rahul@example.com",
    "shipping_address": {**ADDRESS, "phone": "98640 12345"},
    "payment_method": "razorpay",
}


def test_a_visitor_buys_through_the_api_and_pays_by_the_orders_link(rzp, commit, settings):
    settings.SHOP_COD_ENABLED = True
    ProductFactory(slug="physics", price=299, stock=5)
    CouponFactory(code="WELCOME10")
    ShippingRateFactory()  # Assam: ₹40 below ₹499
    api = APIClient()  # keeps the session cookie, as a browser does
    assert api.get("/api/v1/products/physics/").json()["price"] == "299.00"
    assert api.get("/api/v1/cart/").json()["items"] == []
    assert api.post("/api/v1/cart/items/", {"product": "physics"}).json()["count"] == 1
    cart = api.post("/api/v1/cart/coupon/?state=AS", {"code": "welcome10"}).json()
    assert (cart["coupon"], cart["discount"], cart["shipping"], cart["total"]) == (
        "WELCOME10",
        "29.90",
        "40.00",
        "309.10",
    )
    cod = api.post("/api/v1/orders/", {**GUEST, "payment_method": "cod"})  # M8: for confirmed accounts only
    assert cod.status_code == 400 and "log in, or pay online" in cod.json()["non_field_errors"][0]
    bad = api.post("/api/v1/orders/", {**GUEST, "shipping_address": {**ADDRESS, "phone": "12345", "pin": "78100"}})
    assert set(bad.json()["shipping_address"]) == {"phone", "pin"}
    response = api.post("/api/v1/orders/", GUEST)
    assert response.status_code == 201 and "no-store" in response["Cache-Control"]
    order = response.json()
    assert (order["status"], order["total"], order["can_pay"]) == ("pending", "309.10", True)
    assert order["shipping_address"]["phone"] == "+919864012345" and Order.objects.get().user is None
    link = f"/api/v1/orders/t/{order['token']}/"
    assert order["web_url"] == f"http://testserver/orders/t/{order['token']}/"
    assert "token" not in api.get(link).json() and api.get(link).json()["can_pay"]  # the token is given once
    start = api.post(link + "payment/").json()
    assert (start["key"], start["amount"], start["test_mode"]) == (KEY, 30910, True)
    paid = {"razorpay_order_id": start["order_id"], "razorpay_payment_id": "pay_1"}
    assert api.post(link + "payment/confirm/", {**paid, "razorpay_signature": "0" * 64}).status_code == 400
    assert Cart.objects.exists()  # kept until the payment is confirmed
    rzp.payment.fetch.return_value = {**captured(Order.objects.get()), "id": "pay_1"}
    with commit():
        signature = sign(f"{start['order_id']}|pay_1", SECRET)
        order = api.post(link + "payment/confirm/", {**paid, "razorpay_signature": signature}).json()
    assert order["status"] == "paid" and not order["can_pay"] and not Cart.objects.exists()
    page = api.get(link)  # the status page
    assert page.json()["status"] == "paid" and "no-store" in page["Cache-Control"]
    assert page.json()["invoice"]["url"] == f"http://testserver{link}invoice/"  # by the link: no account needed
    assert api.get(link + "invoice/", HTTP_ACCEPT="application/pdf")["Content-Type"] == "application/pdf"
    with commit():
        assert api.post(link + "cancel/").json()["status"] == "cancelled"  # refunded in full
    order = api.get(link).json()
    assert order["status"] == "refunded" and api.get(order["credit_notes"][0]["url"]).status_code == 200
    assert api.post(link + "cancel/").json() == {
        "non_field_errors": ["This order can no longer be cancelled; see the Refund Policy."]
    }
    assert api.post(link + "payment/").json() == {
        "non_field_errors": ["This order is not waiting for an online payment."]
    }
    assert "rahul@example.com" in {to for message in mail.outbox for to in message.to}


def test_a_client_without_cookies_holds_its_cart_by_token_and_brings_it_to_its_account():
    ProductFactory(slug="physics", stock=5)
    api = APIClient()
    start = api.post("/api/v1/cart/")
    assert start.status_code == 201 and start.json()["items"] == [] and not api.cookies.get("sessionid")
    token = start.json()["token"]
    held = {"HTTP_X_CART_TOKEN": token}
    assert api.post("/api/v1/cart/items/", {"product": "physics", "quantity": 2}, **held).json()["count"] == 2
    assert Cart.objects.get().token not in (None, token)  # only its hash is kept
    assert api.get("/api/v1/cart/", HTTP_X_CART_TOKEN="forged").status_code == 404
    user = student()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    assert api.post("/api/v1/cart/").status_code == 400  # signed in: the account's cart
    assert api.get("/api/v1/cart/", **held).json()["count"] == 2  # the guest cart joined the account's
    assert api.get("/api/v1/cart/", **held).json()["count"] == 2 and Cart.objects.get().user == user  # once
    api.credentials()
    stale = api.post("/api/v1/cart/").json()["token"]
    Cart.objects.filter(user=None).update(token_expires=timezone.now() - timedelta(seconds=1))
    assert api.get("/api/v1/cart/", HTTP_X_CART_TOKEN=stale).json() == {
        "detail": "This cart has expired: start a new one (POST cart/)."
    }


def test_a_browsers_guest_cart_needs_the_csrf_token_and_joins_the_account_at_log_in():
    ProductFactory(slug="physics", stock=5)
    user = student()
    browser = APIClient(enforce_csrf_checks=True)
    refused = browser.post("/api/v1/cart/items/", {"product": "physics"})
    assert refused.status_code == 403 and refused.json()["detail"].startswith("CSRF Failed")
    browser.get("/_allauth/browser/v1/auth/session")  # allauth.headless sets the csrftoken cookie
    csrf = {"HTTP_X_CSRFTOKEN": browser.cookies["csrftoken"].value}
    assert browser.post("/api/v1/cart/items/", {"product": "physics"}, **csrf).json()["count"] == 1
    login = {"email": user.email, "password": PASSWORD}
    assert browser.post("/_allauth/browser/v1/auth/login", login, **csrf).status_code == 200
    assert browser.get("/api/v1/cart/").json()["count"] == 1 and Cart.objects.get().user == user


def test_visitors_coupons_and_checkout_keep_the_websites_checks(settings, monkeypatch):
    settings.TURNSTILE, settings.TURNSTILE_SITE_KEY = True, "site-key"
    monkeypatch.setattr(account_forms, "turnstile_passed", lambda token: token == "passed")
    ProductFactory(slug="physics", stock=5)
    ProductFactory(slug="course", kind=Product.Kind.DIGITAL)
    PinCode.objects.create(pin="781001", states=["AS"], districts=["Kamrup Metro"])
    api = APIClient()
    api.post("/api/v1/cart/items/", {"product": "physics"})
    refused = {"turnstile": ["Wait until the check above says it is done, then press the button again."]}
    assert api.post("/api/v1/cart/coupon/", {"code": "NOPE"}).json() == refused
    codes = [api.post("/api/v1/cart/coupon/", {"code": "NOPE", "turnstile": "passed"}) for _ in range(10)]
    assert [r.status_code for r in codes] == [400] * 9 + [429]  # 10 an hour per client address, the refused one too
    assert api.post("/api/v1/orders/", GUEST).json() == refused
    elsewhere = {**GUEST, "turnstile": "passed", "shipping_address": {**GUEST["shipping_address"], "state": "ML"}}
    assert api.post("/api/v1/orders/", elsewhere).json() == {
        "shipping_address": {"state": ["PIN code 781001 is in Assam."]}
    }
    api.post("/api/v1/cart/items/", {"product": "course"})
    course = api.post("/api/v1/orders/", {**GUEST, "turnstile": "passed"}).json()
    assert course == {"non_field_errors": ["Please log in first: the course opens in your account."]}
    assert [api.post("/api/v1/orders/", {}).status_code for _ in range(8)][-1] == 429  # 10 checkouts in 10 minutes
    settings.SHOP_OPEN = False
    assert APIClient().post("/api/v1/cart/items/", {"product": "physics"}).status_code == 403
