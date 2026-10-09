"""Email in and out of a ticket (support/README.md "Email").

Out: every email of a ticket goes through the site's email (ops.tasks.queue_email: Amazon SES, the suppression list)
from DEFAULT_FROM_EMAIL with Reply-To the support address, the number in its subject ([SR-2026-000123]), a Message-ID
of ours, and the ticket's thread id (Ticket.thread_id, which holds a secret) first in References: SES may put its own
Message-ID on what it sends, but the References it keeps, and a reply that names the thread id has seen our email.

In: the support address is forwarded to POST /api/hooks/support-mail/ (views.SupportMailView) as the raw message
(message/rfc822) or as Amazon SES's receipt notification (the SNS message, with its `content`); parse() reads either
with the standard library's email package. guard() says why a message is not one for a ticket (our own mail coming
back, an auto-reply, a bounce, a list, a flood from one sender), thread() which ticket it answers."""

import base64
import binascii
import email
import json
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage as MimeMessage
from email.utils import getaddresses, make_msgid, parseaddr

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from pages.models import PLACEHOLDER
from pages.views import support_email

from .models import ATTACHMENT_TYPES, Ticket, TicketMessage, contact_hash, mail_domain

NUMBER = re.compile(r"\[(SR-\d{4}-\d{6,})\]", re.IGNORECASE)
THREAD_ID = re.compile(r"^<(sr-\d{4}-\d{6,})\.([0-9a-f]{16})@", re.IGNORECASE)
QUOTE_START = re.compile(
    r"^(?:>?\s*On .{4,200} wrote:|-{2,} ?Original Message ?-{2,}|From: .*\S+@\S+.*)$", re.MULTILINE | re.IGNORECASE
)
MAX_RECIPIENTS = 50  # a message to more is a list or a campaign, never a ticket (Freshdesk's rule)
MAX_ATTACHMENTS, MAX_ATTACHMENT_BYTES = 10, 10 * 1024 * 1024
AUTO_HEADERS = ("X-Autoreply", "X-Autorespond", "X-Auto-Response-Suppress")
SENDERS = ("mailer-daemon", "postmaster", "noreply", "no-reply", "donotreply", "do-not-reply")


# Out


def our_addresses():
    """The site's own addresses (lower case): mail from them is ours coming back."""
    found = {parseaddr(settings.DEFAULT_FROM_EMAIL)[1], parseaddr(settings.SERVER_EMAIL)[1], support_email()}
    found.add(settings.SHOP_SELLER.get("email", ""))
    return {address.lower() for address in found if address and "@" in address and not PLACEHOLDER.search(address)}


def officer():
    """The Grievance Officer's contact line for the customer's emails, or "" while it is a [placeholder]."""
    value = settings.DATA_PROTECTION_OFFICER
    return "" if PLACEHOLDER.search(value) else value


def headers_for(ticket, message_id, automatic=False):
    """The threading headers of an email of the ticket: its Message-ID, In-Reply-To the customer's latest message (else
    the thread id), References the thread id and the customer's messages (the last ten)."""
    theirs = list(
        ticket.messages.filter(direction=TicketMessage.Direction.IN)
        .exclude(message_id=None)
        .order_by("-sent_at", "-pk")
        .values_list("message_id", flat=True)[:10]
    )
    references = [ticket.thread_id, *reversed(theirs)]
    found = {
        "Message-ID": message_id,
        "In-Reply-To": theirs[0] if theirs else ticket.thread_id,
        "References": " ".join(references),
        "X-ExamLeaf-Ticket": ticket.number,
    }
    if address := support_email():
        found["Reply-To"] = address
    if automatic:  # RFC 3834: autoresponders do not answer it
        found["Auto-Submitted"] = "auto-replied"
    return found


def compose(ticket, to, subject, body, automatic=False):
    """An email of the ticket, ready for queue_email, and its Message-ID (kept on the TicketMessage)."""
    message_id = make_msgid(idstring=ticket.number.lower(), domain=mail_domain())
    prefix = settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
    message = EmailMessage(f"{prefix}{subject}", body, to=[to], headers=headers_for(ticket, message_id, automatic))
    return message, message_id


def context(ticket):
    from .services import category_words  # (services imports this module)

    return {
        "ticket": ticket,
        "category": category_words(ticket),
        "received": timezone.localtime(ticket.received_at),
        "due": timezone.localtime(ticket.due_at),
        "site_url": settings.SITE_URL,
        "officer": officer(),
    }


def acknowledgement(ticket, to, complaint="", with_copy=False):
    """The acknowledgement (E-Commerce Rules 4(4)): the number, when it was received and the latest answer, and from
    SUPPORT_COMPLAINT_COPY_FROM a copy of the complaint as recorded (amended rule 4(5)). (message, Message-ID, text)."""
    body = render_to_string(
        "support/email/acknowledgement.txt", {**context(ticket), "copy": with_copy, "complaint": complaint}
    ).strip()
    subject = f"[{ticket.number}] We have your request"
    message, message_id = compose(ticket, to, subject, body, automatic=True)
    return message, message_id, body


def reply(ticket, to, text):
    """A person's reply, with the footer that keeps the thread together. (message, Message-ID)."""
    body = render_to_string("support/email/reply.txt", {**context(ticket), "text": text}).strip()
    subject = ticket.subject if ticket.subject.lower().startswith("re:") else f"Re: {ticket.subject}"
    return compose(ticket, to, f"[{ticket.number}] {subject}"[:250], body)


def support_copy(ticket, name, email, text):
    """The contact form's message as a copy for the support address (SUPPORT_COPY_TO_EMAIL), Reply-To the sender; it
    carries the ticket's header, so if the address is forwarded in, guard() drops it."""
    body = f"{text}\n\n{name} <{email}>, through the contact form: {ticket.number}."
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Contact form: {ticket.number} {name}"[:250]
    headers = {"Reply-To": email, "X-ExamLeaf-Ticket": ticket.number, "Auto-Submitted": "auto-generated"}
    return EmailMessage(subject, body, to=[support_email()], headers=headers)


# In


@dataclass
class Inbound:
    """A message as it came, read: who sent it, to whom, its ids, its text, its files and the provider's verdicts."""

    sender_name: str = ""
    sender: str = ""
    recipients: list = field(default_factory=list)
    subject: str = ""
    message_id: str = ""
    in_reply_to: str = ""
    references: list = field(default_factory=list)
    date: str = ""
    text: str = ""
    attachments: list = field(default_factory=list)  # [(name, content_type, bytes)]
    dropped: list = field(default_factory=list)  # attachments not kept: [(name, why)]
    spam: bool = False
    virus: bool = False
    headers: dict = field(default_factory=dict)  # lower-case names, the ones guard() reads


def raw_message(body):
    """The RFC 822 bytes inside what the forwarder posted: the raw message itself, a base64 wrapper (the hook keeps a
    body that is not UTF-8 as "base64:…"), or Amazon SES's receipt notification (its SNS envelope or the notification
    alone) whose `content` holds the message, plain or base64. Raises ValueError for anything else."""
    if body.startswith("base64:"):
        return base64.b64decode(body[7:]), {}
    stripped = body.lstrip()
    if not stripped.startswith("{"):
        return body.encode("utf-8", "surrogateescape"), {}
    data = json.loads(stripped)
    if data.get("Type") == "Notification" and isinstance(data.get("Message"), str):
        data = json.loads(data["Message"])
    content = data.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("No message in the notification: the SES action must include the content.")
    receipt = data.get("receipt") or {}
    verdicts = {name: (receipt.get(name) or {}).get("status", "") for name in ("spamVerdict", "virusVerdict")}
    try:
        return base64.b64decode(content, validate=True), verdicts
    except binascii.Error, ValueError:
        return content.encode("utf-8", "surrogateescape"), verdicts


def message_ids(value):
    return re.findall(r"<[^<>\s]+>", str(value or ""))


def strip_quoted(text):
    """The reply without the message it quotes (written above it): cut at the first "On … wrote:" (or "-- Original
    Message --", or a "From:" line with an address), then the lines quoted with ">" at its end. A reply written under
    the quote (nothing above it) is kept whole."""
    text = text.replace("\r\n", "\n")
    quote = QUOTE_START.search(text)
    if quote and quote.start() > 0:
        text = text[: quote.start()]
    lines = text.rstrip().split("\n")
    while lines and lines[-1].lstrip().startswith(">"):
        lines.pop()
    return "\n".join(lines).strip()


def body_text(message):
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except LookupError, ValueError:  # an unknown charset: read what can be read
        content = part.get_payload(decode=True).decode("utf-8", "replace")
    return strip_tags(content) if part.get_content_type() == "text/html" else content


def parse(body):
    """Read the message the forwarder posted (raw_message)."""
    raw, verdicts = raw_message(body)
    message = email.message_from_bytes(raw, policy=policy.default)
    sender_name, sender = parseaddr(str(message.get("From", "")))
    recipients = [address.lower() for _, address in getaddresses(message.get_all("To", []) + message.get_all("Cc", []))]
    found = Inbound(
        sender_name=" ".join(sender_name.split())[:120],
        sender=sender.strip().lower(),
        recipients=[address for address in recipients if address],
        subject=" ".join(str(message.get("Subject", "")).split())[:200],
        message_id=(message_ids(message.get("Message-ID")) or [""])[0][:255],
        in_reply_to=(message_ids(message.get("In-Reply-To")) or [""])[0],
        references=message_ids(message.get("References"))[-20:],
        date=str(message.get("Date", ""))[:100],
        spam=verdicts.get("spamVerdict") == "FAIL" or str(message.get("X-SES-Spam-Verdict", "")).upper() == "FAIL",
        virus=verdicts.get("virusVerdict") == "FAIL" or str(message.get("X-SES-Virus-Verdict", "")).upper() == "FAIL",
        headers={
            name.lower(): str(message.get(name, ""))
            for name in ("Auto-Submitted", "Precedence", "List-Id", "X-ExamLeaf-Ticket", "Content-Type", *AUTO_HEADERS)
            if message.get(name) is not None
        },
    )
    if isinstance(message, MimeMessage):
        found.text = strip_quoted(body_text(message))[:20000]
        for part in message.iter_attachments():
            name = (part.get_filename() or "attachment")[:200]
            kind = part.get_content_type()
            data = part.get_payload(decode=True) or b""
            if found.virus:
                found.dropped.append((name, "the provider found a virus"))
            elif kind not in ATTACHMENT_TYPES:
                found.dropped.append((name, f"not a kind kept ({kind})"))
            elif len(data) > MAX_ATTACHMENT_BYTES:
                found.dropped.append((name, "over 10 MB"))
            elif len(found.attachments) >= MAX_ATTACHMENTS:
                found.dropped.append((name, "more than 10 files"))
            else:
                found.attachments.append((name, kind, data))
    return found


def guard(inbound):
    """Why this message must not reach a ticket, or "": our own mail come back (our address, our header), an
    auto-reply (RFC 3834's Auto-Submitted, the vendors' own headers, Precedence), a bounce (a delivery report, a
    mailer daemon), a list or a mail to more than MAX_RECIPIENTS, a message without a sender or an id."""
    headers = inbound.headers
    if not inbound.sender or "@" not in inbound.sender:
        return "no sender"
    if inbound.sender in our_addresses() or "x-examleaf-ticket" in headers:
        return "our own mail"
    if headers.get("auto-submitted", "no").strip().lower() != "no" or any(
        name.lower() in headers for name in AUTO_HEADERS
    ):
        return "an auto-reply"
    if headers.get("precedence", "").strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return "bulk mail"
    if "list-id" in headers:
        return "a mailing list"
    if "multipart/report" in headers.get("content-type", "") or inbound.sender.split("@")[0] in SENDERS:
        return "a bounce or a no-reply sender"
    if len(inbound.recipients) > MAX_RECIPIENTS:
        return f"more than {MAX_RECIPIENTS} recipients"
    if not inbound.message_id:
        return "no Message-ID"
    return ""


def thread(inbound):
    """The ticket this message answers, or None (a new ticket): one whose thread id or one of whose messages it names
    in In-Reply-To or References (it has seen our email), else one whose number is in its subject, when it comes from
    that ticket's requester (a number alone is easy to guess)."""
    ids = [inbound.in_reply_to, *inbound.references]
    for value in ids:
        if match := THREAD_ID.match(value):
            ticket = Ticket.objects.filter(number__iexact=match.group(1), thread_token=match.group(2).lower()).first()
            if ticket:
                return ticket
    known = TicketMessage.objects.filter(message_id__in=[value for value in ids if value]).select_related("ticket")
    if found := known.order_by("-pk").first():
        return found.ticket
    if match := NUMBER.search(inbound.subject):
        ticket = Ticket.objects.filter(number__iexact=match.group(1)).first()
        if ticket and ticket.requester_email_hash == contact_hash("email", inbound.sender):
            return ticket
    return None
