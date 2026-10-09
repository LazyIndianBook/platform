"""The fraud rules: each fires on a made-up case and not on a clean one; tries of book codes are kept as hashes; the
night's email; acknowledging a signal."""

from datetime import timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from api.tests import sign_in, student
from insights.jobs import digest, fraud
from insights.models import FraudSignal, RedemptionAttempt
from learn.models import BookCode
from learn.services import make_codes
from shop.factories import CouponFactory, ProductFactory

from .helpers import learners, sell

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
Kind = FraudSignal.Kind


def tries(count, user=lambda n: 1, ip=lambda n: 1, code=lambda n: "", outcome="unknown", hours_ago=2):
    """Failed tries of book codes in the middle of the hour `hours_ago`: the account, address and code of each are
    functions of its number."""
    when = fraud.hour_of(timezone.now() - timedelta(hours=hours_ago)) + timedelta(minutes=30)
    RedemptionAttempt.objects.bulk_create(
        RedemptionAttempt(
            user_hash=digest("user", user(n)), ip_hash=digest("ip", ip(n)), code_hash=code(n), outcome=outcome,
            created=when,
        )
        for n in range(count)
    )  # fmt: skip


def kinds():
    return sorted(FraudSignal.objects.values_list("kind", flat=True))


def test_each_try_of_a_book_code_is_kept_as_hashes_with_its_batch_and_outcome(physics):
    api = APIClient(REMOTE_ADDR="203.0.113.7")
    user = sign_in(api, student())
    code = make_codes(physics, 1, "PHY-1")[0]
    assert api.post("/api/v1/learn/redeem/", {"code": "ABCD-EFGH-JKLM"}).status_code == 400
    assert api.post("/api/v1/learn/redeem/", {"code": code}).status_code == 200
    sign_in(api, student())
    assert api.post("/api/v1/learn/redeem/", {"code": code}).status_code == 400  # another account: used already
    rows = list(RedemptionAttempt.objects.order_by("created", "pk"))
    assert [(row.outcome, row.batch) for row in rows] == [("unknown", ""), ("redeemed", "PHY-1"), ("used", "PHY-1")]
    assert rows[0].user_hash == rows[1].user_hash == digest("user", user.pk) != rows[2].user_hash
    assert {row.ip_hash for row in rows} == {digest("ip", "203.0.113.7")}
    assert rows[1].code_hash == rows[2].code_hash == digest("code", code.replace("-", ""))
    kept = " ".join(str(value) for row in rows for value in vars(row).values())
    for raw in (code, code.replace("-", ""), "ABCDEFGHJKLM", "203.0.113.7", user.email):
        assert raw not in kept  # no raw value: hashes, the batch and the outcome only


def test_a_failure_to_keep_a_try_does_not_change_the_students_answer(physics, monkeypatch):
    api = APIClient()
    sign_in(api, student())
    monkeypatch.setattr(RedemptionAttempt.objects, "create", lambda **kwargs: 1 / 0)
    code = make_codes(physics, 1, "PHY-1")[0]
    assert api.post("/api/v1/learn/redeem/", {"code": code}).status_code == 200


def test_the_rules_find_nothing_in_ordinary_use(physics):
    tries(4)  # one account's four failures in an hour
    tries(9, user=lambda n: n + 10, ip=lambda n: 7)  # nine accounts at one address (a classroom)
    tries(2, user=lambda n: n + 30, ip=lambda n: n + 30, code=lambda n: "c" * 64)  # one code, two accounts
    make_codes(physics, 4, "PHY-1")
    BookCode.objects.update(redeemed_by=learners(1)[0], redeemed_at=timezone.now())  # four subjects: no resale
    book = ProductFactory(subject=physics)
    for n in range(2):
        sell(book, timezone.localdate(), method="cod", email=f"sibling{n}@example.com")  # two accounts, one home
    assert fraud.fraud_rules() == 0 and not FraudSignal.objects.exists()


def test_failed_codes_from_one_account_or_address_in_an_hour_are_signalled():
    tries(5, ip=lambda n: n)  # five failures of one account, from five addresses
    tries(10, user=lambda n: n + 100, ip=lambda n: "shared")  # ten accounts, one address
    assert fraud.fraud_rules() == 2
    account = FraudSignal.objects.get(kind=Kind.FAILED_CODES_ACCOUNT)
    address = FraudSignal.objects.get(kind=Kind.FAILED_CODES_ADDRESS)
    assert (account.subject, account.count) == (digest("user", 1), 5)
    assert (address.subject, address.count) == (digest("ip", "shared"), 10)
    assert account.window_end - account.window_start == timedelta(hours=1)
    assert fraud.fraud_rules() == 0 and FraudSignal.objects.count() == 2  # the same findings again: nothing new


def test_an_hour_of_failures_far_above_the_usual_is_a_spike():
    tries(19, user=lambda n: n, ip=lambda n: n, hours_ago=30)  # the day before: below the floor of 20
    tries(25, user=lambda n: n + 100, ip=lambda n: n + 100)  # 25 accounts and addresses, one hour
    assert fraud.fraud_rules() == 1
    spike = FraudSignal.objects.get()
    assert (spike.kind, spike.subject, spike.count) == (Kind.FAILED_CODES_SPIKE, "all", 25)
    assert spike.details == {"usual_hour": 0}  # the median hour of the week before


def test_one_account_redeeming_many_codes_and_one_code_tried_by_several_accounts_are_signalled(physics):
    person = learners(1)[0]
    make_codes(physics, 5, "PHY-1")
    BookCode.objects.update(redeemed_by=person, redeemed_at=timezone.now() - timedelta(days=3))
    tries(3, user=lambda n: n + 50, code=lambda n: "c" * 64, outcome="used")
    RedemptionAttempt.objects.update(batch="PHY-1")
    assert fraud.fraud_rules() == 2
    resold = FraudSignal.objects.get(kind=Kind.CODES_PER_ACCOUNT)
    assert (resold.subject, resold.count) == (digest("user", person.pk), 5)
    assert resold.details == {"batches": ["PHY-1"], "codes": sorted(BookCode.objects.values_list("pk", flat=True))}
    shared = FraudSignal.objects.get(kind=Kind.ACCOUNTS_PER_CODE)
    assert (shared.subject, shared.count, shared.details) == ("c" * 64, 3, {"batch": "PHY-1"})


def test_accounts_sharing_a_phone_or_an_address_on_cod_or_coupon_orders_are_signalled(physics):
    book, coupon, today = ProductFactory(subject=physics), CouponFactory(), timezone.localdate()
    one = sell(book, today, method="cod", email="one@example.com")
    two = sell(book, today, method="cod", email="two@example.com", line1="House 4,  ZOO ROAD")  # the same, written so
    three = sell(book, today, coupon=coupon, email="three@example.com")
    sell(book, today, email="four@example.com")  # paid online without a coupon: not counted
    assert fraud.fraud_rules() == 2
    assert {(s.kind, s.count) for s in FraudSignal.objects.all()} == {(Kind.SHARED_PHONE, 3), (Kind.SHARED_ADDRESS, 3)}
    phone = FraudSignal.objects.get(kind=Kind.SHARED_PHONE)
    assert phone.subject == digest("phone", "9864012345")
    assert phone.details == {"orders": sorted([one.number, two.number, three.number])}  # for staff to open them


def test_an_acknowledged_signal_comes_back_only_when_it_grew(client):
    tries(5)
    fraud.fraud_rules()
    admin = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin)
    signals = reverse("admin:insights_fraudsignal_changelist")
    client.post(signals, {"action": "acknowledge", "_selected_action": [FraudSignal.objects.get().pk]})
    signal = FraudSignal.objects.get()
    assert (signal.acknowledged_by, signal.acknowledged_at is not None) == (admin.pk, True)
    assert LogEntry.objects.get().change_message == "Acknowledged."
    assert fraud.fraud_rules() == 0  # acknowledged, and no more than then
    tries(2)
    assert fraud.fraud_rules() == 1 and FraudSignal.objects.filter(acknowledged_at=None).get().count == 7
    assert client.get(signals + "?acknowledged_at__isempty=1").status_code == 200  # the email's link


def test_the_nights_signals_are_emailed_without_personal_data(settings):
    tries(5)
    settings.INSIGHTS_ALERT_EMAILS = []
    fraud.fraud_rules()
    assert not mail.outbox  # nobody to tell
    settings.INSIGHTS_ALERT_EMAILS = ["owner@examleaf.in", "ops@examleaf.in"]
    tries(1)
    assert fraud.fraud_rules() == 1
    assert [message.to for message in mail.outbox] == [["owner@examleaf.in"], ["ops@examleaf.in"]]
    body = mail.outbox[0].body
    assert "Failed book codes from one account in an hour: 6" in body and digest("user", 1)[:8] in body
    assert digest("user", 1) not in body  # the start of the hash only
    mail.outbox.clear()
    assert fraud.fraud_rules() == 0 and not mail.outbox  # nothing new: no email
