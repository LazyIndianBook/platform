"""The platform's side of the sync with ERPNext (erp/README.md), on the integrations framework (the ERPNext account,
its call log, the dead-letter list and the webhooks received are integrations' own models):

- ErpOutbox: one fact for ERPNext, written in the transaction of the change it describes and sent by the relay
  (tasks.relay) in order per aggregate (an order's invoice, payments, delivery notes, credit notes and COD
  settlement; a product's item and bundle), its id the idempotency key;
- ErpLink: the platform object and the ERPNext document made for it, by its stable reference (examleaf_ref);
- ErpCursor: how far the 15-minute pull has read each doctype;
- ErpStockSnapshot: ERPNext's stock of an item in a warehouse, as last read;
- ErpMirror: a read-only copy of a B2B document (a school's invoice or quotation, a B2B customer);
- ErpReconciliationRun and ErpReconciliationDifference: the nightly comparison of a day, and what did not match.
Each model has a stable `kind` (the difference's is a field) for the staff inbox and the audit log."""

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from integrations.models import IntegrationFailure


class ErpOutbox(models.Model):
    """One fact for ERPNext. Pending until the relay sends it; failed (tried again at next_at, the delay growing) or
    dead after ERP_MAX_ATTEMPTS (a dead letter: IntegrationFailure, dead_letter_created) while its aggregate's later
    rows wait behind it; sent with ERPNext's answer kept; or discarded by staff with a reason (the dead letter's),
    which lets the aggregate go on. `sequence` orders an aggregate's rows; the payload is what goes, built when the
    row is written (null: it could not be, and is built again at the send). No personal data of a B2C customer."""

    kind = "erp_outbox"

    class State(models.TextChoices):
        PENDING = "pending", "pending"
        SENDING = "sending", "sending"
        SENT = "sent", "sent"
        FAILED = "failed", "failed, to be tried again"
        DEAD = "dead", "dead letter (its aggregate waits)"
        DISCARDED = "discarded", "discarded by staff"

    OPEN = [State.PENDING, State.SENDING, State.FAILED, State.DEAD]  # each holds its aggregate's later rows

    aggregate_type = models.CharField(max_length=20, help_text="order, product or settlement.")
    aggregate_id = models.CharField(max_length=64, help_text="The order's number, the product's id, the settlement's.")
    sequence = models.PositiveIntegerField(help_text="The row's place in its aggregate.")
    event = models.CharField(max_length=40)
    examleaf_ref = models.CharField("reference", max_length=140, db_index=True)
    model = models.CharField(max_length=40, blank=True, help_text="The platform object it is about: shop.invoice …")
    object_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(null=True, blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_at = models.DateTimeField("next try", default=timezone.now)
    last_error = models.CharField(max_length=500, blank=True)
    created = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    response = models.JSONField("ERPNext's answer", null=True, blank=True)
    failure = models.ForeignKey(
        IntegrationFailure, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )

    class Meta:
        ordering = ["-pk"]
        verbose_name = "outbox row"
        permissions = [  # the staff API's (labels: staff.catalogue, area "ERP sync")
            ("view_sync", "See the ERPNext sync"),
            ("replay_sync", "Replay or discard the ERPNext sync's dead letters"),
            ("run_initial_load", "Run the initial load into ERPNext"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["aggregate_type", "aggregate_id", "sequence"], name="erp_outbox_sequence")
        ]
        indexes = [
            models.Index(fields=["state", "next_at"], name="erp_outbox_due"),
            models.Index(fields=["aggregate_type", "aggregate_id", "sequence"], name="erp_outbox_aggregate"),
        ]

    def __str__(self):
        return f"#{self.pk} {self.event} {self.examleaf_ref} ({self.get_state_display()})"

    @property
    def idempotency_key(self):
        """The row's id, which ERPNext's side remembers: a repeat answers its first result. ERP_INSTANCE_PREFIX keeps
        two platforms apart when they send to one ERPNext site (a staging copy beside production)."""
        return f"{settings.ERP_INSTANCE_PREFIX}{self.pk}"

    def replay(self, by=None, request=None):
        """Staff: send a dead or failing row again, now, from its first try; its dead letter is closed as replayed
        (whose task, erp.tasks.replay_row, finds it done), its inbox item done; an audit event (`erp.replay`).
        Returns whether it did."""
        from staff.audit import record

        from .inbox import done
        from .producers import nudge

        with transaction.atomic():
            row = type(self).objects.select_for_update().get(pk=self.pk)
            if row.state not in (self.State.DEAD, self.State.FAILED):
                return False
            if row.failure_id and row.failure.state == IntegrationFailure.State.OPEN:
                row.failure.replay(by=by)
            before = row.state
            row.state, row.attempts, row.next_at = self.State.PENDING, 0, timezone.now()
            row.save(update_fields=["state", "attempts", "next_at"])
            details = {"event": row.event, "reference": row.examleaf_ref, "was": before}
            record("erp.replay", request=request, actor=by, permission="erp.replay_sync", target=row, details=details)
            done(row)
            nudge()
        self.refresh_from_db()
        return True

    def discard(self, reason, by=None, request=None):
        """Staff: give a dead row up, with the reason why (required; kept on its dead letter and in the audit event,
        `erp.discard`): its aggregate's later rows go on, its inbox item is done. Returns whether it did."""
        from staff.audit import record

        from .inbox import done
        from .producers import nudge

        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Say why it is discarded.")
        with transaction.atomic():
            row = type(self).objects.select_for_update().get(pk=self.pk)
            if row.state != self.State.DEAD:
                return False
            if row.failure_id and row.failure.state == IntegrationFailure.State.OPEN:
                row.failure.discard(reason, by=by)
            row.state = self.State.DISCARDED
            row.save(update_fields=["state"])
            details = {"event": row.event, "reference": row.examleaf_ref}
            record(
                "erp.discard",
                request=request,
                actor=by,
                permission="erp.replay_sync",
                target=row,
                reason=reason,
                details=details,
            )
            done(row)
            nudge()
        self.refresh_from_db()
        return True


class ErpLink(models.Model):
    """A platform object (its model's label and id) and the ERPNext document made for it, by the reference both
    sides know it by: written from each answer of ERPNext ({name, examleaf_ref})."""

    kind = "erp_link"

    examleaf_ref = models.CharField("reference", max_length=140, unique=True)
    model = models.CharField(max_length=40)
    object_id = models.CharField(max_length=64)
    doctype = models.CharField(max_length=60)
    name = models.CharField("ERPNext name", max_length=140)
    synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-synced_at"]
        verbose_name = "link"
        indexes = [models.Index(fields=["model", "object_id"], name="erp_link_object")]

    def __str__(self):
        return f"{self.examleaf_ref} → {self.doctype} {self.name}"


class ErpCursor(models.Model):
    """How far the 15-minute pull (inbound.pull) has read a doctype: the `modified` and name of the last row read,
    as ERPNext gave them (its own time, without an offset)."""

    kind = "erp_cursor"

    doctype = models.CharField(max_length=60, unique=True)
    modified_after = models.CharField(max_length=32, blank=True, help_text="Empty: from the start.")
    last_name = models.CharField(max_length=140, blank=True)
    rows_read = models.PositiveIntegerField(default=0, help_text="In all, since the cursor was made.")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["doctype"]
        verbose_name = "pull cursor"

    def __str__(self):
        return f"{self.doctype} after {self.modified_after or 'the start'}"


class ErpStockSnapshot(models.Model):
    """ERPNext's stock of an item in a warehouse as last read (get_stock): what it holds (actual), what its own B2B
    orders hold of it (reserved), what it expects after its orders (projected), and its batches (print runs). With
    ERP_STOCK_PROJECTION the product's copies for sale follow it (inbound.project)."""

    kind = "erp_stock_snapshot"

    item_code = models.CharField(max_length=140)
    warehouse = models.CharField(max_length=140)
    product = models.ForeignKey(
        "shop.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="erp_stock"
    )
    actual = models.DecimalField(max_digits=12, decimal_places=3)
    reserved = models.DecimalField(max_digits=12, decimal_places=3, default=0, help_text="By ERPNext's own orders.")
    projected = models.DecimalField(max_digits=12, decimal_places=3)
    batches = models.JSONField(default=list, blank=True)
    as_of = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["item_code", "warehouse"]
        verbose_name = "stock snapshot"
        constraints = [models.UniqueConstraint(fields=["item_code", "warehouse"], name="erp_one_snapshot_per_bin")]

    def __str__(self):
        return f"{self.item_code} in {self.warehouse}: {self.actual:g}"


class ErpMirror(models.Model):
    """A read-only copy of a B2B document in ERPNext (a school's or distributor's invoice, a quotation, a B2B
    customer) for the pages that may show it later: the fields contract.MIRROR_FIELDS keeps, never a contact's."""

    kind = "erp_mirror"

    doctype = models.CharField(max_length=60)
    name = models.CharField("ERPNext name", max_length=140)
    examleaf_ref = models.CharField("reference", max_length=140, blank=True)
    status = models.CharField(max_length=40, blank=True)
    data = models.JSONField(default=dict, blank=True)
    modified = models.CharField(max_length=32, blank=True, help_text="ERPNext's, as it gave it.")
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["doctype", "-modified"]
        verbose_name = "B2B mirror"
        constraints = [models.UniqueConstraint(fields=["doctype", "name"], name="erp_one_mirror_per_document")]

    def __str__(self):
        return f"{self.doctype} {self.name}"


class ErpReconciliationRun(models.Model):
    """The nightly comparison of a day (reconcile.run): the platform's totals and ERPNext's (daily_totals), the stock
    invariant, and how many differences it found."""

    kind = "erp_reconciliation"

    class State(models.TextChoices):
        RUNNING = "running", "running"
        DONE = "done", "done"
        FAILED = "failed", "failed"

    date = models.DateField(db_index=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.RUNNING)
    platform_totals = models.JSONField(default=dict, blank=True)
    erp_totals = models.JSONField("ERPNext's totals", default=dict, blank=True)
    differences_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = "reconciliation run"

    def __str__(self):
        return f"Reconciliation of {self.date:%d %b %Y} ({self.get_state_display()})"


class ErpReconciliationDifference(models.Model):
    """What did not match in a run: `kind` the check, `key` what it is about (a payment mode, an item code, a
    document's reference), the two values; resolved by staff with a note. reconciliation_difference tells the staff
    inbox."""

    class Kind(models.TextChoices):
        INVOICES = "invoices", "invoices"
        CREDIT_NOTES = "credit_notes", "credit notes"
        PAYMENTS = "payments", "payments and refunds"
        SETTLEMENTS = "settlements", "settlements"
        DELIVERIES = "deliveries", "delivery notes"
        STOCK = "stock", "stock invariant"
        MISSING = "missing", "document not in ERPNext"

    run = models.ForeignKey(ErpReconciliationRun, on_delete=models.CASCADE, related_name="differences")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    key = models.CharField(max_length=140)
    platform_value = models.CharField(max_length=60, blank=True)
    erp_value = models.CharField("ERPNext's value", max_length=60, blank=True)
    note = models.CharField(max_length=300, blank=True, help_text="Staff's, when resolved.")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["run", "kind", "key"]
        verbose_name = "reconciliation difference"
        permissions = [("resolve_difference", "Resolve the reconciliation's differences")]

    def __str__(self):
        return f"{self.get_kind_display()} {self.key}: {self.platform_value or '-'} here, {self.erp_value or '-'} there"

    def resolve(self, note, by=None, request=None):
        """Staff: what was done about it (required). Once (compare-and-set); an audit event (`erp.resolve`); the run's
        inbox item done with its last difference. Returns whether it did."""
        from staff.audit import record

        from .inbox import done

        note = (note or "").strip()
        if not note:
            raise ValueError("Say what was done about it.")
        now, user = timezone.now(), by if getattr(by, "pk", None) else None
        with transaction.atomic():
            open_ = type(self).objects.filter(pk=self.pk, resolved_at__isnull=True)
            if not open_.update(note=note[:300], resolved_at=now, resolved_by=user):
                return False
            self.note, self.resolved_at, self.resolved_by = note[:300], now, user
            # "about", not "key": the audit log masks a "key" as a secret
            details = {"run": self.run_id, "date": self.run.date.isoformat(), "kind": self.kind, "about": self.key}
            record(
                "erp.resolve",
                request=request,
                actor=by,
                permission="erp.resolve_difference",
                target=self,
                reason=note,
                details=details,
            )
            if not self.run.differences.filter(resolved_at__isnull=True).exists():
                done(self.run)
        return True
