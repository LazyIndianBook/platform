"""Email deliverability: the provider's bounce and complaint events suppress an address (ops.models), nothing more goes
to it, and the webhooks exist only with their secret."""

import pytest
from anymail.signals import AnymailTrackingEvent, tracking
from django.core import mail
from django.core.mail import EmailMessage
from django.urls import Resolver404, resolve

from ops.models import EmailSuppression

pytestmark = pytest.mark.django_db


def report(event_type, recipient="Rahul@Example.com", **fields):
    event = AnymailTrackingEvent(event_type=event_type, recipient=recipient, **fields)
    tracking.send(sender=object, event=event, esp_name="Amazon SES")


def test_hard_bounces_complaints_and_invalid_addresses_are_suppressed_soft_bounces_not():
    report("bounced", reject_reason="bounced", description="Transient: MailboxFull")  # SES
    report("bounced", reject_reason="bounced", esp_event={"event": "soft_bounce"})  # Brevo
    report("bounced", reject_reason="bounced", esp_event={"Type": "SoftBounce"})  # Postmark
    report("delivered")
    report("complained", recipient=None)
    assert not EmailSuppression.objects.exists()
    report("bounced", reject_reason="bounced", description="Permanent: General")
    report("complained", recipient="parent@example.com", esp_event=["not a dict"])
    report("rejected", recipient="typo@exmaple.com", reject_reason="invalid")
    report("bounced", reject_reason="bounced", description="Permanent: General")  # again: one row
    assert dict(EmailSuppression.objects.values_list("email", "reason")) == {
        "rahul@example.com": "bounce",
        "parent@example.com": "complaint",
        "typo@exmaple.com": "invalid",
    }


def test_nothing_is_sent_to_a_suppressed_address(settings):
    settings.MAILERS = {"default": {"BACKEND": "anymail.backends.test.EmailBackend"}}  # Anymail's run pre_send
    EmailSuppression.objects.create(email="rahul@example.com", reason="bounce", esp="Amazon SES")
    EmailMessage("Your code", "483920", to=["Rahul Das <Rahul@Example.com>"]).send()
    EmailMessage("Order shipped", "…", to=["rahul@example.com"], cc=["anita@example.com"]).send()
    assert [(m.to, m.cc) for m in mail.outbox] == [([], ["anita@example.com"])]


def test_the_webhooks_exist_only_with_their_secret():
    with pytest.raises(Resolver404):  # ANYMAIL_WEBHOOK_SECRET is not set in the tests
        resolve("/anymail/amazon_ses/tracking/")
