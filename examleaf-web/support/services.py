"""What happens to a ticket (support/README.md), in one place: the staff API, the contact form, "My requests", the
inbound mail and the tasks all go through these functions. A change locks the ticket's row, keeps its clocks, writes
its message and its audit event (staff.audit) in the same transaction, and what goes to the customer leaves once the
transaction is committed. The rules are here, never in the panel: which statuses follow which, what closing asks for,
who may be mentioned or assigned, which orders and records a ticket may name."""

import logging
import re
from datetime import timedelta
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions, serializers

from ops.tasks import queue_email
from staff import audit
from staff.backends import scoped
from staff.models import InboxItem
from staff.signals import close_items, open_item

from . import mail
from .models import SavedReply, Ticket, TicketAttachment, TicketMessage, TicketSeries, contact_hash

logger = logging.getLogger(__name__)
User = get_user_model()
Status, Category, Source = Ticket.Status, Ticket.Category, Ticket.Source
Direction, Channel = TicketMessage.Direction, TicketMessage.Channel
HANDLE, VIEW = "staff.handle_ticket", "support.view_ticket"
AUTO_CLOSE_AFTER = timedelta(days=4)  # a resolved ticket is closed once nobody has come back for 4 days
SPAM_KEPT = timedelta(days=30)  # then purged, and never in a report
ERASED = "[erased with the account]"
ORDER_NUMBER = re.compile(r"\b(?:T-)?EL-\d{4}-\d{6}\b", re.IGNORECASE)
PAPER_CODE = re.compile(r"[A-Z]{3}-[EMH]\d{2}")
ASSAMESE, BENGALI_SCRIPT = re.compile("[ৰৱ]"), re.compile("[ঀ-৿]")


def refuse(message, field="non_field_errors"):
    return serializers.ValidationError({field: [message]})


def target(ticket):
    """How the audit log names a ticket: its number, never its requester."""
    return ("support.ticket", str(ticket.pk), ticket.number)


def lock(ticket):
    return Ticket.objects.select_for_update().get(pk=ticket.pk)


def category_words(ticket):
    return ticket.get_category_display() if ticket.category else ""


def guess_language(text):
    """The language a customer wrote in: Assamese if its script's own letters (ৰ, ৱ) are there, Bengali for the rest of
    that script, else English. Staff change it on the ticket; the saved replies follow it."""
    if ASSAMESE.search(text or ""):
        return Ticket.Language.AS
    return Ticket.Language.BN if BENGALI_SCRIPT.search(text or "") else Ticket.Language.EN


def next_number(today=None):
    """SR-YYYY-NNNNNN, the next of the year's series (India's calendar year), under its row's lock, in the caller's
    transaction: two tickets made at once queue on the row and take one number each, and a ticket rolled back gives
    its number back, so the series has neither a gap nor a number twice."""
    year = (today or timezone.localdate()).year
    TicketSeries.objects.get_or_create(year=year)
    series = TicketSeries.objects.select_for_update().get(year=year)
    series.last += 1
    series.save(update_fields=["last"])
    return f"SR-{year}-{series.last:06d}"


def account_for(email):
    """The account whose confirmed email address this is, or None (an address nobody confirmed links nothing)."""
    if not email:
        return None
    found = EmailAddress.objects.filter(email__iexact=email, verified=True).select_related("user").first()
    return found.user if found and found.user.is_active and not found.user.is_staff else None


def contact_email(ticket):
    """Where the ticket's emails go: the requester's address, else their account's (never an erased one's)."""
    if ticket.requester_email:
        return ticket.email
    user = ticket.user
    return user.email if user and user.is_active and not user.email.endswith("@deleted.invalid") else ""


def contact_phone(ticket):
    if ticket.requester_phone:
        return ticket.phone
    user = ticket.user
    return user.login_phone if user and user.is_active and user.login_phone_verified else ""


def requester_orders(ticket):
    """The requester's orders: their account's, and a guest's placed with their email address (newest first)."""
    from shop.models import Order

    condition = Q(pk__in=[])
    if ticket.user_id:
        condition |= Q(user_id=ticket.user_id)
    if email := contact_email(ticket):
        condition |= Q(user=None, email__iexact=email)
    if ticket.order_id:
        condition |= Q(pk=ticket.order_id)
    return Order.objects.filter(condition)


def order_for(ticket, number, user, perm="shop.view_order"):
    """One of the requester's orders by its number, within `user`'s scope: the linked one when no number is given."""
    if not number:
        if ticket.order_id is None:
            raise refuse("Name the order: this ticket has none linked.", "order")
        number = ticket.order.number
    order = scoped(requester_orders(ticket), user, perm).filter(number=str(number).strip().upper()).first()
    if order is None:
        raise refuse("Not one of this requester's orders (or not one you may see).", "order")
    return order


def paper_for(code, user):
    """A paper by its code (PHY-E01), within `user`'s scope (content.view_paper)."""
    from content.models import Paper

    code = str(code or "").strip().upper()
    found = PAPER_CODE.fullmatch(code) and scoped(Paper.objects.all(), user, "content.view_paper").filter(code=code)
    paper = found.first() if found else None
    if paper is None:
        raise refuse("No paper with this code (PHY-E01), or not one you may see.", "record")
    return paper


# Making a ticket


def save_attachments(message, files):
    """Keep a message's files (name, content type, bytes) in the private storage."""
    import hashlib

    for name, content_type, data in files:
        attachment = TicketAttachment(
            message=message,
            name=name[:200],
            content_type=content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        attachment.file.save("upload", ContentFile(data), save=False)
        attachment.save()


def create_ticket(
    *,
    source,
    channel,
    subject,
    body,
    received_at=None,
    user=None,
    name="",
    email="",
    phone="",
    category="",
    priority=Ticket.Priority.MEDIUM,
    nch_docket="",
    order=None,
    by=None,
    request=None,
    spam=False,
    language=None,
    message_id=None,
    headers=None,
    inbound_event=None,
    attachments=(),
):
    """A new ticket and its first message (the complaint as recorded), its number and its clocks from when it was
    received (never later than now). `by`: the member of staff who logged it (a call, WhatsApp, an NCH docket, a letter
    by email), audited. Unless it came in quarantined (`spam`), the acknowledgement follows once it is committed."""
    now = timezone.now()
    received_at = min(received_at or now, now)
    with transaction.atomic():
        ticket = Ticket(
            source=source,
            nch_docket=nch_docket.strip()[:40],
            category=category,
            priority=priority,
            status=Status.SPAM if spam else Status.NEW,
            spam_at=now if spam else None,
            language=language or guess_language(f"{subject}\n{body}"),
            subject=" ".join((subject or "").split())[:200] or "(no subject)",
            user=user,
            requester_name=" ".join((name or "").split())[:120] or (user.full_name if user else ""),
            order=order,
            received_at=received_at,
        )
        ticket.set_email(email)
        ticket.set_phone(phone)
        ticket.number = next_number()
        ticket.refresh_clocks()
        ticket.save()
        message = TicketMessage.objects.create(
            ticket=ticket,
            direction=Direction.IN,
            channel=channel,
            author=by or user,
            body=(body or "").strip()[:20000],
            sent_at=received_at,
            message_id=message_id or None,
            headers=headers or {},
            inbound_event=inbound_event,
        )
        save_attachments(message, attachments)
        if by is not None:
            details = {"source": source, "category": category, "nch": bool(nch_docket), "received_at": received_at}
            audit.record("support.ticket_logged", request=request, actor=by, target=target(ticket), details=details)
        if not spam:
            transaction.on_commit(lambda: queue_acknowledgement(ticket.pk), robust=True)
    return ticket


def from_contact_form(name, email, text, request=None):
    """The contact form's message as a ticket (its source the website), linked to the account whose confirmed address
    sent it and to the order whose number it names when that order was placed with the same address; the address
    the support mailbox had before gets a copy while SUPPORT_COPY_TO_EMAIL is on."""
    from shop.models import Order

    order = None
    if match := ORDER_NUMBER.search(text):
        order = Order.objects.filter(number=match.group(0).upper(), email__iexact=email).first()
    ticket = create_ticket(
        source=Source.FORM,
        channel=Channel.WEB,
        subject=text.split("\n", 1)[0][:120],
        body=text,
        user=account_for(email),
        name=name,
        email=email,
        order=order,
        request=request,
    )
    if settings.SUPPORT_COPY_TO_EMAIL:
        copy = mail.support_copy(ticket, name, email, text)
        transaction.on_commit(lambda: queue_email(copy), robust=True)
    return ticket


def from_account(user, *, category, subject, text, order_number="", request=None):
    """A request made on My requests: the account's own, its address the requester's, one of its orders linked."""
    order = None
    if order_number:
        order = user.orders.filter(number=order_number.strip().upper()).first()
        if order is None:
            raise refuse("Not one of your orders.", "order")
    phone = user.login_phone if user.login_phone_verified else ""
    return create_ticket(
        source=Source.FORM,
        channel=Channel.WEB,
        subject=subject,
        body=text,
        user=user,
        email=user.email,
        phone=phone,
        category=category,
        order=order,
        request=request,
    )


# The acknowledgement


def queue_acknowledgement(ticket_id):
    """Hand the acknowledgement to the worker; with the queue down, send it here and now (as queue_email does)."""
    from .tasks import send_acknowledgement

    try:
        send_acknowledgement.delay(ticket_id)
    except send_acknowledgement.OperationalError:
        logger.exception("broker unavailable, acknowledging ticket %s here", ticket_id)
        try:
            acknowledge(ticket_id)
        except Exception:
            logger.exception("the acknowledgement of ticket %s could not be sent here either", ticket_id)


def sms_ready():
    """Whether an acknowledgement can go by SMS: SMS on, and on MSG91 the DLT template of `ticket_ack` registered."""
    return settings.SMS_ENABLED and (
        settings.SMS_BACKEND != "msg91" or bool(settings.MSG91_TEMPLATES.get("ticket_ack"))
    )


def complaint_as_recorded(ticket):
    first = ticket.messages.filter(direction=Direction.IN).order_by("sent_at", "pk").first()
    return first.body if first else ""


def acknowledge(ticket_id, *, by=None, request=None, again=False):
    """Send the acknowledgement with the number (E-Commerce Rules 4(4)) by email, or by SMS when only a mobile number is
    known (at 08:00 if it is night: ops' quiet hours); from SUPPORT_COMPLAINT_COPY_FROM the email carries a copy of the
    complaint as recorded. Once: a ticket acknowledged already is left alone unless staff send it `again` (an address
    added, a copy owed). Returns its message, or None when nothing could go (no contact, SMS off, a limit, the
    night): the clock runs on and the inbox hears of it."""
    from ops.sms import queue_sms
    from shipping.messages import quiet

    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
        if ticket.status == Status.SPAM or (ticket.acknowledged_at and not again):
            return None
        with_copy = timezone.localdate() >= settings.SUPPORT_COMPLAINT_COPY_FROM
        message_id, outgoing = None, None
        if address := contact_email(ticket):
            outgoing, message_id, text = mail.acknowledgement(
                ticket, address, complaint_as_recorded(ticket), with_copy=with_copy
            )
            channel = Channel.EMAIL
        elif phone := contact_phone(ticket):
            if not sms_ready():
                return None
            if quiet():
                ticket.ack_held = True
                ticket.save(update_fields=["ack_held"])
                return None
            if not queue_sms("ticket_ack", phone, {"var1": ticket.number}, user=ticket.user):
                return None
            channel, with_copy = Channel.SMS, False
            text = f"ExamLeaf: we have your request {ticket.number}."
        else:
            return None
        now = timezone.now()
        ticket.acknowledged_at = ticket.acknowledged_at or now
        ticket.ack_held = False
        if with_copy:
            ticket.complaint_copy_sent_at = now
        if ticket.acknowledged_at > ticket.ack_due_at and not ticket.ack_breached:
            breached(ticket, "ack")
        ticket.save()
        message = TicketMessage.objects.create(
            ticket=ticket,
            direction=Direction.OUT,
            channel=channel,
            author=by,
            automatic=True,
            body=text,
            message_id=message_id,
        )
        close_items(ticket, InboxItem.Kind.TICKET_DUE)
        if by is not None:
            details = {"channel": channel, "copy": with_copy, "again": again}
            audit.record("support.acknowledged", request=request, actor=by, target=target(ticket), details=details)
        if outgoing is not None:
            transaction.on_commit(lambda: queue_email(outgoing), robust=True)
    return message


def record_acknowledgement(ticket, *, by, note, request=None):
    """The acknowledgement given another way (on the call, on WhatsApp, on NCH's portal), with how: an internal note."""
    with transaction.atomic():
        ticket = lock(ticket)
        if ticket.acknowledged_at:
            raise refuse("It was acknowledged already.")
        ticket.acknowledged_at = timezone.now()
        if ticket.acknowledged_at > ticket.ack_due_at and not ticket.ack_breached:
            breached(ticket, "ack")
        ticket.save()
        TicketMessage.objects.create(
            ticket=ticket, direction=Direction.NOTE, channel=Channel.PANEL, author=by, body=f"Acknowledged: {note}"
        )
        close_items(ticket, InboxItem.Kind.TICKET_DUE)
        audit.record("support.acknowledged", request=request, actor=by, target=target(ticket), details={"how": "noted"})
    return ticket


# Messages


def staff_who_may_see(ticket, ids):
    """The active members of staff with these ids who may see the ticket (in their scope); refuses any other id."""
    people = {person.pk: person for person in User.objects.filter(pk__in=ids, is_active=True, is_staff=True)}
    missing = [pk for pk in ids if pk not in people or not people[pk].has_perm(VIEW, ticket)]
    if missing:
        raise refuse(f"Not someone who may see this ticket: {', '.join(f'#{pk}' for pk in missing)}.", "mentions")
    return list(people.values())


def mention(ticket, person, message):
    """An inbox item for the person a note names, one per ticket and person while it waits (a target of its own,
    "support.mention" with "ticket:person", since one note may name several people; the panel opens the ticket)."""
    item, created = InboxItem.objects.get_or_create(
        kind=InboxItem.Kind.TICKET_MENTION,
        target_type="support.mention",
        target_id=f"{ticket.pk}:{person.pk}",
        done_at=None,
        defaults={
            "title": f"{ticket.number}: you were named in a note",
            "permission": VIEW,
            "assignee": person,
            "data": {"ticket": ticket.number, "note": message.pk},
        },
    )
    if not created:
        item.data = {**item.data, "note": message.pk}
        item.save(update_fields=["data"])


def seen_mentions(ticket, user):
    """The person opened the ticket: the mentions waiting for them there are done."""
    InboxItem.objects.filter(
        kind=InboxItem.Kind.TICKET_MENTION,
        target_type="support.mention",
        target_id=f"{ticket.pk}:{user.pk}",
        done_at=None,
    ).update(done_at=timezone.now(), done_by=user)


def add_message(ticket, *, by, direction, body, channel="", mentions=(), request=None):
    """A reply to the customer (out: emailed, or a call or WhatsApp message recorded) or an internal note (mentions
    open an inbox item for each person named). Only a person's reply counts as the first response."""
    body = (body or "").strip()
    if not body:
        raise refuse("Write the message.", "body")
    with transaction.atomic():
        ticket = lock(ticket)
        if direction == Direction.NOTE:
            people = staff_who_may_see(ticket, sorted(set(mentions)))
            message = TicketMessage.objects.create(
                ticket=ticket,
                direction=Direction.NOTE,
                channel=Channel.PANEL,
                author=by,
                body=body[:20000],
                mentions=[person.pk for person in people],
            )
            for person in people:
                if person.pk != by.pk:
                    mention(ticket, person, message)
            details = {"message": message.pk, "mentions": message.mentions}
            audit.record("support.noted", request=request, actor=by, target=target(ticket), details=details)
            return message
        if ticket.status == Status.SPAM:
            raise refuse("A ticket in spam gets no reply: take it out of spam first.")
        address = contact_email(ticket)
        channel = channel or (Channel.EMAIL if address else "")
        if channel == Channel.EMAIL and not address:
            raise refuse("No email address for this requester: record how you answered (phone, WhatsApp).", "channel")
        if channel not in (Channel.EMAIL, Channel.PHONE, Channel.WHATSAPP, Channel.NCH):
            raise refuse("Say how you answered: email, phone, WhatsApp or NCH's portal.", "channel")
        outgoing, message_id = mail.reply(ticket, address, body) if channel == Channel.EMAIL else (None, None)
        message = TicketMessage.objects.create(
            ticket=ticket, direction=Direction.OUT, channel=channel, author=by, body=body[:20000], message_id=message_id
        )
        now = message.sent_at
        ticket.first_response_at = ticket.first_response_at or now
        if not ticket.acknowledged_at:  # a person's reply acknowledges it too
            ticket.acknowledged_at = now
            if now > ticket.ack_due_at and not ticket.ack_breached:
                breached(ticket, "ack")
            close_items(ticket, InboxItem.Kind.TICKET_DUE)
        if ticket.status == Status.NEW:
            ticket.status = Status.OPEN
        ticket.save()
        details = {"message": message.pk, "channel": channel}
        audit.record("support.replied", request=request, actor=by, target=target(ticket), details=details)
        if outgoing is not None:
            transaction.on_commit(lambda: queue_email(outgoing), robust=True)
    return message


def receive(ticket, inbound, event=None):
    """A customer's email that answers a ticket: kept on it; a ticket waiting on them is open again, a resolved one
    reopened (counted), a closed one stays closed and the message starts a follow-up ticket instead."""
    with transaction.atomic():
        ticket = lock(ticket)
        if ticket.status == Status.CLOSED:
            follow_up = create_ticket(
                source=Source.EMAIL,
                channel=Channel.EMAIL,
                subject=inbound.subject,
                body=inbound.text,
                user=ticket.user,
                name=inbound.sender_name or ticket.requester_name,
                email=inbound.sender,
                category=ticket.category,
                order=ticket.order,
                message_id=inbound.message_id,
                headers=headers_of(inbound),
                inbound_event=event,
                attachments=inbound.attachments,
            )
            note(
                follow_up, f"A follow-up of {ticket.number}, closed on {timezone.localtime(ticket.closed_at):%d %b %Y}."
            )
            return follow_up
        sender = contact_hash("email", inbound.sender)
        theirs = {ticket.requester_email_hash, contact_hash("email", ticket.user.email if ticket.user else "")}
        message = TicketMessage.objects.create(
            ticket=ticket,
            direction=Direction.IN,
            channel=Channel.EMAIL,
            author=ticket.user if sender in theirs else None,
            body=inbound.text,
            message_id=inbound.message_id,
            headers={**headers_of(inbound), "other_sender": sender not in theirs},
            inbound_event=event,
        )
        save_attachments(message, inbound.attachments)
        if ticket.status in (Status.WAITING_CUSTOMER, Status.WAITING_THIRD_PARTY):
            ticket.status = Status.OPEN
            ticket.save(update_fields=["status"])
        elif ticket.status == Status.RESOLVED:
            reopened(ticket, actor=None)
    return ticket


def headers_of(inbound):
    return {
        "from_name": inbound.sender_name,
        "in_reply_to": inbound.in_reply_to,
        "references": inbound.references,
        "subject": inbound.subject,
        "date": inbound.date,
        "dropped": [f"{name}: {why}" for name, why in inbound.dropped],
    }


def note(ticket, text, by=None):
    """A line the site writes on the ticket (an action's outcome, a follow-up's origin): an automatic internal note."""
    return TicketMessage.objects.create(
        ticket=ticket, direction=Direction.NOTE, channel=Channel.PANEL, author=by, automatic=True, body=text[:20000]
    )


# Changes, statuses, assignment


TRANSITIONS = {  # status → the statuses staff may move it to (reopen/ takes a resolved or closed one back)
    Status.NEW: {Status.OPEN, Status.WAITING_CUSTOMER, Status.WAITING_THIRD_PARTY, Status.RESOLVED, Status.CLOSED}
    | {Status.SPAM},
    Status.OPEN: {Status.WAITING_CUSTOMER, Status.WAITING_THIRD_PARTY, Status.RESOLVED, Status.CLOSED, Status.SPAM},
    Status.WAITING_CUSTOMER: {Status.OPEN, Status.WAITING_THIRD_PARTY, Status.RESOLVED, Status.CLOSED, Status.SPAM},
    Status.WAITING_THIRD_PARTY: {Status.OPEN, Status.WAITING_CUSTOMER, Status.RESOLVED, Status.CLOSED, Status.SPAM},
    Status.RESOLVED: {Status.CLOSED},
    Status.CLOSED: set(),
    Status.SPAM: {Status.OPEN},  # not spam after all: back to work, acknowledged then
}
CLOSING = {  # what closing a ticket of each category asks for, beside its category and the resolution
    Category.ORDER: ["order"],
    Category.PAYMENT: ["order"],
    Category.CONTENT_ERROR: ["record"],
    Category.PRIVACY_REQUEST: ["data_request"],
}


def closing_fields(ticket):
    """The fields resolving or closing this ticket asks for (the panel draws only these)."""
    return ["category", "resolution", *CLOSING.get(ticket.category, [])]


def allowed(ticket):
    return sorted(TRANSITIONS[ticket.status])


def breached(ticket, which):
    """A clock found past its time (`ack` or `due`): flagged once, audited, and an inbox item for whoever handles it.
    The caller saves the ticket."""
    setattr(ticket, f"{which}_breached", True)
    due = ticket.ack_due_at if which == "ack" else ticket.due_at
    audit.record(
        "support.clock_breached",
        actor_type=audit.ActorType.SYSTEM,
        target=target(ticket),
        details={"clock": which, "due": due, "category": ticket.category, "source": ticket.source},
    )
    if ticket.status in Ticket.RUNNING:
        open_item(
            InboxItem.Kind.TICKET_BREACH,
            ticket,
            f"{ticket.number} is past its legal deadline{f' ({category_words(ticket)})' if ticket.category else ''}",
            HANDLE,
            due,
        )
        assign_items(ticket)


def assign_items(ticket):
    """The ticket's open inbox items go to its assignee (or back to everyone who handles tickets)."""
    InboxItem.objects.filter(
        target_type="support.ticket",
        target_id=str(ticket.pk),
        done_at=None,
        kind__in=[InboxItem.Kind.TICKET_DUE, InboxItem.Kind.TICKET_BREACH],
    ).update(assignee=ticket.assignee_id)


def change(ticket, data, *, by, request=None):
    """Staff's edit of a ticket: its category, priority, language, subject, source and NCH docket, the order or paper
    it is about, the requester's name, email address or mobile number. A new category or source sets its clocks
    again from when it was received (they never move otherwise). Returns the ticket."""
    with transaction.atomic():
        ticket = lock(ticket)
        changes = {}
        for name in ("category", "priority", "language", "source", "nch_docket"):
            if name in data and data[name] != getattr(ticket, name):
                changes[name] = [getattr(ticket, name), data[name]]
                setattr(ticket, name, data[name])
        if ticket.source == Source.NCH and not ticket.nch_docket:
            raise refuse("A complaint from the National Consumer Helpline needs its docket number.", "nch_docket")
        if "subject" in data and data["subject"] != ticket.subject:
            changes["summary"] = [ticket.subject, data["subject"]]  # free text: masked in the log
            ticket.subject = data["subject"]
        if "name" in data and data["name"] != ticket.requester_name:
            changes["full_name"] = [ticket.requester_name, data["name"]]
            ticket.requester_name = data["name"]
        if "email" in data and data["email"] != ticket.email:
            changes["email"] = [ticket.email, data["email"]]
            ticket.set_email(data["email"])
            ticket.user = ticket.user or account_for(data["email"])
        if "phone" in data and data["phone"] != ticket.phone:
            changes["phone"] = [ticket.phone, data["phone"]]
            ticket.set_phone(data["phone"])
        if "order" in data:
            order = order_for(ticket, data["order"], by) if data["order"] else None
            if order != ticket.order:
                changes["order"] = [getattr(ticket.order, "number", None), getattr(order, "number", None)]
                ticket.order = order
        if "record" in data:
            paper = paper_for(data["record"], by) if data["record"] else None
            record = ("content.paper", str(paper.pk)) if paper else ("", "")
            if record != (ticket.record_type, ticket.record_id):
                changes["record"] = [ticket.record_id or None, record[1] or None]
                ticket.record_type, ticket.record_id = record
        if not (ticket.user_id or ticket.requester_email or ticket.requester_phone):
            raise refuse("A ticket keeps a way to reach its requester: an email address or a mobile number.", "email")
        if {"category", "source"} & set(changes):
            ticket.refresh_clocks()
        ticket.save()
        if changes:
            audit.record("support.changed", request=request, actor=by, target=target(ticket), changes=changes)
    return ticket


def set_status(ticket, status, *, by, request=None, resolution="", order="", record=""):
    """Move a ticket to `status` if TRANSITIONS allows it. Resolving or closing asks for the category's fields
    (closing_fields: the resolution always, the order of an order or payment ticket, the paper of a content error, the
    data request of a privacy request), refused with each field's error; it stops the clocks, and a resolution past
    the due time is a breach. Spam quarantines it (purged after 30 days); out of spam it is acknowledged then."""
    from shop.models import Order

    with transaction.atomic():
        ticket = lock(ticket)
        if status not in TRANSITIONS[ticket.status]:
            raise refuse(f"A {ticket.get_status_display()} ticket cannot become {Status(status).label}.", "status")
        before, now = ticket.status, timezone.now()
        if status in Ticket.DONE:
            if order and ticket.order is None:
                ticket.order = order_for(ticket, order, by)
            if record and not ticket.record_id:
                ticket.record_type, ticket.record_id = "content.paper", str(paper_for(record, by).pk)
            resolution = (resolution or "").strip() or ticket.resolution
            problems = {}
            if not ticket.category:
                problems["category"] = ["Sort it first: its category decides what closing it asks for."]
            if not resolution:
                problems["resolution"] = ["Say what was done."]
            for name in CLOSING.get(ticket.category, []):
                if name == "order" and ticket.order is None:
                    problems["order"] = ["Link the order it is about (its number)."]
                if name == "record" and not ticket.record_id:
                    problems["record"] = ["Name the paper the mistake is in (its code, PHY-E01)."]
                if name == "data_request" and ticket.data_request_id is None:
                    problems["data_request"] = ["Start its data request first: that request's own clocks follow it."]
            if problems:
                raise serializers.ValidationError(problems)
            ticket.resolution = resolution[:5000]
            ticket.resolved_at = ticket.resolved_at or now
            if status == Status.CLOSED:
                ticket.closed_at = now
            if ticket.resolved_at > ticket.due_at and not ticket.due_breached:
                breached(ticket, "due")
            close_items(ticket, InboxItem.Kind.TICKET_DUE)
            close_items(ticket, InboxItem.Kind.TICKET_BREACH)
        elif status == Status.SPAM:
            ticket.spam_at = now
            close_items(ticket)
        if before == Status.SPAM:
            ticket.spam_at = None
        ticket.status = status
        ticket.save()
        details = {"from": before, "to": status, "order": getattr(ticket.order, "number", None)}
        if isinstance(ticket.order, Order) and ticket.order.is_test:
            details["test"] = True
        audit.record("support.status", request=request, actor=by, target=target(ticket), details=details)
        if before == Status.SPAM and not ticket.acknowledged_at:
            transaction.on_commit(lambda: queue_acknowledgement(ticket.pk), robust=True)
    return ticket


def reopened(ticket, *, actor, request=None):
    """Back to open (the caller holds its lock): counted; its clocks did not stop for it, so past its due time it is a
    breach at once."""
    ticket.status = Status.OPEN
    ticket.reopened_count += 1
    ticket.resolved_at = ticket.closed_at = None
    if timezone.now() > ticket.due_at and not ticket.due_breached:
        breached(ticket, "due")
    ticket.save()
    actor_type = None if actor else audit.ActorType.SYSTEM
    details = {"count": ticket.reopened_count, "by_customer": actor is None}
    audit.record(
        "support.reopened", request=request, actor=actor, actor_type=actor_type, target=target(ticket), details=details
    )


def reopen(ticket, *, by, request=None):
    with transaction.atomic():
        ticket = lock(ticket)
        if ticket.status not in Ticket.DONE:
            raise refuse("Only a resolved or closed ticket is reopened.")
        reopened(ticket, actor=by, request=request)
    return ticket


def assign(ticket, assignee, *, by, request=None):
    """Give the ticket to a member of staff who handles tickets and may see this one (None: nobody); its inbox items
    follow."""
    with transaction.atomic():
        ticket = lock(ticket)
        if assignee is not None and not (
            assignee.is_active and assignee.is_staff and assignee.has_perm(HANDLE) and assignee.has_perm(VIEW, ticket)
        ):
            raise refuse("Not someone who handles tickets like this one.", "assignee")
        before = ticket.assignee_id
        ticket.assignee = assignee
        ticket.save(update_fields=["assignee"])
        assign_items(ticket)
        details = {"from": before, "to": getattr(assignee, "pk", None)}
        audit.record("support.assigned", request=request, actor=by, target=target(ticket), details=details)
    return ticket


# Saved replies


VARIABLES = {"name", "order", "refund_days", "number"}
TOKEN = re.compile(r"\{(\w+)(?:\|([^{}]{0,80}))?\}")
REFUND_DAYS = {  # Razorpay's usual time to the customer by the payment's method (research lms 4.6), working days
    "upi": "2 to 7",
    "netbanking": "2 to 10",
    "card": "5 to 10",
    "emi": "5 to 10",
}


def unknown_variables(body):
    return sorted({match.group(1) for match in TOKEN.finditer(body or "")} - VARIABLES)


def reply_variables(ticket):
    """What a saved reply's variables say for this ticket: the requester's first name, the linked order's number, the
    days Razorpay usually takes to refund its payment's method, the ticket's number. Empty: the reply's fallback."""
    from shop.models import Order, Payment

    name = (ticket.requester_name or (ticket.user.full_name if ticket.user else "")).split()
    days = ""
    if ticket.order_id:
        payment = ticket.order.payments.filter(method=Order.Method.RAZORPAY, status=Payment.Status.CAPTURED).first()
        payment = payment or ticket.order.payments.filter(status=Payment.Status.REFUNDED).first()
        method = str((payment.raw_payload or {}).get("method") or "") if payment else ""
        days = REFUND_DAYS.get(method, "")
    return {
        "name": name[0] if name else "",
        "order": ticket.order.number if ticket.order_id else "",
        "refund_days": days,
        "number": ticket.number,
    }


def render_reply(body, values):
    """{name|there}: the value, else the fallback after the bar, else nothing."""
    return TOKEN.sub(lambda match: values.get(match.group(1)) or (match.group(2) or ""), body)


def rendered_replies(ticket, user):
    """The saved replies (not in the bin) as this ticket fills them, its language first; none without
    support.view_savedreply."""
    if not user.has_perm("support.view_savedreply"):
        return []
    values = reply_variables(ticket)
    replies = SavedReply.objects.filter(deleted_at=None)
    ordered = sorted(replies, key=lambda reply: (reply.language != ticket.language, reply.language, reply.title))
    return [
        {"id": reply.pk, "title": reply.title, "language": reply.language, "text": render_reply(reply.body, values)}
        for reply in ordered
    ]


# The clocks' watch (every 15 minutes: tasks.watch_clocks)


def warn(ticket, which, due):
    words = "acknowledge it" if which == "ack" else "resolve it"
    category = f" ({category_words(ticket)})" if ticket.category else ""
    open_item(InboxItem.Kind.TICKET_DUE, ticket, f"{ticket.number}: {words} soon{category}", HANDLE, due)
    assign_items(ticket)
    setattr(ticket, f"{which}_warned", True)


def watch(now=None):
    """Each running ticket's clocks: an inbox item once three quarters of a clock's time has gone (the
    acknowledgement's while it is not given, then the resolution's), a breach flagged once its time is over (an audit
    event and an inbox item, once: a second run, or one overlapping this one, finds the flag). Spam, resolved and
    closed tickets have no running clock. Returns the counts."""
    now = now or timezone.now()
    counts = {"warned": 0, "breached": 0}
    due = Ticket.objects.filter(status__in=Ticket.RUNNING).filter(
        Q(acknowledged_at=None, ack_breached=False, ack_due_at__lte=now)
        | Q(acknowledged_at=None, ack_warned=False, ack_breached=False, ack_warn_at__lte=now)
        | Q(due_breached=False, due_at__lte=now)
        | Q(acknowledged_at__isnull=False, due_warned=False, due_breached=False, due_warn_at__lte=now)
    )
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().filter(pk=pk, status__in=Ticket.RUNNING).first()
            if ticket is None:  # resolved meanwhile
                continue
            fields = set()
            if not ticket.acknowledged_at:
                if not ticket.ack_breached and ticket.ack_due_at <= now:
                    breached(ticket, "ack")
                    fields.add("ack_breached")
                    counts["breached"] += 1
                elif not ticket.ack_warned and ticket.ack_warn_at <= now:
                    warn(ticket, "ack", ticket.ack_due_at)
                    fields.add("ack_warned")
                    counts["warned"] += 1
            if not ticket.due_breached and ticket.due_at <= now:
                breached(ticket, "due")
                fields.add("due_breached")
                counts["breached"] += 1
            elif (
                ticket.acknowledged_at and not (ticket.due_warned or ticket.due_breached) and ticket.due_warn_at <= now
            ):
                warn(ticket, "due", ticket.due_at)
                fields.add("due_warned")
                counts["warned"] += 1
            if fields:
                ticket.save(update_fields=fields)
    return counts


def close_resolved(now=None):
    """Resolved tickets nobody came back to for AUTO_CLOSE_AFTER: closed (the system's audit event each)."""
    now = now or timezone.now()
    closed = 0
    for pk in Ticket.objects.filter(status=Status.RESOLVED, resolved_at__lte=now - AUTO_CLOSE_AFTER).values_list(
        "pk", flat=True
    ):
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().filter(pk=pk, status=Status.RESOLVED).first()
            if ticket is None or ticket.resolved_at > now - AUTO_CLOSE_AFTER:  # reopened meanwhile
                continue
            ticket.status, ticket.closed_at = Status.CLOSED, now
            ticket.save(update_fields=["status", "closed_at"])
            audit.record(
                "support.status",
                actor_type=audit.ActorType.SYSTEM,
                target=target(ticket),
                details={"from": Status.RESOLVED, "to": Status.CLOSED, "auto": True},
            )
            closed += 1
    return closed


def send_held():
    """The SMS acknowledgements held through the night, once it is morning (each ticket's own lock: sent once)."""
    from shipping.messages import quiet

    if quiet():
        return 0
    return sum(acknowledge(pk) is not None for pk in Ticket.objects.filter(ack_held=True).values_list("pk", flat=True))


def purge_spam(now=None):
    """Tickets in spam for SPAM_KEPT: deleted with their messages, files and the raw mail they came in; the numbers
    purged are in the audit log (so the series' gaps are explained). Returns how many."""
    from django.core.files.storage import default_storage

    from integrations.models import InboundEvent

    now = now or timezone.now()
    old = Ticket.objects.filter(status=Status.SPAM, spam_at__lte=now - SPAM_KEPT)
    numbers = list(old.order_by("number").values_list("number", flat=True))
    if not numbers:
        return 0
    files = list(TicketAttachment.objects.filter(message__ticket__in=old).values_list("file", flat=True))
    events = (
        TicketMessage.objects.filter(ticket__in=old).exclude(inbound_event=None).values_list("inbound_event", flat=True)
    )
    with transaction.atomic():
        InboundEvent.objects.filter(pk__in=list(events)).delete()
        old.delete()
        audit.record(
            "support.spam_purged",
            actor_type=audit.ActorType.SYSTEM,
            details={"count": len(numbers), "numbers": numbers[:500]},
        )
    transaction.on_commit(lambda: [default_storage.delete(name) for name in files], robust=True)
    return len(numbers)


def forget_requester(user):
    """The account was erased (accounts.DeletionRequest.complete): its tickets keep their numbers, categories, dates and
    clocks (the grievance register), and lose what identifies the person: the requester's details, the messages'
    text and files, the raw mail. Returns how many tickets."""
    from django.core.files.storage import default_storage

    from integrations.models import InboundEvent

    tickets = Ticket.objects.filter(user=user)
    count = tickets.count()
    if not count:
        return 0
    files = list(TicketAttachment.objects.filter(message__ticket__in=tickets).values_list("file", flat=True))
    messages = TicketMessage.objects.filter(ticket__in=tickets)
    with transaction.atomic():
        InboundEvent.objects.filter(
            pk__in=list(messages.exclude(inbound_event=None).values_list("inbound_event", flat=True))
        ).delete()
        TicketAttachment.objects.filter(message__ticket__in=tickets).delete()
        messages.update(body=ERASED, headers={}, mentions=[], inbound_event=None)
        tickets.update(
            requester_name="",
            requester_email="",
            requester_email_hash="",
            requester_phone="",
            requester_phone_hash="",
            subject=ERASED,
            resolution="",
        )
        audit.record(
            "support.requester_forgotten", actor_type=audit.ActorType.SYSTEM, target=user, details={"tickets": count}
        )
    transaction.on_commit(lambda: [default_storage.delete(name) for name in files], robust=True)
    return count


# Actions from a ticket (each logged on it and audited)


def logged(ticket, *, by, action, line, request=None, **details):
    """An action's outcome on the ticket (an automatic note with `line`, which names no customer detail) and in the
    audit log (support.action)."""
    with transaction.atomic():
        note(ticket, line, by=by)
        audit.record(
            "support.action",
            request=request,
            actor=by,
            target=target(ticket),
            details={"action": action, **details},
        )


def refund_amount(order, lines):
    """The refund of these order lines ([{item, quantity}], each from zero: nothing is refunded by accident): each
    unit's price less its share of the line's discount, in rupees to the paisa."""
    items = {item.pk: item for item in order.items.all()}
    total = Decimal("0.00")
    for line in lines:
        item = items.get(line.get("item"))
        quantity = line.get("quantity", 0)
        if item is None:
            raise refuse("Not a line of this order.", "lines")
        if not isinstance(quantity, int) or not 0 <= quantity <= item.quantity:
            raise refuse(f"Between 0 and {item.quantity} copies of {item.title}.", "lines")
        each = item.unit_price.amount - (item.discount.amount if item.discount else Decimal(0)) / item.quantity
        total += each * quantity
    return total.quantize(Decimal("0.01"))


def refund(ticket, *, by, reason, order="", amount=None, lines=None, idempotency_key="", request=None):
    """A refund through the shop's refund action (staff.approvals' "order.refund": its permission, the maker's limit, a
    change request above it, which FINANCE approves). An order not yet shipped is cancelled and refunded in full; a
    shipped one by the amount, or by the lines' quantities. Returns (the change request, whether it is new)."""
    from staff import approvals

    order = order_for(ticket, order, by)
    payload = {}
    if lines:
        payload["amount"] = str(refund_amount(order, lines))
        if Decimal(payload["amount"]) <= 0:
            raise refuse("Choose at least one copy to refund.", "lines")
    elif amount not in (None, ""):
        payload["amount"] = str(amount)
    change_request, created = approvals.ask(
        "order.refund",
        maker=by,
        target=order.number,
        payload=payload,
        reason=f"{reason} (ticket {ticket.number})",
        idempotency_key=idempotency_key,
        request=request,
    )
    if not created:  # the same Idempotency-Key again: answered as the first time, logged once
        return change_request, False
    state = change_request.get_status_display()
    line = f"Refund of ₹{change_request.amount} on {order.number} asked: change request #{change_request.pk}, {state}."
    logged(ticket, by=by, action="refund", line=line, request=request, change_request=change_request.pk)
    if ticket.order_id is None:
        Ticket.objects.filter(pk=ticket.pk, order=None).update(order=order)
    return change_request, True


def cancel(ticket, *, by, reason, order="", idempotency_key="", request=None):
    """Cancel an order of the requester's. One paid online is cancelled by its refund (as the admin's Cancel: the
    refund's permission and limit, FINANCE above it): (the change request, whether it is new); any other is
    cancelled at once (the order's own permission, shop.change_order): the order."""
    from django_fsm import TransitionNotAllowed

    from shop import services as shop
    from staff.approvals import Refund

    order = order_for(ticket, order, by, "shop.change_order")
    if Refund._paid(order) is not None:
        if not by.has_perm("staff.refund_order"):
            raise exceptions.PermissionDenied("Needs staff.refund_order: this order was paid online.")
        return refund(
            ticket, by=by, reason=reason, order=order.number, idempotency_key=idempotency_key, request=request
        )
    try:
        order = shop.cancel_order(order, reason[:200], by=by)
    except TransitionNotAllowed as error:
        raise refuse(f"Order {order.number} cannot be cancelled now ({order.status_label}).", "order") from error
    logged(ticket, by=by, action="cancel", line=f"Order {order.number} cancelled.", request=request, order=order.number)
    return order


def resend_invoice(ticket, *, by, order="", request=None):
    """The order's invoice again: an email to the order's own address with the link to its page, where the invoice is
    (the shop's `invoice` email). Refused while it has none, and while its file is still being made."""
    from shop import services as shop
    from shop import tasks as shop_tasks
    from shop.models import Invoice

    order = order_for(ticket, order, by)
    invoice = Invoice.objects.filter(order=order).first()
    if invoice is None:
        raise refuse(f"Order {order.number} has no invoice yet (it is made once the order is paid or dispatched).")
    if not invoice.pdf:
        transaction.on_commit(lambda: shop_tasks.generate_invoice.delay(order.pk), robust=True)
        raise refuse(f"The invoice {invoice.number} is being made again: send it in a few minutes.")
    shop.notify(order, "invoice", sms=False, invoice=invoice)
    line = f"Invoice {invoice.number} of {order.number} sent again to the order's email address."
    logged(ticket, by=by, action="resend_invoice", line=line, request=request, order=order.number)
    return invoice


def resend_confirmation(ticket, *, by, order="", request=None):
    """The order's confirmation email again (the shop's own, to the order's address): its lines, its link and, for an
    order with the course, how to open it in the app ("the code email": the course opens on the account itself)."""
    from shop import services as shop

    order = order_for(ticket, order, by)
    if order.placed_at is None:
        raise refuse(f"Order {order.number} was never paid or placed: it has no confirmation to send.", "order")
    shop.notify(order, "confirmation", sms=False)
    line = f"The confirmation of {order.number} sent again to the order's email address."
    logged(ticket, by=by, action="resend_confirmation", line=line, request=request, order=order.number)
    return order


def extend_access(ticket, *, by, entitlement, days, reason, request=None):
    """One of the requester's course entitlements extended by `days` from its end (from today if it has ended), with
    the reason kept on it. An entitlement without an end needs none."""
    from learn.models import Entitlement

    if ticket.user_id is None:
        raise refuse("This requester has no account: there is no course to extend.")
    with transaction.atomic():
        found = (
            scoped(Entitlement.objects.filter(user_id=ticket.user_id), by, "learn.change_entitlement")
            .select_for_update()
            .filter(pk=entitlement)
            .first()
        )
        if found is None:
            raise refuse("Not one of this requester's entitlements (or not one you may change).", "entitlement")
        if found.valid_until is None:
            raise refuse("It has no end date: nothing to extend.", "entitlement")
        before = found.valid_until
        found.valid_until = max(before, timezone.localdate()) + timedelta(days=days)
        found.note = reason[:200]
        found.save(update_fields=["valid_until", "note", "modified"])
    subject = found.subject.name if found.subject_id else "every subject"
    line = f"Course access ({subject}) extended by {days} days: until {found.valid_until:%d %b %Y}. {reason}"
    logged(
        ticket,
        by=by,
        action="extend_access",
        line=line,
        request=request,
        entitlement=found.pk,
        days=days,
        valid_until=[before, found.valid_until],
    )
    return found


def look_up_code(ticket, *, by, code, request=None):
    """A book code, by its digest (the code is never kept nor logged): its batch, its subject and whether it was
    redeemed, by this requester or someone else (never who), in one line."""
    from learn.models import CODE_ALPHABET, CODE_LENGTH, BookCode, clean_code, code_digest

    cleaned = clean_code(code)
    if len(cleaned) != CODE_LENGTH or set(cleaned) - set(CODE_ALPHABET):
        raise refuse("A book code has 12 letters and digits, like 7KQM-3XPA-9TRW.", "code")
    found = scoped(BookCode.objects.select_related("subject"), by, "learn.view_bookcode").filter(
        digest=code_digest(cleaned)
    )
    book_code = found.first()
    if book_code is None:
        answer = {"found": False, "line": "No such code: check it against the one printed in the book."}
    else:
        subject = book_code.subject.name if book_code.subject_id else "every subject"
        mine = book_code.redeemed_by_id is not None and book_code.redeemed_by_id == ticket.user_id
        if book_code.redeemed_at is None:
            state = "not redeemed yet"
        elif mine:
            state = f"redeemed by this requester on {timezone.localtime(book_code.redeemed_at):%d %b %Y}"
        else:
            state = f"redeemed by another account on {timezone.localtime(book_code.redeemed_at):%d %b %Y}"
        answer = {
            "found": True,
            "batch": book_code.batch,
            "subject": subject,
            "redeemed": book_code.redeemed_at is not None,
            "by_requester": mine,
            "line": f"Code of batch {book_code.batch} ({subject}): {state}.",
        }
    if by.has_perm(HANDLE):  # on the ticket for whoever works on it; the code itself: nowhere
        logged(ticket, by=by, action="book_code", line=answer["line"], request=request, found=answer["found"])
    else:  # a reader (an auditor) writes nothing on the ticket: the look is audited
        details = {"action": "book_code", "found": answer["found"]}
        audit.record("support.action", request=request, actor=by, target=target(ticket), details=details)
    return answer


DATA_REQUEST_CHANNELS = {
    Source.FORM: "form",
    Source.EMAIL: "email",
    Source.PHONE: "phone",
    Source.WHATSAPP: "phone",
    Source.NCH: "letter",
}


def start_data_request(ticket, *, by, kind, summary="", request=None):
    """A data request (staff.DataRequest: the DPDP rights queue, its own clocks) from a grievance or privacy ticket,
    received when the ticket was, the ticket named in its details and linked to it. Once per ticket."""
    from staff.models import DataRequest

    with transaction.atomic():
        ticket = lock(ticket)
        if ticket.category not in (Category.GRIEVANCE, Category.PRIVACY_REQUEST):
            raise refuse("A data request starts from a grievance or a privacy request.", "kind")
        if ticket.data_request_id:
            raise refuse(f"Its data request DR-{ticket.data_request_id} is started already.", "kind")
        requester = contact_email(ticket) or contact_phone(ticket)
        if not requester:
            raise refuse("No email address or mobile number to answer the request to: add one first.", "kind")
        data_request = DataRequest.objects.create(
            kind=kind,
            channel=DATA_REQUEST_CHANNELS[ticket.source],
            user=ticket.user,
            requester=requester[:200],
            summary=(summary or ticket.subject)[:300],
            received_at=ticket.received_at,
            created_by=by,
            details={"ticket": ticket.number},
        )
        ticket.data_request = data_request
        ticket.save(update_fields=["data_request"])
        audit.record(
            "data_request.created",
            request=request,
            actor=by,
            target=data_request,
            details={"kind": kind, "channel": data_request.channel, "ticket": ticket.number},
        )
    logged(
        ticket,
        by=by,
        action="data_request",
        line=f"Data request DR-{data_request.pk} ({data_request.get_kind_display()}) started from this ticket.",
        request=request,
        data_request=data_request.pk,
    )
    return data_request
