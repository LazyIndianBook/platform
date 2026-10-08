import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from content.management.commands.import_papers import SUBJECTS
from content.models import Subject
from learn.models import Chapter

PYQ_ROW = re.compile(r"^\|\s*\d+\s*\|\s*\d{4}\s*\|", re.M)  # | Marks | Year | Topic | Question |


def chapter_marks(fmt):
    """Marks per chapter number: Mathematics gives each chapter's; the others give a unit's, shared equally by its
    chapters (Biology lists some chapters under both Botany and Zoology: both shares count)."""
    per_unit = Counter((c.get("part"), c["unit"]) for c in fmt["chapters"])
    marks = defaultdict(Decimal)
    for c in fmt["chapters"]:
        share = (
            c["chapter_marks"]
            if "chapter_marks" in c
            else Decimal(c["unit_marks"]) / per_unit[c.get("part"), c["unit"]]
        )
        marks[c["ch"]] += Decimal(share)
    return {number: value.quantize(Decimal("0.1")) for number, value in marks.items()}


class Command(BaseCommand):
    help = (
        "Fill each chapter's Board marks (production/<subject>/format.json) and the number of previous-year "
        "questions on it (production/<subject>/pyq/chNN.md). Run import_papers first: it makes the subjects."
    )

    def add_arguments(self, parser):
        parser.add_argument("--root", default=str(settings.BOOK_ROOT), help="root of the book repository")
        parser.add_argument("--subject", choices=SUBJECTS, action="append", help="default: all four")

    def handle(self, root, subject, **options):
        for name in subject or SUBJECTS:
            folder = Path(root) / "production" / name
            if not (folder / "format.json").exists():
                raise CommandError(f"{folder / 'format.json'} not found: --root (BOOK_ROOT) is the book repository.")
            fmt = json.loads((folder / "format.json").read_text())
            subj = Subject.objects.filter(code=fmt["code"], board__short_name="ASSEB", class_level__number=12).first()
            if subj is None:
                raise CommandError(f"No subject {fmt['code']}: run import_papers --subject {name} first.")
            titles = {c["ch"]: c["title"] for c in reversed(fmt["chapters"])}  # the first listing wins
            created = 0
            for number, weight in sorted(chapter_marks(fmt).items()):
                pyq = folder / "pyq" / f"ch{number:02d}.md"
                frequency = len(PYQ_ROW.findall(pyq.read_text())) if pyq.exists() else 0
                _, new = Chapter.objects.update_or_create(
                    subject=subj, number=number, defaults=dict(title=titles[number], weight=weight, frequency=frequency)
                )
                created += new
                self.stdout.write(
                    f"  {fmt['code']} ch {number:2d}: {weight:>4} marks, {frequency:2d} PYQs  {titles[number]}"
                )
            total = sum(chapter_marks(fmt).values())
            self.stdout.write(f"{name}: {len(titles)} chapters ({created} new), {total} of {fmt['full_marks']} marks")
