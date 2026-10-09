"""Legal and privacy's staff API, under /api/v1/staff/privacy/ (API.md "Legal and privacy (staff)"; plan 5.15), on the
staff API's rules (staff.api.StaffView): the panel's session with a second factor (or an API key for the reads), each
action's catalogued permission, a re-authentication for the high ones, the admin host only, every refusal an
`authz_fail`, cursor pages, `Cache-Control: no-store`. Every change is an audit event. What it holds:

- the compliance cockpit (every clock the rules start, with the record behind it; staff.compliance), and the retention
  schedule (examleaf.retention);
- legal holds on a person or a record (accounts.LegalHold), made and released with staff.manage_holds;
- a customer's nominee, its contact masked and revealed with a reason; a child's deletion confirmed by the parent
  through staff, with the evidence;
- the legal pages' versions, their diffs, publishing one now or for a later day (pages.versions);
- the e-commerce disclosures, the site settings of the group "disclosures", saved together with one reason;
- the yearly dark-pattern self-audit and its certificate (staff.DarkPatternAudit), with staff.manage_compliance."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import transaction
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from accounts.models import ConsentRecord, DeletionRequest, LegalHold, Nominee
from api.schema import AutoSchema
from examleaf import retention
from pages import versions as page_versions
from pages.models import Page

from . import audit, compliance, privacy
from .api import StaffView, describe_setting
from .backends import scoped
from .config import DISCLOSURES, SETTINGS, changed, site_setting
from .models import DARK_PATTERNS, DarkPatternAudit, DataRequest, InboxItem, SiteSetting

User = get_user_model()
PATTERNS = dict(DARK_PATTERNS)


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["privacy (staff)"]


class PrivacyView(StaffView):
    schema = StaffSchema()


def refused(message, field="non_field_errors"):
    return serializers.ValidationError({field: [message]})


# The cockpit and the retention schedule

CLOCK_KINDS = [
    *["data_request_ack", "data_request_answer", "incident_cert_in", "incident_board", "complaint_ack"],
    *["complaint_redress", "complaint_nch", "parent_consent", "deletion_parent", "dark_pattern_audit"],
]


class ClockSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=CLOCK_KINDS)
    label = serializers.CharField()
    rule = serializers.CharField(help_text="the law's clock, in words")
    started_at = serializers.DateTimeField(allow_null=True)
    due_at = serializers.DateTimeField(allow_null=True, help_text="null: awaited, no legal end")
    overdue = serializers.BooleanField()
    target_type = serializers.CharField(help_text="the record behind it: app_label.model")
    target_id = serializers.CharField()
    target_label = serializers.CharField()
    account = serializers.IntegerField(allow_null=True, help_text="the account it is about (its number), if any")


class ClockCountSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    overdue = serializers.IntegerField()


class CockpitSerializer(serializers.Serializer):
    now = serializers.DateTimeField()
    clocks = ClockSerializer(many=True, help_text="the overdue first, then by due time; 20 of each kind at most")
    counts = serializers.DictField(child=ClockCountSerializer(), help_text="every one of each kind")
    support = inline_serializer(
        "PrivacyCockpitSupport",
        {"installed": serializers.BooleanField(), "error": serializers.CharField(allow_blank=True)},
    )
    consents = inline_serializer(
        "PrivacyConsentVersion",
        {
            "version": serializers.CharField(help_text="the privacy notice's version the consents were given under"),
            "number": serializers.IntegerField(allow_null=True),
            "in_force": serializers.BooleanField(),
            "given": serializers.IntegerField(),
            "withdrawn": serializers.IntegerField(),
        },
        many=True,
    )
    dark_pattern = inline_serializer(
        "PrivacyDarkPatternState",
        {
            "year": serializers.IntegerField(),
            "due": serializers.DateField(),
            "audit": serializers.IntegerField(allow_null=True),
            "state": serializers.ChoiceField(choices=["missing", "draft", "completed"]),
            "completed_at": serializers.DateTimeField(allow_null=True),
            "effective_from": serializers.DateField(allow_null=True),
            "certificate_year": serializers.IntegerField(allow_null=True, help_text="the certificate shown now"),
        },
    )
    calendar = inline_serializer(
        "PrivacyCalendarItem",
        {
            "date": serializers.DateField(),
            "title": serializers.CharField(),
            "detail": serializers.CharField(),
            "state": serializers.ChoiceField(choices=["upcoming", "in_force", "done", "overdue"]),
        },
        many=True,
    )
    inbox = serializers.IntegerField(help_text="the processors' tasks and compliance items open in the inbox")


class CockpitView(PrivacyView, generics.GenericAPIView):
    """The compliance cockpit: every clock the rules start, the consents by the notice's version, the dark-pattern
    self-audit, the legal calendar."""

    permissions = {"GET": "staff.view_datarequest"}
    queryset = DataRequest.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(responses=CockpitSerializer)
    def get(self, request, *args, **kwargs):
        return Response(CockpitSerializer(compliance.cockpit()).data)


class RetentionRuleSerializer(serializers.Serializer):
    key = serializers.CharField()
    records = serializers.CharField()
    minimum = serializers.CharField(help_text="the law's least time today")
    minimum_days = serializers.IntegerField(allow_null=True)
    source = serializers.CharField()
    changes_on = serializers.DateField(allow_null=True, help_text="when the minimum changes next")
    next_minimum = serializers.CharField(allow_null=True)
    keep = serializers.CharField(help_text="what this site keeps")
    keep_days = serializers.IntegerField(allow_null=True)
    trim_days = serializers.IntegerField(allow_null=True)
    enforced_by = serializers.CharField()


class RetentionView(PrivacyView, generics.GenericAPIView):
    """The retention schedule in code (examleaf/retention.py): each kind of record's minimum today, the day it
    changes, what is kept and who deletes it."""

    permissions = {"GET": "staff.view_datarequest"}
    queryset = DataRequest.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(responses=RetentionRuleSerializer(many=True))
    def get(self, request, *args, **kwargs):
        return Response(RetentionRuleSerializer(retention.table(), many=True).data)


# Legal holds


class LegalHoldSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField(help_text="app_label.model; empty for a person")
    target_label = serializers.SerializerMethodField(help_text="what it keeps, by number or code")
    active = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = LegalHold
        fields = [
            *["id", "user", "target_type", "target_id", "target_label", "reason", "note", "until", "active"],
            *["created", "created_by", "released_at", "released_by", "release_reason"],
        ]
        read_only_fields = fields

    def get_target_type(self, hold) -> str:
        return f"{hold.target_type.app_label}.{hold.target_type.model}" if hold.target_type_id else ""

    def get_target_label(self, hold) -> str:
        labels = self.context.get("labels") or privacy.hold_labels([hold])
        return labels.get(hold.pk, "")


class HoldCreateSerializer(serializers.Serializer):
    user = serializers.IntegerField(required=False, allow_null=True, help_text="the account held (its number)")
    target_type = serializers.ChoiceField(
        choices=sorted(privacy.HOLD_TARGETS), required=False, allow_blank=True, help_text="a record instead"
    )
    target_id = serializers.CharField(max_length=64, required=False, allow_blank=True, help_text="its number or id")
    reason = serializers.ChoiceField(choices=LegalHold.Reason.choices)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    until = serializers.DateField(required=False, allow_null=True, help_text="the last day it holds; none: released")

    def validate_until(self, until):
        if until is not None and until < timezone.localdate():
            raise serializers.ValidationError("Today or a later day.")
        return until

    def validate(self, data):
        user, label = data.get("user"), data.get("target_type") or ""
        if bool(user) == bool(label):
            raise serializers.ValidationError({"non_field_errors": ["Hold an account, or one record: one of them."]})
        if user:
            data["user"] = User.objects.filter(pk=user).first()
            if data["user"] is None:
                raise serializers.ValidationError({"user": ["No such account."]})
            return data
        found = privacy.find_hold_target(label, data.get("target_id"))
        if found is None:
            raise serializers.ValidationError({"target_id": ["No such record."]})
        data["target_type"], data["target_id"] = found[0], str(found[1].pk)
        return data


class ReleaseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, help_text="why it ends: kept with it and in the audit log")


class LegalHoldFilter(django_filters.FilterSet):
    active = django_filters.BooleanFilter(method="filter_active", help_text="true: in force now")
    target_type = django_filters.ChoiceFilter(
        choices=[(label, label) for label in sorted(privacy.HOLD_TARGETS)], method="filter_target_type"
    )

    class Meta:
        model = LegalHold
        fields = ["reason", "user"]

    def filter_active(self, queryset, name, value):
        held = LegalHold.objects.active().values("pk")
        return queryset.filter(pk__in=held) if value else queryset.exclude(pk__in=held)

    def filter_target_type(self, queryset, name, value):
        app_label, model = value.split(".")
        return queryset.filter(target_type__app_label=app_label, target_type__model=model)


class LegalHoldViewSet(PrivacyView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Legal holds on an account or one record (an order, an invoice, a credit note, a payment, a refund, a data
    request): they keep it from the erasure and the retention clean-up until their day, or their release."""

    serializer_class = LegalHoldSerializer
    filterset_class = LegalHoldFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "accounts.view_legalhold"),
        **dict.fromkeys(["create", "release"], "staff.manage_holds"),
    }

    def get_queryset(self):
        holds = LegalHold.objects.select_related("target_type")
        return scoped(holds, self.request.user, "accounts.view_legalhold")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        context = {**self.get_serializer_context(), "labels": privacy.hold_labels(page)}
        return self.get_paginated_response(LegalHoldSerializer(page, many=True, context=context).data)

    @extend_schema(request=HoldCreateSerializer, responses={201: LegalHoldSerializer})
    def create(self, request, *args, **kwargs):
        data = HoldCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        held, user = data.validated_data, data.validated_data.get("user")
        with transaction.atomic():
            hold = LegalHold.objects.create(
                user=user,
                target_type=None if user else held["target_type"],
                target_id="" if user else held["target_id"],
                reason=held["reason"],
                note=held.get("note", ""),
                until=held.get("until"),
                created_by=self.human(),
            )
            label = privacy.hold_labels([hold])[hold.pk]
            audit.record(
                "legal_hold.created",
                request=request,
                target=("accounts.legalhold", hold.pk, f"Legal hold {hold.pk}"),
                details={"reason": hold.reason, "holds": label, "until": hold.until},
            )
        return Response(self.get_serializer(hold).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReleaseSerializer, responses=LegalHoldSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, *args, **kwargs):
        data = ReleaseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            hold = LegalHold.objects.select_for_update().get(pk=self.get_object().pk)
            if hold.released_at:
                raise refused("Released already.")
            hold.released_at, hold.released_by = timezone.now(), self.human()
            hold.release_reason = data.validated_data["reason"]
            hold.save(update_fields=["released_at", "released_by", "release_reason"])
            audit.record(
                "legal_hold.released",
                request=request,
                target=("accounts.legalhold", hold.pk, f"Legal hold {hold.pk}"),
                reason=hold.release_reason,
            )
        return Response(self.get_serializer(hold).data)


# A customer's nominee, and a child's deletion confirmed by staff


class PrivacyNomineeSerializer(serializers.Serializer):
    name = serializers.CharField()
    contact = serializers.CharField(help_text="masked: reveal/ shows it, with a reason (logged)")
    relation = serializers.CharField()
    verified_at = serializers.DateTimeField(allow_null=True, help_text="when a claim proved it (Phase C)")
    created = serializers.DateTimeField()
    updated = serializers.DateTimeField()


class AccountNomineeSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    nominee = PrivacyNomineeSerializer(allow_null=True)


def customer(request, pk):
    """A customer (never staff), within the reader's scope of accounts.view_user; else 404."""
    customers = User.objects.filter(is_staff=False, is_superuser=False)
    return get_object_or_404(scoped(customers, request.user, "accounts.view_user"), pk=pk)


class NomineeView(PrivacyView, generics.GenericAPIView):
    """The nominee a customer recorded on My account (DPDP s.14), its contact masked; each look at one is a
    `sensitive_read`, a child's marked as such."""

    permissions = {"GET": "accounts.view_user"}
    queryset = Nominee.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(responses=AccountNomineeSerializer)
    def get(self, request, user, *args, **kwargs):
        account = customer(request, user)
        nominee = Nominee.objects.filter(user=account).first()
        if nominee is not None:
            audit.record("sensitive_read", request=request, target=account,
                         details={"what": "nominee", "child": account.is_minor})  # fmt: skip
        shown = None
        if nominee is not None:
            shown = {
                "name": nominee.name,
                "contact": privacy.mask_contact(nominee.contact),
                "relation": nominee.relation,
                "verified_at": nominee.verified_at,
                "created": nominee.created,
                "updated": nominee.updated,
            }
        return Response(AccountNomineeSerializer({"user": account.pk, "nominee": shown}).data)


class RevealReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=300, help_text="why: kept in the audit log")


class NomineeRevealView(PrivacyView, generics.GenericAPIView):
    """The nominee's contact, shown with a reason (re-authenticated, 30 an hour, a `sensitive_read` event)."""

    permissions = {"POST": "staff.reveal_contact"}
    throttle_scope = "staff_reveal"
    queryset = Nominee.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(
        request=RevealReasonSerializer,
        responses=inline_serializer("PrivacyNomineeContact", {"contact": serializers.CharField()}),
    )
    def post(self, request, user, *args, **kwargs):
        self.human()
        account = customer(request, user)
        data = RevealReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        nominee = Nominee.objects.filter(user=account).first()
        if nominee is None:
            raise exceptions.NotFound("No nominee recorded.")
        audit.record(
            "sensitive_read",
            request=request,
            target=account,
            reason=data.validated_data["reason"],
            details={"what": "reveal", "fields": ["nominee_contact"], "child": account.is_minor},
        )
        return Response({"contact": nominee.contact})


class ParentConfirmationSerializer(serializers.Serializer):
    evidence_ref = serializers.CharField(
        max_length=200, help_text="where the evidence is: a ticket's number, a letter's date; never the document"
    )


class DeletionParentView(PrivacyView, generics.GenericAPIView):
    """A child's deletion confirmed by their parent or guardian by phone or letter (when their link cannot reach
    them): staff record it, with where the evidence is; the nightly purge erases it once due."""

    permissions = {"POST": "staff.handle_data_request"}
    queryset = DeletionRequest.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(
        request=ParentConfirmationSerializer,
        responses=inline_serializer(
            "PrivacyDeletionConfirmed",
            {"deletion": serializers.IntegerField(), "parent_confirmed_at": serializers.DateTimeField()},
        ),
    )
    def post(self, request, pk, *args, **kwargs):
        staff = self.human()
        data = ParentConfirmationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        accounts = scoped(User.objects.filter(is_staff=False), request.user, "accounts.view_user")
        with transaction.atomic():
            deletion = get_object_or_404(DeletionRequest.objects.select_for_update().filter(user__in=accounts), pk=pk)
            if deletion.status != DeletionRequest.Status.PENDING:
                raise refused("This deletion is not waiting any more.")
            if not deletion.user.is_minor:
                raise refused("Not a student under 18: no parent's confirmation is needed.")
            if deletion.parent_confirmed_at:
                raise refused("The parent's confirmation is recorded already.")
            deletion.parent_confirmed_at, deletion.parent_confirmed_by = timezone.now(), staff
            deletion.parent_evidence_ref = data.validated_data["evidence_ref"]
            deletion.save(update_fields=["parent_confirmed_at", "parent_confirmed_by", "parent_evidence_ref"])
            ConsentRecord.record(
                request,
                deletion.user,
                event=ConsentRecord.Event.WITHDRAWN,
                by_parent=True,
                method=ConsentRecord.Method.STAFF_MANUAL,
                verified_at=deletion.parent_confirmed_at,
                verified_by=staff,
                evidence_ref=deletion.parent_evidence_ref,
            )
            audit.record(
                "account.deletion_parent_confirmed",
                request=request,
                target=("accounts.user", deletion.user_id, f"Account #{deletion.user_id}"),
                details={"deletion_request": deletion.pk, "through": "staff", "evidence": deletion.parent_evidence_ref},
            )
        return Response({"deletion": deletion.pk, "parent_confirmed_at": deletion.parent_confirmed_at})


# The legal pages' versions


class PolicyVersionSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    version = serializers.CharField(help_text="the label consent records keep")
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    effective_from = serializers.DateField()
    published_at = serializers.DateTimeField(allow_null=True)
    published_by = serializers.IntegerField(allow_null=True)
    in_force = serializers.BooleanField()
    upcoming = serializers.BooleanField(help_text="published for a later day: not in force yet")


class PolicySerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="the page's: its audit events and notes name it (pages.page)")
    slug = serializers.CharField()
    title = serializers.CharField()
    version = serializers.CharField()
    number = serializers.IntegerField(help_text="the version in force")
    effective_from = serializers.DateField()
    summary = serializers.CharField(allow_blank=True)
    updated = serializers.DateTimeField()
    placeholders = serializers.IntegerField(help_text="[placeholders] still to fill in")
    scheduled = PolicyVersionSerializer(allow_null=True, help_text="a version waiting for its day")
    versions = serializers.IntegerField(help_text="how many versions it has had")


class PolicyDetailSerializer(PolicySerializer):
    markdown = serializers.CharField(help_text="the text in force")
    versions = PolicyVersionSerializer(many=True, help_text="every version, newest first")


class PolicyDiffLineSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["hunk", "added", "removed", "context"])
    text = serializers.CharField(allow_blank=True)


class PolicyDiffSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    version = serializers.CharField()
    previous = serializers.IntegerField(allow_null=True)
    effective_from = serializers.DateField()
    summary = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    title_changed = serializers.BooleanField()
    added = serializers.IntegerField()
    removed = serializers.IntegerField()
    lines = PolicyDiffLineSerializer(many=True)


class PublishSerializer(serializers.Serializer):
    markdown = serializers.CharField(max_length=100_000, help_text="the new text, in Markdown")
    title = serializers.CharField(max_length=120, required=False, allow_blank=True, help_text="the same if empty")
    summary = serializers.CharField(max_length=200, help_text="what this version changes, in a line")
    effective_from = serializers.DateField(required=False, help_text="in force from (today if empty, never before)")


def policy_of(page, detail=False):
    known = page_versions.versions(page)
    upcoming = next((version for version in known if version.upcoming), None)
    current = next(version for version in known if version.in_force)
    body = {
        "id": page.pk,
        "slug": page.slug,
        "title": page.title,
        "version": page.version,
        "number": current.number,
        "effective_from": page.effective_from,
        "summary": page.summary,
        "updated": page.updated,
        "placeholders": len(page.placeholders),
        "scheduled": vars(upcoming) if upcoming else None,
        "versions": len([version for version in known if not version.upcoming]),
    }
    if detail:
        body["markdown"] = page.body_md
        body["versions"] = [vars(version) for version in reversed(known)]
    return body


class PolicyViewSet(PrivacyView, viewsets.GenericViewSet):
    """The legal pages (privacy, terms, refunds, shipping, contact) and their versions: each publish a numbered version
    with the day it is in force from and a line on what changed; a diff of each against the one before."""

    queryset = Page.objects.all()
    lookup_field = "slug"
    pagination_class = None
    permissions = {
        **dict.fromkeys(["list", "retrieve", "diff"], "pages.view_page"),
        **dict.fromkeys(["publish", "cancel_scheduled"], "pages.change_page"),
    }

    def get_queryset(self):
        return scoped(Page.objects.order_by("id"), self.request.user, "pages.view_page")

    @extend_schema(responses=PolicySerializer(many=True))
    def list(self, request, *args, **kwargs):
        return Response(PolicySerializer([policy_of(page) for page in self.get_queryset()], many=True).data)

    @extend_schema(responses=PolicyDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(PolicyDetailSerializer(policy_of(self.get_object(), detail=True)).data)

    @extend_schema(responses=PolicyDiffSerializer)
    @action(detail=True, url_path=r"versions/(?P<number>\d+)/diff")
    def diff(self, request, number=None, *args, **kwargs):
        found = page_versions.diff(self.get_object(), int(number))
        if found is None:
            raise exceptions.NotFound("No such version.")
        return Response(PolicyDiffSerializer(found).data)

    @extend_schema(request=PublishSerializer, responses=PolicyDetailSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, *args, **kwargs):
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        page = page_versions.publish(
            self.get_object(),
            markdown=data.validated_data["markdown"],
            title=data.validated_data.get("title", ""),
            summary=data.validated_data["summary"],
            effective_from=data.validated_data.get("effective_from") or timezone.localdate(),
            by=self.human(),
            request=request,
        )
        return Response(PolicyDetailSerializer(policy_of(page, detail=True)).data)

    @extend_schema(request=ReleaseSerializer, responses=PolicyDetailSerializer)
    @action(detail=True, methods=["post"], url_path="cancel-scheduled")
    def cancel_scheduled(self, request, *args, **kwargs):
        data = ReleaseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        page = page_versions.cancel_scheduled(
            self.get_object(), by=self.human(), reason=data.validated_data["reason"], request=request
        )
        return Response(PolicyDetailSerializer(policy_of(page, detail=True)).data)


# The e-commerce disclosures: one form for the group of settings


DISCLOSURE_KEYS = [key for key, spec in SETTINGS.items() if spec.group == DISCLOSURES]


class DisclosureSettingSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.JSONField(help_text='"str", or the allowed values')
    max_length = serializers.IntegerField()
    public = serializers.BooleanField(help_text="shown on the website (config/'s disclosures)")
    value = serializers.JSONField(help_text="in effect now")
    environment = serializers.JSONField(help_text="settings.py's value, which stands until the panel sets one")
    source = serializers.ChoiceField(choices=["environment", "database"])
    effective_from = serializers.DateTimeField(allow_null=True)
    changed_by = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)


class DisclosureHistorySerializer(serializers.Serializer):
    key = serializers.CharField()
    value = serializers.JSONField()
    effective_from = serializers.DateTimeField()
    changed_by = serializers.IntegerField(source="changed_by_id", allow_null=True)
    reason = serializers.CharField()
    created = serializers.DateTimeField()


class DisclosuresSerializer(serializers.Serializer):
    settings = DisclosureSettingSerializer(many=True)
    history = DisclosureHistorySerializer(many=True, help_text="the group's changes, newest first (the last 100)")


class DisclosuresChangeSerializer(serializers.Serializer):
    values = serializers.DictField(
        child=serializers.JSONField(allow_null=True), help_text="{KEY: the new value}; null: back to settings.py's"
    )
    reason = serializers.CharField(max_length=300)


PRIVATE = {"CERT_IN_POINT_OF_CONTACT"}  # never on the website


def panel_value(key):
    """The panel's own value in effect (None: none, settings.py's stands)."""
    rows = SiteSetting.objects.filter(key=key, effective_from__lte=timezone.now())
    return rows.order_by("-effective_from", "-pk").values_list("value", flat=True).first()


def disclosures_answer():
    settings_rows = []
    for key in DISCLOSURE_KEYS:
        spec = SETTINGS[key]
        settings_rows.append({**describe_setting(key), "max_length": spec.max_length, "public": key not in PRIVATE})
    history = SiteSetting.objects.filter(key__in=DISCLOSURE_KEYS).order_by("-created", "-pk")[:100]
    return DisclosuresSerializer({"settings": settings_rows, "history": list(history)}).data


class DisclosuresView(PrivacyView, generics.GenericAPIView):
    """The e-commerce disclosures and the privacy contacts (site settings of the group "disclosures"): GET each in
    effect with where it comes from, and the group's history; PUT the changed ones together, with one reason (each a
    `setting.changed` event)."""

    permissions = {"GET": "staff.view_sitesetting", "PUT": "staff.manage_settings"}
    queryset = SiteSetting.objects.none()  # (for the schema)
    pagination_class = None

    @extend_schema(responses=DisclosuresSerializer)
    def get(self, request, *args, **kwargs):
        return Response(disclosures_answer())

    @extend_schema(request=DisclosuresChangeSerializer, responses=DisclosuresSerializer)
    def put(self, request, *args, **kwargs):
        user = self.human()
        data = DisclosuresChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values, errors = {}, {}
        for key, value in data.validated_data["values"].items():
            if key not in DISCLOSURE_KEYS:
                errors[key] = ["Not one of the disclosures."]
                continue
            try:
                values[key] = SETTINGS[key].check(value.strip() if isinstance(value, str) else value)
            except ValueError as error:
                errors[key] = [str(error)]
        if errors:
            raise serializers.ValidationError(errors)
        changes = {key: value for key, value in values.items() if value != panel_value(key)}
        if not changes:
            raise refused("Nothing changed.")
        reason = data.validated_data["reason"]
        with transaction.atomic():
            for key, value in changes.items():
                before = site_setting(key)
                row = SiteSetting.objects.create(key=key, value=value, changed_by=user, reason=reason)
                audit.record(
                    "setting.changed",
                    request=request,
                    target=("staff.sitesetting", row.pk, key),
                    reason=reason,
                    changes={key: [before, value]},
                    details={"setting": key, "effective_from": row.effective_from, "group": DISCLOSURES},
                )
        changed(SiteSetting)
        return Response(disclosures_answer())


# The dark-pattern self-audit


class AuditRowSerializer(serializers.Serializer):
    pattern = serializers.ChoiceField(choices=DARK_PATTERNS)
    label = serializers.SerializerMethodField()
    finding = serializers.CharField(max_length=2000, allow_blank=True)
    fix = serializers.CharField(max_length=2000, allow_blank=True)

    def get_label(self, row) -> str:
        return PATTERNS.get(row.get("pattern"), "")


class DarkPatternAuditSerializer(serializers.ModelSerializer):
    rows = AuditRowSerializer(many=True, required=False, help_text="the 13 patterns, each once (new: all blank)")
    has_file = serializers.SerializerMethodField(help_text="its signed copy is kept: file/")

    class Meta:
        model = DarkPatternAudit
        fields = [
            *["id", "year", "rows", "certificate_text", "effective_from", "completed_at", "completed_by"],
            *["created", "created_by", "has_file"],
        ]
        read_only_fields = ["completed_at", "completed_by", "created", "created_by"]

    def get_has_file(self, audit_row) -> bool:
        return bool(audit_row.certificate_file)

    def validate_year(self, year):
        if not compliance.FIRST_CERTIFICATE_YEAR - 1 <= year <= timezone.localdate().year + 1:
            raise serializers.ValidationError("From 2026 to next year.")
        if self.instance is not None and year != self.instance.year:
            raise serializers.ValidationError("A self-audit keeps its year.")
        return year

    def validate_rows(self, rows):
        if sorted(row["pattern"] for row in rows) != sorted(PATTERNS):
            raise serializers.ValidationError("The 13 named patterns, each once.")
        order = list(PATTERNS)
        return sorted(
            [{"pattern": row["pattern"], "finding": row["finding"], "fix": row["fix"]} for row in rows],
            key=lambda row: order.index(row["pattern"]),
        )

    def create(self, validated_data):  # `rows` is a JSON field: written as it is
        return DarkPatternAudit.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save(update_fields=[*validated_data])
        return instance


class CompleteSerializer(serializers.Serializer):
    effective_from = serializers.DateField(required=False, help_text="shown on the website from (today if empty)")


class CertificateFileSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="the signed certificate: PDF, PNG or JPEG, 5 MB at most")

    def validate_file(self, upload):
        if upload.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("5 MB at most.")
        if Path(upload.name).suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg"):
            raise serializers.ValidationError("A PDF, PNG or JPEG file.")
        return upload


class DarkPatternAuditViewSet(
    PrivacyView,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """The yearly dark-pattern self-audit (the CCPA's 13 named patterns): a finding and a fix for each, the
    certificate's text and its signed copy; completed once (then unchanged), its certificate shown on the website
    from its day (config/)."""

    serializer_class = DarkPatternAuditSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "file"], "staff.view_darkpatternaudit"),
        **dict.fromkeys(["create", "update", "partial_update", "complete", "upload"], "staff.manage_compliance"),
    }
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return scoped(DarkPatternAudit.objects.all(), self.request.user, "staff.view_darkpatternaudit")

    def perform_create(self, serializer):
        if DarkPatternAudit.objects.filter(year=serializer.validated_data["year"]).exists():
            raise refused("That year's self-audit exists: open it.", "year")
        with transaction.atomic():
            audit_row = serializer.save(created_by=self.human())
            audit.record("dark_pattern_audit.created", request=self.request, target=audit_row,
                         details={"year": audit_row.year})  # fmt: skip

    def perform_update(self, serializer):
        if serializer.instance.completed_at:
            raise refused("Completed: a self-audit stays as it was signed. Start next year's.")
        with transaction.atomic():
            audit_row = serializer.save()
            audit.record("dark_pattern_audit.updated", request=self.request, target=audit_row,
                         details={"fields": sorted(serializer.validated_data)})  # fmt: skip

    @extend_schema(request=CompleteSerializer, responses=DarkPatternAuditSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, *args, **kwargs):
        data = CompleteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            audit_row = DarkPatternAudit.objects.select_for_update().get(pk=self.get_object().pk)
            if audit_row.completed_at:
                raise refused("Completed already.")
            missing = [PATTERNS[row["pattern"]] for row in audit_row.rows if not (row["finding"] and row["fix"])]
            if missing:
                raise refused(f"A finding and a fix for each pattern first: {', '.join(missing)}.", "rows")
            if not audit_row.certificate_text.strip():
                raise refused("The certificate's text first.", "certificate_text")
            audit_row.completed_at, audit_row.completed_by = timezone.now(), self.human()
            audit_row.effective_from = data.validated_data.get("effective_from") or audit_row.effective_from
            audit_row.effective_from = audit_row.effective_from or timezone.localdate()
            audit_row.save(update_fields=["completed_at", "completed_by", "effective_from"])
            reminder = {"target_type": "staff.darkpatternaudit", "target_id": f"year:{audit_row.year}"}
            InboxItem.objects.filter(kind=InboxItem.Kind.COMPLIANCE, done_at=None, **reminder).update(
                done_at=timezone.now(), done_by=audit_row.completed_by
            )
            audit.record("dark_pattern_audit.completed", request=request, target=audit_row,
                         details={"year": audit_row.year, "effective_from": audit_row.effective_from})  # fmt: skip
        return Response(self.get_serializer(audit_row).data)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY}, request=None)
    @action(detail=True, methods=["get"], parser_classes=[MultiPartParser])  # (the POST below: the signed copy)
    def file(self, request, *args, **kwargs):
        audit_row = self.get_object()
        if not audit_row.certificate_file:
            raise exceptions.NotFound("No signed copy is kept.")
        audit.record("dark_pattern_audit.file_read", request=request, target=audit_row)
        if not isinstance(default_storage, FileSystemStorage):  # the bucket's own link, signed for 5 minutes
            return HttpResponseRedirect(default_storage.url(audit_row.certificate_file))
        name = audit_row.certificate_file.rsplit("/", 1)[-1]
        return FileResponse(default_storage.open(audit_row.certificate_file, "rb"), as_attachment=True, filename=name)

    @extend_schema(request={"multipart/form-data": CertificateFileSerializer}, responses=DarkPatternAuditSerializer)
    @file.mapping.post
    def upload(self, request, *args, **kwargs):
        audit_row = self.get_object()
        data = CertificateFileSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        suffix = Path(upload.name).suffix.lower()
        name = default_storage.save(f"compliance/dark-patterns/certificate-{audit_row.year}{suffix}", upload)
        old = audit_row.certificate_file
        with transaction.atomic():
            DarkPatternAudit.objects.filter(pk=audit_row.pk).update(certificate_file=name)
            audit.record("dark_pattern_audit.file_kept", request=request, target=audit_row)
            if old and old != name:
                transaction.on_commit(lambda: default_storage.delete(old), robust=True)
        audit_row.refresh_from_db()
        return Response(self.get_serializer(audit_row).data)


router = SimpleRouter()
router.register("privacy/holds", LegalHoldViewSet, basename="privacy-hold")
router.register("privacy/policies", PolicyViewSet, basename="privacy-policy")
router.register("privacy/dark-pattern-audits", DarkPatternAuditViewSet, basename="privacy-dark-pattern-audit")

urlpatterns = [
    path("privacy/cockpit/", CockpitView.as_view(), name="privacy-cockpit"),
    path("privacy/retention/", RetentionView.as_view(), name="privacy-retention"),
    path("privacy/disclosures/", DisclosuresView.as_view(), name="privacy-disclosures"),
    path("privacy/nominees/<int:user>/", NomineeView.as_view(), name="privacy-nominee"),
    path("privacy/nominees/<int:user>/reveal/", NomineeRevealView.as_view(), name="privacy-nominee-reveal"),
    path(
        "privacy/deletions/<int:pk>/parent-confirmation/",
        DeletionParentView.as_view(),
        name="privacy-deletion-parent",
    ),
    *router.urls,
]
