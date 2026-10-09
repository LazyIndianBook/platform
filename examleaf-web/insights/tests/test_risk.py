"""The COD return-to-origin rules and the school and distributor score, on made-up orders and signals."""

from decimal import Decimal

import pytest

from insights.jobs.risk import RtoHistory, rto_risk, score_account, score_accounts
from insights.models import AccountScore
from shop.factories import ADDRESS
from shop.models import Order

pytestmark = pytest.mark.django_db


def order(method="cod", total="300", **address):
    return Order(payment_method=method, total=Decimal(total), shipping_address={**ADDRESS, **address})


def test_a_prepaid_order_or_a_first_small_cod_order_is_low_risk(directory):
    assert (rto_risk(order("razorpay")).bucket, rto_risk(order("razorpay")).reasons) == ("low", ["paid online"])
    risk = rto_risk(order())  # no history yet: every rate at the prior, 15 %
    assert (risk.bucket, risk.score, risk.reasons, risk.action) == (
        "low", 1, ["the customer's first cash-on-delivery order"], "Ship.",
    )  # fmt: skip


def test_a_pin_code_that_returns_parcels_and_a_customer_who_refused_before_are_high_risk(directory):
    history = RtoHistory(pin_parcels=50, pin_returned=25, customer_returned=1, customer_cod_orders=2)
    risk = rto_risk(order(total="1200"), history)  # PIN: (25 + 20 × 0.15) / (50 + 20) = 40 %
    assert (risk.bucket, risk.score) == ("high", 7)
    assert risk.reasons == [
        "40% of COD parcels to this PIN code come back",
        "1 of the customer's parcels came back before",
        "an order of ₹1,200",
    ]
    assert risk.action == "Prepaid only, or confirm by SMS or WhatsApp before dispatch."


def test_a_few_returns_to_one_pin_code_are_smoothed_toward_its_district(directory):
    history = RtoHistory(
        pin_parcels=2, pin_returned=2, district_parcels=100, district_returned=10, customer_cod_orders=1
    )
    risk = rto_risk(order(), history)  # district (10 + 3) / 120 = 10.8 %; PIN (2 + 20 × 0.108) / 22 = 18.9 %
    assert (risk.bucket, risk.score, risk.reasons) == ("low", 0, [])


def test_an_address_the_directory_does_not_know_or_places_elsewhere_is_medium_risk(directory):
    risk = rto_risk(order(pin="799999"))
    assert (risk.bucket, risk.reasons[0]) == ("medium", "PIN code 799999 is not in India Post's directory")
    risk = rto_risk(order(pin="781001", state="WB"))
    assert (risk.bucket, risk.reasons[0]) == ("medium", "PIN code 781001 is in Assam.")
    assert risk.action == "Call the customer to confirm."


def test_schools_and_distributors_are_scored_by_the_rules_with_their_reasons():
    signals = {"ordered_last_year": True, "verified_teachers": 2, "codes_redeemed_nearby": 25, "days_since_contact": 75}
    score, bucket, reasons = score_account(signals)
    assert (score, bucket) == (3 + 2 + 3 - 2, "medium")  # two months without contact: -2
    assert reasons == ["ordered last year", "25 book codes redeemed in its PIN code or district", "2 verified teachers"]
    assert score_account({**signals, "adopted_last_year": True})[:2] == (9, "high")
    assert score_account({"sample_followed_up": True, "class12_enrolment": 150}) == (
        4, "medium", ["sample sent and followed up", "150 pupils in Class 12"],
    )  # fmt: skip
    assert score_account({"days_since_contact": 400}) == (-3, "low", ["no contact for 400 days"])
    assert score_accounts("school", {"Cotton Collegiate": signals, "Unknown school": {}}) == 2
    assert {(s.external_ref, s.bucket, s.score) for s in AccountScore.objects.all()} == {
        ("Cotton Collegiate", "medium", 6), ("Unknown school", "low", 0),
    }  # fmt: skip
