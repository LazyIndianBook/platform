from django.core.management.base import BaseCommand

from staff.audit import purge, purgeable, retention_cutoffs


class Command(BaseCommand):
    help = (
        "Delete the audit events past their retention (2 years; money events 8 financial years), each chain's oldest "
        "first, and record the purge with the anchors that keep the rest verifiable. On PostgreSQL run it as the "
        "audit table's owner (DATABASE_URL of that role): the app's own role may not delete (staff/README.md)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="say what would go, delete nothing")

    def handle(self, *args, dry_run=False, **options):
        for chain, cutoff in retention_cutoffs().items():
            self.stdout.write(f"{chain}: {purgeable(chain, cutoff).count()} events before {cutoff:%Y-%m-%d}")
        if not dry_run:
            self.stdout.write(f"Deleted: {purge()}")
