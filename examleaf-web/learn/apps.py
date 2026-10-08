from django.apps import AppConfig


class LearnConfig(AppConfig):
    name = "learn"
    verbose_name = "Revision course"

    def ready(self):
        from . import signals  # noqa: F401  account deletion, clip files
