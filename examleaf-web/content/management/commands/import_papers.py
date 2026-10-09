"""Import the Markdown sample papers and solutions of the books repository LazyIndianBook/Class-12-Assam.

    python manage.py import_papers --root "<a checkout of the books repository>" --subject physics
    python manage.py import_papers --all              # --root defaults to the PAPERS_ROOT setting
    python manage.py import_papers --all --fixtures   # the copies in content/fixtures/papers/ (tests, CI)
    python manage.py import_papers --all --dry-run    # what it would do, writing nothing

The work is content/imports.py's, which the panel's import job calls too (content/README.md): only what changed is
written, so simple-history keeps real edits, not import noise; a question no longer in the books is unpublished and
kept with its history. The panel's page is the usual way; this command stays for the shell (RUNBOOK.md).
"""

from django.core.management.base import BaseCommand, CommandError

from content.imports import FIXTURES, SUBJECTS, import_subject, papers_root  # noqa: F401  (the names others import)


class Command(BaseCommand):
    help = "Import the sample papers and solutions (Markdown) of one subject or all four."

    def add_arguments(self, parser):
        parser.add_argument("--root", help="a checkout of the books repository (default: the PAPERS_ROOT setting)")
        parser.add_argument("--fixtures", action="store_true", help="the test copies in content/fixtures/papers/")
        parser.add_argument("--subject", choices=SUBJECTS)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--dry-run", action="store_true", help="compare and report, write nothing")

    def handle(self, root, fixtures, subject, all, dry_run, **options):
        if not (subject or all):
            raise CommandError("Give --subject <name> or --all.")
        root = papers_root(root, fixtures)
        problems = 0
        for name in SUBJECTS if all else [subject]:
            s = import_subject(root, name, dry_run=dry_run)
            c = s["report"].counts
            self.stdout.write(
                f"{name}: {s['papers']} papers, {s['questions']} questions, {s['solutions']} solutions matched, "
                f"{s['tagged']} tagged; records created {c['created']}, updated {c['updated']}, "
                f"unchanged {c['unchanged']}; unmatched solution labels: {len(s['unmatched'])}; "
                f"questions without a solution: {len(s['missing'])}; no longer in the books (unpublished): "
                f"{c['removed']}" + (" (a dry run: nothing written)" if dry_run else "")
            )
            for item in s["unmatched"]:
                self.stdout.write(f"  unmatched solution: {item}")
            for item in s["missing"]:
                self.stdout.write(f"  question without solution: {item}")
            problems += len(s["unmatched"]) + len(s["missing"])
        if problems:
            raise CommandError(f"{problems} labels did not match.")
