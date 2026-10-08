"""Error pages and small site-wide views. The 400 and 500 pages are self-contained HTML (no layout, no static files,
no database): they must still render when those are what failed. API paths get JSON instead."""

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseServerError, JsonResponse
from django.template.loader import render_to_string
from django.views.generic import TemplateView
from django_guid import get_guid


def error_handler(template, status, detail, response_class):
    def handler(request, exception=None):
        if request.path.startswith("/api/"):  # a JSON client gets JSON, as from the API's own errors
            return JsonResponse({"detail": detail}, status=status)
        return response_class(render_to_string(template, {"request_id": get_guid()}))

    return handler


bad_request = error_handler("400.html", 400, "Bad request.", HttpResponseBadRequest)
server_error = error_handler("500.html", 500, "Server error.", HttpResponseServerError)


class RobotsView(TemplateView):
    """/robots.txt: keeps crawlers out of the account, cart and checkout pages, the admin and the API."""

    template_name = "robots.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        return super().get_context_data(site_url=settings.SITE_URL, **kwargs)
