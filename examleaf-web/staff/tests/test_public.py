"""The public endpoints Phase B added (plan 9.2; OWASP API5 and API3): My requests (me/tickets/), the nominee
(me/nominee/), a marketing consent withdrawn (me/consent/withdraw/), a return asked for (orders/<number>/returns/), a
legal page's versions (pages/<slug>/versions/), a parent's link (parent-consent/<token>/), the e-commerce disclosures
(config/), and the forms (reports/, contact/). Each is throttled; the ones a website session writes through need its
CSRF token; the forms take Turnstile's token while the bot check is on; and none answers staff's data."""

import pytest
from django.middleware.csrf import _get_new_csrf_string
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from accounts import roles
from shop.factories import ProductFactory, make_order, verified_user

from .conftest import make_staff

pytestmark = pytest.mark.django_db


@pytest.fixture
def customer():
    rahul = verified_user("rahul@example.com")
    client = APIClient(enforce_csrf_checks=True)  # the website's session, as a browser sends it
    client.force_login(rahul)
    return rahul, client


WRITES = [  # (method, path, body): what a signed-in website session changes here
    ("put", "me/nominee/", {"name": "Asha Das", "contact": "asha@example.com", "relation": "mother"}),
    ("delete", "me/nominee/", None),
    ("post", "me/consent/withdraw/", {"purpose": "marketing"}),
    ("post", "me/tickets/", {"category": "order", "subject": "My parcel", "message": "It has not come."}),
    ("post", "orders/{order}/returns/", {"lines": [{"product": "x", "quantity": 1}], "reason": "damaged"}),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=[f"{m} {p}" for m, p, _ in WRITES])
def test_a_session_write_needs_its_csrf_token(customer, method, path, body):
    user, client = customer
    order = make_order((ProductFactory(stock=5), 1), user=user, email=user.email)
    url = "/api/v1/" + path.format(order=order.number)
    refused = getattr(client, method)(url, body, format="json")
    assert refused.status_code == 403 and "CSRF" in refused.json()["detail"], refused.content[:200]
    token = _get_new_csrf_string()
    client.cookies["csrftoken"] = token
    assert getattr(client, method)(url, body, format="json", HTTP_X_CSRFTOKEN=token).status_code != 403


RATED = [  # (the rate, method, path, body, signed in): each answers 429 past its limit
    ("dj_rest_auth", "get", "me/nominee/", None, True),
    ("dj_rest_auth", "post", "me/consent/withdraw/", {"purpose": "marketing"}, True),
    ("dj_rest_auth", "get", "parent-consent/a.b/", None, False),
    ("anon", "get", "pages/privacy/versions/", None, False),
    ("anon", "get", "config/", None, False),
    ("user", "post", "orders/{order}/returns/", {"lines": [], "reason": "damaged"}, True),
]


@pytest.mark.parametrize(("rate", "method", "path", "body", "signed"), RATED, ids=[f"{r} {p}" for r, _, p, *_ in RATED])
def test_each_public_endpoint_is_throttled(monkeypatch, rate, method, path, body, signed):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, rate, "2/hour")
    client = APIClient()
    order = None
    if signed:
        user = verified_user("rahul@example.com")
        client.force_authenticate(user)  # (the app's way: no CSRF; the rate is what is asked here)
        order = make_order((ProductFactory(stock=5), 1), user=user, email=user.email)
    url = "/api/v1/" + path.format(order=getattr(order, "number", ""))
    answers = [getattr(client, method)(url, body, format="json").status_code for _ in range(3)]
    assert answers[:2] != [429, 429] and answers[2] == 429, answers


def test_the_forms_need_turnstiles_token_while_the_bot_check_is_on(settings):
    settings.TURNSTILE, settings.SUPPORT_EMAIL = True, "support@examleaf.in"
    report = APIClient().post("/api/v1/reports/", {"kind": "solution", "paper": "PHY-E01", "question": "2(c)",
                                                   "category": "wrong_answer"}, format="json")  # fmt: skip
    assert report.status_code == 400 and "turnstile" in report.json(), report.content[:200]
    contact = APIClient().post("/api/v1/contact/", {"name": "Rahul", "email": "rahul@example.com",
                                                    "message": "Where is my parcel?"}, format="json")  # fmt: skip
    assert contact.status_code == 400 and "turnstile" in contact.json(), contact.content[:200]


def test_no_public_answer_holds_staff_data(customer, settings, commit):
    """My requests: never a staff note, nor who works on it; the disclosures: never CERT-In's contact."""
    from support import services
    from support.tests.conftest import make_ticket

    user, _ = customer
    agent = make_staff(roles.SUPPORT, full_name="Agent Bora")
    with commit():
        ticket = make_ticket(user=user, email=user.email, category="order")
    services.assign(ticket, agent, by=agent)
    services.note(ticket, "Called the courier: private to staff", by=agent)
    mine = APIClient()
    mine.force_authenticate(user)
    answer = mine.get("/api/v1/me/tickets/")
    text, [row] = answer.content.decode(), answer.json()["results"]
    assert row["number"] == ticket.number and "assignee" not in row and "messages" not in row
    assert "private to staff" not in text
    assert "Bora" not in text
    settings.CERT_IN_POINT_OF_CONTACT = "Incident desk, incident.desk@examleaf.in"
    assert "incident.desk" not in APIClient().get("/api/v1/config/").content.decode()
