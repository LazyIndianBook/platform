from datetime import date

from django.core.management.base import BaseCommand

from erp import producers
from staff.audit import record


class Command(BaseCommand):
    help = (
        'The initial load (erp/README.md, "Operations"; from the panel: the staff job erp_initial_load): every '
        "product's item, then the bundles' components; with --invoices-from YYYY-MM-DD, every invoice issued since "
        "that day with what hangs on it (its credit notes and refunds, payments, delivery notes, COD settlement), in "
        "order. Each flow only while its ERP_SYNC_* is on, and each document once (what the outbox has already is not "
        "written again). A dry run by default: it counts what it would write and writes nothing; --apply writes it, "
        "and the relay sends it once ERP_ENABLED is on. Either way an audit event (erp.initial_load)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the rows (default: a dry run)")
        parser.add_argument("--invoices-from", type=date.fromisoformat, help="YYYY-MM-DD: invoices since that day")

    def handle(self, *args, apply=False, invoices_from=None, **options):
        written, off = producers.initial_load(invoices_from, apply=apply)
        since = invoices_from.isoformat() if invoices_from else None
        details = {"invoices_from": since, "dry_run": not apply, "written": written, "flows_off": off}
        record("erp.initial_load", permission="erp.run_initial_load", details=details)  # the shell's: the system
        verb = "Wrote" if apply else "Dry run, nothing written; would write"
        rows = ", ".join(f"{count} {event}" for event, count in written.items()) or "nothing"
        self.stdout.write(f"{verb}: {rows}.")
        if off:
            self.stdout.write(f"Flows off, not loaded: {', '.join(off)}.")
        if invoices_from is None:
            self.stdout.write("No invoices: give --invoices-from YYYY-MM-DD to load them.")
        if apply and written and not producers.switch("ERP_ENABLED"):
            self.stdout.write("ERP_ENABLED is off: the rows wait until it is on.")
