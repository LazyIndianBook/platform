"""Celery app. Settings are the CELERY_* names in settings.py; tasks live in each app's tasks.py.

Development and tests run tasks inline (CELERY_TASK_ALWAYS_EAGER), so no broker is needed there.
Production: `celery -A examleaf worker` and `celery -A examleaf beat` (see docker-compose.yml).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examleaf.settings")
app = Celery("examleaf")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
