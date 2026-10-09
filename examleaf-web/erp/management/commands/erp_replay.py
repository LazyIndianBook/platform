from argparse import ArgumentTypeError
from datetime import datetime, time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from erp.models import ErpOutbox
from erp.producers import nudge
from staff.audit import record


def moment(value):
    """YYYY-MM-DD (from its midnight) or YYYY-MM-DDTHH:MM, in the platform's time zone unless it says another."""
    day = parse_date(value)
    when = datetime.combine(day, time()) if day else parse_datetime(value)
    if when is None:
        raise ArgumentTypeError("YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    return when if timezone.is_aware(when) else timezone.make_aware(when)


class Command(BaseCommand):
    help = (
        "Send an outbox row again now, from its first try (a dead letter: closed as replayed): `erp_replay <id>`, "
        "every dead row with --dead, or with --sent-since every row ERPNext answered since then (ERPNext restored from "
        "a backup of that time: sent again in order, with their keys, ERPNext answering duplicates for what it kept; "
        'RUNBOOK.md "ERPNext"). The relay sends them once ERP_ENABLED is on.'
    )

    def add_arguments(self, parser):
        parser.add_argument("id", nargs="?", type=int, help="the outbox row's id")
        parser.add_argument("--dead", action="store_true", help="every dead row")
        parser.add_argument("--sent-since", type=moment, help="every row sent since then (YYYY-MM-DD[THH:MM])")

    def handle(self, *args, id=None, dead=False, sent_since=None, **options):
        if [id is not None, dead, sent_since is not None].count(True) != 1:
            raise CommandError("Give a row's id, --dead or --sent-since (one of them).")
        if sent_since is not None:
            return self.resend(sent_since)
        rows = ErpOutbox.objects.filter(state=ErpOutbox.State.DEAD) if dead else ErpOutbox.objects.filter(pk=id)
        if not dead and not rows.exists():
            raise CommandError(f"No outbox row #{id}.")
        replayed = [row.pk for row in rows.order_by("pk") if row.replay()]
        skipped = "" if dead or replayed else f" (row #{id} is {rows.get().get_state_display()})"
        self.stdout.write(f"Replayed {len(replayed)} row(s){skipped}: {', '.join(map(str, replayed)) or 'none'}.")

    def resend(self, since):
        with transaction.atomic():
            sent = ErpOutbox.objects.select_for_update().filter(state=ErpOutbox.State.SENT, sent_at__gte=since)
            ids = list(sent.order_by("pk").values_list("pk", flat=True))
            ErpOutbox.objects.filter(pk__in=ids).update(
                state=ErpOutbox.State.PENDING, attempts=0, next_at=timezone.now(), last_error=""
            )
            details = {"sent_since": since.isoformat(), "rows": len(ids)}
            record("erp.resend", permission="erp.replay_sync", details=details)  # the shell's: the system
            nudge()
        self.stdout.write(f"Sent again: {len(ids)} row(s) sent since {timezone.localtime(since):%Y-%m-%d %H:%M}.")
