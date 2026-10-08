"""Error pages and small site-wide views. The 400 and 500 pages are self-contained HTML (no layout, no static files,
no database): they must still render when those are what failed. API paths get JSON instead."""

import time

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseServerError, JsonResponse
from django.template.loader import render_to_string
from django.views.generic import TemplateView
from django_guid import get_guid
from health_check.views import HealthCheckView


def error_handler(template, status, detail, response_class):
    def handler(request, exception=None):
        if request.path.startswith("/api/"):  # a JSON client gets JSON, as from the API's own errors
            return JsonResponse({"detail": detail}, status=status)
        return response_class(render_to_string(template, {"request_id": get_guid()}))

    return handler


bad_request = error_handler("400.html", 400, "Bad request.", HttpResponseBadRequest)
server_error = error_handler("500.html", 500, "Server error.", HttpResponseServerError)


class Done:
    """A check already run (HealthView): gives its result again."""

    def __init__(self, result):
        self.result = result

    async def get_result(self, executor=None):
        return self.result


class HealthView(HealthCheckView):
    """django-health-check's view, the results kept for SECONDS in each process: however often /health/ is called,
    each gunicorn worker runs the checks (a storage write, the Celery ping) at most once in that time. In memory, not
    in the cache, so that a Redis outage does not switch it off (H1)."""

    SECONDS = 20
    results_by_path = {}  # request.path: (time.monotonic(), results); per process
    cached = None  # the results being served again, if fresh

    async def get(self, request, *args, **kwargs):
        when, results = self.results_by_path.get(request.path, (0, None))
        self.cached = results if time.monotonic() - when < self.SECONDS else None
        response = await super().get(request, *args, **kwargs)
        if self.cached is None:
            self.results_by_path[request.path] = (time.monotonic(), self.results)
        return response

    def get_checks(self):
        return (Done(result) for result in self.cached) if self.cached else super().get_checks()


class RobotsView(TemplateView):
    """/robots.txt: keeps crawlers out of the account, cart and checkout pages, the admin and the API."""

    template_name = "robots.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        return super().get_context_data(site_url=settings.SITE_URL, **kwargs)
