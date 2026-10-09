from django.core.management.base import BaseCommand

from shipping import services
from shipping.tasks import courier_accounts


class Command(BaseCommand):
    help = "Keep the courier accounts' wallet statements of the last days as charges (lines already kept are skipped)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="How many days back (default 7).")

    def handle(self, *args, days=7, **options):
        for account in courier_accounts():
            self.stdout.write(f"{account}: {services.sync_statement(account, days=days)} new line(s).")
