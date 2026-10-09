"""/api/: the REST API by version (api/urls.py; the staff's: staff/urls.py), its OpenAPI schema and the Swagger UI and
Redoc pages, and the couriers' webhook (hooks/parcel-events/: shipping/webhooks.py; outside the version, the carrier's
address)."""

from django.http import JsonResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView

from shipping.webhooks import ParcelEventsView


def not_found(request, *args, **kwargs):
    return JsonResponse({"detail": "Not found."}, status=404)


urlpatterns = [
    re_path(r"^(?P<version>v1)/staff/", include(("staff.urls", "staff"))),  # the Admin Control Panel's API
    re_path(r"^(?P<version>v1)/", include(("api.urls", "api"))),
    path("schema/", SpectacularAPIView.as_view(api_version="v1"), name="api-schema"),
    path("docs/", SpectacularSwaggerSplitView.as_view(url_name="api-schema"), name="api-docs"),  # no inline script
    path("redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),
    path("hooks/parcel-events/", ParcelEventsView.as_view(), name="parcel-events"),  # no "sr" or "kr" in it
    re_path(r"", not_found),  # any other /api/ address: a JSON 404 like the API's own (and no slash redirects)
]
