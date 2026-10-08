from email.utils import parseaddr

from anymail.exceptions import AnymailCancelSend
from anymail.signals import pre_send, tracking
from django.db import models
from django.dispatch import receiver


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


@receiver(tracking)
def suppress_bounces(sender, event, esp_name, **kwargs):
    """Anymail's tracking webhooks (/anymail/<esp>/tracking/). Kept small: an exception here answers 400, and the
    provider sends the event again. Soft bounces (a full mailbox) suppress nothing."""
    esp = event.esp_event if isinstance(event.esp_event, dict) else {}
    kinds = {esp.get("event"), esp.get("Type")}  # Brevo, Postmark; SES says "Transient: …" in the description
    soft = (event.description or "").startswith("Transient") or bool(kinds & {"soft_bounce", "SoftBounce"})
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
    """One SMS asked for (ops.sms): sent, refused by the provider, or held back by the daily cap. The number is kept as
    a keyed hash (to count, and to find a number's messages when asked) and its last four digits (for support), never
    whole. Rows older than 90 days are deleted as new SMS go out."""

    class Status(models.TextChoices):
        SENT = "sent", "sent"
        FAILED = "failed", "refused by the provider"
        CAPPED = "capped", "not sent: daily cap reached"

    kind = models.CharField(max_length=20)
    phone_hash = models.CharField("number (hashed)", max_length=64, db_index=True)
    phone_last4 = models.CharField("last 4 digits", max_length=4)
    status = models.CharField(max_length=10, choices=Status.choices)
    provider_id = models.CharField("provider's request id", max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name, verbose_name_plural = "SMS", "SMS log"
        ordering = ["-created"]

    def __str__(self):
        return f"SMS #{self.pk}"
