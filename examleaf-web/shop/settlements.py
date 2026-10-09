"""Razorpay's settlements (plan 5.8; research-integrations.md 4.1, research-commerce-gst.md 4): a day's settlements read
from the settlement recon API (`GET /v1/settlements/recon/combined?year=&month=&day=`, paged by `count` and `skip`)
and each settlement's own figures (`GET /v1/settlements/:id`), through the integrations client (the call log, the
circuit breaker, its timeouts), for the mode of the keys in force, never both. Kept once (a Settlement per Razorpay
id, a line per settlement and entity); each line matched to our Payment, Refund or B2B link by Razorpay's id (an
order's payment we never heard of, its receipt one of our orders, is asked of Razorpay first: a lost webhook); a
settlement whose lines are all ours and whose net is their sum is matched and posted to ERPNext once
(erp.producers.razorpay_settlement: the Journal Entry: Razorpay Clearing to the bank, the fees an expense, the GST on
them input credit); one that is not opens one inbox item for FINANCE, who matches the rest by hand (manual_match).
The tests' recorded answers are shop/fixtures/razorpay_settlements.json: Razorpay's documented shapes, those marked
_inferred not yet seen in a live answer."""

import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import InvoicePaymentLink, Order, Payment, Refund, Settlement, SettlementLine, razorpay_keys, rupees

logger = logging.getLogger(__name__)
PAGE = 100  # recon items a call (Razorpay's `count`, which it caps at 1,000)
MAX_PAGES = 100  # 10,000 items in a day at most: more is refused, never looped over for ever
RECONCILE_AT_MOST = 50  # orders asked of Razorpay in one fetch for payments of theirs we never heard of
# Razorpay's `fee` includes its GST (`tax`): its Payment entity says "Fee (including GST)"; the recon's items follow
# it (_inferred: a payment line's credit is then amount - fee). A line keeps its fee without the GST. Should a live
# answer say otherwise, this knob is the one change: a settlement's own fees come from the money moved, either way.
FEE_INCLUDES_TAX = True
# What a line keeps of Razorpay's item: no card, bank or contact field, no notes or descriptions
KEPT = [
    *["entity_id", "type", "amount", "fee", "tax", "debit", "credit", "currency", "settled", "settled_at"],
    *["settlement_id", "settlement_utr", "order_id", "order_receipt", "payment_id", "method", "on_hold"],
    *["dispute_id", "created_at", "posted_at"],
]
TYPES = {"payment": SettlementLine.Type.PAYMENT, "refund": SettlementLine.Type.REFUND}
INBOX = "staff.reconcile_settlements"  # who sees a settlement that does not match: FINANCE (and the owners, ADMIN)


class NotConfigured(Exception):
    """Razorpay has no keys in force (or it is switched off on the connections page): nothing to fetch."""


def transport():
    """The HTTP transport of the fetch's calls: the network (the tests put Razorpay's recorded answers here)."""
    return None


def paise_to_rupees(value):
    try:
        return rupees(Decimal(str(value if value not in (None, "") else 0)) / 100)
    except ArithmeticError, ValueError:
        return Decimal("0.00")


def moment(value):
    """A Razorpay time (seconds since 1970), or None."""
    try:
        return datetime.fromtimestamp(int(value), UTC) if value not in (None, "") else None
    except TypeError, ValueError, OverflowError, OSError:
        return None


# Razorpay, through the integrations client


def account(live):
    """The integrations account the calls are logged on, whose circuit they obey: the connections page's account in
    use; else, while the environment's keys are in force, the account of their mode (made for their call log, as the
    connection test makes it)."""
    from integrations.models import IntegrationAccount

    if found := IntegrationAccount.objects.filter(provider="razorpay", enabled=True).first():
        return found
    mode = IntegrationAccount.Mode.LIVE if live else IntegrationAccount.Mode.TEST
    found, _ = IntegrationAccount.objects.get_or_create(
        provider="razorpay", mode=mode, defaults={"label": "The environment's keys"}
    )
    return found


def razorpay(live):
    """Razorpay's REST client with the keys in force. The panel's account's circuit is the client's own check; the
    environment keys' account is never switched on (it only keeps their calls), so its circuit is read here."""
    from integrations.client import CircuitOpen
    from integrations.connections import RazorpayClient
    from integrations.models import COOL_OFF

    keys = razorpay_keys()
    if not (keys.key_id and keys.key_secret):
        raise NotConfigured("Razorpay is not set up: no keys are in force (the connections page says why).")
    held = account(live)
    force = False
    if not held.enabled:
        held.refresh_from_db(fields=["held_open", *held.CIRCUIT_FIELDS])
        last = held.trial_started_at or held.opened_at
        waiting = held.circuit_state != held.Circuit.CLOSED and last and timezone.now() - last < COOL_OFF
        if held.held_open or waiting:
            raise CircuitOpen(f"{held}: no call made (its circuit is open)", account=held)
        # ponytail: no compare-and-set trial for the environment's account; the fetch runs one at a time anyway
        force = True
    return RazorpayClient(held, keys.key_id, keys.key_secret, transport=transport(), force=force)


def recon_items(client, day):
    """Every item of the day's settlement recon, page by page."""
    from integrations.client import IntegrationRejected

    items = []
    for page in range(MAX_PAGES):
        params = {"year": day.year, "month": day.month, "day": day.day, "count": PAGE, "skip": page * PAGE}
        data = client.request("GET", "/settlements/recon/combined", operation="settlement_recon", params=params)
        rows = data.get("items") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise IntegrationRejected(
                f"Razorpay's settlement recon of {day} was not understood", account=client.account
            )
        items += [row for row in rows if isinstance(row, dict)]
        if len(rows) < PAGE:
            return items
    raise IntegrationRejected(
        f"More than {PAGE * MAX_PAGES:,} settlement items on {day}: not fetched", account=client.account
    )


def settlement_entity(client, settlement_id):
    """Razorpay's own figures of a settlement: {amount (the net, paise), fees, tax, utr, status, created_at}."""
    data = client.request("GET", f"/settlements/{quote(settlement_id, safe='')}", operation="settlement")
    return data if isinstance(data, dict) else {}


# Matching


def line_fields(item):
    """A SettlementLine's fields from a recon item (rupees, the fee without its GST)."""
    fee, tax = paise_to_rupees(item.get("fee")), paise_to_rupees(item.get("tax"))
    receipt = item.get("order_receipt")
    return {
        "type": TYPES.get(str(item.get("type") or ""), SettlementLine.Type.ADJUSTMENT),
        "amount": paise_to_rupees(item.get("amount")),
        "fee": fee - tax if FEE_INCLUDES_TAX else fee,
        "tax": tax,
        "credit": paise_to_rupees(item.get("credit")),
        "debit": paise_to_rupees(item.get("debit")),
        "settled_at": moment(item.get("settled_at")),
        "order_receipt": str(receipt or "")[:40],
        "raw": {name: item[name] for name in KEPT if name in item},
    }


def match_lines(settlement):
    """Each line not yet matched, matched by Razorpay's id to one of our payments, refunds or B2B links of the
    settlement's mode, of the same amount (a payment matched to another settlement already is not taken twice).
    Returns how many it matched now. In the caller's transaction, the settlement locked."""
    lines = list(settlement.lines.select_for_update().filter(matched_at=None))
    ids = {line.entity_id for line in lines}
    live = settlement.livemode
    payments = {
        payment.razorpay_payment_id: payment
        for payment in Payment.objects.filter(razorpay_payment_id__in=ids, livemode=live).select_related("order")
    }
    taken = set(
        SettlementLine.objects.filter(type=SettlementLine.Type.PAYMENT, payment__in=list(payments.values()))
        .exclude(settlement=settlement)
        .values_list("payment_id", flat=True)
    )
    refunds = {
        refund.razorpay_refund_id: refund
        for refund in Refund.objects.filter(razorpay_refund_id__in=ids, payment__livemode=live).select_related("order")
    }
    links = {link.razorpay_payment_id: link for link in InvoicePaymentLink.objects.filter(razorpay_payment_id__in=ids)}
    now, matched = timezone.now(), 0
    for line in lines:
        if line.type == SettlementLine.Type.PAYMENT:
            payment, link = payments.get(line.entity_id), links.get(line.entity_id)
            if payment is not None and payment.pk not in taken and payment.amount.amount == line.amount.amount:
                line.payment, line.order = payment, payment.order
            elif link is not None and link.livemode == live and link.amount.amount == line.amount.amount:
                line.link = link
            else:
                continue
        elif line.type == SettlementLine.Type.REFUND:
            refund = refunds.get(line.entity_id)
            if refund is None or refund.amount.amount != line.amount.amount:
                continue
            line.refund, line.order = refund, refund.order
        else:
            continue  # an adjustment: FINANCE says what it is (manual_match)
        line.matched_at = now
        line.save(update_fields=["payment", "refund", "link", "order", "matched_at"])
        matched += 1
    return matched


def totals(lines):
    """The settlement's figures from its lines: gross (payments less refunds, with the adjustments), Razorpay's fees
    without their GST (what the money moved says it kept, whatever the fields' convention), the GST, the adjustments,
    and the net the lines add up to."""
    gross = adjustments = tax = net = Decimal("0.00")
    for line in lines:
        moved = line.credit.amount - line.debit.amount
        net += moved
        tax += line.tax.amount
        if line.type == SettlementLine.Type.PAYMENT:
            gross += line.amount.amount
        elif line.type == SettlementLine.Type.REFUND:
            gross -= line.amount.amount
        else:
            gross += moved
            adjustments += moved
    return {"gross": gross, "fees": gross - net - tax, "tax": tax, "adjustments": adjustments, "net": net}


def evaluate(settlement, actor=None, request=None):
    """The settlement's state from its lines, in the caller's transaction (the settlement locked): its figures; matched
    (its inbox item done, then posted) when every line is ours and Razorpay's net is the lines' sum; mismatched (one
    inbox item for FINANCE, saying what is wrong in counts) otherwise. A posted one keeps what was posted; a line that
    comes after the posting opens its item all the same."""
    from staff.audit import record
    from staff.models import InboxItem
    from staff.signals import close_items, open_item

    lines = list(settlement.lines.all())
    figures = totals(lines)
    unmatched = sum(1 for line in lines if line.matched_at is None)
    problems = []
    if unmatched:
        problems.append(f"{unmatched} line{'s' if unmatched != 1 else ''} not ours yet")
    if figures["net"] != settlement.net.amount:
        problems.append(f"Razorpay's net ₹{settlement.net.amount} is not its lines' ₹{figures['net']}")
    title = f"Razorpay settlement {settlement.settlement_id} of {settlement.date:%d %b %Y}: {'; '.join(problems)}"

    def waits(title):  # one item a settlement, its title the settlement's latest state
        open_item(InboxItem.Kind.SETTLEMENT, settlement, title, INBOX, settlement=settlement.settlement_id)
        InboxItem.objects.filter(
            kind=InboxItem.Kind.SETTLEMENT, target_type="shop.settlement", target_id=str(settlement.pk), done_at=None
        ).update(title=title[:200])

    if settlement.state == Settlement.State.POSTED:
        if problems:
            waits(f"{title} (after it was posted: correct ERPNext's entry by hand)")
        return settlement
    for name in ("gross", "fees", "tax", "adjustments"):
        setattr(settlement, name, figures[name])
    was = settlement.state
    if problems:
        settlement.state, settlement.problem = Settlement.State.MISMATCHED, "; ".join(problems)[:300]
        waits(title)
        if was != Settlement.State.MISMATCHED:
            details = {"settlement": settlement.settlement_id, "unmatched": unmatched, "problem": settlement.problem}
            record(
                "payment.settlement_mismatched",
                request=request,
                actor=actor,
                target=target(settlement),
                details=details,
            )
    else:
        settlement.state, settlement.problem = Settlement.State.MATCHED, ""
        settlement.matched_at = settlement.matched_at or timezone.now()
        close_items(settlement, InboxItem.Kind.SETTLEMENT)
        if was != Settlement.State.MATCHED:
            details = {"settlement": settlement.settlement_id, "lines": len(lines), "net": settlement.net.amount}
            record(
                "payment.settlement_matched", request=request, actor=actor, target=target(settlement), details=details
            )
    settlement.save()
    post(settlement, actor=actor, request=request)
    return settlement


def target(settlement):
    return ("shop.settlement", settlement.pk, f"Settlement {settlement.settlement_id}")


def post(settlement, actor=None, request=None):
    """Once: a matched live settlement's Journal Entry into ERPNext's outbox (erp.producers.razorpay_settlement), while
    ERP_SYNC_SETTLEMENTS is on (off: it stays matched, and the nightly fetch posts what waits once it is on). A test
    one never goes. The producer's failure never undoes the matching: it is logged and tried again the next night."""
    from erp import contract, producers
    from erp.models import ErpOutbox
    from staff.audit import record

    if settlement.state != Settlement.State.MATCHED or not settlement.livemode or settlement.erp_outbox_id:
        return None
    payment_ids = list(
        settlement.lines.filter(type=SettlementLine.Type.PAYMENT).order_by("pk").values_list("entity_id", flat=True)
    )
    fields = {
        "id": settlement.settlement_id,
        "date": settlement.date.isoformat(),
        "gross": settlement.gross.amount,
        "fees": settlement.fees.amount,
        "tax": settlement.tax.amount,
        "net": settlement.net.amount,
        "utr": settlement.utr,
        "payment_ids": payment_ids,
    }
    try:
        with transaction.atomic():
            row = producers.razorpay_settlement(fields)
    except Exception:
        logger.exception("Settlement %s not posted to ERPNext's outbox", settlement.settlement_id)
        return None
    row = row or ErpOutbox.objects.filter(examleaf_ref=contract.settlement_ref(settlement.settlement_id)).first()
    if row is None:  # the flow is off
        return None
    settlement.erp_outbox, settlement.state, settlement.posted_at = row, Settlement.State.POSTED, timezone.now()
    settlement.save(update_fields=["erp_outbox", "state", "posted_at", "modified"])
    details = {"settlement": settlement.settlement_id, "outbox": row.pk, "gross": settlement.gross.amount}
    record("payment.settlement_posted", request=request, actor=actor, target=target(settlement), details=details)
    return row


# The fetch


def keep(day, live, groups, entities, progress=None):
    """The day's settlements kept (once each), their lines added (once each) and matched, each evaluated. Returns
    ({counts}, [the settlements kept], {settlement id: the orders whose payment Razorpay settled and we never heard
    of})."""
    counts = Counter()
    kept, lost = [], {}
    for settlement_id, items in groups.items():
        entity = entities.get(settlement_id) or {}
        utr = str(entity.get("utr") or items[0].get("settlement_utr") or "")[:60]
        lines_net = sum((line_fields(item)["credit"] - line_fields(item)["debit"] for item in items), Decimal("0.00"))
        net = paise_to_rupees(entity["amount"]) if entity.get("amount") not in (None, "") else lines_net
        with transaction.atomic():
            settlement, created = Settlement.objects.select_for_update().get_or_create(
                settlement_id=settlement_id, defaults={"date": day, "utr": utr, "net": net, "livemode": live}
            )
            if settlement.livemode != live:  # the other mode's (ids never cross; kept apart all the same)
                counts["other_mode"] += 1
                continue
            if settlement.state != Settlement.State.POSTED and not created:
                settlement.utr, settlement.net = utr or settlement.utr, net  # Razorpay's latest word
            counts["settlements"] += 1
            counts["new_settlements"] += created
            for item in items:
                line, made = SettlementLine.objects.get_or_create(
                    settlement=settlement, entity_id=str(item["entity_id"])[:40], defaults=line_fields(item)
                )
                counts["lines"] += 1
                counts["new_lines"] += made
                if progress is not None:
                    progress.row()
            counts["matched_lines"] += match_lines(settlement)
            evaluate(settlement)
            kept.append(settlement)
            lost[settlement.pk] = unheard_of(settlement)
    return counts, kept, lost


def unheard_of(settlement):
    """The orders (numbers) of the settlement's payment lines not matched, whose Razorpay order's receipt is one of our
    orders of the settlement's mode: a payment Razorpay settled that the platform never heard of (a lost webhook)."""
    receipts = set(
        settlement.lines.filter(type=SettlementLine.Type.PAYMENT, matched_at=None)
        .exclude(order_receipt="")
        .values_list("order_receipt", flat=True)
    )
    found = Order.objects.filter(
        number__in=receipts, livemode=settlement.livemode, payment_method=Order.Method.RAZORPAY
    )
    return list(found.values_list("number", flat=True))


def fetch_day(day, *, actor=None, dry_run=False, progress=None, request=None):
    """A day's Razorpay settlements fetched, kept, matched and posted (module docstring), for the keys in force; a dry
    run changes nothing (and asks Razorpay about nothing more than the day's settlements). Returns the counts. Raises
    NotConfigured, or an integrations error (Razorpay unreachable or refusing: nothing kept)."""
    from staff.audit import record

    from . import payments
    from .models import live_mode

    live = live_mode()
    client = razorpay(live)
    items = [item for item in recon_items(client, day) if item.get("settlement_id") and item.get("entity_id")]
    groups = {}
    for item in items:
        groups.setdefault(str(item["settlement_id"])[:40], []).append(item)
    if progress is not None:
        progress.job.total = len(items)
    known = Settlement.objects.filter(settlement_id__in=list(groups), state=Settlement.State.POSTED)
    posted = set(known.values_list("settlement_id", flat=True))
    entities = {sid: settlement_entity(client, sid) for sid in groups if sid not in posted}
    with transaction.atomic():
        counts, kept, lost = keep(day, live, groups, entities, progress)
        if dry_run:
            transaction.set_rollback(True)
    if not dry_run:
        asked = 0  # an order's payment Razorpay settled and we never heard of: asked now, then matched again
        for settlement in kept:
            numbers = lost.get(settlement.pk, [])[: max(0, RECONCILE_AT_MOST - asked)]
            for order in Order.objects.filter(number__in=numbers):
                asked += 1
                if payments.reconcile(order):
                    counts["orders_paid_now"] += 1
            if numbers:
                with transaction.atomic():
                    locked = Settlement.objects.select_for_update().get(pk=settlement.pk)
                    counts["matched_lines"] += match_lines(locked)
                    evaluate(locked)
    states = (
        Counter(Settlement.objects.filter(settlement_id__in=list(groups)).values_list("state", flat=True))
        if not dry_run
        else Counter()
    )
    result = {
        "day": day.isoformat(),
        "mode": "live" if live else "test",
        "dry_run": dry_run,
        **{name: counts[name] for name in ["settlements", "new_settlements", "lines", "new_lines", "matched_lines"]},
        "orders_paid_now": counts["orders_paid_now"],
        "states": dict(states),
    }
    if not dry_run:
        target_ = ("shop.settlement", day.isoformat(), f"Razorpay settlements of {day:%d %b %Y}")
        record("payment.settlements_fetched", request=request, actor=actor, target=target_, details=result)
    return result


def post_waiting():
    """The matched live settlements not yet posted (ERP_SYNC_SETTLEMENTS was off then): posted now, once. Returns how
    many went."""
    posted = 0
    for pk in Settlement.objects.filter(state=Settlement.State.MATCHED, livemode=True, erp_outbox=None).values_list(
        "pk", flat=True
    ):
        with transaction.atomic():
            settlement = Settlement.objects.select_for_update().get(pk=pk)
            posted += post(settlement) is not None
    return posted


# By hand


def manual_match(settlement, line_id, *, payment=None, refund=None, accept=False, note, by, request=None):
    """FINANCE matches one line by hand: to a payment or a refund of the settlement's mode (a payment line only to a
    payment of its amount that no other payment line has), or accepts an adjustment as it is; with a note (why), once;
    audited; then the settlement is evaluated again (matched and posted once nothing is left). Raises ValueError (the
    API's 400) or SettlementLine.DoesNotExist (404)."""
    from staff.audit import record

    note = " ".join(str(note or "").split())
    if not note:
        raise serializers.ValidationError({"note": ["Say why: it is kept in the audit log."]})
    if sum(bool(choice) for choice in (payment, refund, accept)) != 1:
        raise serializers.ValidationError({"non_field_errors": ["Choose one: a payment, a refund, or accept it."]})
    with transaction.atomic():
        settlement = Settlement.objects.select_for_update().get(pk=settlement.pk)
        line = settlement.lines.select_for_update().get(pk=line_id)
        if settlement.state == Settlement.State.POSTED:
            raise ValueError(f"Settlement {settlement.settlement_id} was posted to ERPNext: correct its entry there.")
        if line.matched_at is not None:
            raise ValueError(f"Line {line.entity_id} is matched already.")
        if payment is not None:
            if payment.livemode != settlement.livemode:
                raise ValueError(f"Payment #{payment.pk} is of the other mode's keys.")
            if line.type == SettlementLine.Type.PAYMENT:
                if payment.amount.amount != line.amount.amount:
                    raise ValueError(
                        f"Payment #{payment.pk} is ₹{payment.amount.amount}, the line ₹{line.amount.amount}."
                    )
                elsewhere = SettlementLine.objects.filter(type=SettlementLine.Type.PAYMENT, payment=payment)
                if elsewhere.exists():
                    raise ValueError(f"Payment #{payment.pk} is another settlement line's already.")
            line.payment, line.order = payment, payment.order
        elif refund is not None:
            if refund.payment.livemode != settlement.livemode:
                raise ValueError(f"Refund #{refund.pk} is of the other mode's keys.")
            line.refund, line.order = refund, refund.order
        elif line.type != SettlementLine.Type.ADJUSTMENT:
            raise ValueError("Only an adjustment is accepted as it is: match a payment or a refund to this line.")
        line.matched_at, line.matched_by, line.note = timezone.now(), by, note[:300]
        line.save(update_fields=["payment", "refund", "order", "matched_at", "matched_by", "note"])
        details = {
            "line": line.pk,
            "entity": line.entity_id,
            "payment": getattr(payment, "pk", None),
            "refund": getattr(refund, "pk", None),
            "accepted": bool(accept),
        }
        record(
            "payment.settlement_line_matched",
            request=request,
            actor=by,
            permission="staff.reconcile_settlements",
            target=target(settlement),
            reason=note[:500],
            details=details,
        )
        evaluate(settlement, actor=by, request=request)
    return SettlementLine.objects.select_related("settlement", "payment", "refund", "link", "order").get(pk=line.pk)


# For the Orders record and the panel's jobs


def fees_for(order):
    """What Razorpay kept of an order's payments, once their settlements are in: [{payment, entity, amount, fee, tax,
    settlement, date, utr}], oldest first (plan 5.8: an order's page shows its fee, the GST on it and the UTR)."""
    lines = (
        SettlementLine.objects.filter(order=order, type=SettlementLine.Type.PAYMENT)
        .select_related("settlement")
        .order_by("pk")
    )
    return [
        {
            "payment": line.payment_id,
            "entity": line.entity_id,
            "amount": line.amount.amount,
            "fee": line.fee.amount,
            "tax": line.tax.amount,
            "settlement": line.settlement.settlement_id,
            "date": line.settlement.date,
            "utr": line.settlement.utr,
        }
        for line in lines
    ]


EARLIEST = date(2020, 1, 1)


def job_params(params):
    """settlement_fetch's params: {"day": "YYYY-MM-DD"}, today (India) at the latest. Raises ValidationError."""
    try:
        day = date.fromisoformat(str((params or {}).get("day") or ""))
    except ValueError:
        raise serializers.ValidationError({"params": {"day": ["A day: YYYY-MM-DD."]}}) from None
    if day > timezone.localdate():
        raise serializers.ValidationError({"params": {"day": ["Not a day to come: Razorpay has not settled it."]}})
    if day < EARLIEST:
        raise serializers.ValidationError({"params": {"day": ["A day from 2020 on."]}})
    return {"day": day.isoformat()}


def fetch_job(job, progress):
    """The staff job settlement_fetch: a day's settlements fetched (a dry run changes nothing). Its result: the
    counts."""
    try:
        return fetch_day(
            date.fromisoformat(job.params["day"]), actor=job.started_by, dry_run=job.dry_run, progress=progress
        )
    except NotConfigured as error:
        raise serializers.ValidationError({"non_field_errors": [str(error)]}) from error


def yesterday():
    return timezone.localdate() - timedelta(days=1)
