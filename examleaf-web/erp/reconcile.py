"""The nightly reconciliation (plan 3.2; research-erpnext.md 5.8): a day of the platform's documents against ERPNext's
totals of the same day (daily_totals), for each flow switched on: the invoices and the credit notes (their number and
total, their taxable and exempt values and GST), the payments and refunds by mode, the COD settlements, the delivery
notes and the copies they took out per item; every document of the day ERPNext has not answered for (no ErpLink),
with where its outbox row is; and, with ERP_PULL_STOCK, the stock invariant per item: ERPNext's free copies (its own,
less what its B2B orders hold) less those reserved here and not shipped must equal the copies for sale here.

The platform's side is worked out from its own documents with the payloads' definitions (contract.py: the same
dates, the same lines, the shipping in the treatment of the goods it carries), so that a day that went through whole
is quiet. Counts, totals and exempt values must be equal; taxable values and GST may differ by 0.01 for each taxed
document, because ERPNext rounds each tax once per invoice where the platform's invoices round each line
(examleaf-erp/API.md, deviation 7). Differences are rows to resolve (ErpReconciliationDifference): the run files one
item in the staff inbox for those who may resolve them (erp/inbox.py), each difference is announced
(reconciliation_difference), and a summary is emailed to ERP_ALERT_EMAILS. No personal data in any of them:
references, item codes and totals."""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integrations.client import IntegrationError
from ops.tasks import queue_text_email
from shipping.models import CodRemittance
from shipping.status import LEFT
from shop.models import CreditNote, Invoice, Payment, Refund, Settlement, Shipment

from . import contract, inbox, signals
from .client import client
from .inbound import read_stock, reserved_not_shipped, stocked_products
from .models import ErpLink, ErpOutbox, ErpReconciliationDifference, ErpReconciliationRun
from .producers import REMITTED, enabled, switch

logger = logging.getLogger(__name__)
Kind = ErpReconciliationDifference.Kind
LATEST_PREPARED = timedelta(days=14)  # a courier's parcel leaves at most this long after it was prepared
PAISA = Decimal("0.01")
EXACT = ("count", "total", "exempt_value")
ROUNDED = ("taxable_value", "tax_total")  # within PAISA a taxed document


def parse_day(day=None):
    """A day (a date, or its ISO text); None: yesterday, India's."""
    if day is None:
        return timezone.localdate() - timedelta(days=1)
    return day if isinstance(day, date) else date.fromisoformat(str(day))


def bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def invoiced(order):
    return Invoice.objects.filter(order=order).exists()


def documents(values):
    """The totals of a day's invoices or credit notes from their (total, taxable, exempt, tax, taxed?) values."""
    sums, taxed = defaultdict(Decimal), 0
    for total, taxable, exempt, tax, is_taxed in values:
        sums["total"] += total
        sums["taxable_value"] += taxable
        sums["exempt_value"] += exempt
        sums["tax_total"] += tax
        taxed += is_taxed
    keys = ("total", "exempt_value", *ROUNDED)
    return {"count": len(values), **{key: contract.money(sums[key]) for key in keys}, "taxed": taxed}


def platform_totals(day):
    """The day as ERPNext should have it, for each flow switched on: ({check: totals}, the references expected)."""
    start, end = bounds(day)
    totals, refs = {}, []
    if enabled("invoices"):
        dated = Invoice.objects.filter(created__gte=start, created__lt=end).select_related("order")
        found = [invoice for invoice in dated if not invoice.order.is_test]
        totals["invoices"] = documents([contract.invoice_values(invoice) for invoice in found])
        refs += [contract.invoice_ref(invoice) for invoice in found]
        dated = CreditNote.objects.filter(created__gte=start, created__lt=end)
        notes = [note for note in dated.select_related("invoice__order", "refund") if not note.invoice.order.is_test]
        totals["credit_notes"] = documents([contract.credit_note_values(note) for note in notes])
        refs += [contract.credit_note_ref(note) for note in notes]
    if enabled("payments"):
        sides = {"receive": defaultdict(lambda: [0, Decimal(0)]), "refund": defaultdict(lambda: [0, Decimal(0)])}
        for payment in captured_on(day):
            if not payment.order.is_test and invoiced(payment.order):
                entry = sides["receive"][contract.payment_mode(payment)]
                entry[0], entry[1] = entry[0] + 1, entry[1] + payment.amount.amount
                refs.append(contract.payment_ref(payment))
        for refund in refunded_on(day):
            entry = sides["refund"][contract.payment_mode(refund.payment)]
            entry[0], entry[1] = entry[0] + 1, entry[1] + Decimal(contract.refund(refund)["amount"])
            refs.append(contract.refund_ref(refund))
        totals["payments"] = {
            side: {mode: {"count": n, "amount": contract.money(total)} for mode, (n, total) in sorted(found.items())}
            for side, found in sides.items()
        }
    if enabled("settlements"):
        remitted = CodRemittance.objects.filter(remitted_at=day, state__in=REMITTED).select_related("shipment__order")
        cod = [r for r in remitted if not r.shipment.order.is_test and invoiced(r.shipment.order)]
        gross = contract.money(sum((r.remitted_amount for r in cod), Decimal(0)))
        totals["settlements"] = {"cod": {"count": len(cod), "total": gross}} if cod else {}
        refs += [contract.settlement_ref(contract.cod_settlement_id(r)) for r in cod]
        # Phase B: finance. The Razorpay settlements the platform posted for the day (shop/settlements.py), their
        # gross as ERPNext's Journal Entry has it
        razorpay = list(Settlement.objects.filter(date=day, livemode=True, erp_outbox__isnull=False))
        if razorpay:
            total = contract.money(sum((s.gross.amount for s in razorpay), Decimal(0)))
            totals["settlements"]["razorpay"] = {"count": len(razorpay), "total": total}
        refs += [contract.settlement_ref(s.settlement_id) for s in razorpay]
    if enabled("deliveries"):
        notes, copies = 0, defaultdict(int)
        for shipment in dispatched_on(day):
            order = shipment.order
            if order.is_test or not invoiced(order) or not (lines := contract.physical_items(order)):
                continue
            notes += 1
            for entry in lines:
                for pk, count in entry.product.stock_lines(entry.quantity).items():
                    copies[pk] += count
            refs.append(contract.delivery_ref(shipment))
        codes = contract.item_codes(stocked_products().filter(pk__in=copies))
        shipped = dict(sorted((codes[pk], count) for pk, count in copies.items() if pk in codes))
        totals["shipped"] = {"delivery_notes": notes, "items": shipped}
    return totals, refs


def captured_on(day):
    """The payments first captured on that day (their history: one captured earlier is not)."""
    start, end = bounds(day)
    captured = Payment.history.filter(status=Payment.Status.CAPTURED)
    ids = set(captured.filter(history_date__gte=start, history_date__lt=end).values_list("id", flat=True))
    ids -= set(captured.filter(id__in=ids, history_date__lt=start).values_list("id", flat=True))
    return Payment.objects.filter(pk__in=ids).select_related("order").order_by("pk")


def refunded_on(day):
    """The refunds processed that day that went to ERPNext (against a credit note: of an invoiced order)."""
    start, end = bounds(day)
    processed = Refund.objects.filter(status=Refund.Status.PROCESSED, processed_at__gte=start, processed_at__lt=end)
    processed = processed.filter(credit_note__isnull=False).select_related("order", "payment", "credit_note")
    processed = processed.exclude(method=Refund.Method.NONE)  # a credit note alone (a parcel back unpaid): no money
    return [refund for refund in processed.order_by("pk") if not refund.order.is_test]


def dispatched_on(day):
    """The parcels that left us on that day (contract.dispatched_on, the delivery note's date)."""
    start, end = bounds(day)
    by_hand = Shipment.objects.filter(shipped_at__gte=start - LATEST_PREPARED, shipped_at__lt=end)
    scanned = Shipment.objects.filter(
        events__status__in=LEFT, events__occurred_at__gte=start, events__occurred_at__lt=end
    )
    candidates = (by_hand | scanned).distinct().select_related("order").order_by("pk")
    return [s for s in candidates if contract.has_left(s) and contract.dispatched_on(s) == day]


def compare(run, platform, theirs):
    """The day's totals that differ, as rows (not saved)."""
    found = []

    def check(kind, key, ours, erp, tolerance=Decimal(0)):
        if ours == erp or (tolerance and abs(Decimal(ours) - Decimal(erp)) <= tolerance):
            return
        difference = ErpReconciliationDifference(run=run, kind=kind, key=key, platform_value=ours, erp_value=erp)
        found.append(difference)

    for part, kind in (("invoices", Kind.INVOICES), ("credit_notes", Kind.CREDIT_NOTES)):
        if part in platform:
            ours, erp = platform[part], theirs[part]
            for key in EXACT:
                check(kind, key, ours[key], erp[key])
            for key in ROUNDED:
                check(kind, key, ours[key], erp[key], tolerance=PAISA * ours["taxed"])
    if "payments" in platform:
        empty = {"count": 0, "amount": "0.00"}
        for side in ("receive", "refund"):
            ours, erp = platform["payments"][side], theirs["payments"][side]
            for mode in sorted(set(ours) | set(erp)):
                mine, there = ours.get(mode, empty), erp.get(mode, empty)
                check(Kind.PAYMENTS, f"{side} {mode} count", mine["count"], there["count"])
                check(Kind.PAYMENTS, f"{side} {mode} amount", mine["amount"], there["amount"])
    if "settlements" in platform:
        ours, erp, empty = platform["settlements"], theirs["settlements"], {"count": 0, "total": "0.00"}
        for kind in sorted(set(ours) | set(erp)):
            mine, there = ours.get(kind, empty), erp.get(kind, empty)
            check(Kind.SETTLEMENTS, f"{kind} count", mine["count"], there["count"])
            check(Kind.SETTLEMENTS, f"{kind} total", mine["total"], there["total"])
    if "shipped" in platform:
        ours, erp = platform["shipped"], theirs["shipped"]
        check(Kind.DELIVERIES, "delivery notes", ours["delivery_notes"], erp["delivery_notes"])
        for code in sorted(set(ours["items"]) | set(erp["items"])):
            check(Kind.DELIVERIES, code, ours["items"].get(code, 0), erp["items"].get(code, 0))
    return found


def missing(run, refs):
    """The day's documents ERPNext has not answered for: the reference, and where its outbox row is."""
    linked = set(ErpLink.objects.filter(examleaf_ref__in=refs).values_list("examleaf_ref", flat=True))
    rows = dict(ErpOutbox.objects.filter(examleaf_ref__in=refs).values_list("examleaf_ref", "state"))
    return [
        ErpReconciliationDifference(
            run=run, kind=Kind.MISSING, key=ref, platform_value=f"outbox: {rows.get(ref, 'no row')}", erp_value=""
        )
        for ref in refs
        if ref not in linked
    ]


def stock(run, erp):
    """The stock invariant per item, as rows (not saved), and what was compared: the copies for sale here against
    ERPNext's free copies less those reserved here and not shipped (an item ERPNext has without a Bin: none)."""
    products = list(stocked_products().filter(is_active=True))
    codes = contract.item_codes(products)
    refs = [contract.item_ref(product) for product in products]
    linked = set(ErpLink.objects.filter(examleaf_ref__in=refs).values_list("examleaf_ref", flat=True))
    held, reserved = read_stock(erp), reserved_not_shipped()
    found, checked = [], {}
    for product in products:
        code = codes[product.pk]
        actual = erp_reserved = None
        if code in held:
            actual, _projected, erp_reserved, _batches = held[code]
        elif contract.item_ref(product) in linked:
            actual = erp_reserved = Decimal(0)
        projection = None if actual is None else actual - erp_reserved - reserved[product.pk]
        checked[code] = {
            "available": product.stock,
            "erp_actual": None if actual is None else contract.copies(actual),
            "erp_reserved": None if erp_reserved is None else contract.copies(erp_reserved),
            "reserved_here": reserved[product.pk],
        }
        if projection is None or projection != product.stock:
            erp_value = contract.copies(projection) if projection is not None else "not in ERPNext"
            found.append(
                ErpReconciliationDifference(
                    run=run, kind=Kind.STOCK, key=code, platform_value=str(product.stock), erp_value=erp_value
                )
            )
    return found, checked


def run(day=None):
    """Reconcile a day (None: yesterday): the run, or None while ERP_ENABLED is off or no account is enabled. A
    failure to ask ERPNext marks the run failed and is raised (the task tries again)."""
    day = parse_day(day)
    erp = client() if switch("ERP_ENABLED") else None
    if erp is None:
        logger.info("erp: no reconciliation of %s: ERP_ENABLED is off or no ERPNext account is enabled", day)
        return None
    this = ErpReconciliationRun.objects.create(date=day)
    try:
        platform, refs = platform_totals(day)
        theirs = contract.day_totals(erp.call("daily_totals", {"date": day.isoformat()})) if platform else {}
        differences = [*compare(this, platform, theirs), *missing(this, refs)]
        if switch("ERP_PULL_STOCK"):
            found, checked = stock(this, erp)
            differences += found
            platform["stock"] = checked
    except IntegrationError as error:
        this.state, this.error, this.finished_at = this.State.FAILED, str(error)[:500], timezone.now()
        this.save(update_fields=["state", "error", "finished_at"])
        raise
    with transaction.atomic():
        ErpReconciliationDifference.objects.bulk_create(differences)
        this.platform_totals, this.erp_totals, this.differences_count = platform, theirs, len(differences)
        this.state, this.finished_at = this.State.DONE, timezone.now()
        this.save()
        if differences:
            inbox.differences_wait(this)
        for difference in differences:
            transaction.on_commit(
                lambda difference=difference: signals.reconciliation_difference.send(
                    sender=ErpReconciliationDifference, difference=difference
                ),
                robust=True,
            )
    if differences:
        email_summary(this, differences)
    logger.info("erp: reconciliation of %s: %s difference(s)", day, len(differences))
    return this


def email_summary(run, differences):
    """The day's differences to ERP_ALERT_EMAILS (none: no email): references, item codes and totals only."""
    if not settings.ERP_ALERT_EMAILS:
        return
    lines = [
        f"The reconciliation of {run.date:%d %B %Y} with ERPNext found {len(differences)} difference(s):",
        "",
        *(
            f"- {d.get_kind_display()} {d.key}: {d.platform_value or '-'} here, {d.erp_value or '-'} in ERPNext"
            for d in differences[:100]
        ),
        *(["- …"] if len(differences) > 100 else []),
        "",
        f'Resolve them in Admin → ERPNext sync → Reconciliation runs (run #{run.pk}); RUNBOOK.md "ERPNext".',
    ]
    subject = f"ERPNext reconciliation of {run.date:%d %b}: {len(differences)} difference(s)"
    for address in settings.ERP_ALERT_EMAILS:
        queue_text_email(address, subject, "\n".join(lines))
