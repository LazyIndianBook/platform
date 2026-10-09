"""The staff API, /api/v1/staff/ (API.md "Staff API"): what the Admin Control Panel draws and does. Every endpoint is a
StaffView: the panel's session or an API key (staff.permissions), the permission it names for each action, a
re-authentication for high and critical ones, its querysets through `scoped()`, cursor pages, per-staff throttles,
`Cache-Control: no-store`. Actions write the audit log (staff.audit) and, where research 1.5 says so, wait for a
second person (staff.approvals)."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

from allauth.account import app_settings as account_settings
from allauth.account.authentication import get_authentication_records
from django.conf import settings
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters import rest_framework as django_filters  # its BooleanFilter takes 1 and 0 too
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import exceptions, generics, mixins, pagination, permissions, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts import roles
from api.views import ReauthenticationRequired, exception_handler, recently_authenticated
from examleaf.middleware import absolute_expiry, idle_limit

from . import approvals, audit, catalogue, jobs, services
from . import serializers as s
from .backends import scoped, staff_scopes
from .config import FLAG_KEY, SETTINGS, changed, environment_value, feature_flags, site_setting
from .models import (
    ApiKey,
    AuditEvent,
    ChangeRequest,
    DataRequest,
    FeatureFlag,
    InboxItem,
    Incident,
    Job,
    ProcessorRecord,
    RoleGrant,
    SavedView,
    SiteSetting,
    StaffInvite,
    StaffScope,
)
from .permissions import ANY_STAFF, ApiKeyAuthentication, IsStaff, StaffPermission, StaffThrottle, make_key
from .privacy import erasure_report, mask_email, response_text

User = get_user_model()
IDEMPOTENCY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, description="once per request")


class Cursor(pagination.CursorPagination):
    """Newest first; `?cursor=` from `next`/`previous`; `?page_size=` up to 200."""

    page_size, page_size_query_param, max_page_size, ordering = 50, "page_size", 200, "-pk"


class StaffView:
    """The staff API's rules for one view. `permissions` maps an action (a viewset's) or a method (a plain view) to
    the permission it needs (or a callable giving it); what is not mapped is refused."""

    authentication_classes = [ApiKeyAuthentication, SessionAuthentication]  # first: 401 + WWW-Authenticate: Api-Key
    permission_classes = [IsStaff, StaffPermission]
    throttle_classes = [StaffThrottle]
    throttle_scope = "staff"
    throttle_scopes = {}  # an action's own scope (staff_search, staff_reveal …)
    pagination_class = Cursor
    filter_backends = [DjangoFilterBackend]
    permissions = {}
    reauth = ()  # actions that always need a re-authentication (approving, running)
    no_reauth = ()  # actions that never do (ending an impersonation)

    def required_permission(self, request):
        name = getattr(self, "action", None)
        perm = self.permissions[name] if name in self.permissions else self.permissions.get(request.method)
        return perm(self, request) if callable(perm) else perm

    def object_permission(self, request, obj):
        perm = self.required_permission(request)
        return None if perm == ANY_STAFF else perm

    def get_throttles(self):
        self.throttle_scope = self.throttle_scopes.get(getattr(self, "action", None), self.throttle_scope)
        return super().get_throttles()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def get_exception_handler(self):
        return coded

    def human(self):
        """The signed-in member of staff (API keys are refused here)."""
        if isinstance(self.request.auth, ApiKey):
            raise exceptions.PermissionDenied("Not with an API key.")
        return self.request.user


REAUTH_FLOWS = [{"id": "reauthenticate"}, {"id": "mfa_reauthenticate"}]  # allauth.headless's, to step up with


def coded(exc, context):
    """The API's error answer, with a `code` beside `detail` (permission_denied, not_found, not_authenticated,
    throttled …) where DRF gave only the text, and a step-up's `flows`: the panel reacts to codes, never to wording."""
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, exceptions.APIException) and isinstance(response.data, dict):
        if set(response.data) == {"detail"} and isinstance(exc.detail, str):
            response.data["code"] = exc.get_codes()
        if isinstance(exc, ReauthenticationRequired):
            response.data["flows"] = REAUTH_FLOWS
    return response


def require_reauth(request, perm):
    if catalogue.needs_reauth(perm) and not recently_authenticated(request):
        raise ReauthenticationRequired()


def accepted(change_request, view):
    """201/200 when it ran (or was asked before), 202 while it waits for approval, 400 when it failed."""
    data = s.ChangeRequestSerializer(change_request, context=view.get_serializer_context()).data
    if change_request.status == ChangeRequest.Status.FAILED:
        return Response({**data, "detail": change_request.result.get("error", "")}, status=status.HTTP_400_BAD_REQUEST)
    if change_request.status == ChangeRequest.Status.PENDING:
        return Response(data, status=status.HTTP_202_ACCEPTED)
    return Response(data, status=status.HTTP_200_OK)


# The session's manifest and the catalogue


def reauth_valid_until(request):
    records = get_authentication_records(request)
    if not records:
        return None
    until = records[-1]["at"] + account_settings.REAUTHENTICATION_TIMEOUT
    return datetime.fromtimestamp(until, UTC) if until > time.time() else None


IMPERSONATION = "staff:impersonation"  # the panel's session, while its member of staff is logged in as a customer


def impersonating(request):
    """{user_id, email (masked), until} while this session's impersonation token is valid, else None."""
    current = request.session.get(IMPERSONATION)
    until = parse_datetime(current["until"]) if current else None
    if until is None or until <= timezone.now():
        return None
    user = User.objects.filter(pk=current["user"]).only("email").first()
    return {"user_id": current["user"], "email": mask_email(user.email) if user else "", "until": until}


def manifest(request):
    """Research 1.7: what the panel may draw for this person (it decides nothing: every call is checked again)."""
    user = request.user
    names = sorted(services.staff_roles(user))
    grants = {grant.role: grant for grant in RoleGrant.objects.filter(user=user)}
    body = {
        "roles": [
            {
                "name": name,
                "expires_at": grants[name].expires_at if name in grants else None,
                "granted_by": grants[name].granted_by_id if name in grants else None,
            }
            for name in names
        ],
        "permissions": sorted(user.get_all_permissions()),
        "scopes": {kind: sorted(values) for kind, values in staff_scopes(user).items()},
        "role_scopes": {name: roles.ROLE_SCOPES[name] for name in names if name in roles.ROLE_SCOPES},
        # a break-glass account has none (staff.approvals.limit_of)
        "limits": {name: None if user.is_superuser else roles.limit(names, name) for name in roles.LIMITS},
        "flags": {**feature_flags(), **({"test_mode": True} if settings.STAFF_TEST_MODE else {})},
    }
    version = hashlib.sha256(json.dumps(audit.plain(body), sort_keys=True).encode()).hexdigest()[:16]
    return {
        "user": {"id": user.pk, "email": user.email, "full_name": user.full_name, "is_superuser": user.is_superuser},
        **body,
        "reauth_valid_until": reauth_valid_until(request),
        "idle_timeout_s": idle_limit(user),
        "absolute_expires_at": absolute_expiry(request.session),
        "impersonating": impersonating(request),
        "manifest_version": version,
    }


MANIFEST = inline_serializer(
    "StaffManifest",
    {
        "user": inline_serializer(
            "StaffUser",
            {
                "id": serializers.IntegerField(),
                "email": serializers.EmailField(),
                "full_name": serializers.CharField(),
                "is_superuser": serializers.BooleanField(),
            },
        ),
        "roles": serializers.ListField(child=serializers.DictField(), help_text="name, expires_at, granted_by"),
        "permissions": serializers.ListField(child=serializers.CharField(), help_text="app_label.codename, sorted"),
        "scopes": serializers.DictField(child=serializers.ListField(child=serializers.CharField())),
        "role_scopes": serializers.DictField(child=serializers.DictField()),
        "limits": serializers.DictField(child=serializers.IntegerField(allow_null=True), help_text="null: none"),
        "flags": serializers.DictField(
            child=serializers.JSONField(), help_text="the feature flags; test_mode: true when not production"
        ),
        "reauth_valid_until": serializers.DateTimeField(allow_null=True),
        "idle_timeout_s": serializers.IntegerField(),
        "absolute_expires_at": serializers.DateTimeField(),
        "impersonating": inline_serializer(
            "StaffImpersonating",
            {
                "user_id": serializers.IntegerField(),
                "email": serializers.CharField(),
                "until": serializers.DateTimeField(),
            },
            allow_null=True,
        ),
        "manifest_version": serializers.CharField(help_text="changes when anything above changes: fetch again"),
    },
)


class SessionView(StaffView, generics.GenericAPIView):
    """The capability manifest of the signed-in member of staff (`Cache-Control: no-store`): roles with expiry,
    permissions, scopes, limits, flags, the re-authentication window, the idle and absolute limits. Fetch it again
    after any 403 and whenever `manifest_version` changes."""

    permissions = {"GET": ANY_STAFF}
    pagination_class = None

    @extend_schema(responses=MANIFEST)
    def get(self, request, *args, **kwargs):
        self.human()
        return Response(manifest(request))


CATALOGUE = inline_serializer(
    "StaffCatalogue",
    {
        "permissions": serializers.ListField(child=serializers.DictField(), help_text="perm, label, area, risk …"),
        "roles": serializers.ListField(child=serializers.DictField(), help_text="name, permissions, limits …"),
    },
)


class CatalogueView(StaffView, generics.GenericAPIView):
    """Every catalogued permission (label, area, risk, what it triggers) and every role (its permissions, limits,
    scopes, separation-of-duty conflicts, members): the role catalogue page and the "Needs: …" tooltips."""

    permissions = {"GET": ANY_STAFF}
    pagination_class = None

    @extend_schema(responses=CATALOGUE)
    def get(self, request, *args, **kwargs):
        names = [
            f"{app}.{codename}"
            for app, codename in Permission.objects.values_list("content_type__app_label", "codename")
        ]
        entries = [entry.as_dict() for name in sorted(names) if (entry := catalogue.entry(name))]
        members = dict(Group.objects.filter(name__in=roles.ROLES).annotate(n=Count("user")).values_list("name", "n"))
        role_rows = [
            {
                "name": name,
                "permissions": wanted
                if isinstance(wanted, list)
                else {"__all__": "all", "__everything__": "everything"}[wanted],
                "limits": roles.ROLE_LIMITS.get(name, {}),
                "scopes": roles.ROLE_SCOPES.get(name, {}),
                "conflicts": sorted({b if a == name else a for a, b in roles.SOD_CONFLICTS if name in (a, b)}),
                "privileged": name in roles.PRIVILEGED_ROLES,
                "admin_site": name in roles.ADMIN_SITE_ROLES,
                "members": members.get(name, 0),
            }
            for name, wanted in roles.ROLES.items()
        ]
        return Response({"permissions": entries, "roles": role_rows})


# The inbox


class InboxFilter(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(choices=InboxItem.Kind.choices)
    done = django_filters.BooleanFilter(method="filter_done", help_text="true: the items done")
    mine = django_filters.BooleanFilter(method="filter_mine", help_text="true: assigned to me")
    snoozed = django_filters.BooleanFilter(method="filter_snoozed", help_text="true: the snoozed ones too")

    class Meta:
        model = InboxItem
        fields = ["kind"]

    def filter_done(self, queryset, name, value):
        return queryset.filter(done_at__isnull=not value)

    def filter_mine(self, queryset, name, value):
        return queryset.filter(assignee=self.request.user) if value else queryset

    def filter_snoozed(self, queryset, name, value):
        return queryset

    def filter_queryset(self, queryset):
        data = self.form.cleaned_data if self.is_bound and self.form.is_valid() else {}
        if not data.get("done"):
            queryset = queryset.filter(done_at=None)
        if not data.get("snoozed"):
            queryset = queryset.filter(Q(snoozed_until=None) | Q(snoozed_until__lte=timezone.now()))
        return super().filter_queryset(queryset)


class InboxViewSet(StaffView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """What waits for this person: items assigned to them, or to nobody and needing a permission they hold (open,
    not snoozed, unless the filters say)."""

    serializer_class = s.InboxItemSerializer
    filterset_class = InboxFilter
    permissions = dict.fromkeys(["list", "count", "done", "snooze", "assign"], "staff.view_inbox")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InboxItem.objects.none()
        user = self.request.user
        items = scoped(InboxItem.objects.all(), user, "staff.view_inbox")
        if user.is_superuser:
            return items
        return items.filter(Q(assignee=user) | Q(assignee=None, permission__in=user.get_all_permissions()))

    def filter_queryset(self, queryset):  # the list's filters (open, not snoozed) never hide an item acted on
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    @extend_schema(responses=s.InboxCountSerializer)
    @action(detail=False, pagination_class=None, filter_backends=[])
    def count(self, request, *args, **kwargs):
        items = self.get_queryset().filter(done_at=None)
        items = items.filter(Q(snoozed_until=None) | Q(snoozed_until__lte=timezone.now()))
        return Response({"open": items.count(), "overdue": items.filter(due_at__lt=timezone.now()).count()})

    @extend_schema(request=None, responses=s.InboxItemSerializer)
    @action(detail=True, methods=["post"])
    def done(self, request, *args, **kwargs):
        item = self.get_object()
        item.done_at, item.done_by = item.done_at or timezone.now(), item.done_by or request.user
        item.save(update_fields=["done_at", "done_by"])
        return Response(self.get_serializer(item).data)

    @extend_schema(request=s.SnoozeSerializer, responses=s.InboxItemSerializer)
    @action(detail=True, methods=["post"])
    def snooze(self, request, *args, **kwargs):
        item = self.get_object()
        data = s.SnoozeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item.snoozed_until = data.validated_data["until"]
        item.save(update_fields=["snoozed_until"])
        return Response(self.get_serializer(item).data)

    @extend_schema(request=s.AssignSerializer, responses=s.InboxItemSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, *args, **kwargs):
        item = self.get_object()
        data = s.AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        assignee = None
        if (pk := data.validated_data["assignee"]) is not None:
            assignee = User.objects.filter(pk=pk, is_active=True, is_staff=True).first()
            if assignee is None or not assignee.has_perm(item.permission):
                raise serializers.ValidationError({"assignee": ["A member of staff who may act on it."]})
        item.assignee = assignee
        item.save(update_fields=["assignee"])
        return Response(self.get_serializer(item).data)


# The audit log


class AuditFilter(django_filters.FilterSet):
    actor = django_filters.NumberFilter(field_name="actor_id")
    action = django_filters.CharFilter(help_text="exact")
    action_prefix = django_filters.CharFilter(field_name="action", lookup_expr="startswith", help_text="e.g. order.")
    since = django_filters.IsoDateTimeFilter(field_name="ts", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="ts", lookup_expr="lt")
    change_request = django_filters.NumberFilter(field_name="change_request_id")

    class Meta:
        model = AuditEvent
        fields = ["actor_type", "target_type", "target_id", "outcome", "request_id", "ip", "chain", "permission"]
        fields += ["break_glass"]


FILTER_NAMES = ["actor", "action", "action_prefix", "since", "until", "change_request", *AuditFilter.Meta.fields]


def audit_filter(filters, queryset):
    """The audit log's events matching `filters` (the list's query parameters), every one of them valid and known:
    an export never widens because of a typo."""
    unknown = sorted(set(filters) - set(FILTER_NAMES))
    filterset = AuditFilter({name: value for name, value in filters.items() if value not in (None, "")}, queryset)
    if unknown or not filterset.is_valid():
        errors = {name: ["Not a filter of the audit log."] for name in unknown}
        raise serializers.ValidationError({"filters": {**errors, **filterset.errors}})
    return filterset.qs


INLINE_EXPORT_ROWS = 5_000  # more: a background job (staff.jobs), its file linked when done


class ExportSerializer(serializers.Serializer):
    filters = serializers.DictField(required=False, default=dict, help_text="the list's filters")


class AuditViewSet(StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Search the audit log (AUDITOR and OWNER: staff.view_auditlog); each read is itself recorded (`audit.read`).
    `export/` gives JSON lines (with the hashes, so a copy can be checked) up to 5,000 rows within your export limit;
    more is a background job (`jobs/`), which ADMIN approves first above your limit."""

    serializer_class = s.AuditEventSerializer
    filterset_class = AuditFilter
    permissions = {"list": "staff.view_auditlog", "retrieve": "staff.view_auditlog", "export": "staff.export_auditlog"}
    throttle_scopes = {"export": "staff_export"}

    def get_queryset(self):
        return scoped(AuditEvent.objects.all(), self.request.user, "staff.view_auditlog")

    def list(self, request, *args, **kwargs):
        query = {name: request.query_params.get(name) for name in FILTER_NAMES if name in request.query_params}
        audit.record("audit.read", request=request, details={"filters": query})
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        event = self.get_object()
        audit.record("audit.read", request=request, target=("staff.auditevent", event.pk, f"Audit event #{event.pk}"))
        return Response(self.get_serializer(event).data)

    @extend_schema(
        request=ExportSerializer,
        responses={
            (200, "application/x-ndjson"): OpenApiResponse(OpenApiTypes.STR, description="one event per line"),
            202: s.JobSerializer,
        },
    )
    @action(detail=False, methods=["post"], pagination_class=None, filter_backends=[])
    def export(self, request, *args, **kwargs):
        user = self.human()
        data = ExportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        filters = data.validated_data["filters"]
        events = audit_filter(filters, self.get_queryset()).order_by("id")
        rows = events.count()
        limit = approvals.limit_of(user, "export_rows")
        if rows > INLINE_EXPORT_ROWS or approvals.over(rows, limit, "{amount} {limit}"):
            job = jobs.start(Job.Kind.AUDIT_EXPORT, {"filters": filters}, user=user, request=request)
            return Response(s.JobSerializer(job, context=self.get_serializer_context()).data, status=202)
        audit.record(
            "audit.exported", request=request, details={"filters": filters, "rows": rows, "heads": audit.heads()}
        )

        def lines():
            for event in events.iterator():
                yield json.dumps(audit.export_row(event), sort_keys=True, ensure_ascii=False) + "\n"

        response = StreamingHttpResponse(lines(), content_type="application/x-ndjson")
        response["Content-Disposition"] = f'attachment; filename="audit-{timezone.localdate():%Y%m%d}.jsonl"'
        return response


# Approvals


class ChangeRequestFilter(django_filters.FilterSet):
    mine = django_filters.BooleanFilter(method="filter_mine", help_text="true: the ones I asked for")
    awaiting = django_filters.BooleanFilter(method="filter_awaiting", help_text="true: waiting for someone like me")

    class Meta:
        model = ChangeRequest
        fields = ["status", "action"]

    def filter_mine(self, queryset, name, value):
        return queryset.filter(maker=self.request.user) if value else queryset

    def filter_awaiting(self, queryset, name, value):
        if not value:
            return queryset
        user = self.request.user
        mine = [name for name, item in approvals.ACTIONS.items() if user.has_perm(item.checker)]
        return queryset.filter(status=ChangeRequest.Status.PENDING, action__in=mine).exclude(maker=user)


class ChangeRequestViewSet(StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Maker-checker. POST asks (with an Idempotency-Key header): within your limits it runs at once (201), above
    them it waits (202). approve/ sends back the payload's hash you read; execute/ runs the stored payload once (its
    maker or a checker). Every member of staff with staff.view_changerequest sees them (the payloads name orders,
    products and accounts by number or id, no one's details); `?awaiting=true` lists those you may approve."""

    serializer_class = s.ChangeRequestSerializer
    filterset_class = ChangeRequestFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve", "approve", "reject", "execute"], "staff.view_changerequest"),
        "create": "staff.add_changerequest",
    }
    reauth = ("approve", "execute")
    throttle_scopes = dict.fromkeys(["create", "approve", "execute"], "staff_money")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChangeRequest.objects.none()
        changes = ChangeRequest.objects.prefetch_related("approvals")
        return scoped(changes, self.request.user, "staff.view_changerequest")

    @extend_schema(
        request=s.AskSerializer,
        responses={200: s.ChangeRequestSerializer, 201: s.ChangeRequestSerializer, 202: s.ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def create(self, request, *args, **kwargs):
        user = self.human()
        data = s.AskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        name = data.validated_data["action"]
        require_reauth(request, approvals.ACTIONS[name].maker)
        change_request, created = approvals.ask(
            name,
            maker=user,
            target=data.validated_data["target"],
            payload=data.validated_data["payload"],
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        response = accepted(change_request, self)
        if created and response.status_code == status.HTTP_200_OK:
            response.status_code = status.HTTP_201_CREATED
        return response

    @extend_schema(request=s.ApproveSerializer, responses=s.ChangeRequestSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        change_request, user = self.get_object(), self.human()
        checker = approvals.ACTIONS[change_request.action].checker_for(change_request)
        if not user.has_perm(checker):  # before reading the body: who may not approve learns nothing more
            raise exceptions.PermissionDenied(f"Needs {checker}.")
        data = s.ApproveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request = approvals.approve(change_request, user=user, request=request, **data.validated_data)
        return Response(self.get_serializer(change_request).data)

    @extend_schema(request=s.CommentSerializer, responses=s.ChangeRequestSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, *args, **kwargs):
        change_request, user = self.get_object(), self.human()
        checker = approvals.ACTIONS[change_request.action].checker_for(change_request)
        if user.pk != change_request.maker_id and not user.has_perm(checker):
            raise exceptions.PermissionDenied(f"Needs {checker} (or to be its maker).")
        data = s.CommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request = approvals.reject(change_request, user=user, request=request, **data.validated_data)
        return Response(self.get_serializer(change_request).data)

    @extend_schema(request=None, responses={200: s.ChangeRequestSerializer, 400: s.ChangeRequestSerializer})
    @action(detail=True, methods=["post"])
    def execute(self, request, *args, **kwargs):
        user, change_request = self.human(), self.get_object()
        item = approvals.ACTIONS[change_request.action]
        if user.pk != change_request.maker_id and not user.has_perm(item.checker_for(change_request)):
            raise exceptions.PermissionDenied(f"Needs {item.checker_for(change_request)} (or to be its maker).")
        return accepted(approvals.execute(change_request, by=user, request=request), self)


# Background jobs


def job_permission(view, request):
    """POST jobs/: the job's own permission, the single action's (staff.jobs.permission); staff.add_job while the
    body names no kind or action that exists (the answer is then 400)."""
    data = getattr(request, "data", None)
    data = data if isinstance(data, dict) else {}
    return jobs.permission(data.get("kind"), data.get("params")) or "staff.add_job"


class JobFilter(django_filters.FilterSet):
    mine = django_filters.BooleanFilter(method="filter_mine", help_text="true: the jobs I started")

    class Meta:
        model = Job
        fields = ["state", "kind"]

    def filter_mine(self, queryset, name, value):
        return queryset.filter(started_by=self.request.user) if value else queryset


class JobViewSet(StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Background work (staff.jobs): POST starts an audit-log export or a bulk action (202, the job; above your limit
    `change_request_id`: an approver passes it first); poll it for `state`, `done` of `total` and the rows' `errors`;
    `result_url` (yours only) links its file for 5 minutes; cancel/ stops it (yours only). You see the jobs you
    started; whoever holds staff.view_system (ADMIN, the owners, AUDITOR) sees everyone's, without their files."""

    serializer_class = s.JobSerializer
    filterset_class = JobFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve", "result", "cancel"], "staff.view_job"),
        "create": job_permission,
    }
    throttle_scopes = {"create": "staff_export"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or isinstance(self.request.auth, ApiKey):
            return Job.objects.none()  # (an API key starts none)
        user = self.request.user
        queryset = scoped(Job.objects.all(), user, "staff.view_job")
        if self.action in ("cancel", "result") or not user.has_perm("staff.view_system"):
            return queryset.filter(started_by=user)
        return queryset

    @extend_schema(request=s.JobStartSerializer, responses={202: s.JobSerializer})
    def create(self, request, *args, **kwargs):
        user = self.human()
        data = s.JobStartSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        job = jobs.start(**data.validated_data, user=user, request=request)
        return Response(self.get_serializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses=s.JobSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        job = jobs.cancel(self.get_object(), user=self.human(), request=request)
        return Response(self.get_serializer(job).data)

    @extend_schema(
        parameters=[OpenApiParameter("token", str, description="from result_url")],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 302: None},
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def result(self, request, *args, **kwargs):
        """The job's file, through the link in `result_url`: for its starter, within 5 minutes of the link."""
        job, user = self.get_object(), self.human()
        if not jobs.check_link(job, user, request.query_params.get("token", "")):
            raise exceptions.PermissionDenied(
                {"detail": "This link has expired: read the job again for a new one.", "code": "link_expired"}
            )
        if not job.result_file:
            raise exceptions.NotFound("Its file is gone (kept a week).")
        audit.record("job.result_downloaded", request=request, target=job)
        if not isinstance(default_storage, FileSystemStorage):  # the bucket's own link, signed for 5 minutes
            return HttpResponseRedirect(default_storage.url(job.result_file))
        name = job.result_file.rsplit("/", 1)[-1]
        return FileResponse(default_storage.open(job.result_file, "rb"), as_attachment=True, filename=name)


# Saved views


class SavedViewViewSet(StaffView, viewsets.ModelViewSet):
    """A person's saved lists: their own, and those shared with a role they hold (read-only to the others)."""

    serializer_class = s.SavedViewSerializer
    filterset_fields = ["list_key"]
    permissions = {
        "list": "staff.view_savedview",
        "retrieve": "staff.view_savedview",
        "create": "staff.add_savedview",
        "update": "staff.change_savedview",
        "partial_update": "staff.change_savedview",
        "destroy": "staff.delete_savedview",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedView.objects.none()
        user = self.request.user
        views = scoped(SavedView.objects.all(), user, "staff.view_savedview")
        if self.action not in ("list", "retrieve"):
            return views.filter(owner=user)
        return views.filter(Q(owner=user) | Q(role__in=services.staff_roles(user), role__gt=""))

    def perform_create(self, serializer):
        serializer.save(owner=self.human())


# Site settings and feature flags


def setting_rows(key):
    return SiteSetting.objects.filter(key=key).order_by("-effective_from", "-pk")


def describe_setting(key):
    spec, now = SETTINGS[key], timezone.now()
    current = setting_rows(key).filter(effective_from__lte=now).first()
    in_db = current is not None and current.value is not None
    upcoming = setting_rows(key).filter(effective_from__gt=now).order_by("effective_from")
    kind = spec.kind if isinstance(spec.kind, list) else spec.kind.__name__
    return {
        "key": key,
        "label": spec.label,
        "kind": kind,
        "permission": spec.permission,
        "value": site_setting(key),
        "environment": environment_value(key),
        "source": "database" if in_db else "environment",
        "effective_from": current.effective_from if current else None,
        "changed_by": current.changed_by_id if current else None,
        "reason": current.reason if current else "",
        "scheduled": [{"value": row.value, "effective_from": row.effective_from} for row in upcoming],
    }


class SettingsView(StaffView, generics.GenericAPIView):
    """The site's switches: what is in effect, the environment's value, where it comes from, changes to come."""

    permissions = {"GET": "staff.view_sitesetting"}
    queryset = SiteSetting.objects.none()  # (for the schema)
    serializer_class = s.SettingSerializer
    pagination_class = None

    @extend_schema(responses=s.SettingSerializer(many=True))
    def get(self, request, *args, **kwargs):
        return Response([describe_setting(key) for key in SETTINGS])


def setting_permission(view, request):
    key = view.kwargs.get("key", "")
    if request.method == "GET":
        return "staff.view_sitesetting"
    return SETTINGS[key].permission if key in SETTINGS else "staff.manage_settings"


class SettingView(StaffView, generics.GenericAPIView):
    """One switch: GET its history (every row); PUT a new value from now or from `effective_from` (null: back to
    the environment's). SHOP_OPEN, SHOP_COD_ENABLED, PARENTAL_CONSENT_MODE and WEB_COURSE need
    staff.manage_settings; MAINTENANCE_MODE and MAINTENANCE_BANNER staff.toggle_maintenance."""

    permissions = {"GET": setting_permission, "PUT": setting_permission}
    queryset = SiteSetting.objects.none()
    serializer_class = s.SwitchChangeSerializer
    pagination_class = None

    def key(self):
        key = self.kwargs["key"]
        if key not in SETTINGS:
            raise exceptions.NotFound("No such setting.")
        return key

    @extend_schema(operation_id="staff_setting_history", responses=s.SwitchRowSerializer(many=True))
    def get(self, request, *args, **kwargs):
        return Response(s.SwitchRowSerializer(setting_rows(self.key()), many=True).data)

    @extend_schema(request=s.SwitchChangeSerializer, responses=s.SettingSerializer)
    def put(self, request, *args, **kwargs):
        key, user = self.key(), self.human()
        data = s.SwitchChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            value = SETTINGS[key].check(data.validated_data["value"])
        except ValueError as error:
            raise serializers.ValidationError({"value": [str(error)]}) from error
        before = site_setting(key)
        with transaction.atomic():
            row = SiteSetting.objects.create(
                key=key,
                value=value,
                changed_by=user,
                reason=data.validated_data["reason"],
                effective_from=data.validated_data.get("effective_from") or timezone.now(),
            )
            audit.record(
                "setting.changed",
                request=request,
                target=("staff.sitesetting", row.pk, key),
                reason=row.reason,
                changes={key: [before, value]},
                details={"setting": key, "effective_from": row.effective_from},
            )
            if key == "MAINTENANCE_MODE" and value:
                audit.alert("Maintenance mode switched on", f"By user #{user.pk}. Reason: {row.reason}")
        changed(SiteSetting)
        return Response(describe_setting(key))


class FlagsView(StaffView, generics.GenericAPIView):
    """Every feature flag that has a value, as it stands now."""

    permissions = {"GET": "staff.view_featureflag"}
    queryset = FeatureFlag.objects.none()
    serializer_class = s.FlagSerializer
    pagination_class = None

    @extend_schema(responses=s.FlagSerializer(many=True))
    def get(self, request, *args, **kwargs):
        now, rows = timezone.now(), {}
        for row in FeatureFlag.objects.filter(effective_from__lte=now).order_by("key", "-effective_from", "-pk"):
            rows.setdefault(row.key, row)
        flags = [
            {
                "key": key,
                "value": row.value,
                "effective_from": row.effective_from,
                "changed_by": row.changed_by_id,
                "reason": row.reason,
            }
            for key, row in sorted(rows.items())
        ]
        return Response(flags)


class FlagView(StaffView, generics.GenericAPIView):
    """One flag: GET its history; PUT a new value (true/false or any JSON; null: off) from now or `effective_from`."""

    permissions = {"GET": "staff.view_featureflag", "PUT": "staff.manage_flags"}
    queryset = FeatureFlag.objects.none()
    serializer_class = s.SwitchChangeSerializer
    pagination_class = None

    def key(self):
        key = self.kwargs["key"]
        if not FLAG_KEY.fullmatch(key):
            raise exceptions.NotFound("A flag's key: capitals, digits and _, e.g. ERP_SYNC_ORDERS.")
        return key

    @extend_schema(operation_id="staff_flag_history", responses=s.SwitchRowSerializer(many=True))
    def get(self, request, *args, **kwargs):
        rows = FeatureFlag.objects.filter(key=self.key()).order_by("-effective_from", "-pk")
        return Response(s.SwitchRowSerializer(rows, many=True).data)

    @extend_schema(request=s.SwitchChangeSerializer, responses=s.SwitchRowSerializer)
    def put(self, request, *args, **kwargs):
        key, user = self.key(), self.human()
        data = s.SwitchChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        value, before = data.validated_data["value"], feature_flags().get(key)
        with transaction.atomic():
            row = FeatureFlag.objects.create(
                key=key,
                value=value,
                changed_by=user,
                reason=data.validated_data["reason"],
                effective_from=data.validated_data.get("effective_from") or timezone.now(),
            )
            audit.record(
                "flag.changed",
                request=request,
                target=("staff.featureflag", row.pk, key),
                reason=row.reason,
                changes={key: [before, value]},
                details={"flag": key, "effective_from": row.effective_from},
            )
        changed(FeatureFlag)
        return Response(s.SwitchRowSerializer(row).data)


# API keys


class ApiKeyViewSet(
    StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Integrations' keys (OWNER: staff.manage_api_keys; ADMIN and AUDITOR see them): made with view permissions
    only, shown once, for 12 months at most, optionally from some addresses; revoked at once."""

    serializer_class = s.ApiKeySerializer
    permissions = {
        "list": "staff.view_apikey",
        "retrieve": "staff.view_apikey",
        "create": "staff.manage_api_keys",
        "revoke": "staff.manage_api_keys",
    }

    def get_queryset(self):
        return scoped(ApiKey.objects.all(), self.request.user, "staff.view_apikey")

    def perform_create(self, serializer):
        user = self.human()
        key, prefix, digest = make_key()
        expires_at = serializer.validated_data.get("expires_at") or timezone.now() + timedelta(days=365)
        sponsor = serializer.validated_data.get("sponsor") or user
        with transaction.atomic():
            api_key = serializer.save(
                prefix=prefix, secret_hash=digest, created_by=user, sponsor=sponsor, expires_at=expires_at
            )
            audit.record(
                "authn_token_created",
                request=self.request,
                target=api_key,
                details={
                    "name": api_key.name,
                    "scopes": api_key.scopes,
                    "expires_at": expires_at,
                    "sponsor": sponsor.pk,
                },
            )
            audit.alert(f"API key {prefix} made", f"By user #{user.pk} for {api_key.name}: {api_key.scopes}")
        api_key.whole_key = key  # in this answer only

    @extend_schema(request=None, responses=s.ApiKeySerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, *args, **kwargs):
        api_key = self.get_object()
        if api_key.revoked_at is None:
            with transaction.atomic():
                api_key.revoked_at, api_key.revoked_by = timezone.now(), self.human()
                api_key.save(update_fields=["revoked_at", "revoked_by"])
                audit.record("authn_token_revoked", request=request, target=api_key)
        return Response(self.get_serializer(api_key).data)


# Staff (people/)


ROLE = OpenApiParameter("role", str, OpenApiParameter.PATH, enum=sorted(roles.STAFF_ROLES))
SCOPE = OpenApiParameter("scope", int, OpenApiParameter.PATH)
INVITE = OpenApiParameter("invite", int, OpenApiParameter.PATH)


def staff_members():
    return User.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(groups__name__in=roles.STAFF_ROLES)
    ).distinct()


class PeopleViewSet(StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The staff: their roles (with who gave them, why, until when), scopes and second factor. Invitations, roles
    (a privileged one, or one for yourself, waits for a second person; SSD refused), scopes, sessions ended, and
    offboarding in one step (staff.services.offboard). Only a superuser changes a superuser."""

    serializer_class = s.PersonSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "invites"], "staff.view_staff"),
        **dict.fromkeys(["invite", "grant_role", "revoke_role", "add_scope", "remove_scope"], "staff.assign_role"),
        **dict.fromkeys(["end_sessions", "offboard"], "staff.assign_role"),
        "revoke_invite": "staff.assign_role",
        "reset_mfa": "staff.reset_user_mfa",
    }
    throttle_scopes = dict.fromkeys(["invite", "grant_role", "offboard"], "staff_money")

    def get_queryset(self):
        members = staff_members().prefetch_related("groups", "role_grants", "staff_scopes").order_by("pk")
        return scoped(members, self.request.user, "staff.view_staff")

    def target(self):
        person = self.get_object()
        services.can_manage(self.human(), person)
        return person

    @extend_schema(
        request=s.InviteSerializer,
        responses={201: s.StaffInviteSerializer, 202: s.ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    @action(detail=False, methods=["post"])
    def invite(self, request, *args, **kwargs):
        user = self.human()
        data = s.InviteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request, _ = approvals.ask(
            "staff.invite",
            maker=user,
            target=None,
            payload={"email": data.validated_data["email"], "role": data.validated_data["role"]},
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        if change_request.status == ChangeRequest.Status.EXECUTED:
            invite = StaffInvite.objects.get(pk=change_request.result["invite"])
            return Response(s.StaffInviteSerializer(invite).data, status=status.HTTP_201_CREATED)
        return accepted(change_request, self)

    @extend_schema(responses=s.StaffInviteSerializer(many=True))
    @action(detail=False)
    def invites(self, request, *args, **kwargs):
        page = self.paginate_queryset(scoped(StaffInvite.objects.all(), request.user, "staff.view_staffinvite"))
        return self.get_paginated_response(s.StaffInviteSerializer(page, many=True).data)

    @extend_schema(request=None, responses={204: None}, parameters=[INVITE])
    @action(detail=False, methods=["delete"], url_path=r"invites/(?P<invite>\d+)")
    def revoke_invite(self, request, invite=None, *args, **kwargs):
        row = get_object_or_404(StaffInvite, pk=invite)
        if row.revoked_at is None and row.accepted_at is None:
            with transaction.atomic():
                row.revoked_at = timezone.now()
                row.save(update_fields=["revoked_at"])
                audit.record("staff.invite_revoked", request=request, target=row)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=s.GrantSerializer,
        responses={200: s.PersonSerializer, 202: s.ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    @action(detail=True, methods=["post"], url_path="roles")
    def grant_role(self, request, *args, **kwargs):
        person, user = self.target(), self.human()
        data = s.GrantSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role = data.validated_data["role"]
        if problem := services.sod_problem(services.staff_roles(person) - {role}, role):
            raise serializers.ValidationError({"role": [problem]})
        change_request, _ = approvals.ask(
            "staff.grant_role",
            maker=user,
            target=person,
            payload={"role": role, "expires_at": data.validated_data.get("expires_at")},
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        if change_request.status == ChangeRequest.Status.EXECUTED:
            return Response(self.get_serializer(User.objects.get(pk=person.pk)).data)
        return accepted(change_request, self)

    @extend_schema(request=None, responses={200: s.PersonSerializer}, parameters=[ROLE])
    @action(detail=True, methods=["delete"], url_path=r"roles/(?P<role>[A-Z_]+)")
    def revoke_role(self, request, role=None, *args, **kwargs):
        person = self.target()
        if role not in services.staff_roles(person):
            raise exceptions.NotFound("The person does not hold this role.")
        services.revoke_role(person, role, by=self.human(), reason=request.query_params.get("reason", ""))
        return Response(self.get_serializer(User.objects.get(pk=person.pk)).data)

    @extend_schema(request=s.ScopeAddSerializer, responses={201: s.ScopeSerializer})
    @action(detail=True, methods=["post"], url_path="scopes")
    def add_scope(self, request, *args, **kwargs):
        person = self.target()
        data = s.ScopeAddSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        scope = services.add_scope(person, **data.validated_data, by=self.human())
        return Response(s.ScopeSerializer(scope).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None}, parameters=[SCOPE])
    @action(detail=True, methods=["delete"], url_path=r"scopes/(?P<scope>\d+)")
    def remove_scope(self, request, scope=None, *args, **kwargs):
        person = self.target()
        services.remove_scope(get_object_or_404(StaffScope, pk=scope, user=person), by=self.human())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "Ended", {"sessions": serializers.IntegerField(), "tokens": serializers.IntegerField()}
        ),
    )
    @action(detail=True, methods=["post"], url_path="end-sessions")
    def end_sessions(self, request, *args, **kwargs):
        sessions, tokens = services.end_sessions(self.target(), request=request)
        return Response({"sessions": sessions, "tokens": tokens})

    @extend_schema(request=s.ReasonSerializer, responses={202: s.ChangeRequestSerializer}, parameters=[IDEMPOTENCY])
    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request, *args, **kwargs):
        """A member of staff's second factor reset: ADMIN or an owner approves it (research 1.5), never the person."""
        person, data = self.target(), s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request, _ = approvals.ask(
            "user.reset_mfa",
            maker=self.human(),
            target=person,
            payload={},
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        return accepted(change_request, self)

    @extend_schema(
        request=s.ReasonSerializer,
        responses=inline_serializer(
            "Offboarded",
            {
                "roles": serializers.ListField(child=serializers.CharField()),
                "scopes": serializers.IntegerField(),
                "api_keys": serializers.IntegerField(),
                "change_requests": serializers.IntegerField(),
                "sessions": serializers.IntegerField(),
                "tokens": serializers.IntegerField(),
            },
        ),
    )
    @action(detail=True, methods=["post"])
    def offboard(self, request, *args, **kwargs):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            services.offboard(self.target(), by=self.human(), reason=data.validated_data["reason"], request=request)
        )


class AccessReviewView(StaffView, generics.GenericAPIView):
    """The quarterly access review (research 6): each member of staff with roles, scopes, last log-in, second
    factor, and the action permissions they hold but have not used in 90 days (the audit log, and the Django admin's
    own log for what they did there)."""

    permissions = {"GET": "staff.view_staff"}
    queryset = User.objects.none()
    serializer_class = s.AccessRowSerializer
    pagination_class = None  # every member of staff, in one answer

    @extend_schema(responses=s.AccessRowSerializer(many=True))
    def get(self, request, *args, **kwargs):
        since = timezone.now() - timedelta(days=90)
        last_used = {}
        events = AuditEvent.objects.filter(ts__gte=since, outcome=AuditEvent.Outcome.SUCCESS).exclude(permission="")
        for actor, perm, when in events.values_list("actor_id", "permission").annotate(last=Max("ts")):
            last_used[actor, perm] = when
        verbs = {ADDITION: "add", CHANGE: "change", DELETION: "delete"}
        entries = (
            LogEntry.objects.filter(action_time__gte=since)
            .values_list("user_id", "content_type__app_label", "content_type__model", "action_flag")
            .annotate(last=Max("action_time"))
        )
        for actor, app_label, model, flag, when in entries:
            last_used.setdefault((actor, f"{app_label}.{verbs[flag]}_{model}"), when)
        dormant_since = timezone.now() - timedelta(days=settings.STAFF_DORMANT_DAYS)
        rows = []
        members = scoped(staff_members().order_by("pk"), request.user, "staff.view_staff")
        for person in members.prefetch_related("role_grants"):
            held = sorted(person.get_all_permissions())
            actions_ = [perm for perm in held if not perm.partition(".")[2].startswith("view_")]
            rows.append(
                {
                    "id": person.pk,
                    "email": person.email,
                    "roles": sorted(services.staff_roles(person)),
                    "grants": s.RoleGrantSerializer(person.role_grants.all(), many=True).data,
                    "scopes": {kind: sorted(values) for kind, values in staff_scopes(person).items()},
                    "last_login": person.last_login,
                    "dormant": not person.last_login or person.last_login < dormant_since,
                    "mfa": s.has_second_factor(person),
                    "permissions": len(held),
                    "unused": [perm for perm in actions_ if (person.pk, perm) not in last_used],
                    "last_used": {perm: when for (actor, perm), when in last_used.items() if actor == person.pk},
                }
            )
        return Response(s.AccessRowSerializer(rows, many=True).data)


class InviteAcceptView(generics.GenericAPIView):
    """An invitation's link (the panel's /invite/<token>/ page): signed in with the invited address, the role is
    given; signed out, a new account is made with a name and a password (the link proves the address). Then the
    second factor before anything opens. The one staff endpoint for people who are not staff yet."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]
    serializer_class = s.AcceptSerializer
    throttle_classes = [StaffThrottle]
    throttle_scope = "staff_invite"

    @extend_schema(responses=s.DetailSerializer)
    def post(self, request, *args, **kwargs):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.accept_invite(
            data.validated_data["token"],
            user=request.user,
            request=request,
            full_name=data.validated_data["full_name"],
            password=data.validated_data["password"],
        )
        return Response({"detail": "Welcome. Log in, then set up an authenticator app or a passkey."})


# Customers (users/)


class CustomerFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search", help_text="an email address, a mobile number, or 3+ letters of a name"
    )

    class Meta:
        model = User
        fields = ["class_level", "board", "is_active"]

    def search(self, queryset, name, value):
        from accounts.forms import normalise_phone

        value = value.strip()
        if "@" in value:
            return queryset.filter(email__iexact=value)
        if phone := normalise_phone(value):
            return queryset.filter(Q(login_phone=phone) | Q(phone=phone))
        if len(value) < 3:
            return queryset.none()
        return queryset.filter(full_name__icontains=value)


class UserViewSet(StaffView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Customers (staff are in people/): search with masked contacts; opening one is logged (`sensitive_read`), and
    so is revealing a detail (reveal/, a reason, a re-authentication, 30 an hour). The account actions each name
    their permission; a second factor reset waits for a second person; impersonation gives a 15-minute token."""

    serializer_class = s.CustomerSerializer
    filterset_class = CustomerFilter
    permissions = {
        "list": "accounts.view_user",
        "retrieve": "accounts.view_user",
        "reveal": "staff.reveal_contact",
        "suspend": "staff.suspend_user",
        "unsuspend": "staff.suspend_user",
        "unlock": "staff.unlock_user",
        "resend_verification": "staff.resend_verification",
        "end_sessions": "staff.end_user_sessions",
        "password_reset": "staff.initiate_password_reset",
        "reset_mfa": "staff.reset_user_mfa",
        "impersonate": "staff.impersonate_user",
        "impersonate_end": "staff.impersonate_user",
    }
    no_reauth = ("impersonate_end",)
    throttle_scopes = {"list": "staff_search", "reveal": "staff_reveal", "impersonate": "staff_reveal"}

    def get_queryset(self):
        customers = User.objects.filter(is_staff=False, is_superuser=False).select_related("board").order_by("pk")
        customers = customers.prefetch_related("emailaddress_set", "deletion_requests", "consents")  # a page: 4 queries
        return scoped(customers, self.request.user, "accounts.view_user")

    def get_serializer_class(self):
        return s.CustomerDetailSerializer if self.action == "retrieve" else s.CustomerSerializer

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        audit.record("sensitive_read", request=request, target=user, details={"what": "record", "child": user.is_minor})
        return Response(self.get_serializer(user).data)

    @extend_schema(
        request=s.RevealSerializer,
        responses=inline_serializer(
            "Revealed", {name: serializers.CharField(required=False, allow_null=True) for name in s.REVEALABLE}
        ),
    )
    @action(detail=True, methods=["post"])
    def reveal(self, request, *args, **kwargs):
        user, data = self.get_object(), s.RevealSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shown = sorted(data.validated_data["show"])
        audit.record(
            "sensitive_read",
            request=request,
            target=user,
            reason=data.validated_data["reason"],
            details={"what": "reveal", "fields": shown, "child": user.is_minor},
        )
        values = {name: getattr(user, name) for name in shown}
        return Response({name: str(value) if value not in (None, "") else None for name, value in values.items()})

    def _reason(self, request):
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return data.validated_data["reason"]

    @extend_schema(request=s.ReasonSerializer, responses=s.CustomerSerializer)
    @action(detail=True, methods=["post"])
    def suspend(self, request, *args, **kwargs):
        user = self.get_object()
        services.suspend(user, reason=self._reason(request), request=request)
        return Response(s.CustomerSerializer(user).data)

    @extend_schema(request=s.ReasonSerializer, responses=s.CustomerSerializer)
    @action(detail=True, methods=["post"])
    def unsuspend(self, request, *args, **kwargs):
        user = self.get_object()
        services.unsuspend(user, reason=self._reason(request), request=request)
        return Response(s.CustomerSerializer(user).data)

    @extend_schema(
        request=None, responses=inline_serializer("Unlocked", {"attempts_cleared": serializers.IntegerField()})
    )
    @action(detail=True, methods=["post"])
    def unlock(self, request, *args, **kwargs):
        return Response({"attempts_cleared": services.unlock(self.get_object(), request=request)})

    @extend_schema(request=None, responses=s.DetailSerializer)
    @action(detail=True, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request, *args, **kwargs):
        user = self.get_object()
        services.resend_verification(user, request=request)
        return Response({"detail": "The parent's link to confirm is on its way."})

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "SessionsEnded", {"sessions": serializers.IntegerField(), "tokens": serializers.IntegerField()}
        ),
    )
    @action(detail=True, methods=["post"], url_path="end-sessions")
    def end_sessions(self, request, *args, **kwargs):
        sessions, tokens = services.end_sessions(self.get_object(), request=request)
        return Response({"sessions": sessions, "tokens": tokens})

    @extend_schema(request=None, responses=s.DetailSerializer)
    @action(detail=True, methods=["post"], url_path="password-reset")
    def password_reset(self, request, *args, **kwargs):
        services.start_password_reset(self.get_object(), request=request)
        return Response({"detail": "A link to set a new password went to the account's address."})

    @extend_schema(request=s.ReasonSerializer, responses={202: s.ChangeRequestSerializer}, parameters=[IDEMPOTENCY])
    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request, *args, **kwargs):
        user = self.get_object()
        change_request, _ = approvals.ask(
            "user.reset_mfa",
            maker=self.human(),
            target=user,
            payload={},
            reason=self._reason(request),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        return accepted(change_request, self)

    @extend_schema(request=s.ImpersonateSerializer, responses=s.ImpersonationSerializer)
    @action(detail=True, methods=["post"])
    def impersonate(self, request, *args, **kwargs):
        user, data = self.get_object(), s.ImpersonateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        token, expires_at = services.impersonation_token(self.human(), user, request=request, **data.validated_data)
        request.session[IMPERSONATION] = {"user": user.pk, "until": expires_at.isoformat()}  # the manifest's banner
        return Response({"token": token, "expires_at": expires_at})

    @extend_schema(request=s.TokenSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="impersonate/end")
    def impersonate_end(self, request, *args, **kwargs):
        user, data = self.get_object(), s.TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.end_impersonation(self.human(), user, data.validated_data["token"], request=request)
        if (request.session.get(IMPERSONATION) or {}).get("user") == user.pk:
            del request.session[IMPERSONATION]
        return Response(status=status.HTTP_204_NO_CONTENT)


# Data protection


class DataRequestFilter(django_filters.FilterSet):
    overdue = django_filters.BooleanFilter(method="filter_overdue", help_text="true: past its answer-by time")

    class Meta:
        model = DataRequest
        fields = ["status", "kind", "user", "assignee"]

    def filter_overdue(self, queryset, name, value):
        late = Q(due_at__lt=timezone.now()) & ~Q(status=DataRequest.Status.CLOSED)
        return queryset.filter(late) if value else queryset.exclude(late)


class DataRequestViewSet(
    StaffView,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """The data principals' requests and complaints by email, letter or phone, with their clocks (acknowledge in 48
    hours; answer in a month, 90 days for the DPDP rights from 13 May 2027). An access request's data goes by email
    to the account's own address; an erasure is dry-run first and approved by a second person."""

    filterset_class = DataRequestFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve", "response", "erasure_report"], "staff.view_datarequest"),
        **dict.fromkeys(
            ["create", "update", "partial_update", "acknowledge", "verify_identity", "close", "erase"],
            "staff.handle_data_request",
        ),
        "export": "staff.export_personal_data",
    }
    reauth = ("erase",)
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return scoped(DataRequest.objects.all(), self.request.user, "staff.view_datarequest")

    def get_serializer_class(self):
        return s.DataRequestListSerializer if self.action == "list" else s.DataRequestSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            data_request = serializer.save(created_by=self.human())
            audit.record(
                "data_request.created",
                request=self.request,
                target=data_request,
                details={"kind": data_request.kind, "channel": data_request.channel},
            )

    def perform_update(self, serializer):
        before = {name: getattr(serializer.instance, name) for name in serializer.validated_data}
        with transaction.atomic():
            data_request = serializer.save()
            changes = {
                name: [before[name], getattr(data_request, name)]
                for name in before
                if before[name] != getattr(data_request, name)
            }
            audit.record("data_request.updated", request=self.request, target=data_request, changes=changes)

    def _event(self, data_request, verb, **kwargs):
        audit.record(f"data_request.{verb}", request=self.request, target=data_request, **kwargs)

    @extend_schema(request=None, responses=s.DataRequestSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, *args, **kwargs):
        data_request = self.get_object()
        if data_request.acknowledged_at is None:
            with transaction.atomic():
                data_request.acknowledged_at = timezone.now()
                if data_request.status == DataRequest.Status.NEW:
                    data_request.status = DataRequest.Status.ACKNOWLEDGED
                data_request.save(update_fields=["acknowledged_at", "status"])
                self._event(
                    data_request,
                    "acknowledged",
                    details={"late": data_request.acknowledged_at > data_request.ack_due_at},
                )
        return Response(s.DataRequestSerializer(data_request).data)

    @extend_schema(request=s.VerifyIdentitySerializer, responses=s.DataRequestSerializer)
    @action(detail=True, methods=["post"], url_path="verify-identity")
    def verify_identity(self, request, *args, **kwargs):
        data_request, data = self.get_object(), s.VerifyIdentitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            data_request.identity_verified, data_request.identity_note = True, data.validated_data["note"]
            data_request.verified_by, data_request.verified_at = request.user, timezone.now()
            data_request.save(update_fields=["identity_verified", "identity_note", "verified_by", "verified_at"])
            self._event(data_request, "identity_verified", reason=data_request.identity_note)
        return Response(s.DataRequestSerializer(data_request).data)

    @extend_schema(request=s.CloseSerializer, responses=s.DataRequestSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, *args, **kwargs):
        data_request, data = self.get_object(), s.CloseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if data_request.status == DataRequest.Status.CLOSED:
            raise serializers.ValidationError({"non_field_errors": ["Closed already."]})
        with transaction.atomic():
            data_request.status, data_request.closed_at, data_request.closed_by = "closed", timezone.now(), request.user
            data_request.outcome, data_request.response = (
                data.validated_data["outcome"],
                data.validated_data["response"],
            )
            data_request.acknowledged_at = data_request.acknowledged_at or data_request.closed_at
            data_request.save()
            self._event(
                data_request,
                "closed",
                details={"outcome": data_request.outcome, "late": data_request.closed_at > data_request.due_at},
            )
        return Response(s.DataRequestSerializer(data_request).data)

    @extend_schema(responses=s.ResponseTextSerializer)
    @action(detail=True)
    def response(self, request, *args, **kwargs):
        return Response(response_text(self.get_object()))

    def _user_of(self, data_request, kind):
        if data_request.kind != kind or data_request.user is None:
            raise serializers.ValidationError({"non_field_errors": [f"Only for an {kind} request about an account."]})
        return data_request.user

    @extend_schema(responses=s.ErasureReportSerializer)
    @action(detail=True, url_path="erasure-report")
    def erasure_report(self, request, *args, **kwargs):
        data_request = self.get_object()
        user = self._user_of(data_request, DataRequest.Kind.ERASURE)
        return Response(erasure_report(user, data_request))

    @extend_schema(
        request=s.ReasonSerializer, responses={202: s.ChangeRequestSerializer, 400: s.ErasureReportSerializer}
    )
    @action(detail=True, methods=["post"])
    def erase(self, request, *args, **kwargs):
        data_request = self.get_object()
        user = self._user_of(data_request, DataRequest.Kind.ERASURE)
        report = erasure_report(user, data_request)
        if not report["can_erase"]:
            return Response(report, status=status.HTTP_400_BAD_REQUEST)
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request, _ = approvals.ask(
            "user.erase",
            maker=self.human(),
            target=user,
            payload={"data_request": data_request.pk},
            reason=data.validated_data["reason"],
            request=request,
        )
        return accepted(change_request, self)

    @extend_schema(request=None, responses={202: s.DetailSerializer})
    @action(detail=True, methods=["post"])
    def export(self, request, *args, **kwargs):
        from .tasks import email_data_export

        data_request = self.get_object()
        user = self._user_of(data_request, DataRequest.Kind.ACCESS)
        if not data_request.identity_verified:
            raise serializers.ValidationError({"non_field_errors": ["Verify the requester's identity first."]})
        with transaction.atomic():
            self._event(data_request, "exported", details={"to": "the account's address", "child": user.is_minor})
            transaction.on_commit(lambda: email_data_export.delay(data_request.pk), robust=True)
        return Response(
            {"detail": "The data goes by email to the account's own address."}, status=status.HTTP_202_ACCEPTED
        )


class IncidentFilter(django_filters.FilterSet):
    open = django_filters.BooleanFilter(field_name="closed_at", lookup_expr="isnull", help_text="true: not closed")

    class Meta:
        model = Incident
        fields = ["kind"]


class IncidentViewSet(
    StaffView,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """The breach register: each incident with its clocks from detection (CERT-In 6 hours, the Board's detailed
    report 72 hours), the reports' times and references, the notices to the people affected, actions and closure.
    A new one tells the owners at once."""

    serializer_class = s.IncidentSerializer
    filterset_class = IncidentFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "staff.view_incident"),
        **dict.fromkeys(["create", "update", "partial_update", "close"], "staff.manage_incident"),
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return scoped(Incident.objects.all(), self.request.user, "staff.view_incident")

    def perform_create(self, serializer):
        with transaction.atomic():
            incident = serializer.save(noticed_by=self.human())
            audit.record(
                "incident.created",
                request=self.request,
                target=incident,
                details={"kind": incident.kind, "children": incident.children_affected},
            )
            audit.alert(
                f"Incident #{incident.pk}: {incident.title}",
                f"Detected {timezone.localtime(incident.detected_at):%d %b %Y %H:%M}. CERT-In within 6 hours "
                f"(by {timezone.localtime(incident.cert_in_due):%H:%M}); the Board's report within 72 hours. "
                f"CERT-In's contact: {settings.CERT_IN_POINT_OF_CONTACT}",
            )

    def perform_update(self, serializer):
        before = {name: getattr(serializer.instance, name) for name in serializer.validated_data}
        with transaction.atomic():
            incident = serializer.save()
            changes = {
                name: [before[name], getattr(incident, name)]
                for name in before
                if before[name] != getattr(incident, name)
            }
            audit.record("incident.updated", request=self.request, target=incident, changes=changes)

    @extend_schema(request=None, responses=s.IncidentSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, *args, **kwargs):
        incident = self.get_object()
        if incident.closed_at is None:
            with transaction.atomic():
                incident.closed_at, incident.closed_by = timezone.now(), request.user
                incident.save(update_fields=["closed_at", "closed_by"])
                audit.record("incident.closed", request=request, target=incident)
        return Response(self.get_serializer(incident).data)


class ProcessorViewSet(StaffView, viewsets.ModelViewSet):
    """The processor register: who handles personal data for ExamLeaf, for what, where, under which contract."""

    serializer_class = s.ProcessorSerializer
    permissions = {
        "list": "staff.view_processorrecord",
        "retrieve": "staff.view_processorrecord",
        "create": "staff.add_processorrecord",
        "update": "staff.change_processorrecord",
        "partial_update": "staff.change_processorrecord",
        "destroy": "staff.delete_processorrecord",
    }

    def get_queryset(self):
        return scoped(ProcessorRecord.objects.all(), self.request.user, "staff.view_processorrecord")

    def perform_create(self, serializer):
        with transaction.atomic():
            audit.record("processor.created", request=self.request, target=serializer.save())

    def perform_update(self, serializer):
        with transaction.atomic():
            audit.record(
                "processor.updated",
                request=self.request,
                target=serializer.save(),
                details={"fields": sorted(serializer.validated_data)},
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit.record("processor.deleted", request=self.request, target=instance)
            instance.delete()


# The system


SYSTEM = inline_serializer(
    "StaffSystem",
    {
        name: serializers.JSONField()
        for name in ["health", "celery", "webhooks", "email", "sms", "backups", "maintenance", "audit"]
    },
)


def health():
    import asyncio

    from examleaf.urls import ALL_CHECKS
    from examleaf.views import HealthView

    checks = list(HealthView(checks=ALL_CHECKS).get_checks())

    async def run():
        return await asyncio.gather(*(check.get_result() for check in checks))

    return [
        {"check": result.check.__class__.__name__, "ok": result.error is None, "error": str(result.error or "")}
        for result in asyncio.run(run())
    ]


def queues():
    """Messages waiting per queue (with a broker), and the failed tasks of the last 7 days (no arguments: they hold
    email texts)."""
    from django_celery_results.models import TaskResult

    from examleaf.celery import app

    depths = None
    if not settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            with app.connection_for_read() as connection:
                channel = connection.default_channel
                depths = {name: channel.queue_declare(name, passive=True).message_count for name in ("celery", "media")}
        except Exception as error:  # the broker is down: say so, do not fail the page
            depths = {"error": str(error)[:200]}
    failed = TaskResult.objects.filter(status="FAILURE", date_done__gte=timezone.now() - timedelta(days=7))
    return {
        "queues": depths,
        "failed_7_days": failed.count(),
        "failed": list(failed.order_by("-date_done").values("task_id", "task_name", "date_done")[:10]),
    }


def backups():
    storage = audit.backups_storage()
    if storage is None:
        return {"configured": False}
    try:
        _, files = storage.listdir("database/")
    except Exception as error:
        return {"configured": True, "error": str(error)[:200]}
    if not files:
        return {"configured": True, "latest": None}
    latest = max(files)  # examleaf-YYYYMMDD-HHMMSS.dump(.age): the name sorts by time
    name = f"database/{latest}"
    return {"configured": True, "latest": latest, "size": storage.size(name), "at": storage.get_modified_time(name)}


class SystemView(StaffView, generics.GenericAPIView):
    """The system at a glance: the health checks (/health/'s), Celery's queues and failed tasks, Razorpay's webhooks,
    email suppressions and the SMS log, the last backup in the bucket, maintenance mode, the audit chain's last
    verification. The panel shows them; Sentry, the logs and the uptime monitor stay where they are."""

    permissions = {"GET": "staff.view_system"}
    pagination_class = None

    @extend_schema(responses=SYSTEM)
    def get(self, request, *args, **kwargs):
        from ops.models import EmailSuppression, SmsLog
        from shop.models import WebhookEvent

        day, week = timezone.now() - timedelta(days=1), timezone.now() - timedelta(days=7)
        failures = InboxItem.objects.filter(kind=InboxItem.Kind.FAILED_WEBHOOK, created__gte=week)
        verified = AuditEvent.objects.filter(action__in=["audit.verified", "audit.chain_broken"]).order_by("-id")
        last = verified.values("action", "ts", "details").first()
        return Response(
            {
                "health": health(),
                "celery": queues(),
                "webhooks": {
                    "last_day": dict(
                        WebhookEvent.objects.filter(received_at__gte=day).values_list("name").annotate(n=Count("pk"))
                    ),
                    "refused_7_days": sum(item.data.get("count", 1) for item in failures),
                },
                "email": {
                    "suppressed": EmailSuppression.objects.count(),
                    "suppressed_7_days": dict(
                        EmailSuppression.objects.filter(created__gte=week).values_list("reason").annotate(n=Count("pk"))
                    ),
                },
                "sms": {
                    "last_day": dict(
                        SmsLog.objects.filter(created__gte=day).values_list("status").annotate(n=Count("pk"))
                    )
                },
                "backups": backups(),
                "maintenance": {"on": site_setting("MAINTENANCE_MODE"), "banner": site_setting("MAINTENANCE_BANNER")},
                "audit": {"last_verification": last, "heads": audit.heads()},
            }
        )


class ReconcileView(StaffView, generics.GenericAPIView):
    """Ask Razorpay what became of an online order's payment (a lost webhook; RUNBOOK.md "A stuck payment"): a payment
    it captured is recorded (shop.payments.reconcile). Webhooks keep no body to replay; this asks the source again."""

    permissions = {"POST": "staff.replay_webhook"}
    serializer_class = s.ReconcileSerializer

    @extend_schema(
        responses=inline_serializer(
            "Reconciled", {"order": serializers.CharField(), "paid": serializers.BooleanField(allow_null=True)}
        )
    )
    def post(self, request, *args, **kwargs):
        from shop import payments
        from shop.models import Order

        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = (
            scoped(Order.objects.all(), request.user, "shop.view_order")
            .filter(number=data.validated_data["order"])
            .first()
        )
        if order is None:
            raise exceptions.NotFound("No such order.")
        paid = payments.reconcile(order) if order.status == Order.Status.PENDING else True
        audit.record("order.reconciled", request=request, target=order, details={"paid": paid})
        return Response({"order": order.number, "paid": paid})
