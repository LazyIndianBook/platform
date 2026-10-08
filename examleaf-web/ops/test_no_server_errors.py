"""No address of Django answers with a server error to an empty GET or POST (one visitor, one signed-in student), nor
any address of the API to a GET, POST, PUT, PATCH or DELETE with an empty or odd JSON body, signed in or not. The
sample values are made from each address's converters (ids, slugs, order numbers, a name that climbs). Found by this
crawl: Google's pages without its keys, a PostgreSQL-only crash on a NUL byte."""

import itertools
import re

import pytest
from django.test import Client
from django.urls import get_resolver
from django.urls.resolvers import URLResolver
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from learn.models import Entitlement
from learn.tests import make_course
from shop.factories import ProductFactory, make_order, verified_user

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
SAMPLES = {
    "int": ["1", "999999999999"],
    "slug": ["physics", "nope"],
    "str": ["PHY-E01", "EL-2026-000001", "a" * 100],
    "path": ["products/x.png"],
}
SKIPPED = ("admin/", "static/", "_allauth/")  # the admin has its own crawl (test_admin_pages)
JSON_BODIES = [{}, {"x": [1, {"y": None}]}, {"code": "x", "token": "t", "phone": "1", "quantity": "a", "answer": "1"}]


def nested(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from nested(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern)


def addresses(only_api):
    """Concrete addresses made from every route (at most 4 for each)."""
    found = set()
    for route in nested(get_resolver().url_patterns):
        route = route.replace("^", "").replace("$", "").replace("(?P<version>v1)", "v1")
        if route.startswith(SKIPPED) or route.startswith("api/") != only_api or "debug" in route:
            continue
        route = re.sub(r"\(\?P<[^>]+>[^)]*\)", "1", route)  # allauth's regular-expression address
        options = []
        for part in re.split(r"(<[^>]+>)", route):
            kind = re.fullmatch(r"<(?:(\w+):)?\w+>", part)
            options.append(SAMPLES.get(kind.group(1) or "str", ["1"]) if kind else [part])
        found.update("/" + "".join(combination) for combination in itertools.islice(itertools.product(*options), 4))
    return sorted(found)


@pytest.fixture
def student():
    subject = make_course(chapters=2, clips=2)
    product = ProductFactory(slug="physics")
    user = verified_user("rahul@example.com")
    Entitlement.objects.create(user=user, subject=subject)
    make_order((product, 1), user=user)
    return user


def test_no_page_answers_with_a_server_error(student):
    visitor, signed_in = Client(raise_request_exception=False), Client(raise_request_exception=False)
    signed_in.force_login(student)
    failures, urls = [], addresses(only_api=False)
    assert len(urls) > 10  # the crawl finds Django's own addresses (the website's pages are the frontend's)
    for url in urls:
        for who, client in (("visitor", visitor), ("student", signed_in)):
            for method in (client.get, client.post):
                if method(url).status_code >= 500:
                    failures.append((who, method.__name__, url))
    assert not failures, failures


def test_no_api_address_answers_with_a_server_error(student):
    visitor, signed_in = APIClient(raise_request_exception=False), APIClient(raise_request_exception=False)
    signed_in.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(student).access_token}")
    failures, urls = [], addresses(only_api=True)
    assert len(urls) > 50
    for url in urls:
        for who, client in (("visitor", visitor), ("student", signed_in)):
            for method in (client.get, client.delete):
                if method(url).status_code >= 500:
                    failures.append((who, method.__name__, url))
            for method, body in itertools.product((client.post, client.put, client.patch), JSON_BODIES):
                if method(url, body, format="json").status_code >= 500:
                    failures.append((who, method.__name__, url, body))
    assert not failures, failures
