"""Error pages (branded, with DEBUG off), robots.txt, the favicon, every page's title and description, a NUL byte in an
address (a 500 on PostgreSQL) and the limit on an attempt's notes."""

import re
import uuid

import pytest
from allauth.account.models import EmailAddress
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from content.tests import make_paper
from shop.factories import ProductFactory
from shop.models import Product

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def test_an_unknown_address_gets_the_branded_404_and_the_api_a_json_one(client):
    page = client.get("/no-such-page/")
    assert page.status_code == 404 and "We could not find that page" in page.text
    assert 'id="site-menu"' in page.text and 'content="noindex"' in page.text  # the site's header and menu
    assert "scan the QR code" in client.get("/s/NOPE-X99/").text  # a mistyped paper code: the way back
    api = client.get("/api/v1/no-such-endpoint/")
    assert api.status_code == 404 and api.json() == {"detail": "Not found."}


def test_a_page_not_allowed_gets_the_branded_403(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:accounts_consentrecord_add"))  # consent records are never added by hand
    assert page.status_code == 403 and "You are not allowed to open this page" in page.text


def test_an_expired_form_gets_the_branded_csrf_page():
    page = Client(enforce_csrf_checks=True).post(reverse("account_login"), {"login": "a@example.com", "password": "x"})
    assert page.status_code == 403 and "Your form could not be sent" in page.text and "CSRF" not in page.text


def test_a_failure_gets_a_page_that_needs_nothing_else_and_the_api_json(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("the database is gone")

    monkeypatch.setattr("content.views.HomeView.get", boom)
    monkeypatch.setattr("api.views.BoardViewSet.list", boom)
    client.raise_request_exception = False
    request_id = uuid.uuid4().hex
    page = client.get("/", HTTP_X_REQUEST_ID=request_id)
    assert page.status_code == 500 and "Something went wrong on our side" in page.text
    assert f"Reference {request_id}" in page.text  # what the log lines carry: support finds the request with it
    assert 'id="site-menu"' not in page.text and "/static/" not in page.text  # self-contained: no layout or static
    api = client.get("/api/v1/boards/")
    assert api.status_code == 500 and api.json() == {"detail": "Server error."} and len(api["X-Request-ID"]) == 32


def test_a_request_that_cannot_be_understood_gets_the_branded_400_or_json(client):
    page = client.get("/", HTTP_HOST="evil.example")  # not in ALLOWED_HOSTS
    assert page.status_code == 400 and "We could not understand that request" in page.text
    api = client.get("/api/v1/boards/", HTTP_HOST="evil.example")
    assert api.status_code == 400 and api.json() == {"detail": "Bad request."}


def test_too_many_lookups_get_the_branded_429_with_retry_after(client):
    for _ in range(10):
        client.post(reverse("shop:lookup"), {"number": "EL-2026-999999", "email": "x@example.com"})
    page = client.post(reverse("shop:lookup"), {"number": "EL-2026-999999", "email": "x@example.com"})
    assert page.status_code == 429 and "Too many tries" in page.text and int(page["Retry-After"]) > 0


def test_robots_txt_keeps_crawlers_off_private_pages_and_names_the_sitemap(client, settings):
    settings.SITE_URL = "https://examleaf.in"
    page = client.get("/robots.txt")
    assert page["Content-Type"].startswith("text/plain")
    lines = page.text.splitlines()
    assert {"Disallow: /admin/", "Disallow: /account/", "Disallow: /cart/", "Disallow: /checkout/"} <= set(lines)
    assert "Sitemap: https://examleaf.in/sitemap.xml" in lines


def test_the_favicon_exists_and_is_linked_and_asked_for(client):
    assert finders.find("img/favicon-32.png") and finders.find("img/apple-touch-icon.png")
    assert finders.find("img/favicon.svg")
    home = client.get("/").text
    assert 'rel="icon"' in home and 'rel="apple-touch-icon"' in home
    response = client.get("/favicon.ico")  # browsers ask for it whatever the page says
    assert response.status_code == 301 and response.url.endswith("/static/img/favicon-32.png")


def meta(response):
    title = re.search(r"<title>(.*?)</title>", response.text, re.S).group(1)
    description = re.search(r'<meta name="description" content="(.*?)">', response.text, re.S).group(1)
    return title, description, 'name="robots" content="noindex"' in response.text


def test_every_page_has_its_own_title_and_description_and_private_ones_are_not_indexed(client, settings):
    settings.SOLUTIONS_REQUIRE_LOGIN = True
    paper = make_paper()
    ProductFactory(title="Physics Sample Papers", slug="physics", subject=paper.book.subject)
    product = ProductFactory(
        title="Physics Bundle", slug="bundle", kind=Product.Kind.BUNDLE, subject=paper.book.subject
    )
    public = ["/", f"/books/{paper.book.slug}/", f"/s/{paper.code}/", "/shop/", product.get_absolute_url(), "/about/"]
    public += [reverse(slug) for slug in ("privacy", "terms", "refunds", "shipping", "contact")]
    seen = {}
    for url in public:
        title, description, noindex = meta(client.get(url))
        assert title.endswith(" · ExamLeaf") and 5 < len(title) < 70, (url, title)
        assert 40 < len(description) < 200 and not noindex, (url, description)
        assert description not in seen.values(), (url, "description shared with another page")
        seen[url] = description
    assert len({meta(client.get(url))[0] for url in public}) == len(public)  # no two pages share a title
    client.force_login(UserFactory())
    client.post(reverse("shop:cart_add", args=[product.pk]))
    private = ["/account/", "/account/record/", "/account/teacher/", "/account/delete/", "/account/addresses/add/"]
    private += ["/cart/", "/checkout/", "/orders/lookup/", "/account/orders/", reverse("account_email")]
    private += [reverse("account_change_password"), reverse("record") + "?tier=E"]
    for url in private:
        response = client.get(url, follow=True)
        _, description, noindex = meta(response)
        assert response.status_code == 200 and noindex and len(description) > 20, (url, response.status_code)
    client.logout()
    for url in [reverse("account_login"), reverse("account_signup"), reverse("account_reset_password")]:
        assert meta(client.get(url))[2], url  # log-in and sign-up pages are not for search results


@pytest.mark.parametrize(
    "url",
    ["/s/AB%00C/", "/qr/a%00b.png", "/account/orders/EL-1%00/", "/api/v1/papers/a%00b/", "/api/v1/qr/a%00b/"]
    + ["/api/v1/products/a%00b/", "/books/x%00y/", "/shop/x%00y/"],
)
def test_a_nul_byte_in_an_address_is_a_404_not_a_server_error(client, url):
    client.raise_request_exception = False  # PostgreSQL refuses NUL in a query: that was a 500 (SQLite accepts it)
    client.force_login(UserFactory())
    assert client.get(url).status_code == 404


def test_the_notes_of_an_attempt_are_limited_on_the_website_and_in_the_api(client):

    paper = make_paper()
    user = UserFactory()
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client.force_login(user)
    data = {"date": "2026-10-01", "marks_obtained": "50", "notes": "x" * 2001}
    page = client.post(reverse("attempt_add", args=[paper.code]), data)
    assert page.status_code == 200 and "Ensure this value has at most 2000 characters" in page.text
    assert not user.attempts.exists()
    assert client.post(reverse("attempt_add", args=[paper.code]), {**data, "notes": "x" * 2000}).status_code == 302
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    body = {"paper": paper.code, "marks_obtained": "50", "notes": "y" * 2001}
    response = api.post("/api/v1/attempts/", body, format="json")
    assert response.status_code == 400 and "no more than 2000 characters" in response.json()["notes"][0]
    assert api.post("/api/v1/attempts/", {**body, "notes": "y" * 2000}, format="json").status_code == 201


def test_what_a_signed_in_user_sees_is_not_kept_by_the_browser_after_log_out(client, settings):
    paper = make_paper()
    for url in ["/account/", "/account/record/", "/account/orders/", "/cart/", "/about/", "/shop/"]:
        client.force_login(UserFactory())
        assert "no-store" in client.get(url)["Cache-Control"], url
    client.logout()
    assert "Cache-Control" not in client.get("/about/")  # visitors' pages are left to the usual caching
    settings.SOLUTIONS_REQUIRE_LOGIN = False
    assert client.get(f"/s/{paper.code}/")["Cache-Control"] == "public, max-age=300"  # views that say so keep it
    client.force_login(UserFactory())
    assert client.get(f"/s/{paper.code}/")["Cache-Control"] == "private"
