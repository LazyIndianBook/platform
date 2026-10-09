"""gunicorn's settings for the web (the Dockerfile's command, docker-compose.yml's web, the Kubernetes chart's web),
each from the environment with its default here; GUNICORN_CMD_ARGS and the command line still win over this file
(gunicorn's order). RESILIENCE.md says what each is for and when to change it; DEPLOYMENT.md section 13 lists them."""

import faulthandler
import os
import sys


def number(name, default):
    return int(os.environ.get(name, default))


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = number("WEB_CONCURRENCY", 2)  # processes: about 2 x the CPUs + 1
worker_class = "gthread"
threads = number("GUNICORN_THREADS", 8)  # requests served at once by each process
# Connections a process takes at once, those waiting for a thread included: past them it stops accepting, and the
# next connection waits in the kernel's queue for whichever process has a thread free (RESILIENCE.md, the load test).
worker_connections = number("GUNICORN_WORKER_CONNECTIONS", 1000)
# Not a request's limit with threads: a process whose main loop is silent this long (stuck as a whole) is killed and
# replaced. A slow request is bounded by the timeouts of what it calls and by the database's statement_timeout.
timeout = number("GUNICORN_TIMEOUT", 60)
graceful_timeout = number("GUNICORN_GRACEFUL_TIMEOUT", 30)  # after SIGTERM, the requests in progress may finish
keepalive = number("GUNICORN_KEEPALIVE", 5)  # seconds an idle connection from the proxy is kept
max_requests = number("GUNICORN_MAX_REQUESTS", 1000)  # a process is replaced after this many (slow leaks)...
max_requests_jitter = number("GUNICORN_MAX_REQUESTS_JITTER", 100)  # ...each after a different number
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None  # the heartbeat file in memory, not on a disk
control_socket_disable = True  # gunicorn 25.1's gunicornc socket: unused, and $HOME is read-only in the chart
# One JSON object per line, as Django's own logs (settings.LOGGING): gunicorn's start, stop and worker messages.
# Requests are logged by Django (examleaf.middleware.RequestLogMiddleware: with the request and user ids), not here.
accesslog = None
if os.environ.get("LOG_JSON", "1") != "0":
    logconfig_dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "rename_fields": {"asctime": "time", "levelname": "level", "name": "logger"},
            }
        },
        "handlers": {"stdout": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "json"}},
        "loggers": {
            "gunicorn.error": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
            "gunicorn.access": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        },
    }


def worker_abort(worker):
    """A process killed for its timeout (SIGABRT): every thread's stack goes to the log first, to show what it was
    waiting for."""
    worker.log.error("worker %s timed out: the stacks of its threads follow", worker.pid)
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
