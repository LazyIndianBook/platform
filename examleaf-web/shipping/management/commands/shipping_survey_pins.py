from django.core.management.base import BaseCommand, CommandError

from shipping import services
from shipping.tasks import courier_accounts


class Command(BaseCommand):
    help = (
        "Ask the courier account which couriers serve the North-East's PINs (the PIN directory's, by state), a batch "
        "at a time, the PINs surveyed longest ago first; or the PINs given."
    )

    def add_arguments(self, parser):
        parser.add_argument("pins", nargs="*", help="Only these PINs.")
        parser.add_argument("--limit", type=int, help="At most this many PINs (default SHIPPING_SURVEY_BATCH).")

    def handle(self, *args, pins=None, limit=None, **options):
        accounts = list(courier_accounts())
        if not accounts:
            raise CommandError("No courier account is enabled.")
        try:
            for account in accounts:
                surveyed, without, without_cod = services.survey_pins(account, pins or None, limit)
                self.stdout.write(
                    f"{account}: {surveyed} PIN(s) surveyed; {without} with no courier (India Post), "
                    f"{without_cod} with no COD courier."
                )
        except services.ShippingError as error:
            raise CommandError(str(error)) from error
