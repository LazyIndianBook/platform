from datetime import date

from django.core.management.base import BaseCommand, CommandError

from support import register


class Command(BaseCommand):
    help = (
        "The grievance register as CSV on standard output (support/register.py): the complaints received in a period, "
        "acknowledged and resolved, against their deadlines, with the NCH docket and no personal data. The panel's "
        '"Grievance register" export is the usual way; this is for when the panel cannot be used (RUNBOOK.md).'
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="since", help="the first day received (YYYY-MM-DD), India's dates")
        parser.add_argument("--until", help="the last day received (YYYY-MM-DD)")

    def handle(self, *args, since=None, until=None, **options):
        params = {}
        for name, value in (("from", since), ("until", until)):
            if value:
                try:
                    params[name] = date.fromisoformat(value).isoformat()
                except ValueError as error:
                    raise CommandError(f"--{name}: a day, YYYY-MM-DD.") from error
        register.write(register.tickets(params), self.stdout)
