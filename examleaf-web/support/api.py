"""Support's staff API, under /api/v1/staff/support/ (API.md "Support (staff)"), on the staff API's rules
(staff.api.StaffView): the panel's session with a second factor (or an API key, for what a key may read), each
action's catalogued permission, a re-authentication for the high ones, the admin host only, every refusal an
`authz_fail` event, cursor pages, no-store. The tickets reach each person through `scoped()`: a SALES member's are the
order, payment and school-order tickets, a content editor's the content errors (accounts.roles.ROLE_SCOPES). Every
change is an audit event; opening a ticket, revealing its requester's details and downloading a file are
`sensitive_read` events, and looking a person up by email or phone the access log's `customer.lookup` (audit.lookup).
The rules themselves are support.services'."""

import re
from datetime import datetime, time, timedelta
from statistics import median

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage, default_storage
from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse, HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import exceptions, generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from accounts.forms import normalise_phone
from api.schema import AutoSchema
from shop.models import Order, live_mode
from staff import audit
from staff import serializers as staff_serializers
from staff.api import IDEMPOTENCY, Cursor, StaffView, accepted
from staff.backends import scoped

from . import serializers as s
from . import services
from .models import SavedReply, Ticket, TicketAttachment, TicketMessage, contact_hash
from .sidebar import SidebarSerializer, sidebar

User = get_user_model()
VIEW, HANDLE = services.VIEW, services.HANDLE
SPAM = Ticket.Status.SPAM
TICKET_NUMBER = re.compile(r"SR-\d{4}-\d{6,}", re.IGNORECASE)
SOURCE_CHANNEL = {
    Ticket.Source.PHONE: TicketMessage.Channel.PHONE,
    Ticket.Source.WHATSAPP: TicketMessage.Channel.WHATSAPP,
    Ticket.Source.NCH: TicketMessage.Channel.NCH,
    Ticket.Source.EMAIL: TicketMessage.Channel.EMAIL,
}


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["support (staff)"]


class SupportView(StaffView):
    schema = StaffSchema()


class DueFirst(Cursor):
    """The queue: the next legal clock first (Ticket.next_due_at), then the ticket's id."""

    ordering = ("next_due_at", "pk")


class TicketFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=Ticket.Status.choices, help_text="one or more; spam only so")
    open = django_filters.BooleanFilter(method="filter_open", help_text="true: new, open or waiting (its clocks run)")
    waiting = django_filters.BooleanFilter(method="filter_waiting", help_text="true: waiting on the customer or others")
    mine = django_filters.BooleanFilter(method="filter_mine", help_text="true: given to me")
    unassigned = django_filters.BooleanFilter(method="filter_unassigned", help_text="true: given to nobody")
    overdue = django_filters.BooleanFilter(method="filter_overdue", help_text="true: a running clock past its time")
    q = django_filters.CharFilter(
        method="search", help_text="a ticket's number, an order's, an email address or a mobile number (logged)"
    )
    test = django_filters.BooleanFilter(
        method="filter_test", help_text="true: the tickets about a test order only (left out otherwise on a live site)"
    )

    class Meta:
        model = Ticket
        fields = ["category", "priority", "source", "language", "assignee"]

    def filter_open(self, queryset, name, value):
        return queryset.filter(status__in=Ticket.RUNNING) if value else queryset.filter(status__in=Ticket.DONE)

    def filter_waiting(self, queryset, name, value):
        waiting = [Ticket.Status.WAITING_CUSTOMER, Ticket.Status.WAITING_THIRD_PARTY]
        return queryset.filter(status__in=waiting) if value else queryset.exclude(status__in=waiting)

    def filter_mine(self, queryset, name, value):
        return queryset.filter(assignee=self.request.user) if value else queryset

    def filter_unassigned(self, queryset, name, value):
        return queryset.filter(assignee=None) if value else queryset.exclude(assignee=None)

    def filter_overdue(self, queryset, name, value):
        late = Q(status__in=Ticket.RUNNING, next_due_at__lt=timezone.now())
        return queryset.filter(late) if value else queryset.exclude(late)

    def search(self, queryset, name, value):
        value = value.strip()
        if TICKET_NUMBER.fullmatch(value):
            return queryset.filter(number__iexact=value)
        if services.ORDER_NUMBER.fullmatch(value):
            return queryset.filter(order__number__iexact=value)
        if "@" in value:
            kind, value, found = "email", value.lower(), Q(requester_email_hash=contact_hash("email", value.lower()))
        elif phone := normalise_phone(value):
            kind, value, found = "phone", phone, Q(requester_phone_hash=contact_hash("phone", phone))
        else:
            return queryset.none()
        queryset = queryset.filter(found)  # a person looked up: the access log's event, the query's keyed hash only
        audit.lookup(self.request, value, queryset.count(), kind=kind, source="tickets")
        return queryset

    def filter_test(self, queryset, name, value):
        return queryset.filter(order__livemode=False) if value else queryset.exclude(order__livemode=False)

    def filter_queryset(self, queryset):
        """Spam only when asked for by its status; on a live site, a test order's tickets only when asked for."""
        queryset = super().filter_queryset(queryset)
        if live_mode() and self.form.cleaned_data.get("test") is None:
            queryset = queryset.exclude(order__livemode=False)
        return queryset if SPAM in (self.form.cleaned_data.get("status") or []) else queryset.exclude(status=SPAM)


def message_permission(view, request):
    """POST messages/: a note needs support.note_ticket (a content editor's, on content errors), a reply
    staff.handle_ticket."""
    data = request.data if isinstance(getattr(request, "data", None), dict) else {}
    return "support.note_ticket" if data.get("direction") == TicketMessage.Direction.NOTE else HANDLE


def cancel_permission(view, request):
    return "shop.change_order"


class TicketRecordSerializer(s.TicketDetailSerializer):
    """A ticket as its page draws it: TicketDetailSerializer, the sidebar (by the reader's permissions) and the saved
    replies filled for it."""

    sidebar = serializers.SerializerMethodField()
    saved_replies = serializers.SerializerMethodField()

    class Meta(s.TicketDetailSerializer.Meta):
        fields = [*s.TicketDetailSerializer.Meta.fields, "sidebar", "saved_replies"]
        read_only_fields = fields

    @extend_schema_field(SidebarSerializer)
    def get_sidebar(self, ticket):
        return sidebar(ticket, self.context["request"].user)

    @extend_schema_field(s.SavedReplyTextSerializer(many=True))
    def get_saved_replies(self, ticket):
        return services.rendered_replies(ticket, self.context["request"].user)


def answered(change_request, created, view):
    """As POST change-requests/ answers: 201 run at once, 202 waiting for a second person, 400 failed; 200 for a key
    sent again."""
    response = accepted(change_request, view)
    if created and response.status_code == status.HTTP_200_OK:
        response.status_code = status.HTTP_201_CREATED
    return response


CHANGE_REQUEST_ANSWERS = {
    200: staff_serializers.ChangeRequestSerializer,
    201: staff_serializers.ChangeRequestSerializer,
    202: staff_serializers.ChangeRequestSerializer,
    400: staff_serializers.ChangeRequestSerializer,
}


class TicketViewSet(
    SupportView, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """The queue (the next legal clock first) and each ticket: its conversation, its sidebar, its actions."""

    serializer_class = s.TicketSerializer
    filterset_class = TicketFilter
    pagination_class = DueFirst
    lookup_field = "number"
    lookup_value_regex = r"[A-Za-z0-9-]+"
    http_method_names = ["get", "post", "patch", "head", "options"]
    permissions = {
        **dict.fromkeys(["list", "retrieve", "attachment"], VIEW),
        **dict.fromkeys(["create", "partial_update", "assign", "claim", "status", "reopen", "acknowledge"], HANDLE),
        **dict.fromkeys(["resend_invoice", "resend_confirmation"], HANDLE),
        "messages": message_permission,
        "reveal": "staff.reveal_contact",
        "refund": "staff.refund_order",
        "cancel": cancel_permission,
        "extend_access": "learn.change_entitlement",
        "book_code": "learn.view_bookcode",
        "data_request": "staff.handle_data_request",
    }
    throttle_scopes = {
        "list": "staff_search",
        "reveal": "staff_reveal",
        "refund": "staff_money",
        "cancel": "staff_money",
        "book_code": "staff_code_lookup",  # the course's lookup's budget: book codes looked up, per member of staff
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Ticket.objects.none()
        tickets = scoped(Ticket.objects.select_related("order", "user"), self.request.user, VIEW)
        if self.action == "list":
            return tickets.annotate(message_count=Count("messages"), last_message_at=Max("messages__sent_at"))
        if self.action == "retrieve":
            messages = TicketMessage.objects.select_related("author").prefetch_related("attachments")
            return tickets.prefetch_related(Prefetch("messages", queryset=messages))
        return tickets

    def get_object(self):
        """By its number (SR-2026-000123) or, from the inbox and the audit log, its id."""
        value = self.kwargs[self.lookup_field]
        queryset = self.get_queryset()
        ticket = (queryset.filter(pk=int(value)) if value.isdigit() else queryset.filter(number__iexact=value)).first()
        if ticket is None:
            raise exceptions.NotFound("No such ticket (or not one you may see).")
        self.check_object_permissions(self.request, ticket)
        return ticket

    def record_of(self, ticket):
        ticket = Ticket.objects.select_related("order", "user").get(pk=ticket.pk)
        return s.TicketDetailSerializer(ticket, context=self.get_serializer_context()).data

    @extend_schema(responses=TicketRecordSerializer)
    def retrieve(self, request, *args, **kwargs):
        """Opening a ticket is a `sensitive_read` (its customer's record: their account's when there is one, a
        child's marked so); the mentions waiting for the reader there are done."""
        ticket = self.get_object()
        account = ticket.user
        what = {"what": "ticket", "ticket": ticket.number, "child": bool(account and account.is_minor)}
        audit.record("sensitive_read", request=request, target=account or services.target(ticket), details=what)
        if getattr(request.user, "pk", None):
            services.seen_mentions(ticket, request.user)
        return Response(TicketRecordSerializer(ticket, context=self.get_serializer_context()).data)

    @extend_schema(request=s.TicketCreateSerializer, responses={201: s.TicketDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Log a ticket that came another way: a call, WhatsApp, an NCH complaint with its docket, a letter or email."""
        by = self.human()
        data = s.TicketCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        order = None
        if values["order"]:
            order = scoped(Order.objects.all(), by, "shop.view_order").filter(number=values["order"].upper()).first()
            if order is None:
                raise services.refuse("No such order (or not one you may see).", "order")
        ticket = services.create_ticket(
            source=values["source"],
            channel=SOURCE_CHANNEL[values["source"]],
            subject=values["subject"],
            body=values["message"],
            received_at=values.get("received_at"),
            user=services.account_for(values["email"]),
            name=values["name"],
            email=values["email"],
            phone=values["phone"],
            category=values["category"],
            priority=values["priority"],
            nch_docket=values["nch_docket"],
            order=order,
            by=by,
            request=request,
        )
        return Response(self.record_of(ticket), status=status.HTTP_201_CREATED)

    @extend_schema(request=s.TicketChangeSerializer, responses=s.TicketDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        """Sort or correct it: category, priority, language, subject, source and NCH docket, the order or paper it is
        about, the requester's name, email address, mobile number."""
        ticket = self.get_object()
        data = s.TicketChangeSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        ticket = services.change(ticket, data.validated_data, by=self.human(), request=request)
        return Response(self.record_of(ticket))

    @extend_schema(request=s.MessageCreateSerializer, responses={201: s.MessageSerializer})
    @action(detail=True, methods=["post"])
    def messages(self, request, *args, **kwargs):
        """A reply (emailed, or a call or WhatsApp message recorded) or an internal note, with @mentions."""
        ticket = self.get_object()
        data = s.MessageCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        message = services.add_message(ticket, by=self.human(), request=request, **data.validated_data)
        return Response(s.MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.TicketAssignSerializer, responses=s.TicketSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, *args, **kwargs):
        ticket = self.get_object()
        data = s.TicketAssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        pk = data.validated_data["assignee"]
        person = User.objects.filter(pk=pk).first() if pk is not None else None
        if pk is not None and person is None:
            raise services.refuse("Not someone who handles tickets like this one.", "assignee")
        ticket = services.assign(ticket, person, by=self.human(), request=request)
        return Response(s.TicketSerializer(ticket).data)

    @extend_schema(request=None, responses=s.TicketSerializer)
    @action(detail=True, methods=["post"])
    def claim(self, request, *args, **kwargs):
        """Give it to yourself."""
        ticket = services.assign(self.get_object(), self.human(), by=self.human(), request=request)
        return Response(s.TicketSerializer(ticket).data)

    @extend_schema(request=s.StatusSerializer, responses=s.TicketSerializer)
    @action(detail=True, methods=["post"])
    def status(self, request, *args, **kwargs):
        """Move it on (its `transitions`); resolving or closing asks for its `closing_fields`."""
        ticket = self.get_object()
        data = s.StatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        ticket = services.set_status(
            ticket,
            values["status"],
            by=self.human(),
            request=request,
            resolution=values["resolution"],
            order=values["order"],
            record=values["record"],
        )
        return Response(s.TicketSerializer(ticket).data)

    @extend_schema(request=None, responses=s.TicketSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, *args, **kwargs):
        """A resolved or closed ticket back to open (counted); its clocks never stopped."""
        ticket = services.reopen(self.get_object(), by=self.human(), request=request)
        return Response(s.TicketSerializer(ticket).data)

    @extend_schema(request=s.AcknowledgeSerializer, responses=s.TicketSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, *args, **kwargs):
        """The acknowledgement again (an address added, a copy of the complaint owed), or `note`: it was given
        another way (on the call)."""
        ticket = self.get_object()
        data = s.AcknowledgeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        by = self.human()
        if data.validated_data["note"]:
            ticket = services.record_acknowledgement(ticket, by=by, note=data.validated_data["note"], request=request)
        elif services.acknowledge(ticket.pk, by=by, request=request, again=True) is None:
            ticket.refresh_from_db()
            if ticket.ack_held:
                raise services.refuse("It goes by SMS at 08:00: messages are not sent at night.")
            raise services.refuse(
                "Nothing could be sent: no email address, and no mobile number SMS can reach. Add one, or record how "
                "it was acknowledged."
            )
        ticket.refresh_from_db()
        return Response(s.TicketSerializer(ticket).data)

    @extend_schema(
        request=s.TicketRevealSerializer,
        responses=inline_serializer(
            "TicketRevealed", {name: serializers.CharField(allow_null=True) for name in ["email", "phone"]}
        ),
    )
    @action(detail=True, methods=["post"])
    def reveal(self, request, *args, **kwargs):
        """The requester's email address or mobile number, with a reason (a `sensitive_read`, re-authenticated, 30 an
        hour)."""
        ticket = self.get_object()
        data = s.TicketRevealSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shown = sorted(data.validated_data["show"])
        account = ticket.user
        details = {
            "what": "reveal",
            "fields": shown,
            "ticket": ticket.number,
            "child": bool(account and account.is_minor),
        }
        audit.record(
            "sensitive_read",
            request=request,
            target=services.target(ticket),
            reason=data.validated_data["reason"],
            details=details,
        )
        values = {"email": services.contact_email(ticket), "phone": services.contact_phone(ticket)}
        return Response({name: values[name] or None for name in shown})

    @extend_schema(
        parameters=[OpenApiParameter("attachment", int, OpenApiParameter.PATH)],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 302: None},
    )
    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<attachment>[0-9]+)", filter_backends=[])
    def attachment(self, request, attachment=None, *args, **kwargs):
        """A file of the conversation: the private storage's link signed for 5 minutes (or the file itself)."""
        ticket = self.get_object()
        found = TicketAttachment.objects.filter(pk=attachment, message__ticket=ticket).first()
        if found is None:
            raise exceptions.NotFound("No such file on this ticket.")
        details = {"what": "attachment", "ticket": ticket.number, "attachment": found.pk}
        audit.record("sensitive_read", request=request, target=services.target(ticket), details=details)
        if not isinstance(default_storage, FileSystemStorage):
            return HttpResponseRedirect(default_storage.url(found.file.name))
        response = FileResponse(found.file.open("rb"), as_attachment=True, filename=found.name)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    # Actions on the requester's orders, course and codes (each its own permission, logged on the ticket, audited)

    @extend_schema(request=s.RefundSerializer, responses=CHANGE_REQUEST_ANSWERS, parameters=[IDEMPOTENCY])
    @action(detail=True, methods=["post"])
    def refund(self, request, *args, **kwargs):
        """Through the shop's refund (order.refund): within your limit it runs (201), above it waits for FINANCE
        (202). Not shipped: cancelled and refunded in full. Shipped: by `amount`, or by `lines` (copies from 0)."""
        ticket = self.get_object()
        data = s.RefundSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        change_request, created = services.refund(
            ticket,
            by=self.human(),
            reason=values["reason"],
            order=values["order"],
            amount=values.get("amount"),
            lines=values["lines"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        return answered(change_request, created, self)

    @extend_schema(
        request=s.TicketCancelSerializer,
        responses={
            **CHANGE_REQUEST_ANSWERS,
            200: inline_serializer(
                "TicketOrderCancelled", {"order": serializers.CharField(), "status": serializers.CharField()}
            ),
        },
        parameters=[IDEMPOTENCY],
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        """Cancel one of the requester's orders: paid online, through its refund (a change request, as refund/);
        otherwise at once."""
        ticket = self.get_object()
        data = s.TicketCancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = services.cancel(
            ticket,
            by=self.human(),
            reason=data.validated_data["reason"],
            order=data.validated_data["order"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        if isinstance(done, Order):
            return Response({"order": done.number, "status": done.status})
        return answered(*done, self)

    @extend_schema(request=s.OrderActionSerializer, responses=staff_serializers.DetailSerializer)
    @action(detail=True, methods=["post"], url_path="resend-invoice")
    def resend_invoice(self, request, *args, **kwargs):
        ticket = self.get_object()
        data = s.OrderActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = services.resend_invoice(ticket, by=self.human(), order=data.validated_data["order"], request=request)
        return Response({"detail": f"Invoice {invoice.number} sent again."})

    @extend_schema(request=s.OrderActionSerializer, responses=staff_serializers.DetailSerializer)
    @action(detail=True, methods=["post"], url_path="resend-confirmation")
    def resend_confirmation(self, request, *args, **kwargs):
        """The order's confirmation email again (for an order with the course: how to open it)."""
        ticket = self.get_object()
        data = s.OrderActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = services.resend_confirmation(
            ticket, by=self.human(), order=data.validated_data["order"], request=request
        )
        return Response({"detail": f"The confirmation of {order.number} sent again."})

    @extend_schema(
        request=s.ExtendSerializer,
        responses=inline_serializer(
            "AccessExtended", {"entitlement": serializers.IntegerField(), "valid_until": serializers.DateField()}
        ),
    )
    @action(detail=True, methods=["post"], url_path="extend-access")
    def extend_access(self, request, *args, **kwargs):
        ticket = self.get_object()
        data = s.ExtendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        found = services.extend_access(ticket, by=self.human(), request=request, **data.validated_data)
        return Response({"entitlement": found.pk, "valid_until": found.valid_until})

    @extend_schema(request=s.BookCodeLookupSerializer, responses=s.CodeAnswerSerializer)
    @action(detail=True, methods=["post"], url_path="book-code")
    def book_code(self, request, *args, **kwargs):
        """A book code looked up by its digest: one line (its batch, its subject, redeemed or not, by this requester
        or someone else). The code is never kept."""
        ticket = self.get_object()
        data = s.BookCodeLookupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            services.look_up_code(ticket, by=self.human(), code=data.validated_data["code"], request=request)
        )

    @extend_schema(request=s.DataRequestStartSerializer, responses={201: staff_serializers.DataRequestSerializer})
    @action(detail=True, methods=["post"], url_path="data-request")
    def data_request(self, request, *args, **kwargs):
        """A data request from a grievance or privacy ticket: the rights queue's own clocks, from when the ticket
        came."""
        ticket = self.get_object()
        data = s.DataRequestStartSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        made = services.start_data_request(ticket, by=self.human(), request=request, **data.validated_data)
        return Response(staff_serializers.DataRequestSerializer(made).data, status=status.HTTP_201_CREATED)


class SavedReplyFilter(django_filters.FilterSet):
    bin = django_filters.BooleanFilter(method="filter_bin", help_text="true: the deleted ones (30 days)")

    class Meta:
        model = SavedReply
        fields = ["language"]

    def filter_bin(self, queryset, name, value):
        return queryset.exclude(deleted_at=None) if value else queryset.filter(deleted_at=None)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return queryset if "bin" in self.data else queryset.filter(deleted_at=None)


class SavedReplyViewSet(SupportView, viewsets.ModelViewSet):
    """Saved replies (support.view_savedreply to read; changes: ADMIN's): a delete puts one in the bin for 30 days,
    restore/ takes it out."""

    serializer_class = s.SavedReplySerializer
    filterset_class = SavedReplyFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "support.view_savedreply"),
        "create": "support.add_savedreply",
        **dict.fromkeys(["update", "partial_update"], "support.change_savedreply"),
        **dict.fromkeys(["destroy", "restore"], "support.delete_savedreply"),
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedReply.objects.none()
        return SavedReply.objects.order_by("-pk")

    def filter_queryset(self, queryset):
        """The list's filters (the bin apart); one reply, in the bin or not, by its id."""
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    def event(self, verb, reply, changes=None):
        details = {"title": reply.title, "language": reply.language}
        audit.record(
            f"support.saved_reply_{verb}", request=self.request, target=reply, changes=changes, details=details
        )

    def perform_create(self, serializer):
        reply = serializer.save(created_by=self.human())
        self.event("created", reply)

    def perform_update(self, serializer):
        before = {name: getattr(serializer.instance, name) for name in ("title", "language")}
        reply = serializer.save()
        changes = {
            name: [before[name], getattr(reply, name)] for name in before if before[name] != getattr(reply, name)
        }
        if "body" in serializer.validated_data:
            changes["text"] = ["…", "…"]  # its words changed: masked in the log
        self.event("changed", reply, changes)

    def perform_destroy(self, instance):
        if instance.deleted_at is None:
            instance.deleted_at = timezone.now()
            instance.save(update_fields=["deleted_at", "modified"])
            self.event("deleted", instance)

    @extend_schema(request=None, responses=s.SavedReplySerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, *args, **kwargs):
        reply = self.get_object()
        if reply.deleted_at is None:
            raise services.refuse("It is not in the bin.")
        if SavedReply.objects.filter(title=reply.title, language=reply.language, deleted_at=None).exists():
            raise services.refuse("A saved reply of this title exists in this language: rename one first.")
        reply.deleted_at = None
        reply.save(update_fields=["deleted_at", "modified"])
        self.event("restored", reply)
        return Response(self.get_serializer(reply).data)


SUMMARY = inline_serializer(
    "SupportSummary",
    {
        "since": serializers.DateField(),
        "until": serializers.DateField(),
        "received": serializers.IntegerField(),
        "by_category": serializers.DictField(child=serializers.IntegerField(), help_text='"" : not sorted yet'),
        "by_source": serializers.DictField(child=serializers.IntegerField()),
        "first_response_hours": serializers.FloatField(allow_null=True, help_text="the median"),
        "resolution_hours": serializers.FloatField(allow_null=True, help_text="the median"),
        "backlog": serializers.DictField(child=serializers.IntegerField(), help_text="open tickets by status, now"),
        "overdue": serializers.IntegerField(help_text="open tickets past a clock, now"),
        "breaches": serializers.DictField(child=serializers.IntegerField(), help_text="ack and due, of the period"),
    },
)


def hours(start, end):
    return round((end - start).total_seconds() / 3600, 1)


def count_by(rows, name):
    """{value: tickets} of one field."""
    return dict(rows.order_by().values_list(name).annotate(total=Count("pk")))


class SummaryView(SupportView, generics.GenericAPIView):
    """The module's numbers (research lms 4.9), from what each ticket stores: the period's volume by category and
    source, the median first response and resolution, the breaches; the backlog and what is overdue now. Spam and
    tickets about a test order are left out of every number."""

    permissions = {"GET": VIEW}
    pagination_class = None
    filter_backends = []

    @extend_schema(parameters=[OpenApiParameter("days", int, description="the period: 1 to 366 days to today (30)")],
                   responses=SUMMARY)  # fmt: skip
    def get(self, request, *args, **kwargs):
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 366)
        except ValueError:
            raise services.refuse("A number of days from 1 to 366.", "days") from None
        tickets = scoped(Ticket.objects.exclude(status=SPAM), request.user, VIEW)
        if live_mode():
            tickets = tickets.exclude(order__livemode=False)
        until = timezone.localdate()
        since = until - timedelta(days=days - 1)
        start = timezone.make_aware(datetime.combine(since, time.min))
        period = tickets.filter(received_at__gte=start)
        times = list(period.values_list("received_at", "first_response_at", "resolved_at"))
        responses = [hours(received, first) for received, first, _ in times if first]
        resolutions = [hours(received, resolved) for received, _, resolved in times if resolved]
        running = tickets.filter(status__in=Ticket.RUNNING)
        return Response(
            {
                "since": since,
                "until": until,
                "received": len(times),
                "by_category": count_by(period, "category"),
                "by_source": count_by(period, "source"),
                "first_response_hours": median(responses) if responses else None,
                "resolution_hours": median(resolutions) if resolutions else None,
                "backlog": count_by(running, "status"),
                "overdue": running.filter(next_due_at__lt=timezone.now()).count(),
                "breaches": {
                    "ack": period.filter(ack_breached=True).count(),
                    "due": period.filter(due_breached=True).count(),
                },
            }
        )


class AgentsView(SupportView, generics.GenericAPIView):
    """Who a ticket may be given to or a note may name: the active staff who read tickets (`handles`: who may be
    given them)."""

    permissions = {"GET": VIEW}
    pagination_class = None  # a few people, in one answer
    filter_backends = []

    @extend_schema(responses=s.AgentSerializer(many=True))
    def get(self, request, *args, **kwargs):
        staff = User.objects.filter(is_active=True, is_staff=True)
        people = staff.filter(holders(VIEW)).distinct().order_by("full_name", "pk")
        handling = set(staff.filter(holders(HANDLE)).values_list("pk", flat=True))
        rows = [
            {"id": person.pk, "name": person.full_name or f"Staff #{person.pk}", "handles": person.pk in handling}
            for person in people
        ]
        return Response(rows)


def holders(perm):
    """Who holds "app_label.codename": through a role (a group), on their own, or as a superuser."""
    app_label, codename = perm.split(".")
    return (
        Q(groups__permissions__content_type__app_label=app_label, groups__permissions__codename=codename)
        | Q(user_permissions__content_type__app_label=app_label, user_permissions__codename=codename)
        | Q(is_superuser=True)
    )


router = SimpleRouter()
router.register("tickets", TicketViewSet, basename="support-ticket")
router.register("saved-replies", SavedReplyViewSet, basename="support-saved-reply")
urlpatterns = [  # under /api/v1/staff/support/ (staff/urls.py)
    path("summary/", SummaryView.as_view(), name="support-summary"),
    path("agents/", AgentsView.as_view(), name="support-agents"),
    *router.urls,
]
