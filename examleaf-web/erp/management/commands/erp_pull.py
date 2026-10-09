from django.core.management.base import BaseCommand

from erp import inbound
from erp.models import ErpCursor
from erp.producers import switch


class Command(BaseCommand):
    help = (
        "Read now what changed in ERPNext since each cursor (the 15-minute pull's work, inbound.pull): the doctypes "
        "ERP_PULL_STOCK and ERP_PULL_B2B switch on, or --doctype (repeatable). --restart reads them from the start "
        "again (the mirrors rebuilt, after ERPNext was restored)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--doctype", action="append", dest="doctypes", help='e.g. "Sales Invoice"')
        parser.add_argument("--restart", action="store_true", help="clear the cursors first")

    def handle(self, *args, doctypes=None, restart=False, **options):
        if not switch("ERP_ENABLED"):
            self.stdout.write("Nothing read: ERP_ENABLED is off.")
            return
        doctypes = doctypes or inbound.pulled_doctypes()
        if not doctypes:
            self.stdout.write("Nothing to read: ERP_PULL_STOCK and ERP_PULL_B2B are off (or give --doctype).")
            return
        if restart:
            ErpCursor.objects.filter(doctype__in=doctypes).update(modified_after="", last_name="")
        for doctype, read in inbound.pull(doctypes).items():
            self.stdout.write(f"{doctype}: {read}{' row(s)' if isinstance(read, int) else ''}")
