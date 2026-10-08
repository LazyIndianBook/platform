from django.conf import settings
from django.core.mail import EmailMessage

from ops.tasks import queue_email

from .models import PLACEHOLDER

CONTACT_SENT = "Thank you: your message is on its way to us. We reply by email."


def support_email():
    """Where the contact form (api/v1/contact/) writes to: SUPPORT_EMAIL, else the seller's address (SELLER_EMAIL); ""
    while that is empty or still a [placeholder], and the form is then refused."""
    address = getattr(settings, "SUPPORT_EMAIL", "") or settings.SHOP_SELLER["email"]
    return "" if not address or PLACEHOLDER.search(address) else address


def send_contact(name, email, message):
    """The contact form's message, emailed to support_email() with the sender to reply to; nothing is stored."""
    body = f"{message}\n\n{name} <{email}>, through the contact form."
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Contact form: {name}"
    queue_email(EmailMessage(subject, body, to=[support_email()], headers={"Reply-To": email}))
