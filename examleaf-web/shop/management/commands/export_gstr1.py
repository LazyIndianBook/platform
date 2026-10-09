from datetime import date

from django.core.management.base import BaseCommand, CommandError

from shop import gstr1


class Command(BaseCommand):
    help = (
        'GSTR-1 files for the accountant (RUNBOOK.md "GST returns"), in the GST Offline Tool\'s CSV templates, from '
        "the invoices and credit notes of the real series (never the test series) dated --from to --to: b2cl, b2cs, "
        "cdnur, exemp, hsn-b2b, hsn-b2c and docs, and the credit notes' register (shop/gstr1.py). Amounts as on the "
        "documents: each line after its share of the discounts, tax included in the price, the shipping following "
        "the goods it carries. The panel runs the same as a job (POST /api/v1/staff/tax/gstr1/)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True, help="YYYY-MM-DD, included")
        parser.add_argument("--out", default=".", help="the folder for the files (default: the current one)")

    def handle(self, start, end, out, **options):
        if start > end:
            raise CommandError("--from is after --to.")
        paths, counts = gstr1.export(start, end, out)
        prefix = paths[0].parent / f"gstr1-{start:%Y%m%d}-{end:%Y%m%d}"
        self.stdout.write(
            f"{counts.get('invoices', 0)} invoices, {counts.get('credit_notes', 0)} credit notes, "
            f"{counts.get('cancelled', 0)} cancelled: {prefix}-*.csv"
        )
