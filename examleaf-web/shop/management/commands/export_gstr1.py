import csv
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shop import invoices
from shop.models import STATES, CreditNote, Invoice

# GST state codes, for the place of supply as the GST portal writes it ("18-Assam").
GST_STATE_CODES = {
    **{"JK": "01", "HP": "02", "PB": "03", "CH": "04", "UT": "05", "HR": "06", "DL": "07", "RJ": "08", "UP": "09"},
    **{"BR": "10", "SK": "11", "AR": "12", "NL": "13", "MN": "14", "MZ": "15", "TR": "16", "ML": "17", "AS": "18"},
    **{"WB": "19", "JH": "20", "OR": "21", "CT": "22", "MP": "23", "GJ": "24", "DH": "26", "MH": "27", "KA": "29"},
    **{"GA": "30", "LD": "31", "KL": "32", "TN": "33", "PY": "34", "AN": "35", "TG": "36", "AP": "37", "LA": "38"},
}
TAXES = ["taxable_value", "igst", "cgst", "sgst"]


def place_of_supply(document):
    state = document.order.shipping_address["state"]
    return f"{GST_STATE_CODES.get(state, '')}-{STATES.get(state, state)}"


def amounts(line):
    return {"taxable_value": line["taxable"], "igst": line["igst"], "cgst": line["cgst"], "sgst": line["sgst"]}


def top_rate(lines):
    """The shipping goes with the invoice's highest rate (all books: 0 %, exempt like them)."""
    return max((line["item"].gst_rate for line in lines), default=0)


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


class Command(BaseCommand):
    help = (
        'GSTR-1 working files for the accountant (RUNBOOK.md "GST returns"): the invoices and credit notes of the real '
        "series (never the test series) dated --from to --to, in three CSV files: B2C supplies by place of supply and "
        "rate, the HSN summary, and the credit notes. Amounts as on the documents: each line after its share of the "
        "order's discount, tax included in the price; the shipping in the row of the document's highest rate."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True, help="YYYY-MM-DD, included")
        parser.add_argument("--out", default=".", help="the folder for the files (default: the current one)")

    def handle(self, start, end, out, **options):
        if start > end:
            raise CommandError("--from is after --to.")
        Path(out).mkdir(parents=True, exist_ok=True)
        prefix = Path(out) / f"gstr1-{start:%Y%m%d}-{end:%Y%m%d}"
        dated = {"created__date__range": (start, end)}  # in India's time (TIME_ZONE)
        b2c, hsn, notes = defaultdict(Counter), defaultdict(Counter), []
        documents = Invoice.objects.filter(**dated).exclude(financial_year__startswith="T").select_related("order")
        for invoice in documents.order_by("financial_year", "serial").iterator(chunk_size=500):
            data = invoices.context(invoice)
            where = place_of_supply(invoice)
            for line in data["lines"]:
                item = line["item"]
                b2c[where, item.gst_rate].update(amounts(line))
                hsn[item.hsn_code, item.gst_rate].update(
                    {"quantity": item.quantity, "total_value": line["amount"], **amounts(line)}
                )
            b2c[where, top_rate(data["lines"])].update({"invoices": 1, "shipping": invoice.order.shipping_fee.amount})
        credit_notes = CreditNote.objects.filter(**dated).exclude(financial_year__startswith="T")
        notes_in_order = credit_notes.select_related("invoice__order", "refund").order_by("financial_year", "serial")
        for note in notes_in_order.iterator(chunk_size=500):
            data = invoices.credit_note_context(note)
            top = top_rate(data["lines"])
            for rate in sorted({line["item"].gst_rate for line in data["lines"]}):
                row = Counter()
                for line in data["lines"]:
                    if line["item"].gst_rate == rate:
                        row.update(amounts(line))
                shipping = data["shipping_credit"] if rate == top else 0
                head = [
                    note.number,
                    f"{note.created:%Y-%m-%d}",
                    note.invoice.number,
                    f"{note.invoice.created:%Y-%m-%d}",
                ]
                notes.append([*head, place_of_supply(note.invoice), rate, *(row[t] for t in TAXES), shipping])
        write(
            f"{prefix}-b2c.csv",
            ["place_of_supply", "rate", "invoices", *TAXES, "shipping"],
            [[*key, row["invoices"], *(row[t] for t in TAXES), row["shipping"]] for key, row in sorted(b2c.items())],
        )
        write(
            f"{prefix}-hsn.csv",
            ["hsn", "uqc", "rate", "quantity", "total_value", *TAXES],
            [
                [code, "NOS", rate, row["quantity"], row["total_value"], *(row[t] for t in TAXES)]
                for (code, rate), row in sorted(hsn.items())
            ],
        )
        write(
            f"{prefix}-credit-notes.csv",
            ["note", "date", "invoice", "invoice_date", "place_of_supply", "rate", *TAXES, "shipping"],
            notes,
        )
        self.stdout.write(f"{documents.count()} invoices, {credit_notes.count()} credit notes: {prefix}-*.csv")
