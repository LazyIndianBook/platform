"""Home (staff_home.py, GET /api/v1/staff/home/): the cards a person's roles and permissions allow, each a number
with its definition, the previous period beside the totals, test mode kept out and said so, and one card failing never
the page."""

import logging
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.factories import UserFactory
from content.models import ErrorReport, Subject
from insights import metrics
from learn.models import BookCode, Chapter, QuizAttempt, QuizItem
from shop.factories import ProductFactory
from shop.models import QuoteRequest
from staff.models import ApiKey, AuditEvent, ChangeRequest
from staff.permissions import make_key
from staff.tests.conftest import STAFF, make_staff, signed_in

from .helpers import as_test, at, learners, pay, sell

pytestmark = pytest.mark.django_db
HOME = STAFF + "home/"
MEASURES = {"net_revenue", "orders_placed", "codes_redeemed", "active_learners"}
CARDS = {  # plan 5.1: the cards of each role
    roles.OWNER: MEASURES
    | {"orders_to_pack", "quotes_open", "tickets_due", "tickets_breached", "reports_open"}
    | {"items_flagged", "refunds_to_approve", "bank_refunds_to_pay", "cod_overdue", "settlement_items_unmatched"},
    roles.ADMIN: MEASURES
    | {"orders_to_pack", "quotes_open", "tickets_due", "tickets_breached", "reports_open"}
    | {"items_flagged", "cod_overdue", "settlement_items_unmatched"},
    # the Finance module's settlements (shop.view_settlement) are FINANCE's, the auditor's and the owners'
    roles.FINANCE: {
        "net_revenue",
        "refunds_to_approve",
        "bank_refunds_to_pay",
        "cod_overdue",
        "settlement_items_unmatched",
    },
    roles.SALES: {"orders_to_pack", "quotes_open"},
    roles.SALES_REP: {"orders_to_pack", "quotes_open"},
    roles.SUPPORT: {"tickets_due", "tickets_breached"},
    roles.CONTENT_EDITOR: {"reports_open", "items_flagged"},
    roles.REVIEWER: {"reports_open", "items_flagged"},
    roles.PACKER: {"orders_to_pack"},
    roles.AUDITOR: MEASURES | {"settlement_items_unmatched"},
    roles.MARKETING: set(),
}


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live: test-mode orders are then left out
    settings.SUPPORT_EMAIL = "help@examleaf.in"


def home(user, **query):
    response = signed_in(user).get(HOME, query)
    assert response.status_code == 200, response.content
    return response.json()


def cards(user, **query):
    return {each["key"]: each for each in home(user, **query)["cards"]}


@pytest.mark.parametrize("role", sorted(CARDS))
def test_each_role_gets_its_cards_and_no_others(role):
    assert set(cards(make_staff(role))) == CARDS[role]


def test_a_break_glass_account_is_an_owner_and_an_api_key_gets_no_cards():
    assert set(cards(make_staff(is_superuser=True))) == CARDS[roles.OWNER]
    key, prefix, digest = make_key()
    ApiKey.objects.create(
        name="Courier",
        prefix=prefix,
        secret_hash=digest,
        scopes=["shop.view_order"],
        sponsor=make_staff(roles.OWNER),
        expires_at=timezone.now() + timedelta(days=30),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    assert client.get(HOME).json()["cards"] == []


def test_home_is_for_staff_only_and_never_cached():
    assert APIClient().get(HOME).status_code == 401
    student = UserFactory()
    refused = signed_in(student).get(HOME)
    assert refused.status_code == 403 and AuditEvent.objects.filter(action="authz_fail", actor_id=student.pk).exists()
    answer = signed_in(make_staff(roles.PACKER)).get(HOME)
    assert answer["Cache-Control"] == "no-store"


def test_the_owner_has_the_money_and_the_counts_beside_the_previous_period():
    physics = Subject.objects.create(name="Physics", code="PHY", board=_board(), class_level=_level())
    book = ProductFactory(subject=physics, price=Decimal("300.00"))
    today = timezone.localdate()
    pay(sell(book, today - timedelta(days=1)), when=at(today - timedelta(days=1)))  # this week
    pay(sell(book, today - timedelta(days=2), copies=2), when=at(today - timedelta(days=2)))  # ... 600
    pay(sell(book, today - timedelta(days=9)), when=at(today - timedelta(days=9)))  # the week before: 300
    as_test(sell(book, today - timedelta(days=1)))  # a test order: in no number
    found = home(make_staff(roles.OWNER))
    card = {each["key"]: each for each in found["cards"]}
    revenue, orders = card["net_revenue"], card["orders_placed"]
    assert (found["period"]["key"], found["period"]["days"]) == ("week", 7)
    assert found["period"]["end"] == str(today) and found["period"]["start"] == str(today - timedelta(days=6))
    assert (revenue["value"], revenue["unit"], revenue["group"], revenue["error"]) == ("900.00", "inr", "measure", "")
    assert revenue["comparison"] == {
        "previous": "300.00",
        "difference": "+600.00",
        "percent": "+200.0",
        "period": {"start": str(today - timedelta(days=13)), "end": str(today - timedelta(days=7)), "days": 7},
    }
    assert (orders["value"], orders["comparison"]["previous"], orders["comparison"]["difference"]) == ("2", "1", "+1")
    assert revenue["definition"].startswith("Money received less money returned") and revenue["as_of"]
    assert revenue["href"] == f"/reports/sales/?from={today - timedelta(days=6)}&to={today}"
    assert (revenue["test_mode"], found["test_mode"], found["test_orders_left_out"]) == (False, False, 1)
    assert card["orders_to_pack"]["period"] is None and card["orders_to_pack"]["comparison"] is None  # a queue


def _board():
    from content.models import Board

    return Board.objects.get_or_create(short_name="ASSEB", defaults={"name": "Assam", "state": "Assam"})[0]


def _level():
    from content.models import ClassLevel

    return ClassLevel.objects.get_or_create(number=12)[0]


def test_a_percent_from_nothing_is_not_made_up():
    book = ProductFactory(price=Decimal("300.00"))
    pay(sell(book, timezone.localdate()), when=at(timezone.localdate()))
    revenue = cards(make_staff(roles.OWNER))["net_revenue"]
    assert (revenue["value"], revenue["comparison"]["previous"], revenue["comparison"]["percent"]) == (
        "300.00",
        "0.00",
        None,
    )


def test_a_packer_gets_the_orders_to_pack_and_nothing_of_the_money():
    book = ProductFactory(price=Decimal("300.00"))
    sell(book, timezone.localdate())
    sell(book, timezone.localdate(), method="cod")
    as_test(sell(book, timezone.localdate()))
    packer = cards(make_staff(roles.PACKER))
    assert set(packer) == {"orders_to_pack"} and packer["orders_to_pack"]["value"] == "2"
    assert packer["orders_to_pack"]["href"] == "/orders/?tab=to_pack"
    assert home(make_staff(roles.PACKER))["test_orders_left_out"] == 1  # the packer reads orders: told, not shown


def test_the_cards_of_the_support_content_and_finance_desks():
    physics = Subject.objects.create(name="Physics", code="PHY", board=_board(), class_level=_level())
    target = ContentType.objects.get_for_model(Subject)
    for number, category in enumerate(("typo", "item_analysis", "item_analysis")):
        ErrorReport.objects.create(target_type=target, target_id=100 + number, subject=physics, category=category)
    QuoteRequest.objects.create(
        school="Cotton Collegiate",
        contact_name="Anita Das",
        email="o@example.com",
        phone="+919864012345",
        delivery_pin="781001",
        items=[{"product": "x", "title": "X", "quantity": 1}],
    )
    assert cards(make_staff(roles.CONTENT_EDITOR))["reports_open"]["value"] == "3"
    flagged = cards(make_staff(roles.CONTENT_EDITOR))["items_flagged"]
    assert (flagged["value"], flagged["href"]) == ("2", "/content/reports/?category=item_analysis")
    assert cards(make_staff(roles.SALES))["quotes_open"]["value"] == "1"
    book = ProductFactory()
    ChangeRequest.objects.create(
        action="order.refund",
        target_type="shop.order",
        target_id=str(sell(book, timezone.localdate()).pk),
        payload={},
        payload_sha256="0" * 64,
        maker=make_staff(roles.SALES),
        reason="Damaged",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    finance = cards(make_staff(roles.FINANCE))
    assert (finance["refunds_to_approve"]["value"], finance["refunds_to_approve"]["href"]) == (
        "1",
        "/approvals/?who=awaiting",
    )
    assert cards(make_staff(roles.SUPPORT))["tickets_breached"]["href"] == "/support/?tab=overdue"


def test_active_learners_are_the_last_seven_days_whatever_the_period():
    chapter = Chapter.objects.create(
        subject=Subject.objects.create(name="Physics", code="PHY", board=_board(), class_level=_level()),
        number=1,
        title="Charges",
    )
    item = QuizItem.objects.create(chapter=chapter, kind="true_false", text="T", answer="true")
    a, b = learners(2)
    QuizAttempt.objects.create(user=a, item=item, correct=True)
    QuizAttempt.objects.create(user=b, item=item, correct=True, created=timezone.now() - timedelta(days=10))
    BookCode.objects.create(digest="a" * 64, batch="PHY-1", redeemed_by=a, redeemed_at=timezone.now())
    owner = make_staff(roles.OWNER)
    for period in ("today", "week", "month"):
        found = cards(owner, period=period)
        assert found["active_learners"]["value"] == "1", period
        assert found["active_learners"]["period"]["days"] == 7, period
        assert found["active_learners"]["comparison"]["previous"] == "1", period  # the one 10 days ago
    assert cards(owner, period="today")["codes_redeemed"]["value"] == "1"
    assert cards(owner, period="today")["codes_redeemed"]["period"]["days"] == 1
    assert cards(owner, period="month")["codes_redeemed"]["period"]["days"] == 30


def test_the_period_is_one_of_three():
    owner = make_staff(roles.OWNER)
    assert (
        home(owner)["period"]["key"] == "week" and home(owner, period="month")["period"]["label"] == "The last 30 days"
    )
    refused = signed_in(owner).get(HOME, {"period": "year"})
    assert refused.status_code == 400 and "period" in refused.json()


def test_a_site_on_test_keys_flags_its_cards(settings):
    book = ProductFactory(price=Decimal("300.00"))
    pay(as_test(sell(book, timezone.localdate())), when=at(timezone.localdate()))
    settings.RAZORPAY_KEY_ID = "rzp_test_abc"
    found = home(make_staff(roles.OWNER))
    assert found["test_mode"] is True and found["test_orders_left_out"] == 0  # nothing is left out: all of it is test
    revenue = {each["key"]: each for each in found["cards"]}["net_revenue"]
    assert (revenue["value"], revenue["test_mode"]) == ("300.00", True)


def test_a_card_that_cannot_be_worked_out_is_a_card_with_an_error_not_a_home_that_fails(monkeypatch, caplog):
    def broken(user, period):
        raise RuntimeError("the database went away")

    monkeypatch.setitem(metrics.SPECS, "orders_to_pack", replace(metrics.SPECS["orders_to_pack"], run=broken))
    with caplog.at_level(logging.ERROR, logger="insights.staff_home"):
        found = cards(make_staff(roles.OWNER))
    assert found["orders_to_pack"]["value"] is None and found["orders_to_pack"]["error"]
    assert found["orders_to_pack"]["definition"] and found["net_revenue"]["error"] == ""  # the rest answer
    assert "orders_to_pack" in caplog.text


def test_a_card_whose_source_is_not_installed_is_left_out_not_zero(monkeypatch):
    def absent(user, period):
        raise metrics.Absent("finance")

    monkeypatch.setitem(metrics.SPECS, "cod_overdue", replace(metrics.SPECS["cod_overdue"], run=absent))
    assert "cod_overdue" not in cards(make_staff(roles.OWNER))
    assert "bank_refunds_to_pay" in cards(make_staff(roles.OWNER))
