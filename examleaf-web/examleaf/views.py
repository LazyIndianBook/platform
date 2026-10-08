"""Error pages and small site-wide views. The 400 and 500 pages are self-contained HTML (no layout, no static files,
no database): they must still render when those are what failed. API paths get JSON instead."""

import hashlib
import json
import os
import time

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseServerError, JsonResponse
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
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


@cache_control(public=True, max_age=86400)
def manifest(request):
    """/manifest.webmanifest: the web app's name, colours and icons (manage.py build_covers draws them), so that a
    phone can add the site to its home screen."""

    def icon(size, purpose="any"):
        src = static(f"img/icon-{size}.png")
        return {"src": src, "sizes": f"{size}x{size}", "type": "image/png", "purpose": purpose}

    data = {
        "id": "/",
        "name": "ExamLeaf",
        "short_name": "ExamLeaf",
        "description": "Sample papers for the Assam Board Class 12 examination, with free worked solutions.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0b2a5b",
        "theme_color": "#0b2a5b",
        "icons": [icon(192), icon(512), icon(512, "maskable")],
    }
    return JsonResponse(data, content_type="application/manifest+json")


class ServiceWorkerView(TemplateView):
    """/sw.js (from the site's root, so that it serves every page): keeps the offline page and the static files of
    this release, never a page (pages hold the visitor's account, cart and CSRF token, and a solution must not outlive
    a log-out). Static files are kept only with hashed names (DEBUG off), or a changed CSS file would not show."""

    template_name = "sw.js"
    content_type = "text/javascript; charset=utf-8"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Cache-Control"] = "no-cache"  # browsers check for a new worker on every visit
        return response

    def get_context_data(self, **kwargs):
        cache_static = not settings.DEBUG
        precache = [reverse("offline")]
        if cache_static:
            precache += [static(name) for name in ["css/site.css", "js/site.js", "img/favicon.svg"]]
        precache = json.dumps(precache)
        release = os.environ.get("RELEASE", "") + precache  # hashed names change with their files
        return super().get_context_data(
            version=hashlib.sha256(release.encode()).hexdigest()[:12],
            precache=precache,
            cache_static=cache_static,
            static_prefix=settings.STATIC_URL if settings.STATIC_URL.startswith("/") else f"/{settings.STATIC_URL}",
            **kwargs,
        )
