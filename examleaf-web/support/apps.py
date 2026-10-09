from django.apps import AppConfig


class SupportConfig(AppConfig):
    name = "support"
    verbose_name = "Support"

    def ready(self):
        """The support mailbox in the integrations framework (its webhook token on an IntegrationAccount, its events
        read by a task), the erasure of an account reaching its tickets, and INTEGRATION_KEYS on a server."""
        from integrations import models

        from . import checks, signals  # noqa: F401  (support.E001; the erasure's receiver)

        models.PROVIDERS["support_mail"] = "Support mailbox (email in)"
        models.INBOUND_PROCESSORS["support_mail"] = "support.tasks.process_inbound_mail"
