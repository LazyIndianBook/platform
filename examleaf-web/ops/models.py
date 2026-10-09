import logging
from email.utils import parseaddr

from anymail.exceptions import AnymailCancelSend
from anymail.signals import post_send, pre_send, tracking
from django.conf import settings
from django.db import models
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


class EmailSuppression(models.Model):
    """An address the email provider reported as bouncing for good, as invalid, or complaining (marked as spam): the
    site sends it nothing more. Staff delete the row to send to it again (RUNBOOK.md "Email")."""

    class Reason(models.TextChoices):
        BOUNCE = "bounce", "hard bounce"
        INVALID = "invalid", "invalid address"
        COMPLAINT = "complaint", "complaint (marked as spam)"

    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=10, choices=Reason.choices)
    esp = models.CharField("reported by", max_length=20)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Suppressed address #{self.pk}"  # no address in the admin's change log


def soft_bounce(event):
    """A bounce that may pass (a full mailbox): Brevo's and Postmark's kind, SES's "Transient: …" description."""
    esp = event.esp_event if isinstance(event.esp_event, dict) else {}
    kinds = {esp.get("event"), esp.get("Type")}
    return (event.description or "").startswith("Transient") or bool(kinds & {"soft_bounce", "SoftBounce"})


@receiver(tracking)
def suppress_bounces(sender, event, esp_name, **kwargs):
    """Anymail's tracking webhooks (/anymail/<esp>/tracking/). Kept small: an exception here answers 400, and the
    provider sends the event again. Soft bounces (a full mailbox) suppress nothing."""
    soft = soft_bounce(event)
    if not event.recipient:
        return
    if event.event_type == "complained":
        reason = EmailSuppression.Reason.COMPLAINT
    elif event.event_type in ("bounced", "rejected") and event.reject_reason in ("bounced", "invalid") and not soft:
        reason = EmailSuppression.Reason.INVALID if event.reject_reason == "invalid" else EmailSuppression.Reason.BOUNCE
    else:
        return
    EmailSuppression.objects.get_or_create(email=event.recipient.lower(), defaults={"reason": reason, "esp": esp_name})


@receiver(pre_send)
def skip_suppressed(sender, message, esp_name, **kwargs):
    """No email to a suppressed address (Anymail's backends: production); a message left with nobody is cancelled."""
    every = [parseaddr(address)[1].lower() for address in [*message.to, *message.cc, *message.bcc]]
    suppressed = set(EmailSuppression.objects.filter(email__in=every).values_list("email", flat=True))
    if suppressed:
        for name in ("to", "cc", "bcc"):
            setattr(message, name, [a for a in getattr(message, name) if parseaddr(a)[1].lower() not in suppressed])
        if not (message.to or message.cc or message.bcc):
            raise AnymailCancelSend("every recipient is suppressed")


class SmsLog(models.Model):
    """One SMS asked for (ops.sms): queued, sent, refused by the provider, or held back by a limit (per number, per
    account, per purpose, the daily cap). The number is kept as a keyed hash (to count, and to find a number's messages
    when asked) and its last four digits (for support), never whole; the account it was for, to count and for Download
    my data (deleted with the account). Rows older than 90 days are deleted as new SMS go out."""

    class Status(models.TextChoices):
        QUEUED = "queued", "queued"
        SENT = "sent", "sent"
        FAILED = "failed", "refused by the provider"
        CAPPED = "capped", "not sent: a limit was reached"

    kind = models.CharField(max_length=20)
    phone_hash = models.CharField("number (hashed)", max_length=64, db_index=True)
    phone_last4 = models.CharField("last 4 digits", max_length=4)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="sms_messages"
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    provider_id = models.CharField("provider's request id", max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    # Phase B: settings and integrations (MSG91's delivery reports, ops/webhooks.py)

    class Delivery(models.TextChoices):
        DELIVERED = "delivered", "delivered"
        PENDING = "pending", "with the operator"
        FAILED = "failed", "not delivered"
        REJECTED = "rejected", "rejected (DLT, DND or a blocked number)"

    delivery = models.CharField("delivery report", max_length=10, choices=Delivery.choices, blank=True)
    delivery_reason = models.CharField(max_length=200, blank=True, help_text="MSG91's words: why it failed.")
    delivered_at = models.DateTimeField("report's time", null=True, blank=True)

    class Meta:
        verbose_name, verbose_name_plural = "SMS", "SMS log"
        ordering = ["-created"]
        indexes = [models.Index(fields=["provider_id"], name="ops_smslog_provider_id")]  # delivery reports

    def __str__(self):
        return f"SMS #{self.pk}"


# Phase B: settings and integrations


class MessageTemplate(models.Model):
    """One message the site sends, per channel and language, as registered with the regulator and the provider
    (research-integrations 4.2; plan 7.11): an SMS's DLT template id, the principal entity id, the sender header and its
    suffix, MSG91's template id; a WhatsApp template's name (Phase D); an email's subject. Its text as registered with
    typed variables, the category and approval state, when it was last used (DLT deactivates a template unused for 90
    days) and when it was last self-certified. ops.sms sends an SMS kind with the approved template's MSG91 id when one
    is here, with the environment's MSG91_TEMPLATE_<KIND> otherwise."""

    class Channel(models.TextChoices):
        EMAIL = "email", "email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Language(models.TextChoices):
        EN = "en", "English"
        AS = "as", "Assamese"
        BN = "bn", "Bengali"

    class Category(models.TextChoices):
        TRANSACTIONAL = "transactional", "transactional (one-time codes)"
        SERVICE = "service", "service (about something bought)"
        PROMOTIONAL = "promotional", "promotional"
        UTILITY = "utility", "utility (WhatsApp)"
        AUTHENTICATION = "authentication", "authentication (WhatsApp)"

    class Approval(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted for approval"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        PAUSED = "paused", "paused"
        DEACTIVATED = "deactivated", "deactivated"

    class Suffix(models.TextChoices):  # DLT headers since 2025: the kind of sender
        PROMOTIONAL = "P", "P (promotional)"
        SERVICE = "S", "S (service)"
        TRANSACTIONAL = "T", "T (transactional)"
        GOVERNMENT = "G", "G (government)"

    VARIABLE_TYPES = ["numeric", "alphanumeric", "url", "urlott", "cbn", "email"]  # TRAI's typed variables (Nov 2025)

    event = models.CharField(max_length=40, help_text="What it is sent for: otp, order_placed … (ops.sms's kinds).")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    text = models.TextField(blank=True, max_length=2000, help_text="As registered: DLT's {#var#} placeholders.")
    subject = models.CharField(max_length=200, blank=True, help_text="An email's subject.")
    variables = models.JSONField(default=list, blank=True, help_text='[{"name", "type", "max_length", "about"}]')
    dlt_template_id = models.CharField("DLT template id", max_length=30, blank=True)
    pe_id = models.CharField("principal entity id", max_length=30, blank=True)
    header = models.CharField(max_length=11, blank=True, help_text="The registered sender id, e.g. EXMLEF.")
    header_suffix = models.CharField(max_length=1, choices=Suffix.choices, blank=True)
    msg91_id = models.CharField("MSG91 template id", max_length=60, blank=True)
    whatsapp_name = models.CharField("WhatsApp template name", max_length=100, blank=True)
    category = models.CharField(max_length=15, choices=Category.choices)
    approval_state = models.CharField(max_length=12, choices=Approval.choices, default=Approval.DRAFT)
    last_used_at = models.DateTimeField(null=True, blank=True)
    self_certified_on = models.DateField(null=True, blank=True, help_text="DLT's yearly self-certification.")
    notes = models.TextField(blank=True, max_length=1000)
    created = models.DateTimeField(default=timezone.now)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("view", "add", "change")  # never deleted: deactivate it
        ordering = ["event", "channel", "language"]
        constraints = [
            models.UniqueConstraint(fields=["event", "channel", "language"], name="one_template_per_message")
        ]

    def __str__(self):
        return f"Template #{self.pk}"


class EmailStat(models.Model):
    """How many emails went out and what became of them, per day (India) and event: sent (anymail's post_send),
    delivered, bounced (for good) and complained (its tracking webhooks). The connections page's bounce and complaint
    rates over 7 days come from here, against SES's review thresholds (5 % and 0.1 %). Counts only, no address."""

    class Event(models.TextChoices):
        SENT = "sent", "sent"
        DELIVERED = "delivered", "delivered"
        BOUNCED = "bounced", "bounced for good"
        COMPLAINED = "complained", "complained (marked as spam)"

    day = models.DateField()
    event = models.CharField(max_length=10, choices=Event.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ("view",)
        ordering = ["-day", "event"]
        constraints = [models.UniqueConstraint(fields=["day", "event"], name="one_email_stat_per_day")]

    def __str__(self):
        return f"{self.day} {self.event}: {self.count}"

    @classmethod
    def count_one(cls, event, n=1):
        """Add `n` to today's count of `event` (concurrent senders each add theirs: an UPDATE of F())."""
        if n <= 0:
            return
        row, _ = cls.objects.get_or_create(day=timezone.localdate(), event=event)
        cls.objects.filter(pk=row.pk).update(count=F("count") + n)


@receiver(post_send)
def count_sent(sender, message, status, esp_name, **kwargs):
    """Every email an anymail backend handed over (production's), by recipient. Never breaks the send."""
    try:
        recipients = getattr(status, "recipients", None) or {}
        sent = sum(1 for each in recipients.values() if getattr(each, "status", "") in ("sent", "queued"))
        EmailStat.count_one(EmailStat.Event.SENT, sent)
    except Exception:  # a count is not worth an email
        logger.exception("The email count could not be kept")


@receiver(tracking)
def count_tracked(sender, event, esp_name, **kwargs):
    """The provider's word on each email (its tracking webhook): delivered, bounced for good, complained."""
    try:
        if event.event_type == "delivered":
            EmailStat.count_one(EmailStat.Event.DELIVERED)
        elif event.event_type == "complained":
            EmailStat.count_one(EmailStat.Event.COMPLAINED)
        elif event.event_type == "bounced" and not soft_bounce(event):
            EmailStat.count_one(EmailStat.Event.BOUNCED)
    except Exception:  # an exception here would answer 400 and the provider would send the event again
        logger.exception("The email event could not be counted")
