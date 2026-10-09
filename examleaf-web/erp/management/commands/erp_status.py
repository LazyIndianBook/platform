from django.core.management.base import BaseCommand
from django.utils import timezone

from erp.tasks import status


def when(moment):
    """In India's time (TIME_ZONE): the database's moments are UTC, which read 5 and a half hours off."""
    return f"{timezone.localtime(moment):%Y-%m-%d %H:%M}" if moment else "never"


class Command(BaseCommand):
    help = (
        'The ERPNext sync at a glance (erp/README.md, RUNBOOK.md "ERPNext"): the switches, the account and its '
        "circuit, the outbox by state with its oldest row waiting, the aggregates a dead row holds, the pull's "
        "cursors and the last reconciliation."
    )

    def handle(self, *args, **options):
        now = status()
        flows = ", ".join(f"{flow} {'on' if on else 'off'}" for flow, on in now["flows"].items())
        out = self.stdout.write
        out(f"ERP_ENABLED {'on' if now['enabled'] else 'off'} (mode {now['mode']}); flows: {flows}")
        pulls = f"stock {'on' if now['pull_stock'] else 'off'}, B2B {'on' if now['pull_b2b'] else 'off'}"
        out(f"Pull: {pulls}; stock projection {'on' if now['stock_projection'] else 'off (shadow)'}")
        if account := now["account"]:
            last = f"last success {when(account['last_success_at'])}"
            out(f"Account: {account['label']}, circuit {account['circuit']}, {last}; {account['last_error'] or ''}")
        else:
            out("Account: none enabled (Admin → Integrations → Integration accounts, provider ERPNext)")
        queue = ", ".join(f"{state} {count}" for state, count in now["outbox"].items())
        out(f"Outbox: {queue}")
        if now["oldest_waiting_at"]:
            minutes = now["oldest_waiting_seconds"] // 60
            out(f"Oldest row waiting: {when(now['oldest_waiting_at'])} ({minutes} min)")
        out(f"Aggregates held by a dead row: {now['held_aggregates']}")
        for cursor in now["cursors"]:
            error = f"; error: {cursor['error']}" if cursor["error"] else ""
            after = cursor["modified_after"] or "the start"
            out(f"Cursor {cursor['doctype']}: after {after}, run {when(cursor['last_run_at'])}{error}")
        if run := now["last_reconciliation"]:
            out(
                f"Last reconciliation: {run['date']} ({run['state']}), {run['differences']} difference(s), "
                f"{run['open_differences']} open"
            )
        else:
            out("Last reconciliation: none yet")
