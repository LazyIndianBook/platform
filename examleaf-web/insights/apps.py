from django.apps import AppConfig


class InsightsConfig(AppConfig):
    name = "insights"
    verbose_name = "Insights"

    def ready(self):
        from . import checks  # noqa: F401  (insights.E001: the minimum cell sizes)
