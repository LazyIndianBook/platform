"""Rules that score one order or one business account, each giving a bucket and its top three reasons (research-b2b-
predictive.md 4.8 and 4.5). Rules, not a model: below about 200 known outcomes a model would only fit noise (0.6);
logistic regression comes after some 200 parcels returned to origin, or 200 schools with a known outcome. The points
are a starting point, to be reviewed each season against what happened."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from shop.models import PinCode

from ..models import AccountScore

PRIOR_RTO = 0.15  # the share of COD parcels returned to origin assumed before any parcel tells
SMOOTHING = 20  # parcels' worth of weight a PIN code's rate gives to its district's (and a district's to PRIOR_RTO)
HIGH_VALUE = Decimal(1000)  # rupees: a cash-on-delivery order worth this much is a bigger loss when refused
ACTIONS = {
    "high": "Prepaid only, or confirm by SMS or WhatsApp before dispatch.",
    "medium": "Call the customer to confirm.",
    "low": "Ship.",
}


@dataclass
class RtoHistory:
    """What the shipping app will know from its parcels' outcomes (delivered, returned to origin); zeros until then."""

    pin_parcels: int = 0  # COD parcels to the order's PIN code
    pin_returned: int = 0
    district_parcels: int = 0  # ... and to its district
    district_returned: int = 0
    customer_returned: int = 0  # parcels of this customer returned to origin
    customer_cod_orders: int = 0  # the customer's earlier cash-on-delivery orders


@dataclass
class Risk:
    bucket: str  # high, medium or low
    score: int
    reasons: list = field(default_factory=list)  # the top three, the strongest first
    action: str = ""


def top(found, buckets):
    """(score, bucket, reasons) from [(points, reason)]: the bucket of the first threshold the score reaches."""
    score = sum(points for points, _ in found)
    bucket = next(name for name, least in buckets if score >= least)
    return score, bucket, [reason for _, reason in sorted(found, key=lambda one: -abs(one[0]))[:3]]


def rto_risk(order, history=None):
    """How likely a cash-on-delivery order is to come back unpaid: the PIN code's return rate smoothed toward its
    district's, the customer's earlier returns, a first COD order, the order's value, a PIN code missing from India
    Post's directory or in another state. High from 4 points, medium from 2."""
    if not order.is_cod:
        return Risk("low", 0, ["paid online"], ACTIONS["low"])
    history = history or RtoHistory()
    district_rate = (history.district_returned + SMOOTHING * PRIOR_RTO) / (history.district_parcels + SMOOTHING)
    pin_rate = (history.pin_returned + SMOOTHING * district_rate) / (history.pin_parcels + SMOOTHING)
    found = []
    if pin_rate >= 0.30:
        found.append((3, f"{pin_rate:.0%} of COD parcels to this PIN code come back"))
    elif pin_rate >= 0.20:
        found.append((1, f"{pin_rate:.0%} of COD parcels to this PIN code come back"))
    if history.customer_returned:
        found.append((3, f"{history.customer_returned} of the customer's parcels came back before"))
    if not history.customer_cod_orders:
        found.append((1, "the customer's first cash-on-delivery order"))
    if order.total.amount >= HIGH_VALUE:
        found.append((1, f"an order of ₹{order.total.amount:,.0f}"))
    pin, state = order.shipping_address.get("pin", ""), order.shipping_address.get("state", "")
    if PinCode.objects.exists() and not PinCode.objects.filter(pin=pin).exists():  # (once the directory is loaded)
        found.append((2, f"PIN code {pin} is not in India Post's directory"))
    elif problem := PinCode.state_problem(pin, state):
        found.append((2, problem))
    score, bucket, reasons = top(found, [("high", 4), ("medium", 2), ("low", -100)])
    return Risk(bucket, score, reasons, ACTIONS[bucket])


def score_account(signals):
    """A school's or distributor's lead score from a dict of signals (research 4.5): ordered last year (3), adopted the
    books last year (3), verified teachers there (1 each, at most 3), book codes redeemed in its PIN code or district
    (1 per 10, at most 3), a sample sent and followed up (2), Class 12 pupils (1 per 100, at most 3); minus 1 a month
    since the last contact (at most 3). High from 7, medium from 4. Returns (score, bucket, top three reasons)."""
    found = []
    if signals.get("ordered_last_year"):
        found.append((3, "ordered last year"))
    if signals.get("adopted_last_year"):
        found.append((3, "adopted our books last year"))
    if teachers := signals.get("verified_teachers", 0):
        found.append((min(teachers, 3), f"{teachers} verified teacher{'s' if teachers > 1 else ''}"))
    if codes := signals.get("codes_redeemed_nearby", 0):
        found.append((min(codes // 10 + 1, 3), f"{codes} book codes redeemed in its PIN code or district"))
    if signals.get("sample_followed_up"):
        found.append((2, "sample sent and followed up"))
    if pupils := signals.get("class12_enrolment", 0):
        found.append((min(pupils // 100 + 1, 3), f"{pupils} pupils in Class 12"))
    if (days := signals.get("days_since_contact", 0)) >= 30:
        found.append((-min(days // 30, 3), f"no contact for {days} days"))
    return top(found, [("high", 7), ("medium", 4), ("low", -100)])


def score_accounts(kind, accounts):
    """AccountScore rows for {ERPNext name: signals} of one kind (school or distributor): the sync from ERPNext is to
    call this; nothing does yet. Returns how many."""
    now, rows = timezone.now(), []
    for ref, signals in accounts.items():
        score, bucket, reasons = score_account(signals)
        rows.append(
            AccountScore(kind=kind, external_ref=ref, score=score, bucket=bucket, reasons=reasons, computed_at=now)
        )
    return len(AccountScore.objects.bulk_create(rows))
