from datetime import date

from django.core.management.base import BaseCommand, CommandError

from shop import settlements


class Command(BaseCommand):
    help = (
        "Fetch a day's Razorpay settlements (yesterday by default), match them to the payments and refunds, and post "
        "the matched ones to ERPNext once: the panel's Finance, Settlements, 'Fetch a day', for when the panel is "
        "down (RUNBOOK.md 'Reconciling Razorpay settlements'). Run twice, a day changes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument("--day", help="YYYY-MM-DD, India's day; yesterday by default")
        parser.add_argument("--dry-run", action="store_true", help="fetch and match, keep nothing")

    def handle(self, day=None, dry_run=False, **options):
        try:
            when = date.fromisoformat(day) if day else settlements.yesterday()
        except ValueError as error:
            raise CommandError("--day is a day: YYYY-MM-DD.") from error
        try:
            result = settlements.fetch_day(when, dry_run=dry_run)
        except settlements.NotConfigured as error:
            raise CommandError(str(error)) from error
        for name, value in result.items():
            self.stdout.write(f"{name}: {value}")
        if not dry_run:
            self.stdout.write(f"posted (waiting before): {settlements.post_waiting()}")
