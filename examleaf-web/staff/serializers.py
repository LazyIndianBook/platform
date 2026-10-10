"""The staff API's serializers: explicit fields only (no mass assignment), personal data masked unless revealed."""

from datetime import date, timedelta

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from accounts import roles
from api.views import DetailSerializer  # noqa: F401  (the API's own, one schema component)

from . import catalogue
from .config import FLAG_KEY
from .models import (
    ApiKey,
    Approval,
    AuditEvent,
    ChangeRequest,
    DataRequest,
    InboxItem,
    Incident,
    Job,
    Note,
    OffboardingStep,
    PolicyAcknowledgement,
    ProcessorRecord,
    RoleGrant,
    SavedView,
    StaffInvite,
    StaffOffboarding,
    StaffScope,
)
from .privacy import mask_email, mask_ip, mask_phone

User = get_user_model()


def has_second_factor(user):
    return is_mfa_enabled(user, [Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN])


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, help_text="Why: kept in the audit log")


class BreakGlassReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=10, max_length=500, help_text="why nothing else works: the owners read it"
    )


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            *["id", "chain", "ts", "actor_id", "actor_type", "actor_roles", "on_behalf_of", "break_glass", "action"],
            *["permission", "target_type", "target_id", "target_label", "outcome", "reason", "change_request_id"],
            "request_id",
            *["ip", "user_agent", "session_hash", "changes", "details", "prev_hash", "hash"],
        ]


class ApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Approval
        fields = ["user", "decision", "comment", "created"]


class ChangeRequestSerializer(serializers.ModelSerializer):
    approvals = ApprovalSerializer(many=True, read_only=True)
    checker = serializers.SerializerMethodField(help_text="the permission an approver needs")
    label = serializers.SerializerMethodField()

    class Meta:
        model = ChangeRequest
        fields = [
            *["id", "action", "label", "target_type", "target_id", "target_label", "payload", "payload_sha256"],
            *["amount", "maker", "reason", "rule", "status", "expires_at", "overridden", "checker", "approvals"],
            *["result", "executed_by", "executed_at", "created", "modified"],
        ]

    def get_checker(self, change_request) -> str:
        from .approvals import ACTIONS

        return ACTIONS[change_request.action].checker_for(change_request)

    def get_label(self, change_request) -> str:
        from .approvals import ACTIONS

        return ACTIONS[change_request.action].label


class AskSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[],
        help_text="order.refund, order.offline_payment, product.price, coupon.create, coupon.change, "
        "offer.create, offer.change",
    )
    target = serializers.CharField(
        max_length=64,
        help_text="an order's number, a product's slug, a coupon's code, an offer's id (\"new\" for a new one)",
    )
    payload = serializers.DictField(help_text="the action's details: amount, reference, price, value …")
    reason = serializers.CharField(max_length=500)

    def __init__(self, *args, **kwargs):
        from .approvals import ACTIONS

        super().__init__(*args, **kwargs)
        self.fields["action"].choices = [name for name, action in ACTIONS.items() if action.generic]


class ApproveSerializer(serializers.Serializer):
    payload_sha256 = serializers.CharField(max_length=64, help_text="the hash of the payload you read")
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    override = serializers.BooleanField(required=False, default=False, help_text="an owner approves their own")


class CommentSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class InboxItemSerializer(serializers.ModelSerializer):
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = InboxItem
        fields = [
            *["id", "kind", "title", "target_type", "target_id", "permission", "assignee", "due_at", "overdue"],
            *["snoozed_until", "done_at", "done_by", "data", "created"],
        ]

    def get_overdue(self, item) -> bool:
        return bool(item.due_at and item.done_at is None and item.due_at < timezone.now())


class SnoozeSerializer(serializers.Serializer):
    until = serializers.DateTimeField()


class AssignSerializer(serializers.Serializer):
    assignee = serializers.IntegerField(allow_null=True, help_text="a member of staff's id; null: nobody")


class InboxCountSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    overdue = serializers.IntegerField()


class JobErrorSerializer(serializers.Serializer):
    id = serializers.JSONField(allow_null=True, help_text="the row's target (an order number, an id), null: the job's")
    label = serializers.CharField()
    message = serializers.CharField()


class JobSerializer(serializers.ModelSerializer):
    errors = JobErrorSerializer(many=True, read_only=True, help_text="the rows that failed (the first 1,000)")
    result_url = serializers.SerializerMethodField(help_text="its file, signed for 5 minutes; its starter only")
    change_request_id = serializers.IntegerField(read_only=True, allow_null=True, help_text="the approval it waits for")
    started_by = serializers.IntegerField(source="started_by_id", read_only=True, allow_null=True)

    class Meta:
        model = Job
        fields = ["id", "kind", "state", "dry_run", "params", "done", "total", "errors", "result", "result_url"]
        fields += ["change_request_id", "cancel_requested", "started_by", "created", "started_at", "finished_at"]
        read_only_fields = fields

    def get_result_url(self, job) -> str | None:
        from .jobs import result_url

        return result_url(job, self.context.get("request"))


def order_jobs():
    from shop import order_jobs

    return order_jobs


def catalogue_jobs():
    from shop import catalogue_jobs

    return catalogue_jobs


class JobStartSerializer(serializers.Serializer):
    MAX_TARGETS = 10_000

    kind = serializers.ChoiceField(choices=Job.Kind.choices)
    params = serializers.DictField(
        required=False,
        default=dict,
        help_text='audit_export: {"filters": {…}} (the audit list\'s); bulk_action: {"action": "order.refund", '
        '"targets": [order numbers, slugs or ids], "payload": {…} (each target\'s, as for change-requests/), '
        '"reason"}; erp_initial_load: {"invoices_from": "YYYY-MM-DD"} (optional: without it, the catalogue only); '
        'gstr1_export: {"month": "YYYY-MM", "months": 1 or 3} (a month, or the quarter ending with it); '
        'orders_pack, orders_print ({"document": packing_slip, label or invoices}) and orders_cancel ({"reason", '
        '"customer_requested"}, 250 at most): {"targets": [order numbers]}; orders_export: {"filters": {…}} (the '
        "order list's); "
        'content_import: {"subject": "physics", "commit": "" or a commit, "dry_run_job": the dry run\'s id (to '
        "apply)}; "
        'grievance_export: {"from": "YYYY-MM-DD", "until": "YYYY-MM-DD"} (the days received, both optional); '
        'settlement_fetch: {"day": "YYYY-MM-DD"} (a day of Razorpay\'s settlements, India, from 2020 to today); '
        'report_export: {"report": "sales", "filters": {...}} (the report\'s own filters: reports/); '
        'coupon_codes: {"coupon": a single-use coupon\'s code, "count", "prefix", "note": the school\'s name}; '
        'product_import: {"file": catalogue/import/\'s, "dry_run_job": the dry run\'s id (to apply)}; '
        'product_export: {"filters": {…}} (the product list\'s); '
        'code_batch: {"batch": a batch\'s id} (its codes made again after a failed job: course/codes/batches/ makes '
        "a new one)",
    )
    dry_run = serializers.BooleanField(required=False, default=False, help_text="check every row, change nothing")

    def validate(self, data):
        from .jobs import bulk_actions

        params = data["params"]
        if data["kind"] == Job.Kind.AUDIT_EXPORT:
            filters = params.get("filters", {})
            if not isinstance(filters, dict):
                raise serializers.ValidationError({"params": {"filters": ["The audit list's filters, as an object."]}})
            data["params"] = {"filters": filters}
            return data
        if data["kind"] == Job.Kind.GSTR1_EXPORT:
            from shop.staff_tax import gstr1_period

            data["params"] = gstr1_period(params)
            return data
        if data["kind"] in order_jobs().PERMISSIONS:  # the Orders module's: shop/order_jobs.py
            data["params"] = order_jobs().params_for(data["kind"], params)
            return data
        if data["kind"] in catalogue_jobs().PERMISSIONS:  # the Catalogue module's: shop/catalogue_jobs.py
            data["params"] = catalogue_jobs().params_for(data["kind"], params, data["dry_run"])
            return data
        if data["kind"] == Job.Kind.CONTENT_IMPORT:
            from content.imports import clean_params

            data["params"] = clean_params(params, dry_run=data["dry_run"])
            return data
        if data["kind"] == Job.Kind.GRIEVANCE_EXPORT:
            data["params"] = {}
            for name in ("from", "until"):
                try:
                    if day := params.get(name):
                        data["params"][name] = date.fromisoformat(str(day)).isoformat()
                except ValueError:
                    raise serializers.ValidationError({"params": {name: ["A day: YYYY-MM-DD."]}}) from None
            if data["params"].get("from", "") > data["params"].get("until", "9999"):
                raise serializers.ValidationError({"params": {"until": ["Not before the first day."]}})
            return data
        if data["kind"] == Job.Kind.SETTLEMENT_FETCH:  # Phase B: finance
            from shop.settlements import job_params

            data["params"] = job_params(params)
            return data
        if data["kind"] == Job.Kind.REPORT_EXPORT:
            from insights.exports import clean_params as report_params

            data["params"] = report_params(params)
            return data
        if data["kind"] == Job.Kind.CODE_BATCH:  # a batch's codes made again after its first job failed (learn.codes)
            from learn.codes import job_params

            if data["dry_run"]:
                raise serializers.ValidationError({"dry_run": ["Making book codes has no dry run."]})
            data["params"] = job_params(params)
            return data
        if data["kind"] == Job.Kind.ERP_INITIAL_LOAD:
            since = params.get("invoices_from")
            try:
                data["params"] = {"invoices_from": date.fromisoformat(since).isoformat() if since else None}
            except TypeError, ValueError:
                raise serializers.ValidationError({"params": {"invoices_from": ["A day: YYYY-MM-DD."]}}) from None
            return data
        action, targets, payload = params.get("action"), params.get("targets"), params.get("payload", {})
        reason = str(params.get("reason") or "").strip()
        problems = {}
        if action not in bulk_actions():
            problems["action"] = [f"One of {', '.join(bulk_actions())}."]
        if not isinstance(targets, list) or not targets or not all(isinstance(t, str | int) for t in targets):
            problems["targets"] = ["A list of order numbers, slugs or ids."]
        elif len(targets) > self.MAX_TARGETS or len({str(t) for t in targets}) != len(targets):
            problems["targets"] = [f"At most {self.MAX_TARGETS:,}, each once."]
        if not isinstance(payload, dict):
            problems["payload"] = ["An object: each target's payload."]
        if not reason:
            problems["reason"] = ["Say why."]
        if problems:
            raise serializers.ValidationError({"params": problems})
        data["params"] = {"action": action, "targets": targets, "payload": payload, "reason": reason[:500]}
        return data


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ["id", "target_type", "target_id", "author", "body", "pinned", "created"]
        read_only_fields = ["id", "author", "created"]


class PolicyAcknowledgementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyAcknowledgement
        fields = ["id", "user", "policy", "version", "acknowledged_at"]
        read_only_fields = ["id", "user", "acknowledged_at"]


class SavedViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedView
        fields = ["id", "owner", "role", "list_key", "name", "filters", "columns", "sort", "created", "modified"]
        read_only_fields = ["owner", "created", "modified"]

    def validate_role(self, role):
        from .services import staff_roles

        if role and role not in staff_roles(self.context["request"].user):
            raise serializers.ValidationError("Share only with a role you hold.")
        return role


SETTING_SOURCES = ["environment", "database"]  # where a switch's value comes from (SettingSourceEnum)


class SettingSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.JSONField(help_text='"bool", "str", or the allowed values')
    permission = serializers.CharField(help_text="what changing it needs")
    value = serializers.JSONField(help_text="in effect now")
    environment = serializers.JSONField(help_text="the environment's value (settings.py, .env)")
    source = serializers.ChoiceField(choices=SETTING_SOURCES)
    effective_from = serializers.DateTimeField(allow_null=True)
    changed_by = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)
    scheduled = serializers.ListField(child=serializers.DictField(), help_text="changes still to come")
    group = serializers.CharField(help_text="the Settings page's section: shop, consent, course, maintenance …")


class SwitchRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    value = serializers.JSONField()
    effective_from = serializers.DateTimeField()
    changed_by = serializers.IntegerField(source="changed_by_id", allow_null=True)
    reason = serializers.CharField()
    created = serializers.DateTimeField()


class SwitchChangeSerializer(serializers.Serializer):
    value = serializers.JSONField(
        allow_null=True, help_text="the new value; null: back to the environment's (a flag: off)"
    )
    reason = serializers.CharField(max_length=300)
    effective_from = serializers.DateTimeField(required=False, help_text="from when (now unless given)")


class FlagSerializer(serializers.Serializer):
    key = serializers.RegexField(FLAG_KEY.pattern)
    value = serializers.JSONField(help_text="in effect now (a known flag not set: the environment's)")
    effective_from = serializers.DateTimeField(allow_null=True, help_text="null: a known flag never set")
    changed_by = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True, help_text="a known flag's (staff.config.KNOWN_FLAGS)")
    group = serializers.CharField(help_text="the Settings page's section: erp, or flags for any other")
    environment = serializers.JSONField(allow_null=True, help_text="a known flag's value in the environment")
    source = serializers.ChoiceField(choices=SETTING_SOURCES)


class ApiKeySerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField(help_text="the whole key: only in the answer that made it")

    class Meta:
        model = ApiKey
        fields = [
            *["id", "name", "prefix", "key", "scopes", "sponsor", "created_by", "created", "expires_at"],
            *["allowed_ips", "last_used_at", "last_used_ip", "revoked_at", "revoked_by"],
        ]
        read_only_fields = ["prefix", "created_by", "created", "last_used_at", "last_used_ip", "revoked_at"]
        read_only_fields += ["revoked_by"]
        extra_kwargs = {"sponsor": {"required": False}, "expires_at": {"required": False}}

    def get_key(self, key) -> str | None:
        return getattr(key, "whole_key", None)

    def validate_scopes(self, scopes):
        user = self.context["request"].user
        for perm in scopes:
            entry = catalogue.entry(perm)
            if entry is None or entry.risk != catalogue.LOW or ".view_" not in perm:
                raise serializers.ValidationError(f"{perm}: keys hold catalogued view permissions only.")
            if not user.has_perm(perm):
                raise serializers.ValidationError(f"{perm}: you cannot give what you do not have.")
        if not scopes:
            raise serializers.ValidationError("At least one permission.")
        return sorted(set(scopes))

    def validate_allowed_ips(self, networks):
        import ipaddress

        for network in networks:
            try:
                ipaddress.ip_network(network, strict=False)
            except ValueError as error:
                raise serializers.ValidationError(f"{network}: not an address or a network.") from error
        return networks

    def validate_expires_at(self, expires_at):
        now = timezone.now()
        if not now < expires_at <= now + timedelta(days=366):
            raise serializers.ValidationError("Within the next 12 months.")
        return expires_at

    def validate_sponsor(self, sponsor):
        if not (sponsor.is_active and sponsor.is_staff):
            raise serializers.ValidationError("A member of staff answers for the key.")
        return sponsor


class RoleGrantSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleGrant
        fields = ["role", "granted_by", "reason", "created", "expires_at"]


class ScopeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffScope
        fields = ["id", "kind", "value", "granted_by", "created", "expires_at"]
        read_only_fields = ["granted_by", "created"]


class PersonSerializer(serializers.ModelSerializer):
    """A member of staff (their own colleagues see their work address and name)."""

    roles = serializers.SerializerMethodField()
    grants = serializers.SerializerMethodField()
    scopes = ScopeSerializer(source="staff_scopes", many=True, read_only=True)
    mfa = serializers.SerializerMethodField(help_text="an authenticator app or a passkey is set up")

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "is_active", "is_superuser", "roles", "grants", "scopes", "mfa"]
        fields += ["last_login", "created"]

    def get_roles(self, user) -> list[str]:
        return sorted(group.name for group in user.groups.all())  # prefetched (staff.api.PeopleViewSet)

    def get_grants(self, user) -> list[dict]:
        return RoleGrantSerializer(user.role_grants.all(), many=True).data

    def get_mfa(self, user) -> bool:
        return has_second_factor(user)


class GrantSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=sorted(roles.STAFF_ROLES))
    expires_at = serializers.DateTimeField(required=False, allow_null=True, help_text="taken away after (JIT)")
    reason = serializers.CharField(max_length=300)

    def validate_expires_at(self, expires_at):
        if expires_at and expires_at <= timezone.now():
            raise serializers.ValidationError("In the future.")
        return expires_at


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=sorted(roles.STAFF_ROLES))
    reason = serializers.CharField(max_length=300)


class StaffInviteSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = StaffInvite
        fields = ["id", "email", "role", "invited_by", "created", "expires_at", "accepted_at", "accepted_by"]
        fields += ["revoked_at"]

    def get_email(self, invite) -> str:
        return mask_email(invite.email)


class AcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=100)
    full_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, allow_blank=True, default="", write_only=True)


class ScopeAddSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=StaffScope.Kind.choices)
    value = serializers.CharField(max_length=120)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AccessRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    roles = serializers.ListField(child=serializers.CharField())
    grants = serializers.ListField(child=serializers.DictField())
    scopes = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    last_login = serializers.DateTimeField(allow_null=True)
    dormant = serializers.BooleanField(help_text="no log-in for STAFF_DORMANT_DAYS")
    mfa = serializers.BooleanField()
    permissions = serializers.IntegerField(help_text="how many it holds")
    unused = serializers.ListField(child=serializers.CharField(), help_text="action permissions unused in 90 days")
    last_used = serializers.DictField(child=serializers.DateTimeField(), help_text="permission: last use")


def customer_status(user) -> str:
    """From the prefetched deletion requests (staff.api.UserViewSet): no query per row."""
    if user.email.endswith("@deleted.invalid"):
        return "erased"
    if not user.is_active:
        return "suspended"
    if any(deletion.status == "pending" for deletion in user.deletion_requests.all()):
        return "pending_deletion"
    return "active"


def consent_state(user) -> str:
    """adult; for a student under 18: verified (a parent confirmed through the link), pending (a confirmation awaited:
    PARENTAL_CONSENT_MODE "verified", as accounts.models.User.consent_pending), else declared. From the prefetched
    consent records."""
    from staff.config import site_setting

    if not user.is_minor:
        return "adult"
    if any(record.event == "given" and record.verified_at for record in user.consents.all()):
        return "verified"
    return "pending" if site_setting("PARENTAL_CONSENT_MODE") == "verified" else "declared"


class CustomerSerializer(serializers.ModelSerializer):
    """A customer as support sees one: contact details masked (reveal/ shows them, logged)."""

    email = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    board = serializers.SlugRelatedField(slug_field="short_name", read_only=True)
    under_18 = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    consent = serializers.SerializerMethodField(help_text="adult, declared, pending, verified")
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "phone", "full_name", "class_level", "board", "district", "under_18", "status"]
        fields += ["consent", "email_verified", "login_phone_verified", "created", "last_login"]

    def get_email(self, user) -> str:
        return mask_email(user.email)

    def get_phone(self, user) -> str:
        return mask_phone(user.login_phone or user.phone)

    def get_under_18(self, user) -> bool:
        return user.is_minor

    def get_status(self, user) -> str:
        return customer_status(user)

    def get_consent(self, user) -> str:
        return consent_state(user)

    def get_email_verified(self, user) -> bool:
        return any(address.verified for address in user.emailaddress_set.all())


class CustomerDetailSerializer(CustomerSerializer):
    roles = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField(help_text="locked out by failed log-ins (axes)")
    mfa = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField(help_text="none, requested, verified")
    parent_contact = serializers.SerializerMethodField()
    orders = serializers.SerializerMethodField()
    consents = serializers.SerializerMethodField()
    sessions = serializers.SerializerMethodField()
    deletion_due_at = serializers.SerializerMethodField()

    class Meta(CustomerSerializer.Meta):
        fields = [*CustomerSerializer.Meta.fields, "roles", "locked", "mfa", "teacher", "parent_contact", "orders"]
        fields += ["consents", "sessions", "deletion_due_at"]

    def get_roles(self, user) -> list[str]:
        return sorted(user.groups.values_list("name", flat=True))

    def get_locked(self, user) -> bool:
        from axes.models import AccessAttempt
        from django.conf import settings

        names = [user.email, *([user.login_phone] if user.login_phone else [])]
        attempts = AccessAttempt.objects.filter(username__in=names).values_list("failures_since_start", flat=True)
        return any(count >= settings.AXES_FAILURE_LIMIT for count in attempts)

    def get_mfa(self, user) -> list[str]:
        return sorted(set(user.authenticator_set.values_list("type", flat=True)))

    def get_teacher(self, user) -> str:
        profile = getattr(user, "teacher_profile", None)
        return "none" if profile is None else ("verified" if profile.verified else "requested")

    def get_parent_contact(self, user) -> str:
        contact = user.parent_contact
        return mask_email(contact) if "@" in contact else mask_phone(contact)

    def get_orders(self, user) -> list[dict]:
        return list(user.orders.order_by("-created").values("number", "status", "created")[:10])

    def get_consents(self, user) -> list[dict]:
        return list(user.consents.values("event", "method", "by_parent", "verified_at", "notice_version", "created"))

    def get_sessions(self, user) -> list[dict]:
        return [
            {"ip": mask_ip(row["ip"]), "user_agent": row["user_agent"], "last_seen_at": row["last_seen_at"]}
            for row in user.usersession_set.values("ip", "user_agent", "last_seen_at")
        ]

    def get_deletion_due_at(self, user) -> str | None:
        deletion = user.pending_deletion
        return deletion.due_at.isoformat() if deletion else None


REVEALABLE = ["email", "phone", "login_phone", "parent_contact", "parent_name", "date_of_birth"]


class RevealSerializer(serializers.Serializer):
    show = serializers.MultipleChoiceField(choices=REVEALABLE, help_text="the details to show")
    reason = serializers.CharField(min_length=5, max_length=300, help_text="why: kept in the audit log")


class ImpersonateSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=300)
    ticket = serializers.CharField(max_length=60, help_text="the support ticket or mail it answers")


class ImpersonationSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="for the website's account area; 15 minutes")
    expires_at = serializers.DateTimeField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class ImpersonatedUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.CharField(help_text="masked")


class ImpersonatingSerializer(serializers.Serializer):
    until = serializers.DateTimeField(help_text="the session ends then")
    user = ImpersonatedUserSerializer()


class DataRequestSerializer(serializers.ModelSerializer):
    ack_overdue = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = DataRequest
        fields = [
            *["id", "kind", "channel", "user", "requester", "summary", "identity_verified", "identity_note"],
            *["verified_by", "verified_at", "received_at", "ack_due_at", "acknowledged_at", "ack_overdue", "due_at"],
            *["overdue", "status", "assignee", "notes", "details", "outcome", "response", "closed_at", "closed_by"],
            "created_by",
        ]
        read_only_fields = [
            *["identity_verified", "identity_note", "verified_by", "verified_at", "ack_due_at", "acknowledged_at"],
            *["due_at", "status", "outcome", "response", "closed_at", "closed_by", "created_by"],
        ]

    def get_ack_overdue(self, request) -> bool:
        return request.acknowledged_at is None and request.ack_due_at < timezone.now()

    def get_overdue(self, request) -> bool:
        return request.status != DataRequest.Status.CLOSED and request.due_at < timezone.now()

    def validate_assignee(self, user):
        if user is not None and not user.is_staff:
            raise serializers.ValidationError("A member of staff.")
        return user


class DataRequestListSerializer(DataRequestSerializer):
    requester = serializers.SerializerMethodField(help_text="masked in lists")

    def get_requester(self, request) -> str:
        contact = request.requester
        return mask_email(contact) if "@" in contact else mask_phone(contact)


class VerifyIdentitySerializer(serializers.Serializer):
    note = serializers.CharField(max_length=300, help_text="how it was checked: the method, not the document")


class CloseSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=DataRequest.Outcome.choices)
    response = serializers.CharField(help_text="the answer sent, as sent")


class ResponseTextSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()


class ErasureEraseSerializer(serializers.Serializer):
    part = serializers.CharField()
    what = serializers.CharField()
    count = serializers.IntegerField()


ERASURE_KEEP_KINDS = ["books", "processing_logs", "legal_hold", "intermediary", "consent", "statistics", "by_hand"]
ERASURE_KEEP_KINDS += ["test"]  # orders made in test mode: shown apart from the books


class ErasureKeepSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ERASURE_KEEP_KINDS, help_text="the hold: the books, the year of logs …")
    part = serializers.CharField()
    what = serializers.CharField()
    count = serializers.IntegerField()
    why = serializers.CharField()
    until = serializers.DateField(allow_null=True, help_text="the last day it is kept; null: no end set")
    line = serializers.CharField(help_text='in words: "kept until 31 March 2035: 3 invoices …, for GST …"')


class ErasureReportSerializer(serializers.Serializer):
    erase = ErasureEraseSerializer(many=True)
    keep = ErasureKeepSerializer(many=True)
    blocks = serializers.ListField(child=serializers.CharField())
    can_erase = serializers.BooleanField()
    notes = serializers.ListField(child=serializers.CharField())


class IncidentSerializer(serializers.ModelSerializer):
    cert_in_due = serializers.DateTimeField(read_only=True)
    board_due = serializers.DateTimeField(read_only=True)
    cert_in_overdue = serializers.SerializerMethodField()
    board_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            *["id", "title", "kind", "detected_at", "noticed_by", "description", "systems", "data_categories"],
            *["people_affected", "children_affected", "cert_in_due", "cert_in_overdue", "cert_in_reported_at"],
            *["cert_in_reference", "board_due", "board_overdue", "board_notified_at", "board_report_at"],
            *["board_reference", "notice_text", "notices_sent", "notices_sent_at", "actions", "root_cause"],
            *["closed_at", "closed_by", "created"],
        ]
        read_only_fields = ["noticed_by", "closed_at", "closed_by", "created"]

    def get_cert_in_overdue(self, incident) -> bool:
        return incident.cert_in_reported_at is None and incident.cert_in_due < timezone.now()

    def get_board_overdue(self, incident) -> bool:
        return incident.board_report_at is None and incident.board_due < timezone.now()


class ProcessorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessorRecord
        fields = ["id", "name", "purpose", "data_categories", "country", "contract_signed_on", "contract_ends_on"]
        fields += ["active", "notes", "holds_personal_data", "holds_marketing_data", "erasure_action"]


class ReconcileSerializer(serializers.Serializer):
    order = serializers.CharField(max_length=20, help_text="the order's number")


# Phase B: the role catalogue, the Access tab, a role change's preview, offboarding's checklist, ERPNext's role mirror,
# a person's own sessions (staff.services)

STAFF_ROLE_CHOICES = sorted(roles.STAFF_ROLES)


class CapabilitySerializer(serializers.Serializer):
    perm = serializers.CharField(help_text="app_label.codename")
    label = serializers.CharField()
    area = serializers.CharField()
    risk = serializers.ChoiceField(choices=catalogue.RISKS)
    reauth = serializers.BooleanField(help_text="needs a re-authentication in the last 5 minutes")
    approval = serializers.BooleanField(help_text="may wait for a second person")
    alert = serializers.BooleanField(help_text="the owners are told")
    last_used = serializers.DateTimeField(
        allow_null=True, required=False, help_text="the Access tab: its last use in a year (high and critical ones)"
    )


class CapabilityAreaSerializer(serializers.Serializer):
    area = serializers.CharField()
    permissions = CapabilitySerializer(many=True)


class RoleCardSerializer(serializers.Serializer):
    cannot = serializers.CharField(help_text="they can't …")

    def get_fields(self):  # "for": a Python keyword, a field all the same
        return {"for": serializers.CharField(help_text="for people who need to …"), **super().get_fields()}


class RoleCatalogueSerializer(serializers.Serializer):
    name = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    card = RoleCardSerializer()
    privileged = serializers.BooleanField(help_text="given only with a second person's approval")
    admin_site = serializers.BooleanField(help_text="opens the Django admin")
    passkey = serializers.BooleanField(help_text="its members need a passkey or a security key")
    idle_timeout_s = serializers.IntegerField()
    limits = serializers.DictField(child=serializers.IntegerField(allow_null=True), help_text="null: no limit")
    scopes = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    conflicts = serializers.ListField(child=serializers.CharField(), help_text="roles it may not be held with")
    erp_profiles = serializers.ListField(child=serializers.CharField(), help_text="its ERPNext role profiles")
    members = serializers.IntegerField(help_text="active members")
    permissions = serializers.IntegerField()
    capabilities = CapabilityAreaSerializer(many=True)


class AccessRoleSerializer(serializers.Serializer):
    name = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    source = serializers.ChoiceField(choices=["panel", "admin"], help_text="admin: given in the Django admin, no grant")
    granted_by = serializers.IntegerField(allow_null=True)
    granted_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)


class AccessScopeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=StaffScope.Kind.choices)
    value = serializers.CharField()
    granted_by = serializers.IntegerField(allow_null=True)
    created = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)


class AccessPendingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.CharField()
    status = serializers.ChoiceField(choices=ChangeRequest.Status.choices)
    target_label = serializers.CharField(allow_blank=True)
    about_them = serializers.BooleanField()
    by_them = serializers.BooleanField()
    created = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()


class SecondFactorsSerializer(serializers.Serializer):
    authenticator_app = serializers.BooleanField()
    passkey = serializers.BooleanField(help_text="a passkey or a security key")
    recovery_codes = serializers.BooleanField()


class AccessSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    last_login = serializers.DateTimeField(allow_null=True)
    roles = AccessRoleSerializer(many=True)
    scopes = AccessScopeSerializer(many=True)
    role_scopes = serializers.DictField(child=serializers.DictField(), help_text="the roles' own narrowing")
    limits = serializers.DictField(child=serializers.IntegerField(allow_null=True), help_text="null: no limit")
    idle_timeout_s = serializers.IntegerField()
    permissions = serializers.IntegerField(help_text="how many it holds")
    capabilities = CapabilityAreaSerializer(many=True)
    pending = AccessPendingSerializer(many=True, help_text="change requests about them or by them, still open")
    second_factors = SecondFactorsSerializer()
    passkey_required = serializers.BooleanField(help_text="their role needs a passkey they have not added")
    erp_profiles = serializers.ListField(child=serializers.CharField())


class RolePreviewRequestSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    action = serializers.ChoiceField(choices=["grant", "revoke"], default="grant")


class LimitChangeSerializer(serializers.Serializer):
    name = serializers.CharField()
    before = serializers.IntegerField(allow_null=True, help_text="null: no limit")
    after = serializers.IntegerField(allow_null=True)


class RoleScopeChangeSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    scopes = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    added = serializers.BooleanField(help_text="false: the narrowing goes with the role")


class ConflictSerializer(serializers.Serializer):
    roles = serializers.ListField(child=serializers.CharField())
    text = serializers.CharField()


class BeforeAfterSecondsSerializer(serializers.Serializer):
    before = serializers.IntegerField()
    after = serializers.IntegerField()


class BeforeAfterProfilesSerializer(serializers.Serializer):
    before = serializers.ListField(child=serializers.CharField())
    after = serializers.ListField(child=serializers.CharField())


class RolePreviewSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    action = serializers.ChoiceField(choices=["grant", "revoke"])
    holds_already = serializers.BooleanField(help_text="a grant of a role held: only its end date would change")
    gains = CapabilityAreaSerializer(many=True)
    losses = CapabilityAreaSerializer(many=True)
    limits = LimitChangeSerializer(many=True, help_text="the limits that change")
    scopes = RoleScopeChangeSerializer(many=True)
    idle_timeout_s = BeforeAfterSecondsSerializer()
    conflicts = ConflictSerializer(many=True, help_text="separation of duties: the grant would be refused")
    blocked = serializers.BooleanField()
    needs_approval = serializers.BooleanField()
    rule = serializers.CharField(allow_blank=True, help_text="why a second person approves it")
    checker = serializers.CharField(allow_blank=True, help_text="the permission its approver needs")
    passkey_needed = serializers.BooleanField(help_text="the role needs a passkey they have not added")
    erp_profiles = BeforeAfterProfilesSerializer()


class OffboardingStepSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = OffboardingStep
        fields = ["key", "label", "kind", "state", "detail", "done_at", "done_by"]

    def get_label(self, step) -> str:
        from .services import STEP_LABELS

        return STEP_LABELS.get(step.key, step.key)


class OffboardingSerializer(serializers.ModelSerializer):
    steps = OffboardingStepSerializer(many=True, read_only=True)

    class Meta:
        model = StaffOffboarding
        fields = ["id", "user", "started_by", "reason", "started_at", "finished_at", "steps"]


class OffboardingTickSerializer(serializers.Serializer):
    step = serializers.CharField(max_length=40, help_text="a step done by hand: its key")
    state = serializers.ChoiceField(choices=OffboardingStep.State.choices)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ErpRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
    profiles = serializers.ListField(child=serializers.CharField())


class ErpMirrorSerializer(serializers.Serializer):
    email = serializers.EmailField()
    enabled = serializers.BooleanField(help_text="the ERPNext user: enabled (or disabled, never deleted)")
    role_profiles = serializers.ListField(child=serializers.CharField())
    by_role = ErpRoleSerializer(many=True)
    erp_in_use = serializers.BooleanField()


class OwnSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    browser = serializers.CharField(allow_blank=True, help_text="Chrome, Firefox …; empty: not known")
    system = serializers.CharField(allow_blank=True, help_text="Android, Windows …; empty: not known")
    place = serializers.CharField(allow_blank=True, help_text="the address's first octets: 203.0.113.x")
    created_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField()
    current = serializers.BooleanField(help_text="this session")


class OwnSessionsEndedSerializer(serializers.Serializer):
    sessions = serializers.IntegerField()
    tokens = serializers.IntegerField(help_text="the app's refresh tokens blacklisted")


SYSTEM_STATES = ["ok", "warn", "bad", "off"]  # green, yellow, red; off: not set up here


class SystemStatusSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="health, queues, webhooks, email, sms, backups, audit, sync, dependencies …")
    state = serializers.ChoiceField(choices=SYSTEM_STATES)
    summary = serializers.CharField(help_text="in a few words")
    since = serializers.DateTimeField(allow_null=True, help_text="when it came to this state, as far as seen")
