"""The connections page's API, under /api/v1/staff/connections/ (staff/urls.py; API.md "Connections (staff)"), on the
staff app's rules (staff.api.StaffView: a member of staff on the panel's session with a second factor, or an API key
for the reads; each action's catalogued permission; the admin host only, every refusal an audit event):

- reading the cards, a provider's webhooks: integrations.view_integrationaccount (OWNER, ADMIN, FINANCE, AUDITOR);
  its events, calls and dead letters: integrations.view_inboundevent, _integrationcall, _integrationfailure;
- testing, replacing credentials, switching the mode, holding or resetting the circuit, rotating a webhook token:
  staff.manage_connections (high: a re-authentication; the owners alerted of every change);
- processing events again and replaying or discarding dead letters: staff.replay_webhook (ERPNext's dead letters
  erp.replay_sync, as on the sync's own pages).

What each does is integrations/connections.py's; the secrets are never answered, only their last four characters (a new
webhook token once, when it is made)."""

from django.db.models import OuterRef, Q, Subquery
from django.urls import path
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from api.schema import AutoSchema
from staff.api import StaffView
from staff.backends import scoped

from . import connections as c
from .models import InboundEvent, IntegrationAccount, IntegrationCall, IntegrationFailure
from .redact import excerpt

VIEW = "integrations.view_integrationaccount"
MANAGE = "staff.manage_connections"
REPLAY = "staff.replay_webhook"


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["connections (staff)"]


class ConnectionView(StaffView):
    schema = StaffSchema()

    def spec(self):
        return c.provider_or_404(self.kwargs["provider"])

    def by(self):
        """Who acts: the member of staff (an API key's principal has no row)."""
        return self.request.user if getattr(self.request.user, "pk", None) else None


# Answers


class AccountRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=IntegrationAccount.Mode.choices)
    enabled = serializers.BooleanField(help_text="the account in use")
    label = serializers.CharField(allow_blank=True)
    held = serializers.DictField(child=serializers.CharField(), help_text="each credential's last four characters")
    unreadable = serializers.BooleanField(help_text="its secrets cannot be read with INTEGRATION_KEYS")
    credentials_updated_at = serializers.DateTimeField(allow_null=True)
    credentials_updated_by = serializers.IntegerField(allow_null=True)
    rotate_by = serializers.DateField(allow_null=True, help_text="our 90-day rotation")
    rotate_in_days = serializers.IntegerField(allow_null=True, help_text="negative: overdue")
    token_expires_at = serializers.DateTimeField(allow_null=True, help_text="the cached access token (Shiprocket)")
    token_in_hours = serializers.FloatField(allow_null=True)
    webhook_token = serializers.CharField(allow_blank=True, help_text="its last four characters")
    webhook_rotated_at = serializers.DateTimeField(allow_null=True)


class LastTestSerializer(serializers.Serializer):
    at = serializers.DateTimeField(allow_null=True)
    ok = serializers.BooleanField(allow_null=True)
    message = serializers.CharField(allow_blank=True)


class CircuitSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=IntegrationAccount.Circuit.choices)
    held_open = serializers.BooleanField(help_text="opened by staff: no trial call until reset")
    opened_at = serializers.DateTimeField(allow_null=True)
    failures = serializers.IntegerField()


class CallsSerializer(serializers.Serializer):
    day = serializers.IntegerField(help_text="calls in the last 24 hours")
    day_errors = serializers.IntegerField()
    week = serializers.IntegerField(help_text="calls in the last 7 days")
    week_errors = serializers.IntegerField()
    p90_ms = serializers.IntegerField(allow_null=True, help_text="the week's 90th percentile, in milliseconds")


class ActionsSerializer(serializers.Serializer):
    test = serializers.BooleanField()
    credentials = serializers.BooleanField(help_text="its keys are the panel's to replace")
    mode = serializers.BooleanField()
    circuit = serializers.BooleanField()
    webhooks = serializers.BooleanField()


class RazorpayHealthSerializer(serializers.Serializer):
    last_event_at = serializers.DateTimeField(allow_null=True)
    age_hours = serializers.FloatField(allow_null=True)
    paid_in_window = serializers.IntegerField(help_text="online payments captured in the window")
    window_hours = serializers.IntegerField()
    silent = serializers.BooleanField(help_text="payments came in, no webhook did")


class SmsFiguresSerializer(serializers.Serializer):
    sent_today = serializers.IntegerField()
    capped_today = serializers.IntegerField(help_text="held back by a limit today")
    capped_7_days = serializers.IntegerField()
    delivery_7_days = serializers.DictField(child=serializers.IntegerField(), help_text="delivery reports by state")
    daily_cap = serializers.IntegerField()
    templates = serializers.IntegerField(help_text="approved SMS templates in the registry")


class EmailRatesSerializer(serializers.Serializer):
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    bounced = serializers.IntegerField()
    complained = serializers.IntegerField()
    bounce_rate = serializers.FloatField(allow_null=True)
    complaint_rate = serializers.FloatField(allow_null=True)
    bounce_limit = serializers.FloatField()
    complaint_limit = serializers.FloatField()


class EmailFiguresSerializer(serializers.Serializer):
    rates = EmailRatesSerializer(help_text="the last 7 days against SES's review thresholds")
    suppressed = serializers.IntegerField()
    suppressions_synced = serializers.DateTimeField(allow_null=True, help_text="SES's list last read")
    topic_restricted = serializers.BooleanField(help_text="SES_SNS_TOPIC_ARN is set")
    webhook_secret_set = serializers.BooleanField(help_text="ANYMAIL_WEBHOOK_SECRET is set")


class BucketSerializer(serializers.Serializer):
    alias = serializers.CharField()
    bucket = serializers.CharField()


class StorageFiguresSerializer(serializers.Serializer):
    buckets = BucketSerializer(many=True)
    public_domain = serializers.CharField(allow_blank=True)


class GoogleFiguresSerializer(serializers.Serializer):
    domain = serializers.CharField(allow_blank=True, help_text="STAFF_GOOGLE_DOMAIN: staff's Workspace")
    auto_staff = serializers.BooleanField()


class ErrorsFiguresSerializer(serializers.Serializer):
    host = serializers.CharField(allow_blank=True)


class ReconciliationLineSerializer(serializers.Serializer):
    date = serializers.DateField()
    state = serializers.CharField()
    differences = serializers.IntegerField()


class ErpHealthSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="ERP_ENABLED")
    waiting = serializers.IntegerField(help_text="outbox rows pending, sending or failing")
    dead = serializers.IntegerField()
    oldest_waiting_seconds = serializers.IntegerField(allow_null=True)
    last_reconciliation = ReconciliationLineSerializer(allow_null=True)
    key_present = serializers.BooleanField(help_text="the sync user's API key is held")
    webhook_secret_set = serializers.BooleanField()


class ExtraSerializer(serializers.Serializer):
    """What a provider's card adds (each key present for its provider only)."""

    webhook = RazorpayHealthSerializer(required=False)
    sms = SmsFiguresSerializer(required=False)
    email = EmailFiguresSerializer(required=False)
    storage = StorageFiguresSerializer(required=False)
    google = GoogleFiguresSerializer(required=False)
    errors = ErrorsFiguresSerializer(required=False)
    erp = ErpHealthSerializer(required=False)
    phase = serializers.CharField(required=False, help_text="WhatsApp: the phase it comes in")


class ConnectionCardSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=list(c.SPEC))
    name = serializers.CharField()
    kind = serializers.ChoiceField(choices=c.KINDS)
    status = serializers.ChoiceField(choices=c.STATUSES)
    mode = serializers.ChoiceField(choices=c.MODES, help_text="the mode in force")
    source = serializers.ChoiceField(choices=c.SOURCES, help_text="where its keys are read from")
    held = serializers.DictField(child=serializers.CharField(), help_text="the environment's keys' last characters")
    accounts = AccountRowSerializer(many=True)
    last_success_at = serializers.DateTimeField(allow_null=True)
    last_error_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)
    last_test = LastTestSerializer()
    circuit = CircuitSerializer()
    calls = CallsSerializer()
    fields = serializers.ListField(child=serializers.CharField(), help_text="the credentials Replace asks for")
    optional = serializers.ListField(child=serializers.CharField())
    modes = serializers.ListField(child=serializers.ChoiceField(choices=IntegrationAccount.Mode.choices))
    overlap_warning = serializers.CharField(allow_blank=True)
    actions = ActionsSerializer()
    extra = ExtraSerializer()


class TestResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField(allow_null=True)
    message = serializers.CharField()
    card = ConnectionCardSerializer()


class ConnectionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, help_text="why (kept in the audit log; the owners read it)")


class CredentialsSerializer(ConnectionReasonSerializer):
    mode = serializers.ChoiceField(choices=IntegrationAccount.Mode.choices)
    credentials = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=500, trim_whitespace=True),
        help_text="the provider's fields (the card's `fields`); never answered",
    )


class ModeSerializer(ConnectionReasonSerializer):
    mode = serializers.ChoiceField(choices=c.MODES)


class CircuitActionSerializer(ConnectionReasonSerializer):
    action = serializers.ChoiceField(choices=["open", "reset"])


class WebhookInfoSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=list(c.SPEC))
    url = serializers.CharField(help_text="our address, to paste at the provider")
    auth = serializers.ChoiceField(choices=["token", "signature", "basic_and_sns"])
    header = serializers.CharField(help_text="the header it sends the token or signature in")
    token = serializers.CharField(allow_blank=True, help_text="its last four characters; empty: none set")
    rotated_at = serializers.DateTimeField(allow_null=True)
    previous_valid_until = serializers.DateTimeField(allow_null=True, help_text="the previous token's last moment")
    rotatable = serializers.BooleanField()
    events_kept = serializers.BooleanField(help_text="its events are listed under events/")
    states = serializers.DictField(child=serializers.IntegerField(), help_text="the last 7 days' events by state")
    last_event_at = serializers.DateTimeField(allow_null=True)
    silence_hours = serializers.IntegerField()
    silent = serializers.BooleanField(help_text="nothing came in silence_hours while it is in use")


class RotatedSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="shown this once: paste it at the provider")
    webhooks = WebhookInfoSerializer()


class InboundEventSerializer(serializers.ModelSerializer):
    body_excerpt = serializers.SerializerMethodField(help_text="redacted: no names, phone numbers to 4 digits")

    class Meta:
        model = InboundEvent
        fields = ["id", "account", "state", "event_id", "sha256", "headers", "received_at", "processed_at", "error"]
        fields += ["body_excerpt"]
        read_only_fields = fields

    def get_body_excerpt(self, event) -> str:
        return excerpt(event.body, 600)


class ReplayFailedSerializer(serializers.Serializer):
    since = serializers.DateTimeField(help_text="every failed event received since then")

    def validate_since(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("A time in the past.")
        return value


class ReplayedSerializer(serializers.Serializer):
    replayed = serializers.IntegerField()
    more = serializers.BooleanField(help_text="more failed events wait: replay again")


class CallSerializer(serializers.ModelSerializer):
    mode = serializers.CharField(source="account.mode", read_only=True)

    class Meta:
        model = IntegrationCall
        fields = ["id", "mode", "operation", "method", "path", "status_code", "duration_ms", "provider_request_id"]
        fields += ["error", "excerpt", "created"]
        read_only_fields = fields


class FailureSerializer(serializers.ModelSerializer):
    erp_outbox = serializers.IntegerField(read_only=True, allow_null=True, help_text="the sync's dead row, if one")

    class Meta:
        model = IntegrationFailure
        fields = ["id", "account", "operation", "task_name", "args", "attempts", "last_error", "state"]
        fields += ["discard_reason", "resolved_at", "resolved_by", "created", "erp_outbox"]
        read_only_fields = fields


class DiscardSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, help_text="why it is given up (kept with it)")


# The cards and the actions


class CardsView(ConnectionView, generics.GenericAPIView):
    """One card per integration, in the page's order: is it working (connected, degraded, expired, disabled,
    not_configured), since when, test or live, where its keys come from, its calls of the day and the week."""

    permissions = {"GET": VIEW}
    pagination_class = None
    filter_backends = []
    serializer_class = ConnectionCardSerializer

    @extend_schema(operation_id="staff_connections_list", responses=ConnectionCardSerializer(many=True))
    def get(self, request, *args, **kwargs):
        return Response(ConnectionCardSerializer(c.cards(), many=True).data)


class CardView(ConnectionView, generics.GenericAPIView):
    """One integration's card (the provider's page opens on it)."""

    permissions = {"GET": VIEW}
    serializer_class = ConnectionCardSerializer

    def get(self, request, *args, **kwargs):
        return Response(ConnectionCardSerializer(c.one_card(self.spec().key)).data)


class TestView(ConnectionView, generics.GenericAPIView):
    """Test the connection with the keys in force: one harmless authenticated read (the result kept on its account,
    the call in the call log). A failed test answers 200 with ok false: the test ran."""

    permissions = {"POST": MANAGE}
    serializer_class = TestResultSerializer

    @extend_schema(request=None, responses=TestResultSerializer)
    def post(self, request, *args, **kwargs):
        _, ok, message = c.run_test(self.spec().key, request=request)
        return Response(TestResultSerializer({"ok": ok, "message": message, "card": c.one_card(self.spec().key)}).data)


class CredentialsView(ConnectionView, generics.GenericAPIView):
    """Replace one mode's credentials: tested first, in the same call, and kept only if the test passes (400 with the
    provider's answer otherwise; the old ones stay). Never answered: the card shows their last four characters."""

    permissions = {"POST": MANAGE}
    serializer_class = CredentialsSerializer

    @extend_schema(request=CredentialsSerializer, responses=TestResultSerializer)
    def post(self, request, *args, **kwargs):
        user, asked = self.human(), CredentialsSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        _, message = c.replace_credentials(
            self.spec().key, data["mode"], data["credentials"], reason=data["reason"], by=user, request=request
        )
        return Response(
            TestResultSerializer({"ok": True, "message": message, "card": c.one_card(self.spec().key)}).data
        )


class ModeView(ConnectionView, generics.GenericAPIView):
    """Off, test or live: the account of that mode used from now on (its credentials needed)."""

    permissions = {"POST": MANAGE}
    serializer_class = ModeSerializer

    @extend_schema(request=ModeSerializer, responses=ConnectionCardSerializer)
    def post(self, request, *args, **kwargs):
        user, asked = self.human(), ModeSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        c.switch_mode(self.spec().key, data["mode"], reason=data["reason"], by=user, request=request)
        return Response(ConnectionCardSerializer(c.one_card(self.spec().key)).data)


class CircuitView(ConnectionView, generics.GenericAPIView):
    """Hold the circuit open (calls wait until it is reset), or reset it (calls go through)."""

    permissions = {"POST": MANAGE}
    serializer_class = CircuitActionSerializer

    @extend_schema(request=CircuitActionSerializer, responses=ConnectionCardSerializer)
    def post(self, request, *args, **kwargs):
        user, asked = self.human(), CircuitActionSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        c.set_circuit(self.spec().key, data["action"], reason=data["reason"], by=user, request=request)
        return Response(ConnectionCardSerializer(c.one_card(self.spec().key)).data)


# Webhooks, events, calls, dead letters


class WebhooksView(ConnectionView, generics.GenericAPIView):
    """The provider's inbound webhooks: our address to paste, how it authenticates, the token's last four characters
    and its rotation (the previous one's last moment), the week's events by state, and whether it fell silent."""

    permissions = {"GET": VIEW}
    serializer_class = WebhookInfoSerializer

    def get(self, request, *args, **kwargs):
        return Response(WebhookInfoSerializer(c.webhook_info(self.spec().key)).data)


class RotateView(ConnectionView, generics.GenericAPIView):
    """A new webhook token, answered this once; the previous one is still accepted for 24 hours."""

    permissions = {"POST": MANAGE}
    serializer_class = ConnectionReasonSerializer

    @extend_schema(request=ConnectionReasonSerializer, responses=RotatedSerializer)
    def post(self, request, *args, **kwargs):
        user, asked = self.human(), ConnectionReasonSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        _, token = c.rotate_webhook(self.spec().key, reason=asked.validated_data["reason"], by=user, request=request)
        answer = {"token": token, "webhooks": c.webhook_info(self.spec().key)}
        return Response(RotatedSerializer(answer).data)


class EventFilter(django_filters.FilterSet):
    class Meta:
        model = InboundEvent
        fields = ["state"]


class EventsView(ConnectionView, generics.ListAPIView):
    """The provider's inbound events, newest first (filter state), their bodies redacted."""

    permissions = {"GET": "integrations.view_inboundevent"}
    serializer_class = InboundEventSerializer
    filterset_class = EventFilter
    queryset = InboundEvent.objects.none()

    def get_queryset(self):
        events = InboundEvent.objects.filter(provider=self.spec().key)
        return scoped(events, self.request.user, "integrations.view_inboundevent")


class EventReplayView(ConnectionView, generics.GenericAPIView):
    """Process one event again (a rejected one never)."""

    permissions = {"POST": REPLAY}
    serializer_class = InboundEventSerializer

    @extend_schema(request=None, responses=InboundEventSerializer)
    def post(self, request, *args, **kwargs):
        event = generics.get_object_or_404(InboundEvent, provider=self.spec().key, pk=self.kwargs["pk"])
        c.replay_event(self.spec().key, event, request=request)
        return Response(InboundEventSerializer(event).data)


class ReplayFailedView(ConnectionView, generics.GenericAPIView):
    """Process again every failed event received since a time (500 at a time)."""

    permissions = {"POST": REPLAY}
    serializer_class = ReplayFailedSerializer

    @extend_schema(request=ReplayFailedSerializer, responses=ReplayedSerializer)
    def post(self, request, *args, **kwargs):
        asked = ReplayFailedSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        since = asked.validated_data["since"]
        replayed, more = c.replay_failed_events(self.spec().key, since, request=request)
        return Response(ReplayedSerializer({"replayed": replayed, "more": more}).data)


class CallFilter(django_filters.FilterSet):
    failed = django_filters.BooleanFilter(method="filter_failed", label="only the calls that failed")

    class Meta:
        model = IntegrationCall
        fields = ["operation"]

    def filter_failed(self, queryset, name, value):
        return queryset.exclude(error="") if value else queryset.filter(error="")


class CallsView(ConnectionView, generics.ListAPIView):
    """The provider's outbound calls, newest first (filters operation, failed), their excerpts redacted when kept."""

    permissions = {"GET": "integrations.view_integrationcall"}
    serializer_class = CallSerializer
    filterset_class = CallFilter
    queryset = IntegrationCall.objects.none()

    def get_queryset(self):
        calls = IntegrationCall.objects.filter(account__provider=self.spec().key).select_related("account")
        return scoped(calls, self.request.user, "integrations.view_integrationcall")


def failures_of(key):
    """A provider's dead letters: its accounts', and those of its app's tasks that failed before knowing one."""
    found = Q(account__provider=key)
    if prefix := c.TASK_PREFIXES.get(key):
        found |= Q(account=None, task_name__startswith=prefix)
    failures = IntegrationFailure.objects.filter(found)
    if key == "erpnext":
        from erp.models import ErpOutbox

        rows = ErpOutbox.objects.filter(failure=OuterRef("pk")).values("pk")[:1]
        return failures.annotate(erp_outbox=Subquery(rows))
    return failures


def failure_permission(view, request):
    return "erp.replay_sync" if view.kwargs.get("provider") == "erpnext" else REPLAY


class FailureFilter(django_filters.FilterSet):
    class Meta:
        model = IntegrationFailure
        fields = ["state", "operation"]


class FailuresView(ConnectionView, generics.ListAPIView):
    """The provider's dead letters, newest first (filters state, operation)."""

    permissions = {"GET": "integrations.view_integrationfailure"}
    serializer_class = FailureSerializer
    filterset_class = FailureFilter
    queryset = IntegrationFailure.objects.none()

    def get_queryset(self):
        failures = failures_of(self.spec().key)
        return scoped(failures, self.request.user, "integrations.view_integrationfailure")


class FailureActionView(ConnectionView, generics.GenericAPIView):
    permissions = {"POST": failure_permission}

    def failure(self):
        return generics.get_object_or_404(failures_of(self.spec().key), pk=self.kwargs["pk"])


class FailureReplayView(FailureActionView):
    """Run a dead letter's task again, once (ERPNext's: the sync's own replay of its outbox row)."""

    serializer_class = FailureSerializer

    @extend_schema(request=None, responses=FailureSerializer)
    def post(self, request, *args, **kwargs):
        c.replay_failure(self.failure(), by=self.by(), request=request)
        return Response(FailureSerializer(self.failure()).data)


class FailureDiscardView(FailureActionView):
    """Give a dead letter up, with the reason."""

    serializer_class = DiscardSerializer

    @extend_schema(request=DiscardSerializer, responses=FailureSerializer)
    def post(self, request, *args, **kwargs):
        asked = DiscardSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        c.discard_failure(self.failure(), asked.validated_data["reason"], by=self.by(), request=request)
        return Response(FailureSerializer(self.failure()).data)


PROVIDER = OpenApiParameter("provider", str, OpenApiParameter.PATH, enum=list(c.SPEC))
for _view in [CardView, TestView, CredentialsView, ModeView, CircuitView, WebhooksView, RotateView, EventsView]:
    extend_schema(parameters=[PROVIDER])(_view)
for _view in [EventReplayView, ReplayFailedView, CallsView, FailuresView, FailureReplayView, FailureDiscardView]:
    extend_schema(parameters=[PROVIDER])(_view)

urlpatterns = [  # under /api/v1/staff/connections/ (staff/urls.py)
    path("", CardsView.as_view(), name="connections"),
    path("<str:provider>/", CardView.as_view(), name="connection"),
    path("<str:provider>/test/", TestView.as_view(), name="connection-test"),
    path("<str:provider>/credentials/", CredentialsView.as_view(), name="connection-credentials"),
    path("<str:provider>/mode/", ModeView.as_view(), name="connection-mode"),
    path("<str:provider>/circuit/", CircuitView.as_view(), name="connection-circuit"),
    path("<str:provider>/webhooks/", WebhooksView.as_view(), name="connection-webhooks"),
    path("<str:provider>/webhooks/rotate/", RotateView.as_view(), name="connection-webhooks-rotate"),
    path("<str:provider>/events/", EventsView.as_view(), name="connection-events"),
    path("<str:provider>/events/replay-failed/", ReplayFailedView.as_view(), name="connection-events-replay-failed"),
    path("<str:provider>/events/<int:pk>/replay/", EventReplayView.as_view(), name="connection-event-replay"),
    path("<str:provider>/calls/", CallsView.as_view(), name="connection-calls"),
    path("<str:provider>/failures/", FailuresView.as_view(), name="connection-failures"),
    path("<str:provider>/failures/<int:pk>/replay/", FailureReplayView.as_view(), name="connection-failure-replay"),
    path("<str:provider>/failures/<int:pk>/discard/", FailureDiscardView.as_view(), name="connection-failure-discard"),
]
