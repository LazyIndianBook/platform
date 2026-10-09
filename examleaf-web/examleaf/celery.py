"""Celery app. Settings are the CELERY_* names in settings.py; tasks live in each app's tasks.py.

Development and tests run tasks inline (CELERY_TASK_ALWAYS_EAGER), so no broker is needed there.
Production: `celery -A examleaf worker` and `celery -A examleaf beat` (see docker-compose.yml).
"""

import functools
import logging
import os

import celery
from celery import Celery, states

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examleaf.settings")


class LostTooOften(Exception):
    pass


class Task(celery.Task):
    """Every task's base (the app's, and IntegrationTask's). A task whose process died under it (killed for its memory,
    a crash in a C library) goes back to the queue at once (CELERY_TASK_REJECT_ON_WORKER_LOST), so one that kills its
    process every time would come back for ever. A run delivered again therefore writes its STARTED state with the
    count of the runs before it that started and never ended (any end writes another state); after LOST_RUNS of them
    it fails instead, acknowledged, with its reason in the results and Sentry. A first delivery reads and writes
    nothing here."""

    LOST_RUNS = 2  # with the first delivery's own, three processes lost: then it fails

    def before_start(self, task_id, args, kwargs):
        if not (self.request.delivery_info or {}).get("redelivered"):
            return
        meta = self.backend.get_task_meta(task_id, cache=False)  # (it keeps a SUCCESS it has read)
        started = meta["status"] == states.STARTED  # the run before this one started and never ended
        lost = (meta["result"] or {}).get("lost", 0) + 1 if started else 0
        if lost >= self.LOST_RUNS:  # not WorkerLostError: that one would be put back in the queue again
            raise LostTooOften(f"{self.name}: its process died under {lost + 1} runs in a row; not run again")
        self.update_state(task_id, states.STARTED, {"lost": lost})


app = Celery("examleaf", task_cls=Task)
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
logger = logging.getLogger(__name__)
# Time limits by kind of task, beside the default (settings.CELERY_TASK_SOFT_TIME_LIMIT, 270 s, then 300 s): a PDF (an
# invoice renders in a fifth of a second), and the nightly and weekly jobs that loop over many rows or providers' calls.
PDF_TASK = {"soft_time_limit": 60, "time_limit": 90}
LONG_TASK = {"soft_time_limit": 1500, "time_limit": 1800}


class TaskIds(logging.Filter):
    """A log line written inside a Celery task names the task and its id (task_name, task_id), beside the request id
    django-guid gives it (the request that queued the task): settings.LOGGING's stdout handler."""

    def filter(self, record):
        from celery import current_task

        if current_task and current_task.request.id:
            record.task_id, record.task_name = current_task.request.id, current_task.name
        return True


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
