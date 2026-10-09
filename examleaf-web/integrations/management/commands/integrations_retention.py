from django.conf import settings
from django.core.management.base import BaseCommand

from integrations.tasks import purge_old_records


class Command(BaseCommand):
    help = (
        "Delete the integration call log, the inbound events and the dead letters dealt with that are older than "
        "INTEGRATIONS_RETENTION_DAYS (what the daily task does)."
    )

    def handle(self, *args, **options):
        counts = purge_old_records()
        days = settings.INTEGRATIONS_RETENTION_DAYS
        self.stdout.write(
            f"Older than {days} days: {counts['calls']} call(s), {counts['events']} inbound event(s), "
            f"{counts['dead_letters']} dead letter(s) deleted."
        )
