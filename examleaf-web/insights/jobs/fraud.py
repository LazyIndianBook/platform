"""Fraud and abuse rules (research-b2b-predictive.md 4.10). Each finding is a FraudSignal; staff are emailed the night's
new ones with the print runs to act on (INSIGHTS_ALERT_EMAILS).

- Book codes (OWASP OAT-002, token cracking): failed tries per account and per IP address in an hour, and an hour of
  failures far above the usual; one account redeeming many codes (resale); one code tried by several accounts (a
  photo of a code shared).
- Shop: several accounts sharing a phone number or an address on cash-on-delivery or coupon orders.
- Not yet, for want of data: redemptions from a batch not yet dispatched (a batch has no dispatch date: ERPNext's Book
  Code Batch is to have one) and repeated COD refusals (no parcel outcome: the shipping app is to record it)."""

import logging
import re
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.throttling import BaseThrottle

from learn.models import CODE_ALPHABET, CODE_LENGTH, BookCode, clean_code, code_digest
from ops.tasks import queue_text_email
from shop.models import Order, live_mode

from .. import stats
from ..models import ForecastRun, FraudSignal, PrintRunAdvice, RedemptionAttempt
from . import digest, latest

logger = logging.getLogger("insights")

FAILS_PER_ACCOUNT, FAILS_PER_ADDRESS = 5, 10  # in an hour (the redeem throttle lets 5 through per account and address)
SPIKE_FLOOR, SPIKE_TIMES = 20, 3  # an hour's failures: at least 20, and 3 times the median hour of the week before
CODES_PER_ACCOUNT = 4  # redeemed by one account in 30 days: more looks like resale (a student has four subjects)
ACCOUNTS_PER_CODE = 3  # accounts trying one code in 30 days
ACCOUNTS_PER_CONTACT = 3  # accounts sharing a phone number or an address on COD or coupon orders in 90 days
KEEP_ATTEMPTS = timedelta(days=180)  # book codes tried: CERT-In's floor for logs
HOUR = timedelta(hours=1)
LISTED = 20  # order numbers or book code ids a signal lists, for staff to open (references, not personal data)


def record_redemption(request, code, ok):
    """Keep a book code tried in the app (api/learn.py RedeemView) as a RedemptionAttempt: keyed hashes of the account,
    the client's address (as the redeem throttle counts it) and the code (a well-formed one only), its batch and the
    outcome. Never raises: a failure is logged and the student's answer stays as it was."""
    try:
        code = clean_code(code)
        batch = BookCode.objects.filter(digest=code_digest(code)).values_list("batch", flat=True).first()
        if ok:
            outcome = RedemptionAttempt.Outcome.REDEEMED
        else:
            outcome = RedemptionAttempt.Outcome.UNKNOWN if batch is None else RedemptionAttempt.Outcome.USED
        well_formed = len(code) == CODE_LENGTH and not set(code) - set(CODE_ALPHABET)
        RedemptionAttempt.objects.create(
            user_hash=digest("user", request.user.pk),
            ip_hash=digest("ip", BaseThrottle().get_ident(request)),
            code_hash=digest("code", code) if well_formed else "",
            batch=batch or "",
            outcome=outcome,
        )
    except Exception:
        logger.exception("could not record a book code tried")


def hour_of(moment):
    return timezone.localtime(moment).replace(minute=0, second=0, microsecond=0)


def failed_codes(now):
    """Findings from the failed tries: per account and per address in an hour of the last day, and spikes."""
    found, day_ago = [], hour_of(now - timedelta(days=1))
    hours, accounts, addresses = defaultdict(int), defaultdict(int), defaultdict(int)
    tries = RedemptionAttempt.objects.exclude(outcome=RedemptionAttempt.Outcome.REDEEMED)
    tries = tries.filter(created__gte=day_ago - timedelta(days=7))
    for user_hash, ip_hash, created in tries.values_list("user_hash", "ip_hash", "created"):
        hour = hour_of(created)
        hours[hour] += 1
        if hour >= day_ago:
            accounts[user_hash, hour] += 1
            addresses[ip_hash, hour] += 1
    for kind, counts, least in (
        (FraudSignal.Kind.FAILED_CODES_ACCOUNT, accounts, FAILS_PER_ACCOUNT),
        (FraudSignal.Kind.FAILED_CODES_ADDRESS, addresses, FAILS_PER_ADDRESS),
    ):
        found += [(kind, subject, n, hour, hour + HOUR, {}) for (subject, hour), n in counts.items() if n >= least]
    usual = stats.quantile([hours.get(day_ago - h * HOUR, 0) for h in range(1, 169)], 0.5)
    for hour, n in hours.items():
        if hour >= day_ago and n >= max(SPIKE_FLOOR, SPIKE_TIMES * usual):
            found.append((FraudSignal.Kind.FAILED_CODES_SPIKE, "all", n, hour, hour + HOUR, {"usual_hour": usual}))
    return found


def codes_shared_or_resold(now):
    """Findings from the last 30 days: accounts redeeming many codes, codes tried by several accounts."""
    found, since = [], now - timedelta(days=30)
    redeemed = BookCode.objects.filter(redeemed_at__gte=since, redeemed_by__isnull=False).order_by()
    for user, n in redeemed.values_list("redeemed_by").annotate(n=Count("pk")).filter(n__gt=CODES_PER_ACCOUNT):
        codes = list(redeemed.filter(redeemed_by=user).order_by("pk").values_list("pk", "batch"))
        details = {"batches": sorted({batch for _, batch in codes}), "codes": [pk for pk, _ in codes][:LISTED]}
        found.append((FraudSignal.Kind.CODES_PER_ACCOUNT, digest("user", user), n, since, now, details))
    tried, batches = defaultdict(set), {}
    tries = RedemptionAttempt.objects.filter(created__gte=since).exclude(code_hash="")
    for code_hash, user_hash, batch in tries.values_list("code_hash", "user_hash", "batch"):
        tried[code_hash].add(user_hash)
        batches[code_hash] = batch
    for code_hash, users in tried.items():
        if len(users) >= ACCOUNTS_PER_CODE:
            details = {"batch": batches[code_hash]}
            found.append((FraudSignal.Kind.ACCOUNTS_PER_CODE, code_hash, len(users), since, now, details))
    return found


def shared_contacts(now):
    """Findings from the last 90 days' COD and coupon orders: a phone number or an address used by several accounts
    (a guest counts by email address), with the orders' numbers for staff to open them."""
    since = now - timedelta(days=90)
    orders = Order.objects.filter(Q(payment_method=Order.Method.COD) | Q(coupon__isnull=False), placed_at__gte=since)
    if live_mode():
        orders = orders.filter(livemode=True)
    groups = {FraudSignal.Kind.SHARED_PHONE: defaultdict(dict), FraudSignal.Kind.SHARED_ADDRESS: defaultdict(dict)}
    for number, user, email, address in orders.values_list("number", "user", "email", "shipping_address"):
        account = f"#{user}" if user else email.lower()
        if phone := re.sub(r"\D", "", str(address.get("phone", "")))[-10:]:
            groups[FraudSignal.Kind.SHARED_PHONE][digest("phone", phone)][number] = account
        if line := re.sub(r"[^a-z0-9]", "", str(address.get("line1", "")).lower()):
            groups[FraudSignal.Kind.SHARED_ADDRESS][digest("address", f"{line} {address.get('pin', '')}")][number] = (
                account
            )
    found = []
    for kind, contacts in groups.items():
        for subject, accounts in contacts.items():
            if len(set(accounts.values())) >= ACCOUNTS_PER_CONTACT:
                details = {"orders": sorted(accounts)[:LISTED]}
                found.append((kind, subject, len(set(accounts.values())), since, now, details))
    return found


def signal(kind, subject, count, start, end, details):
    """A finding as a FraudSignal: a new one, or the open one of its kind and subject whose window it overlaps brought
    up to date; nothing when it adds nothing (an acknowledged one counted as many). The signal if new or grown."""
    earlier = FraudSignal.objects.filter(kind=kind, subject=subject, window_end__gt=start).first()
    if earlier is None or (earlier.acknowledged_at and count > earlier.count):
        return FraudSignal.objects.create(
            kind=kind, subject=subject, count=count, window_start=start, window_end=end, details=details
        )
    if earlier.acknowledged_at is None and count > earlier.count:
        earlier.count, earlier.window_end, earlier.details = count, end, details
        earlier.save(update_fields=["count", "window_end", "details"])
        return earlier
    return None


def fraud_rules(today=None):
    """Run every rule (as at the end of `today`, else now), record the findings, email the digest. Returns how many
    signals are new or grew."""
    now = timezone.make_aware(datetime.combine(today + timedelta(days=1), time())) if today else timezone.now()
    findings = failed_codes(now) + codes_shared_or_resold(now) + shared_contacts(now)
    with transaction.atomic():
        news = [found for finding in findings if (found := signal(*finding))]
        RedemptionAttempt.objects.filter(created__lt=now - KEEP_ATTEMPTS).delete()
    send_digest(news)
    logger.info("insights fraud rules: %s findings, %s new or grown", len(findings), len(news))
    return len(news)


def send_digest(news):
    """One text email to each of INSIGHTS_ALERT_EMAILS with the night's new or grown signals and the print runs to act
    on: kinds, counts, windows and the start of each hash, nothing personal. Nothing to tell: no email."""
    printing = latest(ForecastRun.Kind.PRINT_RUN)
    act = list(printing.advice.filter(level=PrintRunAdvice.Level.ACT).select_related("product")) if printing else []
    if not (news or act) or not settings.INSIGHTS_ALERT_EMAILS:
        return 0
    context = {"signals": news, "advice": act, "site_url": settings.SITE_URL}
    body = render_to_string("insights/email/digest.txt", context)
    for address in settings.INSIGHTS_ALERT_EMAILS:
        queue_text_email(address, f"Insights: {len(news)} new signals, {len(act)} print runs to act on", body)
    return len(settings.INSIGHTS_ALERT_EMAILS)
