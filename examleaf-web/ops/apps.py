from django.apps import AppConfig


class OpsConfig(AppConfig):
    name = "ops"

    def ready(self):
        from integrations import models

        models.INBOUND_PROCESSORS["msg91"] = "ops.tasks.process_sms_event"  # MSG91's delivery reports (ops/webhooks.py)
