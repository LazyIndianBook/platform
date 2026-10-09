from datetime import date

from django.core.management.base import BaseCommand, CommandError

from erp import reconcile
from integrations.client import IntegrationError


class Command(BaseCommand):
    help = (
        'Reconcile a day with ERPNext now (the nightly run\'s work, reconcile.py; RUNBOOK.md "ERPNext"): --date '
        "YYYY-MM-DD, yesterday by default. Prints the differences found (also kept, announced and emailed)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="day", type=date.fromisoformat, help="YYYY-MM-DD (default: yesterday)")

    def handle(self, *args, day=None, **options):
        try:
            run = reconcile.run(day)
        except IntegrationError as error:
            raise CommandError(f"ERPNext could not be asked: {error}") from error
        if run is None:
            self.stdout.write("Nothing reconciled: ERP_ENABLED is off or no ERPNext account is enabled.")
            return
        self.stdout.write(f"Reconciliation of {run.date} (run #{run.pk}): {run.differences_count} difference(s).")
        for difference in run.differences.all():
            self.stdout.write(f"- {difference}")
