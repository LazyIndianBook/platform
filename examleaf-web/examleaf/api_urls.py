"""/api/: the REST API by version (api/urls.py), its OpenAPI schema and the Swagger UI and Redoc pages."""

from django.http import JsonResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView


def not_found(request, *args, **kwargs):
    return JsonResponse({"detail": "Not found."}, status=404)


urlpatterns = [
    re_path(r"^(?P<version>v1)/", include(("api.urls", "api"))),
    path("schema/", SpectacularAPIView.as_view(api_version="v1"), name="api-schema"),
    path("docs/", SpectacularSwaggerSplitView.as_view(url_name="api-schema"), name="api-docs"),  # no inline script
    path("redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),
    re_path(r"", not_found),  # any other /api/ address: a JSON 404 like the API's own (and no slash redirects)
]
