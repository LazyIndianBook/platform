"""API v1 for what the website's shop pages do besides buying (phase 7): reviews, "email me when it is back", school
quotations and the order's link from its emails, each with the website's rules and limits."""

import re

import pytest
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import forms as account_forms
from accounts.factories import UserFactory
from shop.factories import ProductFactory, make_order, verified_user
from shop.models import Order, QuoteRequest, Review, StockAlert

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
QUOTE = {
    "school": "Cotton Collegiate H.S. School", "contact_name": "Anita Das", "email": "office@example.com",
    "phone": "98640 12345", "delivery_pin": "781001",
}  # fmt: skip


@pytest.fixture
def api():
    return APIClient()


def signed_in(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def delivered(user, product):
    order = make_order((product, 1), user=user, email=user.email)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.DELIVERED)
    return order


def test_reviews_are_read_by_anyone_and_written_once_by_buyers_whose_order_was_delivered(api):
    product, buyer = ProductFactory(), verified_user("buyer@example.com")
    url = f"/api/v1/products/{product.slug}/reviews/"
    Review.objects.create(product=product, user=UserFactory(), rating=4, status=Review.Status.APPROVED)
    Review.objects.create(product=product, user=UserFactory(), rating=1, text="spam")  # not read by staff yet
    data = api.get(url).json()
    assert (data["average"], data["count"], data["can_review"]) == ("4.0", 1, False)
    assert data["results"] == [
        {"rating": 4, "text": "", "status": "approved", "created": data["results"][0]["created"]}
    ]
    assert api.post(url, {"rating": 5}, format="json").status_code == 401
    assert signed_in(buyer).post(url, {"rating": 5}, format="json").status_code == 403  # nothing delivered yet
    delivered(buyer, product)
    client = signed_in(buyer)
    assert client.get(url).json()["can_review"] is True
    assert client.post(url, {"rating": 6}, format="json").json() == {
        "rating": ["Ensure this value is less than or equal to 5."]
    }
    response = client.post(url, {"rating": 5, "text": "Every answer step by step."}, format="json")
    assert response.status_code == 201 and response.json()["status"] == "pending"
    assert client.post(url, {"rating": 3}, format="json").status_code == 403  # one each
    assert api.get(url).json()["count"] == 1  # shown once staff approve it


def test_stock_alerts_go_to_the_accounts_own_address_with_the_same_answer_either_way(api):
    """Signed-in accounts only (SECURITY_REVIEW_PHASE5_6.md L3): an address a visitor gives could be anyone's."""
    sold_out, in_stock, user = ProductFactory(stock=0), ProductFactory(), verified_user("rahul@example.com")
    url = f"/api/v1/products/{sold_out.slug}/stock-alert/"
    assert api.post(url, {"email": "Visitor@Example.com"}, format="json").status_code == 401
    member = signed_in(user)
    response = member.post(url, {"email": "other@example.com"}, format="json")  # an address given is ignored
    assert response.status_code == 200 and "rahul@example.com" in response.json()["detail"]
    assert member.post(f"/api/v1/products/{in_stock.slug}/stock-alert/", {}, format="json").status_code == 200
    assert set(StockAlert.objects.values_list("email", "product")) == {("rahul@example.com", sold_out.pk)}
    assert member.post("/api/v1/products/no-such-book/stock-alert/", {}, format="json").status_code == 404


def test_school_quotations_take_the_websites_form_rules_the_bot_check_and_its_limit(api, settings, monkeypatch, commit):
    product = ProductFactory()
    UserFactory(is_superuser=True, is_staff=True, email="sales@example.com")  # no SALES member: superusers are told
    items = [{"product": product.slug, "quantity": 120}]
    errors = api.post("/api/v1/quotes/", {**QUOTE, "phone": "12345", "items": items}, format="json").json()
    assert errors == {"phone": ["Enter a 10-digit Indian mobile number."]}
    unknown = api.post("/api/v1/quotes/", {**QUOTE, "items": [{"product": "nope", "quantity": 1}]}, format="json")
    assert unknown.json() == {"items": ["Not on sale: nope."]}
    settings.TURNSTILE = True
    monkeypatch.setattr(account_forms, "turnstile_passed", lambda token: token == "passed")
    assert "turnstile" in api.post("/api/v1/quotes/", {**QUOTE, "items": items}, format="json").json()
    with commit():
        response = api.post("/api/v1/quotes/", {**QUOTE, "items": items, "turnstile": "passed"}, format="json")
    quote = QuoteRequest.objects.get()
    assert response.status_code == 201 and response.json()["number"] == quote.number
    assert quote.items == [{"product": product.slug, "title": product.title, "quantity": 120}]
    assert str(quote.phone) == "+919864012345" and mail.outbox[-1].to == ["sales@example.com"]
    tries = [api.post("/api/v1/quotes/", {}, format="json").status_code for _ in range(2)]
    assert tries == [400, 429]  # 5 an hour per client address, every request counted


def test_the_order_link_from_the_emails_opens_the_order_read_only(api, commit):
    order = make_order((ProductFactory(), 2), email="guest@example.com")
    with commit():
        api.post("/api/v1/orders/lookup/", {"number": order.number, "email": "guest@example.com"}, format="json")
    token = re.search(r"/orders/t/([\w-]+)/", mail.outbox[-1].body).group(1)
    response = api.get(f"/api/v1/orders/t/{token}/", HTTP_AUTHORIZATION="Bearer expired.or.stale")  # ignored
    data = response.json()
    assert response.status_code == 200 and data["number"] == order.number and data["email"] == "guest@example.com"
    assert (data["can_pay"], data["web_url"]) == (False, f"http://testserver/orders/t/{token}/")
    assert "no-store" in response["Cache-Control"] and data["invoice"] is None
    assert api.get("/api/v1/orders/t/not-a-real-token-at-all/").status_code == 404
    assert api.post(f"/api/v1/orders/t/{token}/").status_code == 405
