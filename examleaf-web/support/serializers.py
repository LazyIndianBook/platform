"""What the support API takes and gives (API.md "Support (staff)" and "My requests"). Explicit fields only. The
requester's contact details leave masked (staff.privacy's masks); a reveal is its own endpoint, logged."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from accounts.forms import normalise_phone
from staff.models import DataRequest
from staff.privacy import mask_email, mask_phone

from . import services
from .models import SavedReply, Ticket, TicketAttachment, TicketMessage

Status, Source, Category = Ticket.Status, Ticket.Source, Ticket.Category
# Choice sets of their own (their enums named in settings.py's ENUM_NAME_OVERRIDES)
LOGGED_SOURCES = [(value, Source(value).label) for value in ("phone", "whatsapp", "nch", "email")]  # staff log these
REPLY_CHANNELS = [(value, TicketMessage.Channel(value).label) for value in ("email", "phone", "whatsapp", "nch")]
REVEAL_FIELDS = [("email", "email address"), ("phone", "mobile number")]


def phone_field(value):
    if not value:
        return ""
    found = normalise_phone(value)
    if not found:
        raise serializers.ValidationError("An Indian mobile number, such as 98640 12345.")
    return found


class RequesterSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.CharField(help_text="masked; reveal/ shows it, logged")
    phone = serializers.CharField(help_text="masked")
    user = serializers.IntegerField(allow_null=True, help_text="the requester's account")


def requester(ticket):
    return {
        "name": ticket.requester_name,
        "email": mask_email(ticket.email),
        "phone": mask_phone(ticket.phone),
        "user": ticket.user_id,
    }


class TicketSerializer(serializers.ModelSerializer):
    """A ticket in the queue."""

    requester = serializers.SerializerMethodField()
    category = serializers.ChoiceField(Category.choices, allow_blank=True, read_only=True, help_text="empty: unsorted")
    order = serializers.SlugRelatedField(slug_field="number", read_only=True)
    overdue = serializers.SerializerMethodField(help_text="a running clock past its due time")
    clock = serializers.SerializerMethodField(help_text="the running clock next_due_at is: ack or due; null: stopped")
    is_test = serializers.SerializerMethodField(help_text="about a test order: shown under the TEST band only")
    message_count = serializers.IntegerField(read_only=True, default=0)
    last_message_at = serializers.DateTimeField(read_only=True, default=None, allow_null=True)

    class Meta:
        model = Ticket
        fields = [
            *["id", "number", "subject", "source", "nch_docket", "category", "priority", "status", "language"],
            *["requester", "assignee", "order", "received_at", "acknowledged_at", "first_response_at"],
            *["resolved_at", "closed_at", "ack_due_at", "due_at", "next_due_at", "ack_breached", "due_breached"],
            *["overdue", "clock", "is_test", "reopened_count", "message_count", "last_message_at"],
        ]
        read_only_fields = fields

    def get_requester(self, ticket) -> RequesterSerializer:
        return requester(ticket)

    def get_overdue(self, ticket) -> bool:
        return ticket.is_running and ticket.next_due_at < timezone.now()

    def get_clock(self, ticket) -> str | None:
        if not ticket.is_running:
            return None
        return "due" if ticket.acknowledged_at else "ack"

    def get_is_test(self, ticket) -> bool:
        return ticket.is_test


class ClockSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="ack, redress, nch, dpdp, it_ack, it_resolve")
    kind = serializers.CharField(help_text="ack (stops at the acknowledgement) or resolve (at the resolution)")
    due = serializers.DateTimeField()
    rule = serializers.CharField()
    stopped_at = serializers.DateTimeField(allow_null=True)
    breached = serializers.BooleanField()


def clock_rows(ticket):
    rows = []
    for clock in ticket.clocks():
        stopped = ticket.acknowledged_at if clock.kind == "ack" else ticket.resolved_at
        moment = stopped or timezone.now()
        rows.append(
            {
                "name": clock.name,
                "kind": clock.kind,
                "due": clock.due,
                "rule": clock.rule,
                "stopped_at": stopped,
                "breached": moment > clock.due and (stopped is not None or ticket.is_running),
            }
        )
    return rows


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketAttachment
        fields = ["id", "name", "content_type", "size"]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField(help_text="a member of staff's name; empty for the customer")
    attachments = AttachmentSerializer(many=True, read_only=True)
    other_sender = serializers.SerializerMethodField(help_text="an email from another address than the requester's")
    dropped = serializers.SerializerMethodField(help_text="attachments not kept, and why")
    mentions = serializers.ListField(child=serializers.IntegerField(), read_only=True, help_text="staff named (ids)")

    class Meta:
        model = TicketMessage
        fields = [
            *["id", "direction", "channel", "author", "author_name", "automatic", "body", "sent_at", "mentions"],
            *["attachments", "other_sender", "dropped"],
        ]
        read_only_fields = fields

    def get_author_name(self, message) -> str:
        author = message.author
        if author is None or not author.is_staff:
            return ""
        return author.full_name or f"Staff #{author.pk}"

    def get_other_sender(self, message) -> bool:
        return bool(message.headers.get("other_sender"))

    def get_dropped(self, message) -> list[str]:
        return list(message.headers.get("dropped") or [])


class SavedReplyTextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    language = serializers.CharField()
    text = serializers.CharField(help_text="filled for this ticket: its variables replaced")


class TicketDetailSerializer(TicketSerializer):
    """A ticket with its requester (masked), its clocks, what closing it asks for, its moves, its messages; the
    sidebar and the saved replies are the view's (by the reader's permissions)."""

    data_request = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    record = serializers.SerializerMethodField(help_text="the paper a content error is in (its code)")
    clocks = serializers.SerializerMethodField()
    closing_fields = serializers.SerializerMethodField(help_text="what resolving or closing asks for")
    transitions = serializers.SerializerMethodField(help_text="the statuses it may move to now")
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(TicketSerializer.Meta):
        fields = [
            *TicketSerializer.Meta.fields,
            *["data_request", "record", "resolution", "complaint_copy_sent_at", "ack_held"],
            *["redress_due_at", "nch_due_at", "dpdp_due_at", "it_due_at", "clocks", "closing_fields", "transitions"],
            "messages",
        ]
        read_only_fields = fields

    def get_record(self, ticket) -> str | None:
        if ticket.record_type != "content.paper" or not ticket.record_id:
            return None
        from content.models import Paper

        return Paper.objects.filter(pk=ticket.record_id).values_list("code", flat=True).first()

    def get_clocks(self, ticket) -> ClockSerializer(many=True):
        return clock_rows(ticket)

    def get_closing_fields(self, ticket) -> list[str]:
        return services.closing_fields(ticket)

    def get_transitions(self, ticket) -> list[str]:
        return [str(status) for status in services.allowed(ticket)]


class TicketCreateSerializer(serializers.Serializer):
    """A ticket staff log: a call, a WhatsApp message, an NCH complaint with its docket, a letter or an email."""

    source = serializers.ChoiceField(choices=LOGGED_SOURCES)
    nch_docket = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(choices=Category.choices, required=False, allow_blank=True, default="")
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, required=False, default=Ticket.Priority.MEDIUM)
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=20000, help_text="the complaint as recorded: what they said or wrote")
    received_at = serializers.DateTimeField(required=False, help_text="when it came (default now); never ahead")
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")

    def validate_phone(self, value):
        return phone_field(value)

    def validate_received_at(self, value):
        now = timezone.now()
        if value > now + timedelta(minutes=1):
            raise serializers.ValidationError("Not ahead of now: when it came.")
        if value < now - timedelta(days=365):
            raise serializers.ValidationError("Within the last year.")
        return min(value, now)

    def validate(self, data):
        problems = {}
        if data["source"] == Source.NCH and not data["nch_docket"].strip():
            problems["nch_docket"] = ["A complaint from the National Consumer Helpline needs its docket number."]
        if data["source"] in (Source.PHONE, Source.WHATSAPP) and not data["phone"]:
            problems["phone"] = ["The number they called or wrote from."]
        if data["source"] == Source.EMAIL and not data["email"]:
            problems["email"] = ["The address it came from."]
        if not (data["email"] or data["phone"]):
            problems["email"] = ["An email address or a mobile number: where the acknowledgement goes."]
        if problems:
            raise serializers.ValidationError(problems)
        return data


class TicketChangeSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.choices, required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, required=False)
    language = serializers.ChoiceField(choices=Ticket.Language.choices, required=False)
    source = serializers.ChoiceField(choices=Source.choices, required=False)
    nch_docket = serializers.CharField(max_length=40, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=200, required=False)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, help_text="its number; empty: none")
    record = serializers.CharField(max_length=20, required=False, allow_blank=True, help_text="a paper's code")

    def validate_phone(self, value):
        return phone_field(value)

    def validate_email(self, value):
        return value.strip().lower()


class MessageCreateSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=[TicketMessage.Direction.OUT, TicketMessage.Direction.NOTE])
    body = serializers.CharField(max_length=20000)
    channel = serializers.ChoiceField(
        choices=REPLY_CHANNELS,
        required=False,
        allow_blank=True,
        default="",
        help_text="a reply's: email (sent), or phone, WhatsApp or NCH's portal (recorded); default email",
    )
    mentions = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=20
    )


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Status.choices)
    resolution = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    record = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class TicketAssignSerializer(serializers.Serializer):
    assignee = serializers.IntegerField(allow_null=True, help_text="a member of staff's id; null: nobody")


class AcknowledgeSerializer(serializers.Serializer):
    note = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        default="",
        help_text="given another way: how (the acknowledgement is not sent then)",
    )


class TicketRevealSerializer(serializers.Serializer):
    show = serializers.MultipleChoiceField(choices=REVEAL_FIELDS)
    reason = serializers.CharField(min_length=5, max_length=300, help_text="why: kept in the audit log")


class RefundLineSerializer(serializers.Serializer):
    item = serializers.IntegerField(help_text="the order line's id")
    quantity = serializers.IntegerField(min_value=0, help_text="copies to refund, from 0")


class RefundSerializer(serializers.Serializer):
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=0)
    lines = RefundLineSerializer(many=True, required=False, default=list)
    reason = serializers.CharField(min_length=5, max_length=300)


class CancelSerializer(serializers.Serializer):
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    reason = serializers.CharField(min_length=5, max_length=200)


class OrderActionSerializer(serializers.Serializer):
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class ExtendSerializer(serializers.Serializer):
    entitlement = serializers.IntegerField()
    days = serializers.IntegerField(min_value=1, max_value=365)
    reason = serializers.CharField(min_length=5, max_length=200)


class BookCodeLookupSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40, help_text="as printed: 7KQM-3XPA-9TRW")


class CodeAnswerSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    batch = serializers.CharField(required=False)
    subject = serializers.CharField(required=False)
    redeemed = serializers.BooleanField(required=False)
    by_requester = serializers.BooleanField(required=False)
    line = serializers.CharField()


class DataRequestStartSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=DataRequest.Kind.choices)
    summary = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class SavedReplySerializer(serializers.ModelSerializer):
    variables = serializers.SerializerMethodField(help_text="the variables its text uses")

    class Meta:
        model = SavedReply
        fields = ["id", "title", "language", "body", "variables", "created_by", "created", "modified", "deleted_at"]
        read_only_fields = ["id", "variables", "created_by", "created", "modified", "deleted_at"]

    def get_variables(self, reply) -> list[str]:
        return sorted({match.group(1) for match in services.TOKEN.finditer(reply.body)})

    def validate_body(self, value):
        if unknown := services.unknown_variables(value):
            known = ", ".join("{" + name + "}" for name in sorted(services.VARIABLES))
            raise serializers.ValidationError(f"Unknown: {', '.join(unknown)}. The variables are {known}.")
        return value

    def validate(self, data):
        title = data.get("title", getattr(self.instance, "title", ""))
        language = data.get("language", getattr(self.instance, "language", Ticket.Language.EN))
        clash = SavedReply.objects.filter(title=title, language=language, deleted_at=None)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"title": ["A saved reply of this title exists in this language."]})
        return data


class AgentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    handles = serializers.BooleanField(help_text="may be given tickets (staff.handle_ticket)")


# My requests (the customer's)


CUSTOMER_STATUS = {
    Status.NEW: "received",
    Status.OPEN: "being looked at",
    Status.WAITING_CUSTOMER: "waiting for your reply",
    Status.WAITING_THIRD_PARTY: "waiting on a courier, bank or printer",
    Status.RESOLVED: "resolved",
    Status.CLOSED: "closed",
}


class MyTicketSerializer(serializers.ModelSerializer):
    """One of the customer's requests: its number, what it is about, where it stands and its dates; never staff's
    notes, never who works on it."""

    category = serializers.ChoiceField(Category.choices, allow_blank=True, read_only=True, help_text="empty: unsorted")
    category_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    order = serializers.SlugRelatedField(slug_field="number", read_only=True)
    answer_by = serializers.DateTimeField(source="due_at", read_only=True, help_text="the latest we answer it by")

    class Meta:
        model = Ticket
        fields = [
            *["number", "subject", "category", "category_label", "status", "status_label", "order", "received_at"],
            *["acknowledged_at", "answer_by", "resolved_at", "closed_at", "modified"],
        ]
        read_only_fields = fields

    def get_category_label(self, ticket) -> str:
        return services.category_words(ticket)

    def get_status_label(self, ticket) -> str:
        return CUSTOMER_STATUS.get(ticket.status, ticket.get_status_display())


class MyTicketCreateSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.choices)
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=5000)
    order = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
