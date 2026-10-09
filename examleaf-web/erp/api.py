"""The ERPNext sync's staff API, under /api/v1/staff/erp/ (API.md "ERPNext sync (staff)"), on the staff app's rules
(staff.api.StaffView): a member of staff on the panel's session with a second factor, or an API key; each action's
catalogued permission (erp.view_sync to read; erp.replay_sync, high, with a recent re-authentication, to replay or
discard a dead letter; erp.resolve_difference to resolve a reconciliation's difference); the admin host only
(ADMIN_HOSTS: 404 elsewhere) and every refusal an `authz_fail` audit event (staff.middleware, by the path). Each
action is an audit event of its own (erp.replay, erp.discard, erp.resolve: erp/models.py). The initial load is a staff
job (`POST /api/v1/staff/jobs/` with kind `erp_initial_load`, erp.run_initial_load). The serializers are for the
panel to reuse."""

from django.urls import path
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from staff.api import StaffView
from staff.backends import scoped

from .models import ErpCursor, ErpOutbox, ErpReconciliationDifference, ErpReconciliationRun
from .tasks import status

VIEW = "erp.view_sync"


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["erp (staff)"]


class ErpView(StaffView):
    schema = StaffSchema()

    def get_queryset(self):
        return scoped(super().get_queryset(), self.request.user, VIEW)

    def by(self):
        """Who acts: the member of staff (an API key's principal has no row)."""
        return self.request.user if getattr(self.request.user, "pk", None) else None


def refused(message):
    return exceptions.ValidationError({"non_field_errors": [message]})


class ErpOutboxSerializer(serializers.ModelSerializer):
    idempotency_key = serializers.CharField(read_only=True)
    dead_letter = serializers.IntegerField(source="failure_id", read_only=True, allow_null=True)

    class Meta:
        model = ErpOutbox
        fields = [
            *["id", "aggregate_type", "aggregate_id", "sequence", "event", "examleaf_ref", "model", "object_id"],
            *["idempotency_key", "payload", "state", "attempts", "next_at", "last_error", "created", "sent_at"],
            *["response", "dead_letter"],
        ]
        read_only_fields = fields


class ErpDiscardSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, help_text="why it is given up (kept with its dead letter)")


class ErpDifferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErpReconciliationDifference
        fields = ["id", "run", "kind", "key", "platform_value", "erp_value", "note", "resolved_at", "resolved_by"]
        read_only_fields = fields


class ErpResolveSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=300, help_text="what was done about it")


class ErpRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErpReconciliationRun
        fields = [
            *["id", "date", "state", "platform_totals", "erp_totals", "differences_count", "started_at"],
            *["finished_at", "error"],
        ]
        read_only_fields = fields


class ErpRunDetailSerializer(ErpRunSerializer):
    differences = ErpDifferenceSerializer(many=True, read_only=True)

    class Meta(ErpRunSerializer.Meta):
        fields = [*ErpRunSerializer.Meta.fields, "differences"]
        read_only_fields = fields


class ErpCursorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErpCursor
        fields = ["id", "doctype", "modified_after", "last_name", "rows_read", "last_run_at", "last_error"]
        read_only_fields = fields


class ErpAccountStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    mode = serializers.CharField()
    circuit = serializers.CharField()
    last_success_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField()


class ErpCursorStatusSerializer(serializers.Serializer):
    doctype = serializers.CharField()
    modified_after = serializers.CharField()
    last_run_at = serializers.DateTimeField(allow_null=True)
    error = serializers.CharField()


class ErpRunStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateField()
    state = serializers.CharField()
    differences = serializers.IntegerField()
    open_differences = serializers.IntegerField()
    finished_at = serializers.DateTimeField(allow_null=True)


class ErpStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="ERP_ENABLED: the platform talks to ERPNext")
    mode = serializers.CharField(help_text="erpnext, or fake (an in-memory ERPNext)")
    flows = serializers.DictField(child=serializers.BooleanField(), help_text="each ERP_SYNC_* switch")
    pull_stock = serializers.BooleanField()
    pull_b2b = serializers.BooleanField()
    stock_projection = serializers.BooleanField()
    account = ErpAccountStatusSerializer(allow_null=True)
    outbox = serializers.DictField(child=serializers.IntegerField(), help_text="rows by state")
    oldest_waiting_at = serializers.DateTimeField(allow_null=True)
    oldest_waiting_seconds = serializers.IntegerField(allow_null=True)
    held_aggregates = serializers.IntegerField(help_text="aggregates whose rows wait behind a dead one")
    cursors = ErpCursorStatusSerializer(many=True)
    last_reconciliation = ErpRunStatusSerializer(allow_null=True)


class OutboxViewSet(ErpView, viewsets.ReadOnlyModelViewSet):
    """The outbox, newest first (filters state, event, aggregate_type, aggregate_id, examleaf_ref)."""

    queryset = ErpOutbox.objects.all()
    serializer_class = ErpOutboxSerializer
    filterset_fields = ["state", "event", "aggregate_type", "aggregate_id", "examleaf_ref"]
    permissions = dict.fromkeys(["list", "retrieve"], VIEW)


class DeadLetterViewSet(ErpView, viewsets.ReadOnlyModelViewSet):
    """The dead rows, each holding its aggregate's later ones: replay (again from its first try), or discard with a
    reason (its aggregate goes on). Both need erp.replay_sync and a recent re-authentication."""

    queryset = ErpOutbox.objects.filter(state=ErpOutbox.State.DEAD)
    serializer_class = ErpOutboxSerializer
    filterset_fields = ["event", "aggregate_type", "aggregate_id"]
    permissions = {
        **dict.fromkeys(["list", "retrieve"], VIEW),
        **dict.fromkeys(["replay", "discard"], "erp.replay_sync"),
    }

    @extend_schema(request=None, responses=ErpOutboxSerializer)
    @action(detail=True, methods=["post"])
    def replay(self, request, *args, **kwargs):
        row = self.get_object()
        if not row.replay(by=self.by(), request=request):
            raise refused("Not dead any more.")
        return Response(ErpOutboxSerializer(row).data)

    @extend_schema(request=ErpDiscardSerializer, responses=ErpOutboxSerializer)
    @action(detail=True, methods=["post"])
    def discard(self, request, *args, **kwargs):
        asked = ErpDiscardSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        row = self.get_object()
        if not row.discard(asked.validated_data["reason"], by=self.by(), request=request):
            raise refused("Not dead any more.")
        return Response(ErpOutboxSerializer(row).data)


class ReconciliationViewSet(ErpView, viewsets.ReadOnlyModelViewSet):
    """The nightly runs, newest first (filters date, state); one with its differences."""

    queryset = ErpReconciliationRun.objects.all()
    filterset_fields = ["date", "state"]
    permissions = dict.fromkeys(["list", "retrieve"], VIEW)

    def get_serializer_class(self):
        return ErpRunDetailSerializer if self.action == "retrieve" else ErpRunSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.prefetch_related("differences") if self.action == "retrieve" else queryset


class DifferenceFilter(django_filters.FilterSet):
    open = django_filters.BooleanFilter(field_name="resolved_at", lookup_expr="isnull", label="not resolved yet")

    class Meta:
        model = ErpReconciliationDifference
        fields = ["run", "kind"]


class DifferenceViewSet(ErpView, viewsets.ReadOnlyModelViewSet):
    """What did not match (filters run, kind, open); resolve one with a note (erp.resolve_difference)."""

    queryset = ErpReconciliationDifference.objects.select_related("run")
    serializer_class = ErpDifferenceSerializer
    filterset_class = DifferenceFilter
    permissions = {**dict.fromkeys(["list", "retrieve"], VIEW), "resolve": "erp.resolve_difference"}

    @extend_schema(request=ErpResolveSerializer, responses=ErpDifferenceSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, *args, **kwargs):
        asked = ErpResolveSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        difference = self.get_object()
        if not difference.resolve(asked.validated_data["note"], by=self.by(), request=request):
            raise refused("Resolved already.")
        return Response(ErpDifferenceSerializer(difference).data)


class CursorViewSet(ErpView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """How far the pull has read each doctype."""

    queryset = ErpCursor.objects.all()
    serializer_class = ErpCursorSerializer
    permissions = {"list": VIEW}


class StatusView(ErpView, generics.GenericAPIView):
    """The sync at a glance: switches, account, outbox by state, the oldest row waiting, aggregates held, cursors,
    the last reconciliation."""

    serializer_class = ErpStatusSerializer
    permissions = {"GET": VIEW}

    def get(self, request, *args, **kwargs):
        return Response(ErpStatusSerializer(status()).data)


router = SimpleRouter()
router.register("outbox", OutboxViewSet, basename="outbox")
router.register("dead-letters", DeadLetterViewSet, basename="dead-letter")
router.register("reconciliations", ReconciliationViewSet, basename="reconciliation")
router.register("differences", DifferenceViewSet, basename="difference")
router.register("cursors", CursorViewSet, basename="cursor")
app_name = "erp"
urlpatterns = [  # under /api/v1/staff/erp/ (examleaf/api_urls.py), namespace "erp"
    path("status/", StatusView.as_view(), name="status"),
    *router.urls,
]
