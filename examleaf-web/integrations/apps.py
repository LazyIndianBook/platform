from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "integrations"
    verbose_name = "Integrations"

    def ready(self):
        # INTEGRATION_KEYS on a server (integrations.E001); the connection tests of Razorpay, MSG91, SES, the buckets …
        from . import checks, connections  # noqa: F401
