from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "integrations"
    verbose_name = "Integrations"

    def ready(self):
        from . import checks  # noqa: F401  INTEGRATION_KEYS on a server (integrations.E001)
