"""The GSTR-1 files of a period for the accountant (research 5.11 and 5.12; plan 5.9), in the GST Offline Tool's CSV
import templates: b2cl (table 5: invoices above ₹1 lakh to another state), b2cs (table 7: the other taxed sales by
place of supply and rate, net of their credit notes), cdnur (table 9B: credit notes against b2cl invoices), exemp
(table 8: exempt, nil-rated and non-GST supplies, intra- and inter-state, to unregistered buyers), hsn-b2b and hsn-b2c
(table 12 since February 2025: the storefront's buyers are unregistered, so its B2B tab stays empty) and docs
(table 13: each series' first and last number, how many, how many cancelled), and the period's credit notes as a
working register. Amounts are those of the documents (shop/invoices.py: each line after its share of the discounts,
the shipping following the goods it carries). Only the real series, never the test one; a cancelled document counts
in table 13 only. Documents are read in chunks, never all at once. `manage.py export_gstr1` writes the files; the
staff job `gstr1_export` (POST staff/tax/gstr1/) zips them for the panel."""

import csv
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db.models import Prefetch
from django.utils import timezone

from . import invoices
from . import tax as rules
from .models import CreditNote, DocumentSeries, HsnCode, HsnRate, Invoice, OrderItem, Taxability

ZERO = Decimal("0.00")
TAXES = ["Taxable Value", "Integrated Tax Amount", "Central Tax Amount", "State/UT Tax Amount"]
HEADERS = {
    "b2cl": ["Invoice Number", "Invoice date", "Invoice Value", "Place Of Supply", "Applicable % of Tax Rate", "Rate",
             "Taxable Value", "Cess Amount", "E-Commerce GSTIN"],
    "b2cs": ["Type", "Place Of Supply", "Applicable % of Tax Rate", "Rate", "Taxable Value", "Cess Amount",
             "E-Commerce GSTIN"],
    "cdnur": ["UR Type", "Note Number", "Note Date", "Note Type", "Place Of Supply", "Note Value",
              "Applicable % of Tax Rate", "Rate", "Taxable Value", "Cess Amount"],
    "exemp": ["Description", "Nil Rated Supplies", "Exempted(other than nil rated/non GST supply)", "Non-GST Supplies"],
    "hsn-b2b": ["HSN", "Description", "UQC", "Total Quantity", "Total Value", "Rate", *TAXES, "Cess Amount"],
    "hsn-b2c": ["HSN", "Description", "UQC", "Total Quantity", "Total Value", "Rate", *TAXES, "Cess Amount"],
    "docs": ["Nature of Document", "Sr. No. From", "Sr. No. To", "Total Number", "Cancelled"],
    "credit-notes": ["Note Number", "Note Date", "Invoice Number", "Invoice Date", "Place Of Supply", "Rate", *TAXES,
                     "Exempt Value", "Shipping Credited"],
}  # fmt: skip
EXEMPT_ROWS = [
    "Inter-State supplies to registered persons",
    "Intra-State supplies to registered persons",
    "Inter-State supplies to unregistered persons",
    "Intra-State supplies to unregistered persons",
]
CHUNK = 500


class RateBook:
    """The whole HSN and SAC master in memory (a few dozen rows): a line's taxability and a code's description and
    unit on a day, without a query per document."""

    def __init__(self):
        self.rows = defaultdict(list)
        for row in HsnRate.objects.order_by("hsn_id", "-effective_from"):
            self.rows[row.hsn_id].append(row)
        self.codes = HsnCode.objects.in_bulk()

    def taxability(self, code, rate, day):
        """A line's taxability on its document's day: taxed at a rate; else as the master has the code then
        (exempt when the master does not know it: books are exempt by notification; research 5.11, the CA confirms)."""
        if rate:
            return Taxability.TAXABLE
        row = next((row for row in self.rows.get(code, []) if row.effective_from <= day), None)
        if row is None or (row.effective_to and row.effective_to < day) or row.taxability == Taxability.TAXABLE:
            return Taxability.EXEMPT
        return Taxability(row.taxability)

    def uqc(self, code):
        known = self.codes.get(code)
        return known.uqc if known else ("NA" if str(code).startswith("99") else "NOS")

    def description(self, code):
        known = self.codes.get(code)
        return known.description if known else ""


def money(value):
    return f"{Decimal(value):.2f}"


def portal_date(moment):
    """The Offline Tool's date: 09-Oct-2026, the day in India."""
    return f"{timezone.localdate(moment):%d-%b-%Y}"


def period_of(month, months=1):
    """The first and last day of `months` months ending with `month` ("2026-12", 3: October to December)."""
    first = date.fromisoformat(f"{month}-01")
    end = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    return first, end


def dated(model, start, end):
    """The real series' documents of a model dated in the period (the days in India)."""
    return model.objects.filter(created__date__range=(start, end)).exclude(financial_year__startswith="T")


def document_count(start, end):
    """How many documents the export reads: the job's rows."""
    return dated(Invoice, start, end).count() + dated(CreditNote, start, end).count()


def items():
    return Prefetch("order__items", queryset=OrderItem.objects.select_related("product").order_by("pk"))


def b2c_large(document):
    """Whether an invoice goes to table 5: taxed lines, to another state, worth more than ₹1 lakh."""
    order = document.order
    return (
        bool(document.taxable_value)
        and order.total.amount > rules.B2C_LARGE_ABOVE
        and invoices.place(order) != settings.SHOP_SELLER["state"]
    )


def follows(data, book, day):
    """The taxability of a document's untaxed charges: that of the goods they follow (its largest untaxed goods
    line's), else exempt."""
    untaxed = [entry for entry in data["lines"] if entry["goods"] and not entry["item"].gst_rate]
    if not untaxed:
        return Taxability.EXEMPT
    largest = max(untaxed, key=lambda entry: entry["amount"])
    return book.taxability(largest["item"].hsn_code, 0, day)


class Tables:
    """The period's sections, added up document by document (a credit note subtracts from what its invoice adds)."""

    def __init__(self, book):
        self.book = book
        self.b2cl, self.cdnur, self.credit_notes = [], [], []
        self.b2cs = defaultdict(Counter)  # (place of supply, rate) → taxable value
        self.exempt = defaultdict(Counter)  # (inter-state?) → {nil, exempt, non_gst}
        self.hsn = defaultdict(Counter)  # (HSN as printed, rate) → quantity, value and taxes
        self.docs = defaultdict(lambda: {"numbers": [], "cancelled": 0, "type": None})

    def add(self, data, day, sign, quantities=True):
        """A document's lines and charges into tables 7 or 5, 8 and 12 (`sign` -1 for a credit note)."""
        where = rules.place_of_supply(data["state"])
        inter = not data["intra_state"]
        charges_taxability = follows(data, self.book, day)
        rows = [
            (entry["item"].hsn_code, entry["item"].gst_rate, entry, entry["item"].quantity) for entry in data["lines"]
        ]
        principal = max(data["lines"], key=lambda entry: entry["amount"]) if data["lines"] else None
        carriers = [entry for entry in data["lines"] if entry["goods"]] or data["lines"]
        for charge in data["charges"]:  # each charge under the HSN of the goods it follows at its rate
            same = [entry for entry in carriers if entry["item"].gst_rate == charge["rate"]] or [principal]
            rows.append((max(same, key=lambda entry: entry["amount"])["item"].hsn_code, charge["rate"], charge, 0))
        for code, rate, entry, quantity in rows:
            if rate and not data.get("b2cl"):
                self.b2cs[where, rate]["taxable"] += sign * entry["taxable"]
            if not rate:
                kind = self.book.taxability(code, 0, day) if "item" in entry else charges_taxability
                self.exempt[inter][str(kind)] += sign * entry["amount"]
            row = self.hsn[invoices.hsn_printed(code), rate]
            row["quantity"] += sign * quantity if quantities else 0
            row["value"] += sign * entry["amount"]
            row["taxable"] += sign * entry["taxable"]
            row["igst"] += sign * entry["igst"]
            row["cgst"] += sign * entry["cgst"]
            row["sgst"] += sign * entry["sgst"]

    def by_rate(self, data):
        """{rate: taxable value} of a document's taxed lines and charges."""
        found = Counter()
        for entry in data["lines"]:
            if entry["item"].gst_rate:
                found[entry["item"].gst_rate] += entry["taxable"]
        for charge in data["charges"]:
            if charge["rate"]:
                found[charge["rate"]] += charge["taxable"]
        return found

    def invoice(self, document, data):
        day = timezone.localdate(document.created)
        large = b2c_large(document)
        if large:
            where, value = rules.place_of_supply(data["state"]), money(document.order.total.amount)
            for rate, taxable in sorted(self.by_rate(data).items()):
                row = [document.number, portal_date(document.created), value, where, "", money(rate), money(taxable)]
                self.b2cl.append([*row, "0.00", ""])
        self.add({**data, "b2cl": large}, day, 1)

    def credit_note(self, note, data):
        day = timezone.localdate(note.created)
        large = b2c_large(note.invoice)
        if large:
            for rate, taxable in sorted(self.by_rate(data).items()):
                self.cdnur.append(["B2CL", note.number, portal_date(note.created), "C",
                                   rules.place_of_supply(data["state"]), money(data["total_credit"]), "", money(rate),
                                   money(taxable), "0.00"])  # fmt: skip
        self.add({**data, "b2cl": large}, day, -1, quantities=False)  # the copies that came back are not known
        rates = Counter()
        for entry in [*data["lines"], *data["charges"]]:
            rate = entry["item"].gst_rate if "item" in entry else entry["rate"]
            for name in ("taxable", "igst", "cgst", "sgst"):
                rates[rate, name] += entry[name] if rate else 0
            rates[rate, "exempt"] += 0 if rate else entry["amount"]
        for rate in sorted({rate for rate, _name in rates}):
            self.credit_notes.append([
                note.number, portal_date(note.created), note.invoice.number, portal_date(note.invoice.created),
                rules.place_of_supply(data["state"]), money(rate),
                *(money(rates[rate, name]) for name in ("taxable", "igst", "cgst", "sgst", "exempt")),
                money(data["shipping_credit"]),
            ])  # fmt: skip

    def register(self, document):
        entry = self.docs[document.series or document.number.split("/")[0], document.financial_year]
        entry["numbers"].append((document.serial, document.number))
        entry["cancelled"] += bool(document.cancelled_at)
        entry["type"] = DocumentSeries.Type.CREDIT_NOTE if isinstance(document, CreditNote) else "invoice"

    def files(self):
        """Each section's rows, as the Offline Tool imports them."""
        b2cs = [["OE", where, "", money(rate), money(row["taxable"]), "0.00", ""]
                for (where, rate), row in sorted(self.b2cs.items())]  # fmt: skip
        exemp = [[EXEMPT_ROWS[0], "0.00", "0.00", "0.00"], [EXEMPT_ROWS[1], "0.00", "0.00", "0.00"]]
        for label, inter in ((EXEMPT_ROWS[2], True), (EXEMPT_ROWS[3], False)):
            row = self.exempt[inter]
            exemp.append([label, money(row["nil"]), money(row["exempt"]), money(row["non_gst"])])
        hsn = [
            [code, self.book.description(code), self.book.uqc(code), str(row["quantity"]), money(row["value"]),
             money(rate), money(row["taxable"]), money(row["igst"]), money(row["cgst"]), money(row["sgst"]), "0.00"]
            for (code, rate), row in sorted(self.hsn.items())
        ]  # fmt: skip
        docs = []
        for _key, entry in sorted(self.docs.items()):
            numbers = sorted(entry["numbers"])
            nature = rules.nature(entry["type"])
            docs.append([nature, numbers[0][1], numbers[-1][1], str(len(numbers)), str(entry["cancelled"])])
        return {
            "b2cl": self.b2cl,
            "b2cs": b2cs,
            "cdnur": self.cdnur,
            "exemp": exemp,
            "hsn-b2b": [],
            "hsn-b2c": hsn,
            "docs": docs,
            "credit-notes": self.credit_notes,
        }


def build(start, end, progress=None):
    """The period's tables, reading its documents in chunks (`progress`: a staff job's, a row a document). Returns
    (files {section: rows}, counts {invoices, credit_notes, cancelled})."""
    catalogue, tables, counts = invoices.Catalogue(), Tables(RateBook()), Counter()
    documents = dated(Invoice, start, end).select_related("order").prefetch_related(items())
    for invoice in documents.order_by("financial_year", "series", "serial").iterator(chunk_size=CHUNK):
        tables.register(invoice)
        if invoice.cancelled_at:
            counts["cancelled"] += 1
        else:
            tables.invoice(invoice, invoices.supply(invoice.order, catalogue))
            counts["invoices"] += 1
        if progress is not None:
            progress.row()
    notes = dated(CreditNote, start, end).select_related("invoice__order", "refund")
    notes = notes.prefetch_related(
        Prefetch("invoice__order__items", queryset=OrderItem.objects.select_related("product"))
    )
    for note in notes.order_by("financial_year", "series", "serial").iterator(chunk_size=CHUNK):
        tables.register(note)
        if note.cancelled_at:
            counts["cancelled"] += 1
        else:
            tables.credit_note(note, invoices.credit_supply(note, catalogue))
            counts["credit_notes"] += 1
        if progress is not None:
            progress.row()
    return tables.files(), dict(counts)


def write(folder, prefix, files):
    """The sections as CSV files in `folder`: <prefix>-<section>.csv. Returns their paths."""
    paths = []
    for section, rows in files.items():
        path = Path(folder) / f"{prefix}-{section}.csv"
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(HEADERS[section])
            writer.writerows(rows)
        paths.append(path)
    return paths


def export(start, end, out, progress=None):
    """The period's files in folder `out`; returns (their paths, the counts)."""
    Path(out).mkdir(parents=True, exist_ok=True)
    files, counts = build(start, end, progress)
    return write(out, f"gstr1-{start:%Y%m%d}-{end:%Y%m%d}", files), counts


def export_job(job, progress):
    """The staff job `gstr1_export`: the period's files zipped into the job's result (the private storage, linked to
    its starter), and an audit event with what it read (counts only: no buyer's details are in the files either)."""
    from staff.audit import record

    start, end = period_of(job.params["month"], job.params.get("months", 1))
    job.total = document_count(start, end)
    if job.dry_run:
        return {"documents": job.total, "from": start.isoformat(), "to": end.isoformat()}
    with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryFile() as archive:
        paths, counts = export(start, end, folder, progress)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for path in paths:
                zipped.write(path, path.name)
        archive.seek(0)
        job.result_file = default_storage.save(
            f"staff/jobs/{job.pk}/gstr1-{start:%Y%m%d}-{end:%Y%m%d}.zip", File(archive)
        )
    details = {"from": start.isoformat(), "to": end.isoformat(), **counts, "job": job.pk}
    record("tax.gstr1_exported", actor=job.started_by, permission="staff.run_gstr1", details=details)
    return {"from": start.isoformat(), "to": end.isoformat(), **counts}
