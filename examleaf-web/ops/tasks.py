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


# The retention schedule's clean-up (examleaf/retention.py): what each kind of record keeps only for a while


BATCH = 1000  # rows deleted at a time: short transactions, bounded memory


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def trim_expired():
    """Nightly (celery beat): the parts the retention schedule keeps only for a while are blanked on the rows past
    it (the SMS log's last four digits after 90 days). A second run finds nothing left to blank. Returns
    {rule: rows}."""
    from django.apps import apps

    from examleaf import retention

    done = {}
    for rule in retention.SCHEDULE:
        if rule.model and rule.trim_days:
            rows = apps.get_model(rule.model).objects.filter(
                **{f"{rule.date_field}__lt": retention.cutoff(rule.key, rule.trim_days)}
            )
            done[rule.key] = rows.exclude(**rule.trim).update(**rule.trim)
    record_clean_up("retention.trimmed", done)
    return done


@shared_task(**LONG_TASK)
@single_run(LONG_TASK["time_limit"])
def purge_expired():
    """Nightly (celery beat): the rows the retention schedule keeps no longer are deleted, a batch at a time (the SMS
    log after a year, Razorpay's webhook records and the tasks' results after 7 days, the app's phones silent for 90
    days), and the orders past their books' period lose the customer's details and their documents' PDFs
    (purge_books), unless a legal hold keeps them. A second run finds nothing more. Returns {rule: rows}."""
    from django.apps import apps

    from examleaf import retention

    done = {}
    for rule in retention.SCHEDULE:
        if not (rule.model and rule.keep_days):
            continue
        model = apps.get_model(rule.model)
        old = model.objects.filter(**{f"{rule.date_field}__lt": retention.cutoff(rule.key)})
        count = 0
        while pks := list(old.values_list("pk", flat=True)[:BATCH]):
            count += model.objects.filter(pk__in=pks).delete()[0]
        done[rule.key] = count
    done["books"] = purge_books()
    record_clean_up("retention.purged", done)
    return done


def purge_books(today=None, limit=500):
    """The orders whose books' period is over (each of their dates, the invoice's and the credit notes' too, before
    examleaf.retention.books_cutoff): the customer's details leave them (shop.services.forget_orders; the numbers and
    totals stay) and the documents' PDFs are deleted once committed. An order a legal hold keeps (itself, a document
    of it, or its customer: staff.privacy.held_order_ids) stays as it is. At most `limit` a night. Returns how
    many."""
    from django.db import transaction

    from examleaf import retention
    from shop.models import CreditNote, Invoice, Order
    from shop.services import DELETED, forget_orders
    from staff.privacy import held_order_ids

    cutoff = retention.midnight(retention.books_cutoff(today))
    orders = (
        Order.objects.filter(created__lt=cutoff)
        .exclude(placed_at__gte=cutoff)
        .exclude(invoice__created__gte=cutoff)
        .exclude(invoice__credit_notes__created__gte=cutoff)
        .exclude(email=DELETED)
        .exclude(pk__in=held_order_ids())
    )
    pks = list(orders.values_list("pk", flat=True)[:limit])
    if not pks:
        return 0
    with transaction.atomic():
        documents = [
            *Invoice.objects.filter(order__in=pks).exclude(pdf=""),
            *CreditNote.objects.filter(invoice__order__in=pks).exclude(pdf=""),
        ]
        forget_orders(Order.objects.filter(pk__in=pks), today=today)
        Invoice.objects.filter(order__in=pks).update(pdf="")
        CreditNote.objects.filter(invoice__order__in=pks).update(pdf="")
        files = [(document.pdf.storage, document.pdf.name) for document in documents]
        transaction.on_commit(lambda: [storage.delete(name) for storage, name in files], robust=True)
    return len(pks)


def record_clean_up(action, counts):
    """One audit event for a night's clean-up that changed anything: its counts per rule (no personal data)."""
    from staff import audit

    if any(counts.values()):
        audit.record(action, actor_type=audit.ActorType.SYSTEM, details={"rows": counts})
