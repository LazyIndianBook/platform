from django.apps import AppConfig


class LearnConfig(AppConfig):
    name = "learn"
    verbose_name = "Revision course"

    def ready(self):
        from . import checks, signals  # noqa: F401  LEARN_CODE_SECRET; account deletion, clip files
