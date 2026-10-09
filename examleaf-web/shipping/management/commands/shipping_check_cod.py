from django.core.management.base import BaseCommand

from shipping import services


class Command(BaseCommand):
    help = "Ask the courier about every COD remittance awaited: remitted, mismatched or overdue (as the daily task)."

    def handle(self, *args, **options):
        counts = services.check_cod()
        self.stdout.write(", ".join(f"{state}: {count}" for state, count in sorted(counts.items())) or "None awaited.")
