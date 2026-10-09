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

from examleaf.celery import LONG_TASK, single_run
from integrations.tasks import InboundEventTask

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


# Phase B: settings and integrations (ops/README.md): MSG91's delivery reports, SES's suppression list, the templates


@shared_task(base=InboundEventTask, bind=True)
def process_sms_event(self, event_id):
    """A delivery report stored by /api/hooks/sms-events/ (ops/webhooks.py) written on its SmsLog rows. Once: a
    processed event is left alone; a report about no SMS of ours (another sender on the same MSG91 account) says so."""
    from django.utils import timezone

    from integrations.models import InboundEvent

    from .webhooks import apply_reports

    event = InboundEvent.objects.get(pk=event_id)
    if event.processed_at or event.state == InboundEvent.State.REJECTED:
        return
    changed = apply_reports(event.body, event.headers.get("Content-Type", "application/json"))
    event.processed_at = timezone.now()
    if not changed:
        event.state, event.error = InboundEvent.State.DUPLICATE, "No SMS of ours waits for this report."
    event.save(update_fields=["processed_at", "state", "error"])


@shared_task(**LONG_TASK)  # SES's suppression list, a thousand addresses a page
@single_run(LONG_TASK["time_limit"])
def sync_ses_suppressions():
    """Daily: SES's account-level suppression list read and the addresses missing from ours added (ops/ses.py; none
    removed, so a second run adds nothing). Only with SES as the email backend."""
    if "amazon_ses" not in settings.MAILERS["default"]["BACKEND"]:
        return None
    from .ses import sync_suppressions

    return sync_suppressions()


@shared_task
@single_run(300)
def check_templates(now=None):
    """Nightly: the approved SMS templates unused for IDLE_WARN_DAYS (DLT deactivates one unused for 90 days) and the
    approved templates whose yearly self-certification is due, each an inbox item for whoever changes templates; done
    once it is used again, certified, or no longer approved. Returns the counts opened."""
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from staff.models import InboxItem
    from staff.signals import close_items, open_item

    from .models import MessageTemplate
    from .staff_api import CERTIFY_WARN_DAYS, IDLE_WARN_DAYS

    now = parse_datetime(now) if isinstance(now, str) else now or timezone.now()
    idle, certify = 0, 0
    for template in MessageTemplate.objects.all():
        approved = template.approval_state == MessageTemplate.Approval.APPROVED
        days = (now - (template.last_used_at or template.created)).days
        if approved and template.channel == MessageTemplate.Channel.SMS and days >= IDLE_WARN_DAYS:
            title = f"SMS template #{template.pk} ({template.event}) unused for {days} days: DLT deactivates it at 90"
            open_item(InboxItem.Kind.TEMPLATE_IDLE, template, title, "ops.change_messagetemplate", days=days)
            idle += 1
        else:
            close_items(template, InboxItem.Kind.TEMPLATE_IDLE)
        certified = template.self_certified_on
        due = certified is None or (timezone.localdate(now) - certified).days >= CERTIFY_WARN_DAYS
        if approved and due:
            title = f"Template #{template.pk} ({template.event}): its yearly self-certification is due"
            open_item(InboxItem.Kind.TEMPLATE_CERTIFY, template, title, "ops.change_messagetemplate")
            certify += 1
        else:
            close_items(template, InboxItem.Kind.TEMPLATE_CERTIFY)
    return {"idle": idle, "certify": certify}
