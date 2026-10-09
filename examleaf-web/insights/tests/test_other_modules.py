"""The reports on stand-ins for other modules' models, which they read by name (the Finance module's settlements and
their lines, the Course module's code batches): the real ones are those modules', so these are the tests that the two
still fit. The stand-ins have tables of their own for the length of one test."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps
from django.utils import timezone

from accounts.factories import UserFactory
from insights import reports
from learn.models import BookCode
from shop.factories import ProductFactory
from shop.models import Product, money_field
from staff.tests.conftest import STAFF, signed_in

from .helpers import as_test, sell

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def finance(monkeypatch, settings):
    """(Settlement, SettlementLine) as the Finance module keeps them, in tables of their own."""
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live
    with isolate_apps("insights"):

        class Settlement(models.Model):
            settlement_id = models.CharField(max_length=40, unique=True)
            date = models.DateField()
            utr = models.CharField(max_length=60, blank=True)
            gross = money_field("gross", default=0)
            fees = money_field("fees", default=0)
            tax = money_field("tax", default=0)
            net = money_field("net", default=0)
            state = models.CharField(max_length=10, default="fetched")
            livemode = models.BooleanField(default=False)

            class Meta:
                app_label = "insights"
                db_table = "stand_in_settlement"
                ordering = ["-date", "-pk"]

            def __str__(self):
                return self.settlement_id

        class SettlementLine(models.Model):
            settlement = models.ForeignKey(Settlement, on_delete=models.CASCADE, related_name="lines")
            type = models.CharField(max_length=10)
            amount = money_field("amount", default=0)

            class Meta:
                app_label = "insights"
                db_table = "stand_in_settlement_line"

            def __str__(self):
                return f"{self.type} {self.amount}"

        with connection.schema_editor() as editor:
            editor.create_model(Settlement)
            editor.create_model(SettlementLine)
        monkeypatch.setattr(reports, "model", lambda label: {"shop.Settlement": Settlement}[label])
        try:
            yield Settlement, SettlementLine
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(SettlementLine)
                editor.delete_model(Settlement)


@pytest.fixture
def made(finance):
    """Two settlements this week (one of them taking back refunds), a test-keys one, and one long ago."""
    settlement, line = finance
    today = timezone.localdate()
    money = dict(gross=Decimal("1000"), fees=Decimal("20"), tax=Decimal("3.60"), net=Decimal("976.40"))
    newest = settlement.objects.create(
        settlement_id="setl_2", date=today, utr="UTR2", state="matched", livemode=True, **money
    )
    for kind, amount in (("payment", "1100"), ("refund", "60"), ("refund", "40")):
        line.objects.create(settlement=newest, type=kind, amount=Decimal(amount))
    earlier = settlement.objects.create(settlement_id="setl_1", date=today - timedelta(days=3), livemode=True, **money)
    line.objects.create(settlement=earlier, type="payment", amount=Decimal("1000"))
    settlement.objects.create(settlement_id="setl_test", date=today, livemode=False, **money)
    settlement.objects.create(settlement_id="setl_old", date=today - timedelta(days=200), livemode=True, **money)
    return settlement


def test_the_report_lists_the_settlements_newest_first_with_the_refunds_from_their_lines(made):
    owner = UserFactory(is_staff=True, is_superuser=True)
    answer = reports.settlements(owner, {})
    assert answer["configured"] is True and answer["test_mode"] is False and answer["period"]["days"] == 90
    assert [row["reference"] for row in answer["rows"]] == ["setl_2", "setl_1"]  # no test one, none long ago
    assert answer["rows"][0] == {
        "reference": "setl_2",
        "date": timezone.localdate(),
        "gross": Decimal("1000.00"),
        "fees": Decimal("20.00"),
        "tax": Decimal("3.60"),
        "refunds": Decimal("100.00"),  # the two refund lines, not the payment
        "net": Decimal("976.40"),
        "utr": "UTR2",
        "state": "matched",
    }
    assert answer["rows"][1]["refunds"] == Decimal("0.00") and answer["rows"][1]["utr"] == ""


def test_a_site_on_test_keys_counts_every_settlement_and_says_so(made, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_abc"
    answer = reports.settlements(UserFactory(is_staff=True, is_superuser=True), {})
    assert answer["test_mode"] is True
    assert [row["reference"] for row in answer["rows"]] == ["setl_test", "setl_2", "setl_1"]


def test_the_period_narrows_the_settlements(made):
    owner = UserFactory(is_staff=True, is_superuser=True)
    today = timezone.localdate()
    answer = reports.settlements(owner, {"from": str(today - timedelta(days=1)), "to": str(today)})
    assert [row["reference"] for row in answer["rows"]] == ["setl_2"]
    wide = reports.settlements(owner, {"from": str(today - timedelta(days=300)), "to": str(today)})
    assert [row["reference"] for row in wide["rows"]] == ["setl_2", "setl_1", "setl_old"]


def test_the_api_answers_the_same_rows_as_json(made):
    answer = signed_in(UserFactory(is_staff=True, is_superuser=True)).get(f"{STAFF}reports/settlements/")
    assert answer.status_code == 200
    body = answer.json()
    assert body["configured"] is True and [row["reference"] for row in body["rows"]] == ["setl_2", "setl_1"]
    assert body["rows"][0]["refunds"] == "100.00" and body["rows"][0]["date"] == str(timezone.localdate())


@pytest.fixture
def course(monkeypatch):
    """learn.CodeBatch as the Course module keeps it: a label, as BookCode.batch uses it, and the title it is printed
    in (none yet for a batch made before the title was recorded)."""
    with isolate_apps("insights"):

        class CodeBatch(models.Model):
            label = models.CharField(max_length=40, unique=True)
            product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

            class Meta:
                app_label = "insights"
                db_table = "stand_in_code_batch"

            def __str__(self):
                return self.label

        with connection.schema_editor() as editor:
            editor.create_model(CodeBatch)
        monkeypatch.setattr(reports, "model", lambda label: {"learn.CodeBatch": CodeBatch}[label])
        try:
            yield CodeBatch
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(CodeBatch)


def test_codes_sold_are_the_live_copies_of_the_title_the_batch_is_printed_in(course, settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live
    book = ProductFactory(title="Physics Sample Papers")
    for label, count in (("PHY-1", 3), ("PHY-2", 2), ("OLD-1", 1)):
        for number in range(count):
            BookCode.objects.create(digest=f"{label}-{number}".ljust(64, "0"), batch=label)
    course.objects.create(label="PHY-1", product=book)
    course.objects.create(label="PHY-2", product=book)  # a second batch of the same title
    course.objects.create(label="OLD-1")  # made before the title was recorded
    today = timezone.localdate()
    sell(book, today, copies=3)
    sell(book, today, copies=2)
    as_test(sell(book, today, copies=9))  # a test order is no sale
    rows = {row["batch"]: row for row in reports.codes(UserFactory(is_staff=True, is_superuser=True), {})["rows"]}
    assert (rows["PHY-1"]["sold"], rows["PHY-2"]["sold"]) == (5, 5)  # the title's copies, all its batches together
    assert rows["OLD-1"]["sold"] is None  # no title recorded: not zero, not known
    assert rows["PHY-1"]["revoked"] is None  # the code has no void marker here: not recorded
