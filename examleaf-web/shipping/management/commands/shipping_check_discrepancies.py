from django.core.management.base import BaseCommand

from shipping import services
from shipping.tasks import courier_accounts


class Command(BaseCommand):
    help = "Read the courier accounts' weight disputes into exceptions due in 7 working days (as the daily task)."

    def handle(self, *args, **options):
        for account in courier_accounts():
            disputes = services.check_discrepancies(account)
            self.stdout.write(f"{account}: {len(disputes)} weight dispute(s).")
