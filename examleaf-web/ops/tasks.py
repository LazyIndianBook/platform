import logging
import re

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.management import call_command
from django.template.loader import render_to_string
from django.utils.html import urlize
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5)
def send_email(self, message):
    """Send one email rendered in the web process (`message` is the dict made by queue_email). A task delivered again
    after its worker died (acks_late) finds the mark its sending left and sends nothing: the mark is the task's id in
    the cache for a day (Redis down: the email may go twice, as it always could)."""
    sent = f"email-sent:{self.request.id}" if self.request.id else None  # None: run here, the queue down
    if sent and cache.get(sent):
        return
    msg = EmailMultiAlternatives(
        message["subject"], message["body"], message["from_email"], message["to"], headers=message["headers"]
    )
    for content, mimetype in message["alternatives"]:
        msg.attach_alternative(content, mimetype)
    msg.send()
    if sent:
        cache.set(sent, True, 24 * 3600)


CODE, LINK = re.compile(r"[A-Z0-9-]{4,12}"), re.compile(r"https?://\S+")


def html_alternative(subject, body):
    """The HTML part of an email, made from its text: templates/email/message.html (the drawn email layout) with the
    subject as the heading and each paragraph of the text, its addresses made links; a code alone in its paragraph
    (483920) shows large, a link alone as a button."""
    blocks = []
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        paragraph = paragraph.strip()
        if CODE.fullmatch(paragraph) and re.search(r"\d", paragraph):
            blocks.append(("code", paragraph))
        elif LINK.fullmatch(paragraph):
            blocks.append(("link", paragraph))
        elif paragraph:
            html = urlize(paragraph, autoescape=True).replace("\n", "<br>")
            blocks.append(("text", mark_safe(html.replace("<a href=", '<a style="color: #0B2A5B" href='))))  # escaped
    title = subject.removeprefix(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
    context = {"title": title, "blocks": blocks, "site_url": settings.SITE_URL, "seller": settings.SHOP_SELLER}
    return render_to_string("email/message.html", context)


def queue_email(msg):
    """Hand an EmailMessage to the worker. If the broker cannot be reached (refused at once, or no answer within a few
    seconds: settings.CELERY_BROKER_TRANSPORT_OPTIONS) the email is sent here and now instead, so a sign-up never fails
    (and no verification code is lost) because Redis is down. If the email provider is down as well, the failure is
    logged (Sentry) and the page goes on: the student asks for a new code, as RUNBOOK.md says. A plain-text email
    without an HTML part gets one made from its text (html_alternative); the text stays the body."""
    alternatives = [tuple(a) for a in getattr(msg, "alternatives", [])]
    if msg.content_subtype == "plain" and not any(mimetype == "text/html" for _, mimetype in alternatives):
        alternatives.append((html_alternative(msg.subject, msg.body), "text/html"))
    message = {
        "subject": " ".join(msg.subject.split()),  # a line break typed into a form would make Django refuse it (I2)
        "body": msg.body,
        "from_email": msg.from_email,
        "to": msg.to,
        "headers": msg.extra_headers,
        "alternatives": alternatives,
    }
    try:
        send_email.delay(message)
    except send_email.OperationalError:
        logger.exception("broker unavailable, sending the email synchronously")
        try:
            send_email.run(message)
        except Exception:
            logger.exception("the email could not be sent here either; dropped")


def queue_text_email(to, subject, body):
    queue_email(EmailMessage(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX + subject, body, to=[to]))


@shared_task
def reset_failed_logins():
    """Daily: forget django-axes' failed log-in records (address and browser) so that they do not pile up."""
    call_command("axes_reset")


@shared_task
def clear_sessions():
    """Daily: delete expired sessions, and with them what they held (allauth's pending email codes and addresses,
    guests' order numbers, the API's verification sessions) (M10), and the signed-in devices of ended sessions
    (allauth.usersessions: their addresses and browsers; allauth itself drops them only when a user lists them)."""
    from allauth.usersessions.models import UserSession

    call_command("clearsessions")
    for device in UserSession.objects.iterator():
        device.purge()
