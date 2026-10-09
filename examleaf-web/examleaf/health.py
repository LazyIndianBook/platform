"""The Celery part of /health/: a ping that waits for every worker, then a check that each queue the platform uses has a
consumer."""

import dataclasses

from django.conf import settings
from health_check.contrib.celery import Ping
from health_check.exceptions import ServiceUnavailable


@dataclasses.dataclass
class WorkerPing(Ping):
    """django-health-check's Ping with two changes. The queues to verify come from settings.CELERY_HEALTH_QUEUES, not
    from Celery's task_queues (the platform leaves that unset so that the default worker never consumes the media
    queue). And the ping has no limit: it waits its timeout for every worker, because with limit=1 the media worker
    answering first left the default queue unseen and /health/ flapped between OK and "No worker for Celery task queue
    celery"."""

    queues: tuple[str, ...] = dataclasses.field(
        default_factory=lambda: tuple(settings.CELERY_HEALTH_QUEUES), repr=False
    )

    def check_active_queues(self, *active_workers):
        active = {
            queue.get("name")
            for queues in (self.app.control.inspect(active_workers).active_queues() or {}).values()
            for queue in queues
        }
        for queue in self.queues:
            if queue not in active:
                raise ServiceUnavailable(f"No worker for Celery task queue {queue}")
