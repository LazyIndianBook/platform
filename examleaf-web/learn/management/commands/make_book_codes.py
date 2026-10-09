import csv
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from content.models import Subject
from learn.models import CodeBatch
from learn.services import make_codes


class Command(BaseCommand):
    help = (
        "Make book codes for the printer: a CSV (code, batch, subject) on stdout or --out. Only the codes' hashes are "
        "kept, so this file is the only copy: keep it safe and delete it once printed (RUNBOOK.md)."
    )

    def add_arguments(self, parser):
        parser.add_argument("subject", help="a subject code (PHY, CHE, MAT, BIO), or ALL for every subject")
        parser.add_argument("count", type=int)
        parser.add_argument("--batch", required=True, help="name of the print run, e.g. PHY-2027-1")
        parser.add_argument("--out", help="CSV file (default: stdout)")

    def handle(self, subject, count, batch, out, **options):
        if not settings.LEARN_CODE_SECRET:  # printed codes match only the key they were made with (L7)
            raise CommandError("Set LEARN_CODE_SECRET first (DEPLOYMENT.md): codes printed without it stay unkeyed.")
        if not 1 <= count <= 100_000:
            raise CommandError("Make between 1 and 100000 codes at a time.")
        subj = None
        if subject.upper() != "ALL":
            subj = Subject.objects.filter(code=subject.upper(), board__short_name="ASSEB").first()
            if subj is None:
                raise CommandError(f"No subject {subject}.")
        codes = make_codes(subj, count, batch)
        # the panel's print run (learn.codes), for a new label: the panel marks it dispatched and voids it
        made = {"subject": subj, "printed": count, "generated_at": timezone.now(), "note": "Made with make_book_codes."}
        CodeBatch.objects.get_or_create(label=batch, defaults=made)
        with open(out, "w", newline="") if out else open(sys.stdout.fileno(), "w", closefd=False) as file:
            writer = csv.writer(file)
            writer.writerow(["code", "batch", "subject"])
            writer.writerows([code, batch, subj.code if subj else "ALL"] for code in codes)
        self.stderr.write(f"{len(codes)} codes for {subj or 'all subjects'}, batch {batch}")
