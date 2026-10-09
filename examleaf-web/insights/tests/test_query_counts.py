"""Home and the reports read the same number of queries whatever the number of rows (no query per product, per place,
per batch or per chapter): each request counted with one row, then with several more (RESILIENCE.md, the database)."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts import roles
from insights.jobs import health
from insights.models import CodeActivationStat
from learn.models import BookCode, CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from shipping.models import CodRemittance
from shop.factories import ProductFactory
from shop.models import Shipment
from staff.tests.conftest import STAFF, make_staff, signed_in

from .helpers import at, give_back, learners, pay, sell

pytestmark = pytest.mark.django_db
PERIOD = {"from": "2026-10-01", "to": "2026-10-07"}


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""
    settings.SUPPORT_EMAIL = "help@examleaf.in"


def queries(client, path, **params):
    """The queries of a request, after a first one has put in the cache what it keeps (the site's switches)."""
    client.get(STAFF + path, params)
    with CaptureQueriesContext(connection) as captured:
        assert client.get(STAFF + path, params).status_code == 200
    return len(captured)


def more_sales(physics, count, start=0):
    """`count` more titles, each sold to a PIN of its own, paid, with a refund and a cash-on-delivery parcel."""
    for number in range(start, start + count):
        book = ProductFactory(subject=physics, price=Decimal("300.00"), slug=f"book-{number}")
        order = sell(book, date(2026, 10, 2), pin=f"78100{number % 10}", state="AS", district=f"District {number}")
        payment = pay(order, when=at(date(2026, 10, 2)))
        give_back(payment, 10, when=at(date(2026, 10, 3)))
        shipment = Shipment.objects.create(order=order, courier=f"Courier {number % 3}", tracking_number=f"T{number}")
        CodRemittance.objects.create(
            shipment=shipment, expected_amount=300, expected_on=date(2026, 10, 1 + number % 5), state="overdue"
        )


def more_course(physics, count, start=0):
    for number in range(start, start + count):
        chapter = Chapter.objects.create(subject=physics, number=number + 1, title=f"Chapter {number}")
        clip = Clip.objects.create(revision=Revision.objects.create(chapter=chapter, title="R"), title="C")
        item = QuizItem.objects.create(chapter=chapter, kind="true_false", text="T", answer="true")
        card = FlashCard.objects.create(chapter=chapter, front="f", back="b")
        for learner in learners(2, start=number * 2 + 100):
            QuizAttempt.objects.create(user=learner, item=item, correct=True, created=at(date(2026, 10, 6)))
            CardReview.objects.create(user=learner, card=card, known=True, created=at(date(2026, 10, 6)))
            Progress.objects.create(user=learner, clip=clip, completed=True)
            Progress.objects.filter(user=learner, clip=clip).update(updated=at(date(2026, 10, 6)))
        BookCode.objects.create(digest=f"{number}".rjust(64, "c"), batch=f"PHY-{number}", subject=physics)
        CodeActivationStat.objects.create(
            batch=f"PHY-{number}", district=f"District {number}", redeemed=12, redeemed_7d=1
        )


def test_the_reports_read_as_many_queries_with_one_row_as_with_several(physics, directory, monkeypatch):
    original = timezone.localdate
    monkeypatch.setattr(
        timezone, "localdate", lambda v=None, tz=None: date(2026, 10, 10) if v is None else original(v, tz)
    )
    client = signed_in(make_staff(roles.OWNER))
    more_sales(physics, 1)
    more_course(physics, 1)
    health.course_health(today=date(2026, 10, 14))
    paths = {
        "sales": ("reports/sales/", {**PERIOD, "by": "product", "grain": "day"}),
        "subject": ("reports/sales/", {**PERIOD, "by": "subject", "grain": "month"}),
        "place": ("reports/sales-by-place/", {**PERIOD, "level": "district"}),
        "pins": ("reports/sales-by-place/", {**PERIOD, "level": "pin"}),
        "codes": ("reports/codes/", {}),
        "health": ("reports/course-health/", {"grain": "day"}),
        "cod": ("reports/cod/", PERIOD),
        "settlements": ("reports/settlements/", {}),
        "index": ("reports/", {}),
        "home": ("home/", {}),
    }
    one = {name: queries(client, path, **params) for name, (path, params) in paths.items()}
    more_sales(physics, 4, start=1)
    more_course(physics, 4, start=1)
    health.course_health(today=date(2026, 10, 14))
    many = {name: queries(client, path, **params) for name, (path, params) in paths.items()}
    assert many == one, (one, many)
    assert (
        max(one.values()) < 60
    )  # Home is the most: a card or two queries each, a comparison twice (a dozen are the session's own)
