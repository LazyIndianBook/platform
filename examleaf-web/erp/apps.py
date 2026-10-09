from django.apps import AppConfig


class ErpConfig(AppConfig):
    name = "erp"
    verbose_name = "ERPNext sync"

    def ready(self):
        """ERPNext in the integrations framework (its doorbells' task, its connection test), and the producers'
        receivers (erp/producers.py)."""
        from integrations import models, services

        from . import inbox, producers  # noqa: F401  connect their receivers
        from .client import connection_test

        models.INBOUND_PROCESSORS["erpnext"] = "erp.tasks.process_inbound_event"
        services.CONNECTION_TESTS["erpnext"] = connection_test
