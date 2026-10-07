import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=5)
def send_email(message):
    """Send one email rendered in the web process (`message` is the dict made by queue_email)."""
    msg = EmailMultiAlternatives(
        message["subject"], message["body"], message["from_email"], message["to"], headers=message["headers"]
    )
    for content, mimetype in message["alternatives"]:
        msg.attach_alternative(content, mimetype)
    msg.send()


def queue_email(msg):
    """Hand an EmailMessage to the worker. If the broker cannot be reached the email is sent here and now instead,
    so a sign-up never fails (and no verification code is lost) because Redis is down."""
    message = {
        "subject": msg.subject,
        "body": msg.body,
        "from_email": msg.from_email,
        "to": msg.to,
        "headers": msg.extra_headers,
        "alternatives": [tuple(a) for a in getattr(msg, "alternatives", [])],
    }
    try:
        send_email.delay(message)
    except send_email.OperationalError:
        logger.exception("broker unavailable, sending the email synchronously")
        send_email.run(message)


def queue_text_email(to, subject, body):
    queue_email(EmailMessage(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX + subject, body, to=[to]))


@shared_task
def reset_failed_logins():
    """Daily: forget django-axes' failed log-in records (address and browser) so that they do not pile up."""
    call_command("axes_reset")
