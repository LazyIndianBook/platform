"""The Admin Control Panel's records (staff/README.md): who may reach what (StaffScope, RoleGrant, StaffInvite,
ApiKey), what staff did (AuditEvent: append-only and hash-chained, staff.audit), what waits for a second person
(ChangeRequest, Approval: staff.approvals) or for anyone (InboxItem), the panel's own switches and views (SiteSetting,
FeatureFlag, SavedView), and the data-protection registers (DataRequest, Incident, ProcessorRecord)."""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_fsm import ConcurrentTransitionMixin, FSMField, transition
from model_utils.models import TimeStampedModel

from . import catalogue

GENESIS = "0" * 64  # the prev_hash of a chain's first event


class StaffPermissions(models.Model):
    """No table and no rows: it holds the staff's action permissions, `staff.<codename>` (labels: staff.catalogue)."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [(codename, label) for codename, label, *_ in catalogue.STAFF_ACTIONS]

    def __str__(self):
        return "Staff permissions"


class StaffScope(models.Model):
    """Which objects one member of staff reaches with their permissions (staff.backends): a subject's content, the
    orders in some states, a school's quotations, a work queue. Rows of one kind narrow the person to their values;
    without any, the role decides (accounts.roles.ROLE_SCOPES), else everything."""

    class Kind(models.TextChoices):
        SUBJECT = "subject", "subject (PHY, CHE, MAT, BIO)"
        BOARD_CLASS = "board_class", "board and class (ASSEB:12)"
        ORDER_STATUS = "order_status", "order status"
        WAREHOUSE = "warehouse", "warehouse"
        SCHOOL = "school", "school"
        TICKET_QUEUE = "ticket_queue", "work queue (an inbox kind)"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_scopes")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    value = models.CharField(max_length=120)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Removed by the nightly task after this.")

    class Meta:
        default_permissions = ("view",)  # given and taken through staff.assign_role
        ordering = ["user", "kind", "value"]
        constraints = [models.UniqueConstraint(fields=["user", "kind", "value"], name="unique_staff_scope")]

    def __str__(self):
        return f"Scope #{self.pk}"


class RoleGrant(models.Model):
    """A role given through the panel (staff.services.grant_role): by whom, why, and until when. The group membership
    is the role (accounts/roles.py); a grant past `expires_at` is taken away by the nightly task (just-in-time
    elevation). Roles given in the admin have no row, and no expiry."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_grants")
    role = models.CharField(max_length=30)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.CharField(max_length=300, blank=True)
    created = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ("view",)
        ordering = ["user", "role"]
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="unique_role_grant")]

    def __str__(self):
        return f"Role grant #{self.pk}"


class AuditEvent(models.Model):
    """One thing someone (or the site) did, written by staff.audit.record only. Append-only: on PostgreSQL a trigger
    refuses UPDATE, DELETE and TRUNCATE (migration 0002); each row carries the hash of the one before it in its chain
    and its own, `hash = SHA-256(prev_hash || canonical JSON of the row)`. Money events (orders, refunds, prices) have a
    chain of their own, kept 8 financial years; the rest 2 years (staff/README.md "Retention"). No personal data: the
    actor and target are ids, labels name no one, `changes` and `details` are masked."""

    class Chain(models.TextChoices):
        GENERAL = "general", "general"
        MONEY = "money", "money"

    class ActorType(models.TextChoices):
        STAFF = "staff", "staff"
        USER = "user", "user"
        SERVICE = "service", "service (API key)"
        SYSTEM = "system", "system"
        ANONYMOUS = "anonymous", "anonymous"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "success"
        DENIED = "denied", "denied"
        FAILED = "failed", "failed"

    chain = models.CharField(max_length=8, choices=Chain.choices, default=Chain.GENERAL)
    ts = models.DateTimeField("time (UTC)", db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    actor_roles = models.JSONField(default=list, help_text="The actor's roles at the time.")
    on_behalf_of = models.BigIntegerField(null=True, blank=True, help_text="The customer, while impersonating.")
    break_glass = models.BooleanField(
        default=False, help_text="By a break-glass account (a superuser), or an owner's override of an approval."
    )
    action = models.CharField(max_length=80, db_index=True)
    permission = models.CharField(max_length=100, blank=True, help_text="The permission exercised (or missing).")
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=200, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.SUCCESS)
    reason = models.CharField(max_length=500, blank=True)
    change_request_id = models.BigIntegerField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    session_hash = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, help_text="{field: [before, after]}, personal data masked.")
    details = models.JSONField(default=dict, help_text="Context: an export's filter and row count; masked too.")
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        default_permissions = ()  # staff.view_auditlog, staff.export_auditlog
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="staff_audit_target"),
            models.Index(fields=["chain", "id"], name="staff_audit_chain"),
        ]

    def __str__(self):
        return f"Audit event #{self.pk}"


class AuditHead(models.Model):
    """The newest hash of each chain, one row, locked while an event is written so that events chain one after the
    other (staff.audit.record); compared with the newest rows by the nightly verification."""

    general = models.CharField(max_length=64, default=GENESIS)
    money = models.CharField(max_length=64, default=GENESIS)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return "Audit chain heads"


class ChangeRequest(ConcurrentTransitionMixin, TimeStampedModel):
    """Maker-checker (research 1.5): an action that waits for a second person, with the exact payload it will run
    (`payload_sha256` binds the approval to it), the maker's reason, the approvals, an expiry and the result. The
    executor runs the stored payload, never one sent again (staff.approvals.execute)."""

    HOURS = 24  # default life of a request; STAFF_CHANGE_REQUEST_HOURS

    class Status(models.TextChoices):
        PENDING = "pending", "waiting for approval"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        EXPIRED = "expired", "expired"
        EXECUTED = "executed", "done"
        FAILED = "failed", "failed"

    action = models.CharField(max_length=40, db_index=True)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=200, blank=True)
    payload = models.JSONField(default=dict)
    payload_sha256 = models.CharField(max_length=64)
    amount = models.DecimalField("amount (₹)", max_digits=12, decimal_places=2, null=True, blank=True)
    maker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=500)
    rule = models.CharField(max_length=200, blank=True, help_text="Why it needed approval, or why not.")
    status = FSMField(default=Status.PENDING, choices=Status.choices, protected=True, db_index=True)
    expires_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=80, blank=True)
    overridden = models.BooleanField(default=False, help_text="Approved by its maker: an owner's override.")
    result = models.JSONField(null=True, blank=True)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ("view", "add")
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["maker", "idempotency_key"], condition=~Q(idempotency_key=""), name="unique_change_request_key"
            )
        ]

    def __str__(self):
        return f"Change request #{self.pk}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @transition(status, source=Status.PENDING, target=Status.APPROVED)
    def approve(self):
        pass

    @transition(status, source=Status.PENDING, target=Status.REJECTED)
    def reject(self):
        pass

    @transition(status, source=[Status.PENDING, Status.APPROVED], target=Status.EXPIRED)
    def expire(self):
        pass

    @transition(status, source=Status.APPROVED, target=Status.EXECUTED)
    def execute(self, by, result):
        self.executed_by, self.executed_at, self.result = by, timezone.now(), result

    @transition(status, source=Status.APPROVED, target=Status.FAILED)
    def fail(self, by, error):
        self.executed_by, self.executed_at, self.result = by, timezone.now(), {"error": error}


class Approval(models.Model):
    """One person's decision on a ChangeRequest; once per person."""

    class Decision(models.TextChoices):
        APPROVE = "approve", "approved"
        REJECT = "reject", "rejected"

    change_request = models.ForeignKey(ChangeRequest, on_delete=models.CASCADE, related_name="approvals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    comment = models.CharField(max_length=500, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ()
        ordering = ["created"]
        constraints = [models.UniqueConstraint(fields=["change_request", "user"], name="one_decision_per_person")]

    def __str__(self):
        return f"Approval #{self.pk}"


class InboxItem(models.Model):
    """Something that waits for a person: an approval, a teacher's request, a deletion, a data request, an incident,
    a failed job or webhook, a parcel's exception, an integration's dead letter, failed event or open circuit
    (staff.signals), a document ERPNext refused for good or a reconciliation's differences (erp/inbox.py). Shown to its
    assignee, or to everyone holding `permission`; done once acted on. One open item per kind and target."""

    class Kind(models.TextChoices):
        APPROVAL = "approval", "approval"
        TEACHER_REQUEST = "teacher_request", "teacher access request"
        DELETION_REQUEST = "deletion_request", "account deletion"
        DATA_REQUEST = "data_request", "data request"
        INCIDENT = "incident", "incident"
        FAILED_JOB = "failed_job", "failed job"
        FAILED_WEBHOOK = "failed_webhook", "failed webhook"
        SYNC_FAILED = "sync_failed", "ERPNext refused a document (a dead letter)"  # erp/inbox.py
        RECONCILIATION = "reconciliation", "ERPNext reconciliation differences"
        SHIPPING_EXCEPTION = "shipping_exception", "parcel exception"
        DEAD_LETTER = "dead_letter", "integration task given up"
        FAILED_EVENT = "failed_event", "provider event not processed"
        INTEGRATION_DOWN = "integration_down", "integration unavailable"
        # Phase B: tax (shop/tax.py)
        TAX_THRESHOLD = "tax_threshold", "a tax threshold crossed"
        CREDIT_NOTE_MISSING = "credit_note_missing", "a refund without its credit note"
        PROCESSOR_TASK = "processor_task", "a processor to tell: erase, or stop"  # staff.privacy
        COMPLIANCE = "compliance", "a compliance duty: a self-audit, a held erasure"
        # Orders (shop/staff_orders.py)
        ORDER_HOLD = "order_hold", "order on hold"
        RETURN_REQUEST = "return_request", "return asked for"
        BANK_REFUND = "bank_refund", "refund to transfer by bank or UPI"

    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    title = models.CharField(max_length=200, help_text="Names no one: a number, a kind.")
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    permission = models.CharField(max_length=100, help_text="Who sees it: the holders of this permission.")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    due_at = models.DateTimeField(null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True, db_index=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    data = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ()  # staff.view_inbox
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "target_type", "target_id"], condition=Q(done_at=None), name="one_open_inbox_item"
            )
        ]

    def __str__(self):
        return f"Inbox item #{self.pk}"


class SavedView(TimeStampedModel):
    """A list's filters, columns and sort order, kept by its owner, private or shared with one of their roles."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_views")
    role = models.CharField(max_length=30, blank=True, help_text="Shared with this role's members; empty: private.")
    list_key = models.CharField("list", max_length=40, help_text="Which list: audit, users, change-requests …")
    name = models.CharField(max_length=80)
    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)
    sort = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["list_key", "name"]

    def __str__(self):
        return f"Saved view #{self.pk}"


class Job(models.Model):
    """Background work started from the panel (plan 3.6, 7.1): an audit-log export, a bulk action or the ERPNext
    initial load, run by Celery (staff.jobs). Its progress, each failed row's error and the result file (the private
    storage; a link signed for 5 minutes; deleted after a week) are kept on it. Above its starter's limits it waits for
    an approver first (`change_request`, "job.run"). Every step is an audit event."""

    class Kind(models.TextChoices):
        AUDIT_EXPORT = "audit_export", "audit log export"
        BULK_ACTION = "bulk_action", "bulk action"
        ERP_INITIAL_LOAD = "erp_initial_load", "ERPNext initial load"  # erp.producers.initial_load
        GSTR1_EXPORT = "gstr1_export", "GSTR-1 export"  # Phase B: tax (export_gstr1)
        # Orders (shop/staff_orders.py): bulk actions on selected orders, and the order export
        ORDERS_PACK = "orders_pack", "orders marked packed"
        ORDERS_PRINT = "orders_print", "order documents printed"
        ORDERS_CANCEL = "orders_cancel", "orders cancelled"
        ORDERS_EXPORT = "orders_export", "order export"

    class State(models.TextChoices):
        QUEUED = "queued", "queued"
        RUNNING = "running", "running"
        DONE = "done", "done"
        FAILED = "failed", "failed"
        CANCELLED = "cancelled", "cancelled"

    FINISHED = [State.DONE, State.FAILED, State.CANCELLED]
    MAX_ERRORS = 1000  # the rows' errors kept (and counted beyond)

    kind = models.CharField(max_length=20, choices=Kind.choices)
    params = models.JSONField(default=dict, help_text="audit_export: filters; bulk_action: action, targets, payload…")
    dry_run = models.BooleanField(default=False, help_text="Checks every row and changes nothing.")
    state = models.CharField(max_length=10, choices=State.choices, default=State.QUEUED, db_index=True)
    done = models.PositiveIntegerField(default=0, help_text="Rows done.")
    total = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, help_text="[{id, label, message}] of the rows that failed.")
    result = models.JSONField(default=dict, blank=True)
    result_file = models.CharField(max_length=200, blank=True, help_text="Its name in the private storage.")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="staff_jobs"
    )
    change_request = models.OneToOneField(
        "ChangeRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="job"
    )
    cancel_requested = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ("view", "add")  # and each kind's own: staff.export_auditlog, the action's (staff.jobs)
        ordering = ["-created", "-pk"]

    def __str__(self):
        return f"Job #{self.pk}"


class Switch(models.Model):
    """A value of a key from `effective_from` on, until a newer row's: the rows are the history (a change adds one)."""

    key = models.CharField(max_length=64, db_index=True)
    value = models.JSONField(null=True, blank=True, help_text="null: back to the environment's value.")
    effective_from = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.CharField(max_length=300)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True
        default_permissions = ("view",)
        ordering = ["key", "-effective_from", "-pk"]

    def __str__(self):
        return f"{self.key} #{self.pk}"


class SiteSetting(Switch):
    """One of the site's switches the panel may change without a deploy (staff.config.SETTINGS); the environment's
    value stands until a row says otherwise."""

    class Meta(Switch.Meta):
        pass


class FeatureFlag(Switch):
    """A feature flag (e.g. ERP_SYNC_ORDERS): off until a row says otherwise."""

    class Meta(Switch.Meta):
        pass


class ApiKey(models.Model):
    """One integration's key (research 2.6): shown once, kept as a SHA-256 of the whole key with a visible prefix; it
    holds only the permissions listed (low and medium risk), until `expires_at` (12 months at most), optionally from
    some addresses only. Never a person and never the panel (staff.permissions.ApiKeyAuthentication)."""

    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=12, unique=True)
    secret_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list, help_text='Permissions, e.g. ["shop.view_order"].')
    sponsor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="api_keys")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    allowed_ips = models.JSONField(default=list, blank=True, help_text="Addresses or networks (CIDR); empty: any.")
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        default_permissions = ("view",)  # created and revoked through staff.manage_api_keys
        ordering = ["-created"]

    def __str__(self):
        return f"API key {self.prefix}"

    @property
    def is_usable(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class Note(models.Model):
    """A note staff keep on a record (plan 7.1): an order, a customer, a parcel, by the record's `app_label.model` and
    id (as the audit log names targets); the record's timeline lists them, pinned first. Readable by those who may
    see the record (in their scope). Its body is what staff typed: never in the audit log, whose event names the
    record and the note's number."""

    target_type = models.CharField(max_length=60, help_text="app_label.model, e.g. shop.order")
    target_id = models.CharField(max_length=64)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=5000)
    pinned = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("view", "add")
        ordering = ["-pinned", "-created", "-pk"]
        indexes = [models.Index(fields=["target_type", "target_id"], name="staff_note_target")]

    def __str__(self):
        return f"Note #{self.pk}"


class PolicyAcknowledgement(models.Model):
    """A member of staff's acknowledgement of one version of a policy (research 6: acceptable use, children's data,
    confidentiality, incident reporting; NIST PS-6): asked again when its version in STAFF_POLICIES changes (the
    manifest's `policies_due`)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="policy_acknowledgements")
    policy = models.CharField(max_length=40)
    version = models.CharField(max_length=40)
    acknowledged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ()  # each person their own; staff.view_staff reads anyone's
        ordering = ["-acknowledged_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["user", "policy", "version"], name="one_acknowledgement_per_version")
        ]

    def __str__(self):
        return f"Acknowledgement #{self.pk}"


class Impersonation(models.Model):
    """A member of staff logged in as a customer on the website (research 2.7; staff.services): the token of the
    panel's `users/<id>/impersonate/` opens one website session (`accepted_at`: once), within 15 minutes, which ends at
    `expires_at`, when either side ends it (`ended_at`), or with the panel's session it was asked from
    (`staff_session_key`: its session no longer signed in as the member of staff)."""

    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(max_length=300)
    ticket = models.CharField(max_length=60)
    staff_session_key = models.CharField(max_length=40, blank=True)
    created = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()  # staff.impersonate_user
        ordering = ["-created"]

    def __str__(self):
        return f"Impersonation #{self.pk}"


class StaffInvite(models.Model):
    """An invitation to join the staff with a role, sent by email; the link (whose token only the email holds) works
    once, for VALID."""

    VALID = timedelta(days=7)

    email = models.EmailField()
    role = models.CharField(max_length=30)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ("view",)
        ordering = ["-created"]

    def __str__(self):
        return f"Invitation #{self.pk}"

    @property
    def is_open(self):
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > timezone.now()


class DataRequest(models.Model):
    """A data principal's request or complaint that came by email, letter, phone or the contact form (research 4.6):
    acknowledged within 48 hours, answered by `due_at`, the strictest clock that applies (staff.privacy.clocks)."""

    class Kind(models.TextChoices):
        ACCESS = "access", "access (a copy of the data)"
        CORRECTION = "correction", "correction"
        ERASURE = "erasure", "erasure"
        NOMINATION = "nomination", "nomination (death or incapacity)"
        GRIEVANCE = "grievance", "grievance"
        COMPLAINT = "complaint", "complaint"

    class Channel(models.TextChoices):
        EMAIL = "email", "email"
        LETTER = "letter", "letter"
        PHONE = "phone", "phone"
        FORM = "form", "the website's contact form"
        IN_PERSON = "in_person", "in person"
        BOARD = "board", "through the Data Protection Board"

    class Status(models.TextChoices):
        NEW = "new", "received"
        ACKNOWLEDGED = "acknowledged", "acknowledged"
        CLOSED = "closed", "closed"

    class Outcome(models.TextChoices):
        DONE = "done", "done as asked"
        REFUSED = "refused", "refused (with the reason)"
        WITHDRAWN = "withdrawn", "withdrawn"

    kind = models.CharField("type", max_length=12, choices=Kind.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="data_requests"
    )
    requester = models.CharField(max_length=200, help_text="Where to answer: the address or number it came from.")
    summary = models.CharField(max_length=300, help_text="What was asked.")
    identity_verified = models.BooleanField(default=False)
    identity_note = models.CharField(
        max_length=300, blank=True, help_text="How the identity was checked (the method, not the document)."
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    ack_due_at = models.DateTimeField("acknowledge by")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField("answer by")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True, help_text="A nominee; a parent's confirmation; holds.")
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True)
    response = models.TextField(blank=True, help_text="The answer sent.")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        default_permissions = ("view",)  # handled through staff.handle_data_request
        ordering = ["-received_at"]

    def __str__(self):
        return f"Data request #{self.pk}"

    def save(self, *args, **kwargs):
        if not (self.ack_due_at and self.due_at):
            from .privacy import clocks

            self.ack_due_at, self.due_at = clocks(self.kind, self.received_at)
        super().save(*args, **kwargs)


class Incident(models.Model):
    """The breach register (research 4.4): what happened and when it was noticed, whom it touched (children too), and
    the reports, each against its clock from detection: CERT-In 6 hours, the Data Protection Board's detailed report
    72 hours. Every personal data breach is reported; there is no harm threshold."""

    CERT_IN_HOURS, BOARD_HOURS = 6, 72

    class Kind(models.TextChoices):  # the CERT-In Directions' Annexure I, the ones a site like this meets
        DATA_BREACH = "data_breach", "data breach"
        DATA_LEAK = "data_leak", "data leak"
        UNAUTHORISED_ACCESS = "unauthorised_access", "unauthorised access to systems or data"
        MALICIOUS_CODE = "malicious_code", "ransomware or other malicious code"
        APPLICATION_ATTACK = "application_attack", "attack on the website, the app or the API"
        DENIAL_OF_SERVICE = "denial_of_service", "denial of service"
        LOSS_OF_ACCESS = "loss_of_access", "loss of access to personal data (outage, deletion)"
        OTHER = "other", "other"

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    detected_at = models.DateTimeField(default=timezone.now)
    noticed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    description = models.TextField(blank=True)
    systems = models.CharField(max_length=300, blank=True)
    data_categories = models.CharField(max_length=300, blank=True)
    people_affected = models.PositiveIntegerField(null=True, blank=True)
    children_affected = models.BooleanField(default=False)
    cert_in_reported_at = models.DateTimeField("CERT-In told at", null=True, blank=True)
    cert_in_reference = models.CharField(max_length=100, blank=True)
    board_notified_at = models.DateTimeField("Board told at (first)", null=True, blank=True)
    board_report_at = models.DateTimeField("Board's detailed report at", null=True, blank=True)
    board_reference = models.CharField(max_length=100, blank=True)
    notice_text = models.TextField("notice to the people affected", blank=True)
    notices_sent = models.PositiveIntegerField(default=0)
    notices_sent_at = models.DateTimeField(null=True, blank=True)
    actions = models.TextField("actions taken", blank=True)
    root_cause = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("view",)  # kept through staff.manage_incident
        ordering = ["-detected_at"]

    def __str__(self):
        return f"Incident #{self.pk}"

    @property
    def cert_in_due(self):
        return self.detected_at + timedelta(hours=self.CERT_IN_HOURS)

    @property
    def board_due(self):
        return self.detected_at + timedelta(hours=self.BOARD_HOURS)


class ProcessorRecord(models.Model):
    """Who processes personal data for ExamLeaf (s.8, r.6): for what, which data, in which country, under which
    contract, so that an access request can name them and a transfer rule can be followed quickly."""

    name = models.CharField(max_length=100)
    purpose = models.CharField(max_length=300)
    data_categories = models.CharField(max_length=300)
    country = models.CharField(max_length=60, help_text="Where the data is processed.")
    contract_signed_on = models.DateField(null=True, blank=True)
    contract_ends_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    # Phase B: legal
    holds_personal_data = models.BooleanField(
        default=False, help_text="Keeps personal data after the processing: each erasure asks them to erase it."
    )
    holds_marketing_data = models.BooleanField(
        default=False, help_text="Holds marketing lists: told to stop when someone withdraws marketing consent."
    )
    erasure_action = models.CharField(
        max_length=150,
        blank=True,
        help_text="What to ask them: 'ask SES to purge the address', 'delete the media in R2'.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# Phase B: legal

# The 13 dark patterns the CCPA's Guidelines for Prevention and Regulation of Dark Patterns, 2023 name (Annexure 1):
# a self-audit answers each once a year (research-lms-crm-cms.md 0; the E-Commerce Rules as amended, from 1 January
# 2027: a yearly self-audit and its certificate displayed prominently).
DARK_PATTERNS = [
    ("false_urgency", "False urgency"),
    ("basket_sneaking", "Basket sneaking"),
    ("confirm_shaming", "Confirm shaming"),
    ("forced_action", "Forced action"),
    ("subscription_trap", "Subscription trap"),
    ("interface_interference", "Interface interference"),
    ("bait_and_switch", "Bait and switch"),
    ("drip_pricing", "Drip pricing"),
    ("disguised_advertisement", "Disguised advertisement"),
    ("nagging", "Nagging"),
    ("trick_question", "Trick question"),
    ("saas_billing", "SaaS billing"),
    ("rogue_malware", "Rogue malware"),
]


def blank_audit_rows():
    return [{"pattern": key, "finding": "", "fix": ""} for key, _ in DARK_PATTERNS]


class DarkPatternAudit(models.Model):
    """One year's dark-pattern self-audit: a finding and a fix for each of the 13 named patterns, completed by a
    person (OWNER or ADMIN: staff.manage_compliance), with the certificate's text (and its signed copy, optional, in
    the private storage). Once completed it is not changed; its certificate shows on the website (config/'s
    `dark_pattern_certificate`) from `effective_from`. A reminder opens in the inbox each 1 December for the coming
    year (staff.tasks.remind_dark_pattern_audit)."""

    year = models.PositiveSmallIntegerField(unique=True, help_text="The calendar year its certificate covers.")
    rows = models.JSONField(default=blank_audit_rows, help_text="[{pattern, finding, fix}], one per named pattern.")
    certificate_text = models.TextField(blank=True)
    certificate_file = models.CharField(max_length=200, blank=True, help_text="Its name in the private storage.")
    effective_from = models.DateField(null=True, blank=True, help_text="Shown on the website from this day.")
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        default_permissions = ("view",)  # kept through staff.manage_compliance
        ordering = ["-year"]

    def __str__(self):
        return f"Dark-pattern self-audit {self.year}"
