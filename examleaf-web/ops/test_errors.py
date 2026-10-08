"""Django's error pages (plain, with DEBUG off; JSON under /api/: the website's pages are the frontend's), a NUL byte
in an address (a 500 on PostgreSQL), the limit on an attempt's notes and what the browser may keep."""

import uuid

import pytest
from allauth.account.models import EmailAddress
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from api.tests import student
from content.tests import make_paper

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def test_an_unknown_address_gets_the_plain_404_and_the_api_a_json_one(client):
    page = client.get("/no-such-page/")
    assert page.status_code == 404 and "We could not find that page" in page.text and 'content="noindex"' in page.text
    api = client.get("/api/v1/no-such-endpoint/")
    assert api.status_code == 404 and api.json() == {"detail": "Not found."}


def test_a_page_not_allowed_gets_the_403_page(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:accounts_consentrecord_add"))  # consent records are never added by hand
    assert page.status_code == 403 and "You are not allowed to open this page" in page.text


def test_an_expired_form_gets_the_csrf_page():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.post(reverse("admin:logout"))  # an admin form without its token
    assert page.status_code == 403 and "Your form could not be sent" in page.text and "CSRF" not in page.text


def test_a_failure_gets_a_page_that_needs_nothing_else_and_the_api_json(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("the database is gone")

    monkeypatch.setattr("content.models.Paper.qr_image", boom)
    monkeypatch.setattr("api.views.BoardViewSet.list", boom)
    make_paper()
    client.raise_request_exception = False
    request_id = uuid.uuid4().hex
    page = client.get("/qr/PHY-E01.png", HTTP_X_REQUEST_ID=request_id)
    assert page.status_code == 500 and "Something went wrong on our side" in page.text
    assert f"Reference {request_id}" in page.text  # what the log lines carry: support finds the request with it
    assert "/static/" not in page.text  # self-contained: no static files
    api = client.get("/api/v1/boards/")
    assert api.status_code == 500 and api.json() == {"detail": "Server error."} and len(api["X-Request-ID"]) == 32


def test_a_request_that_cannot_be_understood_gets_the_branded_400_or_json(client):
    page = client.get("/", HTTP_HOST="evil.example")  # not in ALLOWED_HOSTS
    assert page.status_code == 400 and "We could not understand that request" in page.text
    api = client.get("/api/v1/boards/", HTTP_HOST="evil.example")
    assert api.status_code == 400 and api.json() == {"detail": "Bad request."}


def test_too_many_requests_get_the_429_page_with_retry_after(client, monkeypatch):
    monkeypatch.setattr("shop.views.over_limit", lambda *args, **kwargs: True)  # over Razorpay's 300 a minute
    page = client.post(reverse("shop:razorpay_webhook"), b"{}", content_type="application/json")
    assert page.status_code == 429 and "Too many tries" in page.text and int(page["Retry-After"]) > 0


@pytest.mark.parametrize(
    "url",
    ["/qr/a%00b.png", "/api/v1/orders/EL-1%00/", "/api/v1/papers/a%00b/", "/api/v1/qr/a%00b/"]
    + ["/api/v1/products/a%00b/", "/api/v1/orders/t/x%00y/"],
)
def test_a_nul_byte_in_an_address_is_a_404_not_a_server_error(client, url):
    client.raise_request_exception = False  # PostgreSQL refuses NUL in a query: that was a 500 (SQLite accepts it)
    client.force_login(UserFactory())
    assert client.get(url).status_code == 404


def test_the_notes_of_an_attempt_are_limited():
    paper = make_paper()
    user = UserFactory()
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    body = {"paper": paper.code, "marks_obtained": "50", "notes": "y" * 2001}
    response = api.post("/api/v1/attempts/", body, format="json")
    assert response.status_code == 400 and "no more than 2000 characters" in response.json()["notes"][0]
    assert api.post("/api/v1/attempts/", {**body, "notes": "y" * 2000}, format="json").status_code == 201


def test_what_a_signed_in_user_gets_is_not_kept_by_the_browser_after_log_out(client, settings):
    paper = make_paper()
    for url in ["/api/v1/me/", "/api/v1/cart/", "/api/v1/attempts/"]:
        client.force_login(student())
        assert "no-store" in client.get(url)["Cache-Control"], url
    client.logout()
    settings.SOLUTIONS_REQUIRE_LOGIN = False
    solutions = f"/api/v1/papers/{paper.code}/solutions/"
    assert client.get(solutions)["Cache-Control"] == "public, max-age=300"  # views that say so keep it
    client.force_login(student())
    assert client.get(solutions)["Cache-Control"] == "private"
