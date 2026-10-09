from django.core.management.base import BaseCommand

from shipping import services


class Command(BaseCommand):
    help = "Read the tracking of the parcels silent for 6 hours, as the task does every two hours."

    def handle(self, *args, **options):
        self.stdout.write(f"Tracking read for {services.poll()} parcel(s).")
