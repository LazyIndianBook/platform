"""Celery app. Settings are the CELERY_* names in settings.py; tasks live in each app's tasks.py.

Development and tests run tasks inline (CELERY_TASK_ALWAYS_EAGER), so no broker is needed there.
Production: `celery -A examleaf worker` and `celery -A examleaf beat` (see docker-compose.yml).
"""

import functools
import logging
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examleaf.settings")
app = Celery("examleaf")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
logger = logging.getLogger(__name__)
# Time limits by kind of task, beside the default (settings.CELERY_TASK_SOFT_TIME_LIMIT, 270 s, then 300 s): a PDF (an
# invoice renders in a fifth of a second), and the nightly and weekly jobs that loop over many rows or providers' calls.
PDF_TASK = {"soft_time_limit": 60, "time_limit": 90}
LONG_TASK = {"soft_time_limit": 1500, "time_limit": 1800}


def single_run(seconds):
    """For a periodic task whose second run, overlapping the first, would send the same emails or messages again: a
    run that starts while another holds the lock does nothing. The lock lasts `seconds` at most (the task's hard
    time limit, so that a killed run frees it), in the cache: while Redis is down runs are not held back, and the
    task's own claims (each alert or message taken before it is sent) still keep a message from going twice."""

    def decorator(task):
        @functools.wraps(task)
        def run(*args, **kwargs):
            from django.core.cache import cache

            key = f"single-run:{task.__module__}.{task.__name__}"
            if not cache.add(key, "running", seconds):
                logger.warning("%s.%s is running already: this run does nothing", task.__module__, task.__name__)
                return None
            try:
                return task(*args, **kwargs)
            finally:
                cache.delete(key)

        return run

    return decorator
