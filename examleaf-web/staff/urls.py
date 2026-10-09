"""/api/v1/staff/ (namespace "staff"): the Admin Control Panel's API (staff/api.py, API.md "Staff API")."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import api

router = SimpleRouter()
router.register("inbox", api.InboxViewSet, basename="inbox")
router.register("audit", api.AuditViewSet, basename="audit")
router.register("change-requests", api.ChangeRequestViewSet, basename="change-request")
router.register("jobs", api.JobViewSet, basename="job")
router.register("saved-views", api.SavedViewViewSet, basename="saved-view")
router.register("api-keys", api.ApiKeyViewSet, basename="api-key")
router.register("people", api.PeopleViewSet, basename="person")
router.register("users", api.UserViewSet, basename="user")
router.register("data-requests", api.DataRequestViewSet, basename="data-request")
router.register("incidents", api.IncidentViewSet, basename="incident")
router.register("processors", api.ProcessorViewSet, basename="processor")
router.register("notes", api.NoteViewSet, basename="note")

urlpatterns = [
    path("", include("staff.privacy_api")),  # privacy/…: legal and privacy (staff/privacy_api.py)
    path("session/", api.SessionView.as_view(), name="session"),
    path("session/reason/", api.BreakGlassReasonView.as_view(), name="session-reason"),
    path("catalogue/", api.CatalogueView.as_view(), name="catalogue"),
    path("settings/", api.SettingsView.as_view(), name="settings"),
    path("settings/<str:key>/", api.SettingView.as_view(), name="setting"),
    path("settings/<str:key>/history/", api.SettingHistoryView.as_view(), name="setting-history"),
    path("flags/", api.FlagsView.as_view(), name="flags"),
    path("flags/<str:key>/", api.FlagView.as_view(), name="flag"),
    path("flags/<str:key>/history/", api.FlagHistoryView.as_view(), name="flag-history"),
    path("access-review/", api.AccessReviewView.as_view(), name="access-review"),
    path("system/", api.SystemView.as_view(), name="system"),
    path("system/reconcile/", api.ReconcileView.as_view(), name="reconcile"),
    path("invites/accept/", api.InviteAcceptView.as_view(), name="invite-accept"),
    path("policies/ack/", api.PolicyAcknowledgementView.as_view(), name="policy-ack"),
    # Phase B: the modules' own files, one line each, in the order of their paths
    path("connections/", include("integrations.api")),
    path("content/", include("content.staff_api")),
    path("finance/", include("shop.staff_finance")),
    path("home/", include("insights.staff_home")),
    path("orders/", include("shop.staff_orders")),
    path("reports/", include("insights.staff_api")),
    path("support/", include("support.api")),
    path("system/", include("staff.system_api")),
    path("tax/", include("shop.staff_tax")),
    path("templates/", include("ops.staff_api")),
    *router.urls,
]
