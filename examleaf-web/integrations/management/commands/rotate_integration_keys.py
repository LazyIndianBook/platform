from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from integrations import crypto
from integrations.models import IntegrationAccount


class Command(BaseCommand):
    help = (
        "Re-encrypt every integration secret under the first key of INTEGRATION_KEYS, after a new key was put first "
        '(RUNBOOK.md "Integration keys"); the old key can be removed once this has run.'
    )

    def handle(self, *args, **options):
        rotated = 0
        for pk in IntegrationAccount.objects.order_by("pk").values_list("pk", flat=True):
            with transaction.atomic():  # one account at a time: a failure leaves the others done and itself as it was
                account = IntegrationAccount.objects.select_for_update().get(pk=pk)
                changes = {}
                for name in IntegrationAccount.SECRET_FIELDS:
                    if value := getattr(account, name):
                        try:
                            changes[name] = crypto.rotate(value)
                        except crypto.SecretUnreadable as error:
                            raise CommandError(
                                f"Account #{pk}: its {name} cannot be read with INTEGRATION_KEYS (is the old key still "
                                "in the list?). Accounts before it are done; nothing else changed."
                            ) from error
                if changes:
                    IntegrationAccount.objects.filter(pk=pk).update(**changes)
                    rotated += 1
        self.stdout.write(f"Re-encrypted the secrets of {rotated} account(s) under the first key.")
