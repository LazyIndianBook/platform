from django.core.management.base import BaseCommand, CommandError

from staff.audit import heads, verify


class Command(BaseCommand):
    help = "Recompute the audit log's hash chains (staff.audit.verify); exits with an error at the first break."

    def handle(self, *args, **options):
        problems = verify()
        for chain, head in heads().items():
            self.stdout.write(f"{chain}: newest event #{head['id']}, {head['hash']}")
        if problems:
            raise CommandError("The audit chain is broken:\n" + "\n".join(problems))
        self.stdout.write("Intact.")
