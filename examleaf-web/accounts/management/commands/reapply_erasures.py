"""manage.py reapply_erasures: after a restore from a backup, erase again every account the erasure ledger says was
erased (research 4.5: an erased account never comes back; RUNBOOK.md "Restore the database from a backup"). The
ledger is read from this database's own deletion requests (DeletionRequest.subject_hash), from the backups' bucket
(`erasures/<id>.json`, each erasure's line copied off the server when it was made: those after the backup too) and
from a file of lines (--ledger, written by --export from a database that can still be read). An account is erased
again only while its email address still hashes to the ledger's line: an id that someone else has taken since is never
touched. It prints counts only, no personal data."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import DeletionRequest, User
from accounts.tasks import LEDGER_PREFIX, ledger_line


def bucket_lines():
    """The ledger's lines in the backups' bucket (none without BACKUP_BUCKET)."""
    from staff.audit import backups_storage

    storage = backups_storage()
    if storage is None:
        return []
    try:
        _, names = storage.listdir(LEDGER_PREFIX.rstrip("/"))
    except FileNotFoundError:  # a local folder never written to
        return []
    lines = []
    for name in sorted(names):
        if name.endswith(".json"):
            with storage.open(f"{LEDGER_PREFIX}{name}") as file:
                lines.append(json.loads(file.read()))
    return lines


class Command(BaseCommand):
    help = "Erase again, after a restore from a backup, the accounts the erasure ledger says were erased."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="count what would be erased again; change nothing")
        parser.add_argument("--ledger", help="a file of ledger lines (JSON lines, as --export writes them)")
        parser.add_argument("--export", help="write this database's ledger to this file, and do nothing else")
        parser.add_argument("--no-bucket", action="store_true", help="leave the backups' bucket's copy out")

    def handle(self, *args, dry_run=False, ledger=None, export=None, no_bucket=False, **options):
        done = DeletionRequest.objects.filter(status=DeletionRequest.Status.DONE).exclude(subject_hash="")
        if export:
            lines = [json.dumps(ledger_line(deletion), sort_keys=True) for deletion in done.order_by("pk")]
            Path(export).write_text("".join(f"{line}\n" for line in lines))
            self.stdout.write(f"{len(lines)} ledger lines written to {export}.")
            return
        entries = {}
        sources = [ledger_line(deletion) for deletion in done]
        sources += [] if no_bucket else bucket_lines()
        if ledger:
            sources += [json.loads(line) for line in Path(ledger).read_text().splitlines() if line.strip()]
        for line in sources:
            if line.get("user") and line.get("subject_hash"):
                entries.setdefault((int(line["user"]), line["subject_hash"]), line)
        counts = dict.fromkeys(["erased_again", "erased_already", "not_restored", "someone_else"], 0)
        for (pk, digest), line in sorted(entries.items()):
            counts[self.reapply(pk, digest, line, dry_run)] += 1
        summary = ", ".join(f"{name.replace('_', ' ')}: {count}" for name, count in counts.items())
        self.stdout.write(f"{len(entries)} erasures in the ledger. {summary}" + (" (dry run)" if dry_run else ""))

    def reapply(self, pk, digest, line, dry_run):
        from staff.privacy import ledger_matches

        user = User.objects.filter(pk=pk).first()
        if user is None:
            return "not_restored"
        if user.email.endswith("@deleted.invalid"):
            return "erased_already"
        if not ledger_matches(user.email, digest):
            return "someone_else"  # the id was given to another account since: never touched
        if not dry_run:
            kept = parse_datetime(line.get("registration_until") or "")  # the intermediary rule's days, if any left
            with transaction.atomic():
                deletion = user.pending_deletion or DeletionRequest.objects.create(user=user, due_at=timezone.now())
                deletion.complete(reapply=True, registration_until=kept)
        return "erased_again"
