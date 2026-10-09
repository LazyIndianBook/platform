"""/api/: the REST API by version (api/urls.py; the staff's: staff/urls.py), its OpenAPI schema and the Swagger UI and
Redoc pages, and the providers' webhooks, outside the version (their addresses): the couriers' (hooks/parcel-events/:
shipping/webhooks.py), ERPNext's doorbells (hooks/erp-events/: erp/inbound.py) and the support mailbox's forwarder
(hooks/support-mail/: support/views.py)."""

from django.http import JsonResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView

from erp.inbound import ErpEventsView
from ops.webhooks import SmsEventsView
from shipping.webhooks import ParcelEventsView
from support.views import SupportMailView


def not_found(request, *args, **kwargs):
    return JsonResponse({"detail": "Not found."}, status=404)


urlpatterns = [
    re_path(r"^(?P<version>v1)/staff/erp/", include("erp.api")),  # the panel's ERPNext sync (erp/api.py)
    re_path(r"^(?P<version>v1)/staff/", include(("staff.urls", "staff"))),  # the Admin Control Panel's API
    re_path(r"^(?P<version>v1)/", include(("api.urls", "api"))),
    path("schema/", SpectacularAPIView.as_view(api_version="v1"), name="api-schema"),
    path("docs/", SpectacularSwaggerSplitView.as_view(url_name="api-schema"), name="api-docs"),  # no inline script
    path("redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),
    path("hooks/parcel-events/", ParcelEventsView.as_view(), name="parcel-events"),  # no "sr" or "kr" in it
    path("hooks/erp-events/", ErpEventsView.as_view(), name="erp-events"),
    path("hooks/sms-events/", SmsEventsView.as_view(), name="sms-events"),  # MSG91's delivery reports (ops/webhooks.py)
    path("hooks/support-mail/", SupportMailView.as_view(), name="support-mail"),  # the support mailbox, forwarded
    re_path(r"", not_found),  # any other /api/ address: a JSON 404 like the API's own (and no slash redirects)
]
