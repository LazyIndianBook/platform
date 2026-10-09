from django.apps import AppConfig


class ShippingConfig(AppConfig):
    name = "shipping"
    verbose_name = "Shipping"

    def ready(self):
        """Shiprocket in the integrations framework: its webhooks' processing task and its connection test."""
        from integrations import models, services

        from .carriers.shiprocket import connection_test

        models.INBOUND_PROCESSORS["shiprocket"] = "shipping.tasks.process_inbound_event"
        services.CONNECTION_TESTS["shiprocket"] = connection_test
