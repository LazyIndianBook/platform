"""GST on the storefront's documents (plan 5.9; research-commerce-gst.md section 5): the HSN and SAC master looked up
by date, a bundle's treatment, the billing state, the document's type and its number series, the credit notes'
cut-off, cancelling a document, the threshold monitor, the tax calendar, the tax records' retention, and the products
whose GST disagrees with the master. The documents' arithmetic (the lines, the shipping that follows the goods) is
shop/invoices.py's, the GSTR-1 files export_gstr1's, the staff API shop/staff_tax.py's."""

import logging
import re
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .cart import split
from .models import (
    STATES,
    BundleItem,
    CreditNote,
    DocumentSeries,
    DocumentType,
    HsnCode,
    HsnRate,
    Invoice,
    Product,
    TaxThreshold,
    financial_year,
)

logger = logging.getLogger(__name__)

# GST state codes, for the place of supply as documents and the GST portal write it ("18-Assam").
GST_STATE_CODES = {
    **{"JK": "01", "HP": "02", "PB": "03", "CH": "04", "UT": "05", "HR": "06", "DL": "07", "RJ": "08", "UP": "09"},
    **{"BR": "10", "SK": "11", "AR": "12", "NL": "13", "MN": "14", "MZ": "15", "TR": "16", "ML": "17", "AS": "18"},
    **{"WB": "19", "JH": "20", "OR": "21", "CT": "22", "MP": "23", "GJ": "24", "DH": "26", "MH": "27", "KA": "29"},
    **{"GA": "30", "LD": "31", "KL": "32", "TN": "33", "PY": "34", "AN": "35", "TG": "36", "AP": "37", "LA": "38"},
}


def state_label(state):
    """A state as a document names it, with its GST code: "Assam (18)"."""
    name, code = STATES.get(state, state), GST_STATE_CODES.get(state)
    return f"{name} ({code})" if code else name


def place_of_supply(state):
    """As the GST portal and the Offline Tool write it: "18-Assam"."""
    return f"{GST_STATE_CODES.get(state, '')}-{STATES.get(state, state)}"


def long_date(day):
    return f"{day.day} {day:%B %Y}"


# Financial years ("2026-27"; a test document's "T2026-27")


def year_start(label):
    return int(str(label).removeprefix("T")[:4])


def year_label(start):
    return f"{start}-{(start + 1) % 100:02d}"


def year_bounds(label):
    """The first and last day of a financial year."""
    start = year_start(label)
    return date(start, 4, 1), date(start + 1, 3, 31)


def annual_return_due(label):
    """GSTR-9's due date for the year: 31 December after it (s.44)."""
    return date(year_start(label) + 1, 12, 31)


def retained_until(label):
    """The last day a year's tax records must be kept: 72 months after its annual return's due date (CGST Act s.36;
    FY 2025-26 to 31 December 2032), the last day of that month."""
    return date(year_start(label) + 7, 12, 31)


def credit_note_deadline(label):
    """The last day a credit note against an invoice of the year may be issued: 30 November after the year (s.34(2);
    the annual return's date, if filed earlier, the CA watches)."""
    return date(year_start(label) + 1, 11, 30)


# The HSN and SAC master


def rate_on(code, day):
    """The master's rate of `code` in force on `day` (an HsnRate), or None: no row has started by then, or the latest
    one that has ended before it."""
    row = HsnRate.objects.filter(hsn_id=code, effective_from__lte=day).order_by("-effective_from").first()
    return None if row is None or (row.effective_to and row.effective_to < day) else row


def rates_on(codes, day):
    """{code: its HsnRate on `day`} for many codes in one query (codes without a rate that day are left out)."""
    found, seen = {}, set()
    rows = HsnRate.objects.filter(hsn_id__in=set(codes), effective_from__lte=day).order_by("hsn_id", "-effective_from")
    for row in rows:
        if row.hsn_id not in seen:
            seen.add(row.hsn_id)
            if not (row.effective_to and row.effective_to < day):
                found[row.hsn_id] = row
    return found


def history(code):
    """A code's rates oldest first, each with `until`: its own end, else the day before the next row starts."""
    rows = list(HsnRate.objects.filter(hsn_id=code).select_related("created_by").order_by("effective_from"))
    for row, after in zip(rows, [*rows[1:], None], strict=True):
        row.until = row.effective_to or (after.effective_from - timedelta(days=1) if after else None)
    return rows


def product_tax(product, day, rates=None):
    """(HSN or SAC code, GST rate) of one product on `day`: its master code's rate that day; a product not on the
    master yet, or a day the master has no rate for, keeps its own fields as before the master (its tax_problem
    chip tells FINANCE). `rates`: rates_on()'s answer, when the caller has it."""
    if product.hsn_id:
        row = rates.get(product.hsn_id) if rates is not None else rate_on(product.hsn_id, day)
        if row is not None:
            return product.hsn_id, row.rate
    return product.hsn_code, product.gst_rate


def weights(components):
    """What a bundle's price is shared by: each component's MRP times its copies; else (MRPs of nothing) their
    prices; else their copies."""
    for value in (lambda item: item.product.mrp.amount, lambda item: item.product.price.amount, lambda item: 1):
        found = [value(item) * item.quantity for item in components]
        if any(found):
            return found
    return [Decimal(1)] * len(components)


def apportion(price, shares_by, quantities):
    """`price` (one bundle, in rupees) shared over its components in proportion to `shares_by`, as a unit price in
    whole paise for each component's `quantities`: [(unit price, extra)], where the units times the quantities add up
    to the price plus the extras. A component of one copy takes any share; one of several copies a share its copies
    divide evenly: the paise left over go to a single copy, and when there is none they are rounded up and given back
    as `extra`, a discount on that line, so the lines still add up to the price exactly."""
    shares = [int(share * 100) for share in split(Decimal(price), shares_by)]
    singles = [index for index, quantity in enumerate(quantities) if quantity == 1]
    for index, quantity in enumerate(quantities):
        if (left := shares[index] % quantity) and singles:
            shares[index] -= left
            shares[singles[0]] += left
    paid = []
    for share, quantity in zip(shares, quantities, strict=True):
        unit = -(-share // quantity)  # paise, rounded up
        paid.append((Decimal(unit).scaleb(-2), Decimal(unit * quantity - share).scaleb(-2)))
    return paid


def principal(components, taxes):
    """The index of a composite bundle's principal supply: the component with the largest share of its MRP (goods
    before a service on a tie, then the first). The CA's decision may name another: then the treatment is mixed or
    split, or the bundle's components change."""
    shares = weights(components)
    return max(
        range(len(components)),
        key=lambda index: (shares[index], not components[index].product.is_digital, -index),
    )


def order_line(product, day):
    """What an order line of `product` keeps of its tax at checkout: {hsn_code, gst_rate, parts}. A bundle follows
    its treatment (plan 10.1): split, its components each a line of the invoice with the price shared by their MRPs
    (`parts`; the line itself keeps the bundle's own code and rate); composite, one line at the principal supply's
    code and rate; mixed, one line at the highest rate. Anything else: its master code's rate on the day."""
    if product.kind != Product.Kind.BUNDLE:
        code, rate = product_tax(product, day)
        return {"hsn_code": code, "gst_rate": rate, "parts": None}
    components = list(product.bundle_items.select_related("product").order_by("pk"))
    code, rate = product_tax(product, day)
    if not components:  # nothing to share the price over: the bundle as one line
        return {"hsn_code": code, "gst_rate": rate, "parts": None}
    rates = rates_on([item.product.hsn_id for item in components if item.product.hsn_id], day)
    taxes = [product_tax(item.product, day, rates) for item in components]
    if product.tax_treatment == Product.TaxTreatment.COMPOSITE:
        code, rate = taxes[principal(components, taxes)]
        return {"hsn_code": code, "gst_rate": rate, "parts": None}
    if product.tax_treatment == Product.TaxTreatment.MIXED:
        shares = weights(components)
        code, rate = taxes[max(range(len(components)), key=lambda index: (taxes[index][1], shares[index], -index))]
        return {"hsn_code": code, "gst_rate": rate, "parts": None}
    prices = apportion(product.price.amount, weights(components), [item.quantity for item in components])
    parts = [
        {
            "product": item.product_id,
            "kind": item.product.kind,
            "title": item.product.title,
            "hsn_code": part_code,
            "gst_rate": f"{part_rate:.2f}",
            "mrp": f"{item.product.mrp.amount:.2f}",
            "unit_price": f"{unit:.2f}",
            "quantity": item.quantity,
            "extra": f"{extra:.2f}",
        }
        for item, (part_code, part_rate), (unit, extra) in zip(components, taxes, prices, strict=True)
    ]
    return {"hsn_code": code, "gst_rate": rate, "parts": parts}


def billing_state(lines, address, given=""):
    """The order's place of supply (IGST Act ss.10 and 12(2); research 0.4 and 5.5): for goods, the state the parcel
    goes to; for courses alone, the state the buyer gave at checkout, else their address on record, else the seller's
    own state (Assam)."""
    state = (address or {}).get("state", "")
    if any(not line.product.digital_only for line in lines):
        return state or settings.SHOP_SELLER["state"]
    return given or state or settings.SHOP_SELLER["state"]


def document_type(rates):
    """By the lines' rates: every line taxed, a tax invoice; none, a bill of supply; both, one invoice-cum-bill of
    supply (Rule 46A: the storefront's buyers are unregistered)."""
    taxed = {bool(rate) for rate in rates}
    if taxed == {True, False}:
        return DocumentType.INVOICE_CUM_BILL
    return DocumentType.TAX_INVOICE if True in taxed else DocumentType.BILL_OF_SUPPLY


# Number series


def series_prefix(kind, year, live=True):
    """(prefix, DocumentSeries.Type) of a new document of `kind` (a DocumentType, or a DocumentSeries.Type for notes
    and vouchers) in a financial year: the test series T and TC; before SHOP_SERIES_FROM_FY the shared EL series for
    every invoice and CN for credit notes; from it, each type's own prefix (SHOP_SERIES_PREFIXES)."""
    note = kind == DocumentSeries.Type.CREDIT_NOTE
    if not live:
        return ("TC", DocumentSeries.Type.CREDIT_NOTE) if note else ("T", DocumentSeries.Type.INVOICE)
    if year_start(year) < year_start(settings.SHOP_SERIES_FROM_FY):
        if note:
            return "CN", DocumentSeries.Type.CREDIT_NOTE
        if kind in DocumentType.values:
            return "EL", DocumentSeries.Type.INVOICE
    return settings.SHOP_SERIES_PREFIXES[str(kind)], DocumentSeries.Type(str(kind))


def number(model, kind, live=True, day=None):
    """The next number for a document of `kind` dated `day` (today), from its series under the series' lock:
    {series, financial_year, serial, number}. Call it in the transaction that creates the document."""
    year = financial_year(day or timezone.localdate())
    prefix, series_type = series_prefix(kind, year, live)
    return DocumentSeries.take(model, prefix=prefix, financial_year=year, document_type=series_type, live=live)


KEY = re.compile(r"^([A-Z0-9]{1,2})-(\d{4}-\d{2})-(\d{5})$")


def parse_key(key):
    """A document's number from its address form (the slashes as dashes: EL-2026-27-00001), or None."""
    found = KEY.match(str(key))
    return "/".join(found.groups()) if found else None


def key_of(document):
    return document.number.replace("/", "-")


NATURES = {  # GSTR-1 table 13's nature of document, by a series' type
    DocumentSeries.Type.CREDIT_NOTE: "Credit Note",
    DocumentSeries.Type.DEBIT_NOTE: "Debit Note",
    DocumentSeries.Type.RECEIPT_VOUCHER: "Receipt Voucher",
    DocumentSeries.Type.REFUND_VOUCHER: "Refund Voucher",
}


def nature(series_type):
    """Table 13's words for a series: every kind of invoice is an invoice for outward supply."""
    return NATURES.get(series_type, "Invoices for outward supply")


RECIPIENT_FROM = Decimal(50_000)  # an unregistered buyer's name and address on the document from this value (Rule 46)


def document_checks(document, data):
    """What Rule 46 asks of the document that it does not have ([] when nothing): the buyer's name and address from
    50,000 rupees, HSN codes of SHOP_HSN_DIGITS figures, a place of supply."""
    found = []
    order = data["order"]
    address = order.shipping_address or {}
    if order.total.amount >= RECIPIENT_FROM and not all(
        address.get(name) and address.get(name) != "deleted" for name in ("name", "line1", "state")
    ):
        found.append("From ₹50,000 the buyer's name and address are printed: this order has none left.")
    wanted = settings.SHOP_HSN_DIGITS
    if short := sorted({entry["item"].hsn_code for entry in data["lines"] if len(entry["item"].hsn_code) < wanted}):
        found.append(f"Codes shorter than {wanted} figures (SHOP_HSN_DIGITS): {', '.join(short)}.")
    if not data["state"]:
        found.append("No place of supply.")
    return found


# Credit notes and cancellation


class CreditNoteRefused(Exception):
    """No credit note may be issued against this invoice; the refund goes out regardless, and FINANCE is told."""


class CreditNoteTooLate(CreditNoteRefused):
    pass


class InvoiceCancelled(CreditNoteRefused):
    pass


def credit_note_problem(invoice, day=None):
    """Why no credit note may be issued against the invoice now (the refund path shows it), or None: a cancelled
    invoice, or one of the real series past 30 November after its financial year."""
    if invoice is None:
        return None
    if invoice.cancelled_at:
        return f"Invoice {invoice.number} is cancelled: no credit note goes against it."
    deadline = credit_note_deadline(invoice.financial_year)
    if not invoice.is_test and (day or timezone.localdate()) > deadline:
        return (
            f"No credit note against {invoice.number}: the last day for invoices of FY "
            f"{invoice.financial_year} was {long_date(deadline)} (CGST Act s.34(2))."
        )
    return None


def check_credit_note(invoice, day=None):
    """Raises CreditNoteTooLate or InvoiceCancelled when credit_note_problem() has a reason."""
    if problem := credit_note_problem(invoice, day):
        raise (InvoiceCancelled if invoice.cancelled_at else CreditNoteTooLate)(problem)


def refund_problem(refund):
    """Why the refund has no credit note and will not get one (the refund path's words), or None."""
    return credit_note_problem(Invoice.objects.filter(order=refund.order_id).first())


def open_once(kind, target, title, permission, **data):
    """An inbox item about `target` (staff.signals.open_item) unless one of its kind was ever opened about it: a
    nightly run, or a task delivered again, does not open what staff have already closed."""
    from staff.models import InboxItem
    from staff.signals import open_item

    if not InboxItem.objects.filter(kind=kind, target_type=target._meta.label_lower, target_id=str(target.pk)).exists():
        open_item(kind, target, title, permission, **data)


def report_missing_credit_note(refund, reason):
    """FINANCE's inbox: a refund that went out without its credit note, and why (numbers only)."""
    from staff.models import InboxItem

    title = f"No credit note for refund #{refund.pk} of {refund.order.number}"
    open_once(InboxItem.Kind.CREDIT_NOTE_MISSING, refund, title, "staff.cancel_document", reason=reason)


def document_target(document):
    """A document as the audit log names it: its type, its id and its number."""
    return document._meta.label_lower, document.pk, document.number


def cancel(document, reason, *, by=None, request=None):
    """Cancel an invoice or a credit note. It keeps its number (Table 13 counts it as cancelled), leaves the returns,
    and its PDF is made again marked cancelled; the order and its refunds are left as they are. Refused when it is
    cancelled already, and for an invoice whose credit notes are not cancelled first. Returns the document."""
    from staff import audit

    from .tasks import remake_pdf

    model = type(document)
    with transaction.atomic():
        document = model.objects.select_for_update().get(pk=document.pk)
        if document.cancelled_at:
            raise ValueError(f"{document.number} was cancelled already.")
        if model is Invoice and (live := document.credit_notes.filter(cancelled_at__isnull=True)).exists():
            numbers = ", ".join(live.values_list("number", flat=True))
            raise ValueError(f"Cancel its credit notes first: {numbers}.")
        document.cancelled_at, document.cancel_reason, document.cancelled_by = timezone.now(), reason, by
        document.save(update_fields=["cancelled_at", "cancel_reason", "cancelled_by", "modified"])
        audit.record(
            "tax.document_cancelled",
            request=request,
            actor=by if request is None else None,
            target=document_target(document),
            reason=reason,
            details={"document_type": document.document_type, "series": document.series},
        )
        transaction.on_commit(lambda: remake_pdf.delay(document._meta.label_lower, document.pk), robust=True)
    return document


# The products that disagree with the master (the catalogue's red chip)


def problems(products, day=None):
    """{product id: why its GST disagrees with the master on `day` (today)} for the products that do, in a few
    queries whatever their number: not on the master, no rate that day, its rate not the master's, a course with a
    goods code or goods with a service code, fewer HSN digits than documents need (SHOP_HSN_DIGITS); a bundle: a
    component's problem, or (composite and mixed) its own rate not its treatment's."""
    day = day or timezone.localdate()
    products = list(products)
    bundles = [product.pk for product in products if product.kind == Product.Kind.BUNDLE]
    components = {}
    for item in BundleItem.objects.filter(bundle__in=bundles).select_related("product").order_by("pk"):
        components.setdefault(item.bundle_id, []).append(item)
    everyone = products + [item.product for items in components.values() for item in items]
    codes = {product.hsn_id for product in everyone if product.hsn_id}
    rates, kinds = rates_on(codes, day), dict(HsnCode.objects.filter(code__in=codes).values_list("code", "kind"))
    digits = settings.SHOP_HSN_DIGITS

    def own(product):
        if not product.hsn_id:
            return "Not on the HSN and SAC master: choose its code."
        row = rates.get(product.hsn_id)
        if row is None:
            return f"The master has no rate for {product.hsn_id} on {long_date(day)}."
        if (kinds.get(product.hsn_id) == HsnCode.Kind.SAC) != product.is_digital:
            return f"{product.hsn_id} is a {'goods' if product.is_digital else 'service'} code: choose a " + (
                "SAC code (99…)." if product.is_digital else "goods (HSN) code."
            )
        if product.gst_rate != row.rate:
            return (
                f"GST {product.gst_rate:.2f}% here, {row.rate:.2f}% in the master from "
                f"{long_date(row.effective_from)} ({row.notification})."
            )
        if len(product.hsn_id) < digits:
            return f"{product.hsn_id} has {len(product.hsn_id)} digits; documents need {digits} (SHOP_HSN_DIGITS)."
        return ""

    found = {}
    for product in products:
        if product.kind != Product.Kind.BUNDLE:
            problem = own(product)
        else:
            items = components.get(product.pk, [])
            problem = next((f"{item.product.title}: {why}" for item in items if (why := own(item.product))), "")
            if not problem and items and product.tax_treatment != Product.TaxTreatment.SPLIT:
                taxes = [product_tax(item.product, day, rates) for item in items]
                if product.tax_treatment == Product.TaxTreatment.COMPOSITE:
                    expected = taxes[principal(items, taxes)][1]
                else:
                    expected = max(rate for _code, rate in taxes)
                if product.gst_rate != expected:
                    problem = (
                        f"Its treatment ({product.tax_treatment}) taxes it at {expected:.2f}%; its rate here is "
                        f"{product.gst_rate:.2f}%."
                    )
        if problem:
            found[product.pk] = problem
    return found


# Totals kept on the documents (the threshold monitor's sums)


def fill_totals(model, chunk=200):
    """Documents numbered before their totals were kept get them (once): the type of each as it was issued, worked
    out again from its order. Returns how many."""
    from . import invoices

    done = 0
    rows = model.objects.filter(taxable_value__isnull=True).order_by("pk")
    for document in rows.select_related(*(["order"] if model is Invoice else ["invoice__order", "refund"]))[:chunk]:
        kept = (invoices.supply(document.order) if model is Invoice else invoices.credit_supply(document))["kept"]
        model.objects.filter(pk=document.pk).update(**kept)
        done += 1
    return done


def live_documents(model, label, day=None):
    """A financial year's documents of the real series, not cancelled, dated up to `day`."""
    rows = model.objects.filter(financial_year=label, cancelled_at__isnull=True)
    return rows.filter(created__date__lte=day) if day else rows


def turnover(label, day=None):
    """Aggregate turnover of a financial year so far (s.2(6)): the storefront documents' taxable and exempt values
    without the tax, less their credit notes'."""
    for model in (Invoice, CreditNote):
        while fill_totals(model):
            pass

    def total(model):
        sums = live_documents(model, label, day).aggregate(taxable=Sum("taxable_value"), exempt=Sum("exempt_value"))
        return (sums["taxable"] or Decimal(0)) + (sums["exempt"] or Decimal(0))

    return total(Invoice) - total(CreditNote)


# The threshold monitor (research 0.5 and 5.15; plan 5.9)

CRORE, LAKH = Decimal(10_000_000), Decimal(100_000)
TURNOVER_LINES = [
    (TaxThreshold.Line.GSTR9, 2 * CRORE),
    (TaxThreshold.Line.WARNING, 4 * CRORE),
    (TaxThreshold.Line.E_INVOICE, 5 * CRORE),
    (TaxThreshold.Line.IRP_30_DAYS, 10 * CRORE),
]
B2C_LARGE_ABOVE = LAKH  # an invoice to another state above it: GSTR-1 table 5 (Notification 12/2024-CT)
EWAY_BILL_ABOVE = Decimal(50_000)  # taxable goods in one consignment above it (Rule 138; exempt goods left out)
LISTED = 50  # document numbers kept on a count's row


def b2c_large(label, day=None):
    """The year's invoices to another state above ₹1 lakh with taxed lines (B2CL), as numbers."""
    rows = live_documents(Invoice, label, day).filter(order__total__gt=B2C_LARGE_ABOVE, taxable_value__gt=0)
    rows = rows.exclude(order__billing_state=settings.SHOP_SELLER["state"])
    return list(rows.order_by("serial").values_list("number", flat=True))


def eway_bill(label, day=None):
    """The year's invoices whose parcel carried taxable goods worth more than ₹50,000 with their tax and their share
    of the shipping, exempt goods left out (Rule 138(1), Explanation 2): those may have needed an e-way bill."""
    from . import invoices

    found = []
    rows = live_documents(Invoice, label, day).filter(order__total__gt=EWAY_BILL_ABOVE).select_related("order")
    for invoice in rows.order_by("serial").iterator(chunk_size=100):
        supply = invoices.supply(invoice.order)
        goods = [line for line in supply["lines"] if line["goods"] and line["item"].gst_rate]
        value = sum((line["amount"] for line in goods), Decimal(0))
        value += sum((share["amount"] for share in supply["charges"] if share["rate"]), Decimal(0))
        if value > EWAY_BILL_ABOVE:
            found.append(invoice.number)
    return found


def watch_thresholds(day=None):
    """The night's look at the thresholds (01:45, shop.tasks.watch_tax_thresholds): a row per line for `day` (today),
    the year's figure so far against it; the first night a turnover line is crossed in a year, and each night a count
    grows, an inbox item for FINANCE (once: staff closing it is final). Run again the same day, it changes nothing.
    Returns the day's rows."""
    from staff.models import InboxItem

    day = day or timezone.localdate()
    label = financial_year(day)
    so_far = turnover(label, day)
    counted = {TaxThreshold.Line.B2C_LARGE: b2c_large(label, day), TaxThreshold.Line.EWAY_BILL: eway_bill(label, day)}
    figures = [(line, so_far, limit, so_far > limit, {}) for line, limit in TURNOVER_LINES]
    figures += [
        (line, Decimal(len(numbers)), limit, bool(numbers), {"numbers": numbers[-LISTED:]})
        for (line, numbers), limit in zip(counted.items(), [B2C_LARGE_ABOVE, EWAY_BILL_ABOVE], strict=True)
    ]
    earlier = TaxThreshold.objects.filter(financial_year=label, date__lt=day)
    rows = []
    with transaction.atomic():
        for line, value, limit, crossed, detail in figures:
            row, _ = TaxThreshold.objects.update_or_create(
                date=day,
                line=line,
                defaults={
                    "financial_year": label,
                    "value": value,
                    "limit": limit,
                    "crossed": crossed,
                    "detail": detail,
                },
            )
            rows.append(row)
            before = earlier.filter(line=line).order_by("-date").first()
            if line in TaxThreshold.COUNTS:
                if crossed and value > (before.value if before else 0):
                    title = f"{int(value)} {TaxThreshold.Line(line).label} in FY {label}"
                    open_once(InboxItem.Kind.TAX_THRESHOLD, row, title[:200], "shop.change_hsncode", line=line)
            elif crossed and not earlier.filter(line=line, crossed=True).exists():
                title = f"Turnover of FY {label} passed {TaxThreshold.Line(line).label.split(':')[0]}"
                open_once(InboxItem.Kind.TAX_THRESHOLD, row, title, "shop.change_hsncode", line=line)
    return rows


def thresholds_card(day=None):
    """The threshold card: the latest night's lines, and the year before's turnover (e-invoicing, QRMP and the HSN
    digits follow the year before's: research 5.3, 5.9, 5.11)."""
    latest = TaxThreshold.objects.filter(date__lte=day or timezone.localdate()).aggregate(Max("date"))["date__max"]
    rows = list(TaxThreshold.objects.filter(date=latest).order_by("pk")) if latest else []
    label = rows[0].financial_year if rows else financial_year(day or timezone.localdate())
    previous = year_label(year_start(label) - 1)
    return {"as_of": latest, "financial_year": label, "previous_year": previous, "rows": rows,
            "previous_turnover": turnover(previous)}  # fmt: skip


# The tax calendar (research 5.11, 5.13, 5.15; plan 10.1 "QRMP")

# GSTR-3B under QRMP: the 22nd, or the 24th in these states and territories (Notification 76/2020-CT); Assam's is
# the 24th (research 5.11 [29]). A seller outside Assam: check its state's day with the CA.
QRMP_3B_24TH = {"HP", "PB", "UT", "HR", "RJ", "UP", "BR", "SK", "AR", "NL", "MN", "MZ", "TR", "ML", "AS", "WB"} | {
    "JH",
    "OR",
    "JK",
    "LA",
    "CH",
    "DL",
}
QUARTER_ENDS = {6: "April to June", 9: "July to September", 12: "October to December", 3: "January to March"}
TDS_STATEMENTS = {7: (31, "April to June"), 10: (31, "July to September"), 1: (31, "October to December")} | {
    5: (31, "January to March")
}


def month_before(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def calendar(year, month, qrmp=None, today=None):
    """What is due in a month, computed from the law's dates (statutory dates: an extension comes by notification):
    GSTR-1 or the IFF, GSTR-3B, PMT-06 under QRMP (SHOP_GST_QRMP, on by default: plan 10.1), GSTR-9 on 31 December
    when the year before passed ₹2 crore, the credit notes' 30 November cut-off, the Rule 42 true-up in the September
    return, the quarterly TDS statements; each with what it covers and whether it applies."""
    from staff.config import site_setting

    qrmp = site_setting("SHOP_GST_QRMP") if qrmp is None else qrmp
    today = today or timezone.localdate()
    filed_year, filed = month_before(year, month)  # the month the returns due now are for
    period = f"{date(filed_year, filed, 1):%B %Y}"
    in_quarter = filed in QUARTER_ENDS
    items = []

    def due(day, key, title, covers, applies=True, note=""):
        when = date(year, month, day)
        items.append({"key": key, "title": title, "covers": covers, "due": when, "applies": applies, "note": note,
                      "past": when < today})  # fmt: skip

    three_b_day = 24 if settings.SHOP_SELLER["state"] in QRMP_3B_24TH else 22
    if not qrmp:
        due(11, "gstr1", "GSTR-1", period, note="Every invoice and credit note of the month (the export).")
        due(20, "gstr3b", "GSTR-3B", period, note="Its tax comes from GSTR-1 and cannot be edited.")
    elif in_quarter:
        quarter = f"{QUARTER_ENDS[filed]} {filed_year}"
        due(13, "gstr1", "GSTR-1 (quarterly, QRMP)", quarter, note="The quarter's invoices and credit notes.")
        due(three_b_day, "gstr3b", "GSTR-3B (quarterly, QRMP)", quarter, note="Its tax comes from GSTR-1.")
    else:
        due(
            13,
            "iff",
            "IFF (optional, QRMP)",
            period,
            note="Only invoices to registered buyers: the storefront has none.",
        )
        due(
            25, "pmt06", "PMT-06 tax payment (QRMP)", period, note="The month's tax, by the fixed sum or as worked out."
        )
    if month == 11:
        fy = year_label(year - 1)
        due(30, "credit_note_cutoff", "Last day for credit notes", f"Invoices of FY {fy}",
            note="Credit notes after it are refused; declare November's in a return filed by today.")  # fmt: skip
    if month == 12:
        fy = year_label(year - 1)
        so_far = turnover(fy)
        due(31, "gstr9", "GSTR-9 annual return", f"FY {fy}", applies=so_far > 2 * CRORE,
            note=f"Required above ₹2 crore of turnover; FY {fy}: ₹{so_far:,.2f}.")  # fmt: skip
    if month == 10:
        fy = year_label(year - 1)
        due(three_b_day if qrmp else 20, "rule42", "Rule 42 true-up", f"FY {fy}",
            note="The year's reversal of common input tax credit, in the September return.")  # fmt: skip
    if month in TDS_STATEMENTS:
        day, quarter = TDS_STATEMENTS[month]
        tds_year = year - 1 if month in (1, 5) else year
        due(day, "tds", "Quarterly TDS statement", f"{quarter} {tds_year}", note="Tax deducted from vendors' payments.")
    return sorted(items, key=lambda item: (item["due"], item["key"]))


# Records and retention (CGST Act s.36; research 5.16)


def held_orders(order_ids, today=None):
    """Of these orders, the ids whose tax documents of the real series must still be kept (72 months after their
    year's annual return): their customer's details stay until then."""
    today = today or timezone.localdate()
    years = list(Invoice.objects.filter(order__in=order_ids).values_list("order_id", "financial_year"))
    years += list(
        CreditNote.objects.filter(invoice__order__in=order_ids).values_list("invoice__order_id", "financial_year")
    )
    return {order for order, label in years if not label.startswith("T") and retained_until(label) >= today}
