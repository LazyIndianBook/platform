"""A bulkhead: at most half of a process's threads wait on providers at once (RESILIENCE.md, the load test).

A provider that answers slowly holds a gunicorn thread for its whole timeout, and a process's connections are pinned
to it (the proxy's, kept alive): with every thread of a process waiting on Razorpay or MSG91, the process's other
requests, the catalogue included, waited ten seconds behind them. Every call to a provider made inside a request
takes one of SLOTS first, shared by the providers; a call over that fails at once (the provider's own "unreachable"
error: the same honest answer, and Celery's retry in a task), and the other half of the threads keep the site going.
A Celery process runs one task at a time and never meets the limit."""

import os
import threading

SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get("GUNICORN_THREADS", "8")) // 2))


class Bulkhead:
    def __init__(self, exception, message):
        self.exception, self.message = exception, message

    def __enter__(self):
        if not SLOTS.acquire(blocking=False):
            raise self.exception(self.message)
        return self

    def __exit__(self, *exc):
        SLOTS.release()
