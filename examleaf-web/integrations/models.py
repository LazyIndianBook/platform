"""The connections to services others run for ExamLeaf (Shiprocket now; Razorpay, MSG91, SES, the storage and ERPNext
when the panel manages them): one IntegrationAccount per service and mode, its secrets encrypted (crypto.py), its
health kept with it (the last success and error, a circuit breaker); IntegrationCall, the log of every request made to
it; IntegrationFailure, the dead-letter list of tasks that gave up; InboundEvent, every webhook it sends us, raw and
deduplicated (Razorpay's keep their own shop.WebhookEvent). A secret is never shown or serialised: masked() gives its
last four characters. Each model has a stable `kind` for the staff inbox and the audit log."""

import hmac
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from model_utils.models import TimeStampedModel

from . import crypto, signals

# The services an account can be for. Another app adds its own (PROVIDERS["delhivery"] = "Delhivery") before it makes
# an account; the field's choices read this dict, so a new provider needs no migration.
PROVIDERS = {
    "shiprocket": "Shiprocket",
    "razorpay": "Razorpay",
    "msg91": "MSG91",
    "ses": "Amazon SES",
    "storage": "Storage (R2 or S3)",
    "erpnext": "ERPNext",
}


def provider_choices():
    return list(PROVIDERS.items())


# The task that processes an InboundEvent, by provider: a dotted path, added by the provider's app (shipping/apps.py).
INBOUND_PROCESSORS = {}

FAILURES_TO_OPEN = 5  # failures within FAILURE_WINDOW open the circuit
FAILURE_WINDOW = timedelta(minutes=5)
COOL_OFF = timedelta(minutes=5)  # an open circuit lets one trial call through after this
PREVIOUS_WEBHOOK_TOKEN = timedelta(hours=24)  # the previous token still works this long after a rotation
ROTATE_AFTER = timedelta(days=90)  # our policy for credentials, not the providers'


def mask(value):
    """The last four characters of a secret, never more (and nothing of a short one)."""
    value = str(value or "")
    if not value:
        return ""
    return f"…{value[-4:]}" if len(value) >= 12 else "…"


class IntegrationAccount(TimeStampedModel):
    """One service in one mode: its credentials (a JSON object, encrypted), the access token cached from them
    (encrypted, with its expiry), the token it must send with its webhooks (current and previous, encrypted), when the
    credentials should be rotated, what they may do (`scopes`) and where else the same key is configured; and its
    state: the last success and error, the result of the last connection test, and the circuit breaker (closed: calls
    go through; open after FAILURES_TO_OPEN failures within FAILURE_WINDOW: calls wait; half open after COOL_OFF: one
    trial call, which closes it again or opens it for another COOL_OFF). At most one enabled account per provider:
    the one the site uses."""

    kind = "integration_account"
    SECRET_FIELDS = ["credentials", "token", "webhook_token", "previous_webhook_token"]  # encrypted (crypto.py)

    class Mode(models.TextChoices):
        TEST = "test", "test"
        LIVE = "live", "live"

    class Circuit(models.TextChoices):
        CLOSED = "closed", "closed: calls go through"
        OPEN = "open", "open: calls wait"
        HALF_OPEN = "half_open", "half open: one trial call"

    provider = models.CharField(max_length=30, choices=provider_choices)
    mode = models.CharField(max_length=4, choices=Mode.choices, default=Mode.TEST)
    label = models.CharField(max_length=80, blank=True, help_text="E.g. the API user's name at the provider.")
    enabled = models.BooleanField(default=False, help_text="Off: nothing calls the provider, its webhooks are refused.")
    credentials = models.TextField(blank=True, editable=False)  # crypto.encrypt(JSON object)
    credentials_updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    credentials_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    rotate_by = models.DateField(null=True, blank=True, help_text="Our policy: 90 days after the credentials were set.")
    token = models.TextField(blank=True, editable=False)  # the cached access token, encrypted
    token_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    webhook_token = models.TextField(blank=True, editable=False)  # encrypted; the provider sends it with each webhook
    previous_webhook_token = models.TextField(blank=True, editable=False)  # accepted PREVIOUS_WEBHOOK_TOKEN after
    webhook_rotated_at = models.DateTimeField(null=True, blank=True, editable=False)
    scopes = models.JSONField(
        default=list, blank=True, help_text='What the credentials may do, as the provider grants it: ["orders", ...].'
    )
    where_else_configured = models.TextField(blank=True, help_text="Other places that hold the same key.")
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.CharField(max_length=500, blank=True, editable=False)
    last_test_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_test_ok = models.BooleanField(null=True, editable=False)
    last_test_message = models.CharField(max_length=300, blank=True, editable=False)
    circuit_state = models.CharField(max_length=10, choices=Circuit.choices, default=Circuit.CLOSED, editable=False)
    failure_count = models.PositiveSmallIntegerField(default=0, editable=False)
    failure_window_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    opened_at = models.DateTimeField("unavailable since", null=True, blank=True, editable=False)
    trial_started_at = models.DateTimeField(null=True, blank=True, editable=False)  # the last trial, or failure
    held_open = models.BooleanField(default=False, editable=False, help_text="Opened by staff: no trial until reset.")

    class Meta:
        ordering = ["provider", "mode"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "mode"], name="one_integration_account_per_mode"),
            models.UniqueConstraint(
                fields=["provider"], condition=models.Q(enabled=True), name="one_enabled_integration_account"
            ),
        ]

    def __str__(self):
        name = f"{PROVIDERS.get(self.provider, self.provider)} ({self.mode})"
        return f"{name}, {self.label}" if self.label else name

    @classmethod
    def enabled_for(cls, provider):
        """The account the site uses for `provider`, or None."""
        return cls.objects.filter(provider=provider, enabled=True).first()

    # Secrets

    def get_credentials(self):
        return json.loads(crypto.decrypt(self.credentials)) if self.credentials else {}

    def set_credentials(self, data, by=None):
        """New credentials (a dict; not saved): the cached token goes with the old ones."""
        self.credentials = crypto.encrypt(json.dumps(data)) if data else ""
        self.credentials_updated_at = timezone.now()
        self.credentials_updated_by = by if getattr(by, "pk", None) else None
        self.rotate_by = (timezone.localdate() + ROTATE_AFTER) if data else None
        self.token, self.token_expires_at = "", None

    def get_token(self):
        return crypto.decrypt(self.token) if self.token else ""

    def set_token(self, token, expires_at):
        """Keep a new access token (saved at once, alone)."""
        self.token, self.token_expires_at = crypto.encrypt(token), expires_at
        type(self).objects.filter(pk=self.pk).update(token=self.token, token_expires_at=expires_at)

    def rotate_webhook_token(self):
        """A new webhook token (32 random bytes), returned to be shown once and pasted at the provider; the current one
        becomes the previous one, still accepted for PREVIOUS_WEBHOOK_TOKEN. Saved."""
        token = secrets.token_urlsafe(32)
        self.previous_webhook_token, self.webhook_token = self.webhook_token, crypto.encrypt(token)
        self.webhook_rotated_at = timezone.now()
        self.save(update_fields=["webhook_token", "previous_webhook_token", "webhook_rotated_at", "modified"])
        return token

    def webhook_secrets(self, now=None):
        """The webhook tokens that count now: the current one and, within PREVIOUS_WEBHOOK_TOKEN of a rotation, the
        previous one; none when no token is set (deny by default). Also the secret of a provider that signs its
        webhooks with it instead of sending it (ERPNext's HMAC: erp/webhooks.py)."""
        if not self.webhook_token:
            return []
        found = [crypto.decrypt(self.webhook_token)]
        now = now or timezone.now()
        recent = self.webhook_rotated_at and now - self.webhook_rotated_at < PREVIOUS_WEBHOOK_TOKEN
        if self.previous_webhook_token and recent:
            found.append(crypto.decrypt(self.previous_webhook_token))
        return found

    def webhook_token_matches(self, given, now=None):
        """Whether `given` (the header the provider sent) is the current token or, within PREVIOUS_WEBHOOK_TOKEN of a
        rotation, the previous one. Constant time; False when no token is set (deny by default)."""
        if not given:
            return False
        given = given.encode("utf-8", "replace")
        matches = False
        for token in self.webhook_secrets(now):
            matches |= hmac.compare_digest(given, token.encode())
        return matches

    def masked(self):
        """What may be shown of the secrets: each credential's last four characters, the webhook token's, and whether
        an access token is cached (until when)."""
        credentials = {key: mask(value) for key, value in self.get_credentials().items()}
        webhook = mask(crypto.decrypt(self.webhook_token)) if self.webhook_token else ""
        return {"credentials": credentials, "webhook_token": webhook, "token_expires_at": self.token_expires_at}

    # The circuit breaker

    CIRCUIT_FIELDS = ["circuit_state", "failure_count", "failure_window_started_at", "opened_at", "trial_started_at"]

    def allows_call(self, now=None):
        """Whether a call may go now (read from the row, not from this copy). Closed: yes. Open, COOL_OFF after it
        opened or after its last trial (a half-open circuit whose trial never reported counts as open): one caller
        wins the next trial (compare-and-set on the row), the others wait. Disabled, or held open by staff: never."""
        self.refresh_from_db(fields=["enabled", "held_open", *self.CIRCUIT_FIELDS])
        if not self.enabled or self.held_open:
            return False
        if self.circuit_state == self.Circuit.CLOSED:
            return True
        now = now or timezone.now()
        last = self.trial_started_at or self.opened_at
        if last and now - last < COOL_OFF:
            return False
        trial = type(self).objects.filter(
            pk=self.pk, circuit_state=self.circuit_state, trial_started_at=self.trial_started_at, held_open=False
        )
        if trial.update(circuit_state=self.Circuit.HALF_OPEN, trial_started_at=now):
            self.circuit_state, self.trial_started_at = self.Circuit.HALF_OPEN, now
            return True
        return False

    def record_success(self, answered_only=False):
        """The provider answered: the circuit closes (a trial that reached it succeeded) and the failures counted are
        forgotten. A call that also did what it was for (not `answered_only`: it was refused) is the last success.
        A circuit held open by staff stays open (only reset() closes it)."""
        now = timezone.now()
        accounts = type(self).objects.filter(pk=self.pk)
        recovered = (
            accounts.exclude(circuit_state=self.Circuit.CLOSED)
            .filter(held_open=False)
            .update(circuit_state=self.Circuit.CLOSED, opened_at=None, trial_started_at=None)
        )
        changes = {"failure_count": 0, "failure_window_started_at": None}
        if not answered_only:
            changes["last_success_at"] = self.last_success_at = now
        accounts.update(**changes)
        self.refresh_from_db(fields=self.CIRCUIT_FIELDS)
        if recovered:
            transaction.on_commit(
                lambda: signals.integration_recovered.send(sender=type(self), account=self), robust=True
            )

    def record_failure(self, error, now=None):
        """A call that failed for the provider's reasons (unreachable, timed out, 429, 5xx): counted towards opening
        the circuit (FAILURES_TO_OPEN within FAILURE_WINDOW); a failed trial opens it again for COOL_OFF."""
        now = now or timezone.now()
        opened = False
        with transaction.atomic():
            account = type(self).objects.select_for_update().get(pk=self.pk)
            account.last_error_at, account.last_error = now, str(error)[:500]
            if account.circuit_state == self.Circuit.CLOSED:
                started = account.failure_window_started_at
                if started is None or now - started > FAILURE_WINDOW:
                    account.failure_window_started_at, account.failure_count = now, 0
                account.failure_count += 1
                if account.failure_count >= FAILURES_TO_OPEN:
                    account.circuit_state, account.opened_at, account.trial_started_at = self.Circuit.OPEN, now, None
                    opened = True
            else:  # a trial failed (or a call that started before the circuit opened): wait COOL_OFF again
                account.circuit_state, account.trial_started_at = self.Circuit.OPEN, now
            account.save(update_fields=["last_error_at", "last_error", *self.CIRCUIT_FIELDS])
        for name in ["last_error_at", "last_error", *self.CIRCUIT_FIELDS]:
            setattr(self, name, getattr(account, name))
        if opened:
            transaction.on_commit(
                lambda: signals.integration_failed.send(sender=type(self), account=self, error=str(error)), robust=True
            )

    def record_error(self, error):
        """A failure that says nothing about the provider's health (credentials refused, a request it rejected)."""
        self.last_error_at, self.last_error = timezone.now(), str(error)[:500]
        type(self).objects.filter(pk=self.pk).update(last_error_at=self.last_error_at, last_error=self.last_error)

    def force_open(self):
        """Staff: stop the calls now, until reset() (they wait), e.g. while the provider announces an outage."""
        now = timezone.now()
        self.circuit_state, self.held_open, self.trial_started_at = self.Circuit.OPEN, True, now
        self.opened_at = self.opened_at or now
        self.save(update_fields=["held_open", *self.CIRCUIT_FIELDS, "modified"])

    def reset(self):
        """Staff: close the circuit and forget the failures counted."""
        self.circuit_state, self.held_open, self.failure_count = self.Circuit.CLOSED, False, 0
        self.failure_window_started_at = self.opened_at = self.trial_started_at = None
        self.save(update_fields=["held_open", *self.CIRCUIT_FIELDS, "modified"])


class IntegrationCall(models.Model):
    """One request made to a provider: what for, its result and its time, the provider's request id, and a redacted
    excerpt of what went and came back (redact.py: no names, phone numbers to their last four digits, addresses to
    their PIN). Deleted after INTEGRATIONS_RETENTION_DAYS (tasks.purge_old_records)."""

    kind = "integration_call"

    account = models.ForeignKey(IntegrationAccount, on_delete=models.CASCADE, related_name="calls")
    operation = models.CharField(max_length=60)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=300, help_text="Without its query string.")
    status_code = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty: no answer (network).")
    duration_ms = models.PositiveIntegerField(default=0)
    provider_request_id = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=500, blank=True)
    excerpt = models.TextField(blank=True)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created"]
        indexes = [models.Index(fields=["account", "-created"], name="integration_call_account")]

    def __str__(self):
        return f"{self.method} {self.path} → {self.status_code or 'no answer'}"

    @property
    def ok(self):
        return not self.error


class IntegrationFailure(TimeStampedModel):
    """The dead-letter list: a task that called a provider and gave up (its retries used up, or refused for good),
    with its arguments (ids, redacted all the same), its tries and last error. Staff replay it (the task runs again,
    once) or discard it with a reason. dead_letter_created tells the staff inbox."""

    kind = "dead_letter"

    class State(models.TextChoices):
        OPEN = "open", "waiting for staff"
        REPLAYED = "replayed", "replayed"
        DISCARDED = "discarded", "discarded"

    account = models.ForeignKey(
        IntegrationAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="failures"
    )
    operation = models.CharField(max_length=60)
    task_name = models.CharField(max_length=200)
    task_id = models.CharField(max_length=64, unique=True, null=True, blank=True)  # noqa: DJ001  one row per task run
    args = models.JSONField(default=dict, blank=True, help_text='{"args": [...], "kwargs": {...}}, redacted.')
    attempts = models.PositiveSmallIntegerField(default=1)
    last_error = models.CharField(max_length=500)
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN, db_index=True)
    discard_reason = models.CharField(max_length=300, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Dead letter #{self.pk} ({self.operation})"

    def _close(self, state, by, **fields):
        """Open → `state`, once (compare-and-set: a second click does nothing). Returns whether it did."""
        now = timezone.now()
        user = by if getattr(by, "pk", None) else None
        closed = (
            type(self)
            .objects.filter(pk=self.pk, state=self.State.OPEN)
            .update(state=state, resolved_at=now, resolved_by=user, modified=now, **fields)
        )
        if closed:
            self.state, self.resolved_at, self.resolved_by = state, now, user
            for name, value in fields.items():
                setattr(self, name, value)
            transaction.on_commit(lambda: signals.dead_letter_closed.send(sender=type(self), failure=self), robust=True)
        return bool(closed)

    def replay(self, by=None):
        """Run the task again with its arguments (a new try: if it fails again, a new dead letter). Once."""
        task = import_string(self.task_name)  # first: a task that no longer exists leaves it open
        if not self._close(self.State.REPLAYED, by):
            return False
        transaction.on_commit(
            lambda: task.apply_async(self.args.get("args", []), self.args.get("kwargs", {})), robust=True
        )
        return True

    def discard(self, reason, by=None):
        """Give it up, with the reason why (required)."""
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Say why it is discarded.")
        return self._close(self.State.DISCARDED, by, discard_reason=reason[:300])


class InboundEvent(models.Model):
    """A webhook a provider sent (Razorpay's excepted: shop.WebhookEvent): the raw body and its SHA-256 (unique per
    provider: a repeat is stored once), a few headers (never the token), its state and, once processed, when.
    Accepted: stored, then processed by a task (processed_at); duplicate: processed, nothing new in it; rejected: a
    wrong or missing token, kept without its body; failed: its processing gave up (inbound_event_failed), replayable.
    Deleted after INTEGRATIONS_RETENTION_DAYS."""

    kind = "inbound_event"

    class State(models.TextChoices):
        ACCEPTED = "accepted", "accepted"
        DUPLICATE = "duplicate", "duplicate (nothing new)"
        REJECTED = "rejected", "rejected (wrong or missing token)"
        FAILED = "failed", "failed"

    provider = models.CharField(max_length=30, choices=provider_choices)
    account = models.ForeignKey(
        IntegrationAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="inbound_events"
    )
    body = models.TextField(blank=True)
    sha256 = models.CharField("SHA-256 of the body", max_length=64)
    headers = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.ACCEPTED, db_index=True)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [  # a rejected body never blocks the same body sent later with the right token
            models.UniqueConstraint(
                fields=["provider", "sha256"],
                condition=~models.Q(state="rejected"),
                name="one_inbound_event_per_body",
            )
        ]

    def __str__(self):
        return f"{PROVIDERS.get(self.provider, self.provider)} event #{self.pk}"

    def process_later(self):
        """Queue the provider's processing task, once the transaction is committed."""
        task = import_string(INBOUND_PROCESSORS[self.provider])
        transaction.on_commit(lambda: task.delay(self.pk), robust=True)

    def replay(self):
        """Process it again (a failed one, or any accepted one staff want re-read)."""
        if self.state == self.State.REJECTED:
            return False
        self.state, self.processed_at, self.error = self.State.ACCEPTED, None, ""
        self.save(update_fields=["state", "processed_at", "error"])
        self.process_later()
        return True

    def fail(self, error):
        self.state, self.error = self.State.FAILED, str(error)[:500]
        self.save(update_fields=["state", "error"])
        transaction.on_commit(
            lambda: signals.inbound_event_failed.send(sender=type(self), event=self, error=self.error), robust=True
        )
