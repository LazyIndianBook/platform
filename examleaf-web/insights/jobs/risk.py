"""Rules that score one order or one business account, each giving a bucket and its top three reasons (research-b2b-
predictive.md 4.8 and 4.5). Rules, not a model: below about 200 known outcomes a model would only fit noise (0.6);
logistic regression comes after some 200 parcels returned to origin, or 200 schools with a known outcome. The points
are a starting point, to be reviewed each season against what happened."""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from shop.models import Order, PinCode

from ..models import AccountScore
from . import digest

PRIOR_RTO = 0.15  # the share of COD parcels returned to origin assumed before any parcel tells
SMOOTHING = 20  # parcels' worth of weight a PIN code's rate gives to its district's (and a district's to PRIOR_RTO)
HISTORY_DAYS = 365  # the parcels' outcomes a score reads
RANDOM_RUNS = ("asdf", "qwer", "zxcv", "hjkl", "uiop")
PLACEHOLDERS = re.compile(r"(test|testing|na|n a|none|nil|xyz|abc|address|home|house|my house|-+|\.+)")
ACTIONS = {
    "high": "Prepaid only, or confirm by SMS or WhatsApp before dispatch.",
    "medium": "Call the customer to confirm.",
    "low": "Ship.",
}


@dataclass
class RtoHistory:
    """What the shipping app knows from its parcels' outcomes (delivered, returned to origin): history_for reads it."""

    pin_parcels: int = 0  # COD parcels to the order's PIN code (delivered or returned: their outcome known)
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
    if order.total.amount >= Decimal(settings.SHOP_COD_HIGH_VALUE_INR):
        found.append((1, f"an order of ₹{order.total.amount:,.0f}"))
    if junk := junk_address(order.shipping_address):
        found.append((2, junk))
    pin, state = order.shipping_address.get("pin", ""), order.shipping_address.get("state", "")
    if PinCode.objects.exists() and not PinCode.objects.filter(pin=pin).exists():  # (once the directory is loaded)
        found.append((2, f"PIN code {pin} is not in India Post's directory"))
    elif problem := PinCode.state_problem(pin, state):
        found.append((2, problem))
    score, bucket, reasons = top(found, [("high", 4), ("medium", 2), ("low", -100)])
    return Risk(bucket, score, reasons, ACTIONS[bucket])


def junk_address(address):
    """Why a delivery address looks as if no courier could find it, or None: a first line too short or without a
    letter, a character typed five times running, a keyboard run, a placeholder word."""
    line = " ".join(str(address.get("line1", "")).split()).lower()
    letters = re.sub(r"[^a-z]", "", line)
    if len(line) < 6 or not letters:
        return "the address's first line is too short to find"
    if re.search(r"(.)\1{4,}", line) or any(run in letters for run in RANDOM_RUNS):
        return "the address looks typed at random"
    if PLACEHOLDERS.fullmatch(re.sub(r"[^a-z0-9 .-]", " ", line).strip()):
        return "the address is a placeholder"
    return None


def contacts(address):
    """Keyed hashes of an address snapshot's phone number (its last 10 digits) and of its first line with its PIN code,
    as the fraud rules match them (insights.jobs.fraud.shared_contacts): equal values match, none can be read back."""
    phone = re.sub(r"\D", "", str(address.get("phone", "")))[-10:]
    line = re.sub(r"[^a-z0-9]", "", str(address.get("line1", "")).lower())
    return {
        digest("phone", phone) if phone else None,
        digest("address", f"{line} {address.get('pin', '')}") if line else None,
    } - {None}


def history_for(order, now=None):
    """The RtoHistory of a cash-on-delivery order, from the shipping app's outcomes over the last HISTORY_DAYS: the
    COD parcels delivered or returned to origin (RTO) to its PIN code and to its district; the customer's parcels that
    came back before, matched by their account or email address, or by keyed hashes of the phone number and the
    address (compared here, never kept); and the customer's earlier cash-on-delivery orders. Nothing is stored, so no
    row of this app points to a person (the app's rule)."""
    from shipping.models import ShipmentDetail

    since = (now or timezone.now()) - timedelta(days=HISTORY_DAYS)
    address = order.shipping_address
    known = ShipmentDetail.objects.filter(
        cod_amount__isnull=False, status__in=["delivered", "returned"], modified__gte=since
    ).exclude(shipment__order=order.pk)
    came_back = Count("pk", filter=Q(status="returned"))
    pin = known.filter(shipment__order__shipping_address__pin=address.get("pin", "")).aggregate(
        parcels=Count("pk"), returned=came_back
    )
    district = str(address.get("district", "")).strip()
    region = (
        known.filter(shipment__order__shipping_address__district__iexact=district).aggregate(
            parcels=Count("pk"), returned=came_back
        )
        if district
        else {"parcels": 0, "returned": 0}
    )
    mine, customer_returned = contacts(address), 0
    # ponytail: every returned COD parcel of the year hashed per order placed; a stored hash column when they number
    # in the tens of thousands
    returned = known.filter(status="returned").values_list(
        "shipment__order__shipping_address", "shipment__order__user_id", "shipment__order__email"
    )
    for other, user_id, email in returned:
        same = (order.user_id and user_id == order.user_id) or (email or "").lower() == (order.email or "").lower()
        if same or (mine and mine & contacts(other or {})):
            customer_returned += 1
    earlier = Order.objects.filter(payment_method=Order.Method.COD, placed_at__isnull=False).exclude(pk=order.pk)
    by_customer = Q(email__iexact=order.email) | (Q(user=order.user_id) if order.user_id else Q(pk__in=[]))
    return RtoHistory(
        pin_parcels=pin["parcels"],
        pin_returned=pin["returned"],
        district_parcels=region["parcels"],
        district_returned=region["returned"],
        customer_returned=customer_returned,
        customer_cod_orders=earlier.filter(by_customer).count(),
    )


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
