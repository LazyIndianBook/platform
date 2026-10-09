"""Support (support/README.md; plan 5.14 and 7.10): tickets with a number the customer can track (SR-2026-000123, a
series of its own with no gap: TicketSeries), the legal clocks (clocks.py) stored on each ticket, the conversation
(messages in, out and internal notes, their attachments in the private storage) and the saved replies. The requester's
email address and mobile number are kept encrypted (integrations.crypto) beside a keyed hash for lookups; answers show
them masked and a reveal is logged. The ticket's history (django-simple-history) keeps no contact detail."""

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import salted_hmac
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from integrations import crypto

from . import clocks


def new_thread_token():
    """The secret part of a ticket's thread id (Ticket.thread_id): a reply that names it has seen our email."""
    return secrets.token_hex(8)


def contact_hash(kind, value):
    """A keyed hash of an email address (lower case) or an E.164 mobile number: equal ones compare, none reads back."""
    return salted_hmac(f"support.requester.{kind}", value, algorithm="sha256").hexdigest() if value else ""


class TicketSeries(models.Model):
    """The last number given in a year (India's): its row is locked while a ticket takes the next one, so the series
    has no gap and no number twice (services.next_number)."""

    year = models.PositiveSmallIntegerField(primary_key=True)
    last = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"SR-{self.year}"


class Ticket(TimeStampedModel):
    """A customer's request or complaint, from any source, with its number, its clocks and its people."""

    class Source(models.TextChoices):
        FORM = "form", "the website (the contact form, My requests)"
        EMAIL = "email", "email"
        PHONE = "phone", "phone"
        WHATSAPP = "whatsapp", "WhatsApp"
        NCH = "nch", "the National Consumer Helpline"

    class Category(models.TextChoices):
        ORDER = "order", "order"
        PAYMENT = "payment", "payment or refund"
        BOOK_CODE = "book_code", "book code"
        QR_SOLUTIONS = "qr_solutions", "QR solutions"
        CONTENT_ERROR = "content_error", "a mistake in the content"
        SCHOOL_ORDER = "school_order", "school order"
        PRIVACY_REQUEST = "privacy_request", "privacy request"
        GRIEVANCE = "grievance", "grievance"

    class Priority(models.TextChoices):
        LOW = "low", "low"
        MEDIUM = "medium", "medium"
        HIGH = "high", "high"
        URGENT = "urgent", "urgent"

    class Status(models.TextChoices):
        NEW = "new", "new"
        OPEN = "open", "open"
        WAITING_CUSTOMER = "waiting_customer", "waiting on the customer"
        WAITING_THIRD_PARTY = "waiting_third_party", "waiting on a third party"
        RESOLVED = "resolved", "resolved"
        CLOSED = "closed", "closed"
        SPAM = "spam", "spam (quarantined)"

    class Language(models.TextChoices):
        AS = "as", "Assamese"
        BN = "bn", "Bengali"
        EN = "en", "English"

    RUNNING = [Status.NEW, Status.OPEN, Status.WAITING_CUSTOMER, Status.WAITING_THIRD_PARTY]  # its clocks run
    DONE = [Status.RESOLVED, Status.CLOSED]

    number = models.CharField(max_length=20, unique=True, editable=False)
    thread_token = models.CharField(max_length=16, default=new_thread_token, editable=False)
    source = models.CharField(max_length=10, choices=Source.choices)
    nch_docket = models.CharField("NCH docket number", max_length=40, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, blank=True, help_text="Empty: not sorted.")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    subject = models.CharField(max_length=200)
    user = models.ForeignKey(  # the requester's account; SET_NULL: a ticket outlives an account (its number stays)
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets"
    )
    requester_name = models.CharField(max_length=120, blank=True)
    requester_email = models.TextField(blank=True, editable=False, help_text="Encrypted (integrations.crypto).")
    requester_email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    requester_phone = models.TextField(blank=True, editable=False, help_text="Encrypted: an E.164 mobile number.")
    requester_phone_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    order = models.ForeignKey(
        "shop.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets"
    )
    data_request = models.ForeignKey(
        "staff.DataRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    record_type = models.CharField(max_length=60, blank=True, help_text="Another record it is about: app_label.model")
    record_id = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True, help_text="The first reply a person sent.")
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # the legal clocks (clocks.py), from received_at: the earliest acknowledgement and resolution, each rule's own,
    # and the one the queue sorts by (the acknowledgement's until it is given, then the resolution's)
    ack_due_at = models.DateTimeField("acknowledge by")
    due_at = models.DateTimeField("resolve by")
    next_due_at = models.DateTimeField(db_index=True)
    redress_due_at = models.DateTimeField("redress by (E-Commerce Rules)", null=True, blank=True)
    nch_due_at = models.DateTimeField("respond by (NCH)", null=True, blank=True)
    dpdp_due_at = models.DateTimeField("answer by (SPDI or DPDP Rules)", null=True, blank=True)
    it_due_at = models.DateTimeField("resolve by (IT Rules)", null=True, blank=True)
    ack_breached = models.BooleanField(default=False)
    due_breached = models.BooleanField(default=False)
    ack_warn_at = models.DateTimeField(editable=False)  # 75 % of each clock's time (clocks.warn_at): the inbox is told
    due_warn_at = models.DateTimeField(editable=False)
    ack_warned = models.BooleanField(default=False, editable=False)  # ... once per clock
    due_warned = models.BooleanField(default=False, editable=False)
    ack_held = models.BooleanField(default=False, help_text="An SMS acknowledgement waiting for 08:00.")
    spam_at = models.DateTimeField(null=True, blank=True, help_text="Quarantined since: purged 30 days later.")
    reopened_count = models.PositiveSmallIntegerField(default=0)
    complaint_copy_sent_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True, max_length=5000, help_text="What was done: asked for when closing.")
    history = HistoricalRecords(
        excluded_fields=[
            *["requester_name", "requester_email", "requester_email_hash", "requester_phone"],
            *["requester_phone_hash", "thread_token", "subject", "resolution"],
        ]
    )

    class Meta:
        ordering = ["next_due_at", "pk"]
        permissions = [("note_ticket", "Can write internal notes on tickets")]  # CONTENT_EDITOR's, on errata

    def __str__(self):
        return self.number

    # The requester's contact details: encrypted, hashed for lookups, masked when shown

    @property
    def email(self):
        return crypto.decrypt(self.requester_email) if self.requester_email else ""

    @property
    def phone(self):
        return crypto.decrypt(self.requester_phone) if self.requester_phone else ""

    def set_email(self, value):
        value = (value or "").strip().lower()
        self.requester_email = crypto.encrypt(value) if value else ""
        self.requester_email_hash = contact_hash("email", value)

    def set_phone(self, value):
        """`value`: an E.164 mobile number (accounts.forms.normalise_phone), or empty."""
        value = (value or "").strip()
        self.requester_phone = crypto.encrypt(value) if value else ""
        self.requester_phone_hash = contact_hash("phone", value)

    # The clocks

    @property
    def is_running(self):
        return self.status in self.RUNNING

    @property
    def is_test(self):
        """About an order made with Razorpay's test keys: shown under the TEST band, kept out of every number."""
        return bool(self.order_id and self.order.is_test)

    @property
    def thread_id(self):
        """The Message-ID every email of the ticket names in References: a reply that carries it threads here."""
        return f"<{self.number.lower()}.{self.thread_token}@{mail_domain()}>"

    def clocks(self):
        from staff.config import site_setting

        return clocks.clocks(
            self.received_at,
            category=self.category,
            source=self.source,
            dpdp_from=settings.STAFF_DPDP_RULES_FROM,
            intermediary=bool(site_setting("SUPPORT_INTERMEDIARY_RULES")),
        )

    def refresh_clocks(self):
        """Every due time from `received_at` and the rules that apply now (its category and source). A clock whose due
        time moved may warn again at its new 75 %; a breach once found stays found (it is in the audit log). Saved by
        the caller."""
        before = (self.ack_due_at, self.due_at)
        found = self.clocks()
        named = {clock.name: clock.due for clock in found}
        self.ack_due_at = clocks.earliest(found, clocks.ACK)
        self.due_at = clocks.earliest(found, clocks.RESOLVE)
        self.redress_due_at, self.nch_due_at = named.get("redress"), named.get("nch")
        self.dpdp_due_at, self.it_due_at = named.get("dpdp"), named.get("it_resolve")
        self.ack_warn_at = clocks.warn_at(self.received_at, self.ack_due_at)
        self.due_warn_at = clocks.warn_at(self.received_at, self.due_at)
        self.ack_warned = self.ack_warned and self.ack_due_at == before[0]
        self.due_warned = self.due_warned and self.due_at == before[1]

    def save(self, *args, **kwargs):
        self.next_due_at = self.due_at if self.acknowledged_at else self.ack_due_at
        if kwargs.get("update_fields"):
            kwargs["update_fields"] = {*kwargs["update_fields"], "next_due_at"}
        super().save(*args, **kwargs)


def mail_domain():
    """The domain of the site's own email address (DEFAULT_FROM_EMAIL): the right side of our Message-IDs."""
    from email.utils import parseaddr

    address = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    return (address.rpartition("@")[2] or "examleaf.invalid").lower()


class TicketMessage(models.Model):
    """One message of a ticket: from the customer (in), to the customer (out: an email we sent, or a call or
    WhatsApp message recorded), or an internal note staff keep (never shown to the customer). The site's own messages
    (the acknowledgement, an action's line on the ticket) are `automatic` and never count as the first response."""

    class Direction(models.TextChoices):
        IN = "in", "from the customer"
        OUT = "out", "to the customer"
        NOTE = "note", "internal note"

    class Channel(models.TextChoices):
        WEB = "web", "the website"
        EMAIL = "email", "email"
        PHONE = "phone", "phone"
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"
        NCH = "nch", "the National Consumer Helpline's portal"
        PANEL = "panel", "the panel (a note)"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=4, choices=Direction.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    automatic = models.BooleanField(default=False, help_text="Written by the site, not a person.")
    body = models.TextField(max_length=20000)
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    message_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)  # noqa: DJ001
    headers = models.JSONField(default=dict, blank=True, help_text="Threading: in_reply_to, references, the Date.")
    mentions = models.JSONField(default=list, blank=True, help_text="The staff a note names (ids).")
    inbound_event = models.ForeignKey(
        "integrations.InboundEvent", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        default_permissions = ()  # read and written through the ticket
        ordering = ["sent_at", "pk"]

    def __str__(self):
        return f"Ticket message #{self.pk}"


def attachment_path(attachment, filename):
    """support/<uuid>.<ext>: no name a person typed (filenames carry none, the original name is kept on the row)."""
    return f"support/{uuid.uuid4().hex}{ATTACHMENT_TYPES.get(attachment.content_type, '')}"


ATTACHMENT_TYPES = {  # what is kept of a message's attachments, with the extension it is stored under
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


class TicketAttachment(models.Model):
    """A file that came with a message (a photo of a damaged parcel, a bank statement): in the private storage,
    downloaded through the staff API by a link signed for 5 minutes."""

    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        default_permissions = ()
        ordering = ["pk"]

    def __str__(self):
        return f"Attachment #{self.pk}"


class SavedReply(TimeStampedModel):
    """A reply staff insert in one keystroke, in Assamese, Bengali or English, with variables that the ticket fills
    ({name|there}, {order}, {refund_days}, {number}: services.render_reply). Deleting one puts it in the bin for 30
    days (restorable), then the nightly task purges it."""

    title = models.CharField(max_length=100)
    language = models.CharField(max_length=2, choices=Ticket.Language.choices, default=Ticket.Language.EN)
    body = models.TextField(max_length=5000)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="In the bin since.")

    class Meta:
        ordering = ["language", "title", "pk"]
        verbose_name_plural = "saved replies"
        constraints = [
            models.UniqueConstraint(
                fields=["language", "title"], condition=models.Q(deleted_at=None), name="one_saved_reply_per_title"
            )
        ]

    def __str__(self):
        return f"Saved reply #{self.pk}"
