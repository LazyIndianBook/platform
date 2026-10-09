"""The Finance module's staff API, under /api/v1/staff/finance/ (API.md "Finance (staff)", shop/README.md "Finance"),
on the staff app's rules (staff.api.StaffView): a member of staff on the panel's session with a second factor, or an
API key with a view_ permission; the permission each action names (none named: refused); its objects through
`scoped()`; cursor pages newest first; every change an audit event; test-mode rows (test keys on the live site) out
of every list and count unless `?livemode=false` asks for them. Every rule is the shop's own (shop.payments,
shop.services, shop.settlements): a refusal is its words, `400 {"non_field_errors": [...]}`, Razorpay out of reach a
503.

- finance/today/: what FINANCE has to do today, a row a duty with its count, the oldest and the amount, each row for
  whoever may see its records;
- finance/payments/: every payment with its Razorpay ids, the stuck ones found; one with its webhooks and timeline,
  asked of Razorpay again (the late-authorised case, a lost webhook);
- finance/offline-payments/: the payments received offline waiting for approval (change requests), and those recorded;
- finance/payment-links/: the orders' and the B2B invoices' Razorpay links: made, sent again, cancelled; a B2B link's
  payment asked of Razorpay again, and recorded once posted in ERPNext by hand;
- finance/refunds/: the refunds by state with their method, ARN and credit note; those waiting for approval;
- finance/settlements/: Razorpay's settlements with their lines, a line matched by hand, a day fetched as a job;
- finance/documents/{number}/erp/: an invoice's or credit note's ERPNext mirror, as the outbox and the links have it."""

from datetime import datetime, time, timedelta

import django_filters
from django.conf import settings
from django.db.models import (
    BooleanField,
    CharField,
    Count,
    ExpressionWrapper,
    Min,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Cast
from django.http import Http404
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import exceptions, generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from staff import audit, jobs
from staff.api import Cursor, StaffView
from staff.backends import scoped
from staff.models import ChangeRequest, InboxItem, Job
from staff.serializers import JobSerializer
from staff.signals import close_items

from . import payments, settlements, tax
from .models import (
    CreditNote,
    Invoice,
    InvoicePaymentLink,
    Order,
    OrderMessage,
    Payment,
    Refund,
    Settlement,
    SettlementLine,
    live_mode,
)
from .staff_orders import NUMBER, OrderTimelineEntrySerializer, Unavailable, refused, staff_name
from .staff_tax import DOCUMENT_KINDS

VIEW_PAYMENT, VIEW_REFUND, VIEW_SETTLEMENT = "shop.view_payment", "shop.view_refund", "shop.view_settlement"
RECONCILE = "staff.reconcile_settlements"
LINK_KINDS = [("order", "an order's link"), ("invoice", "a B2B invoice's link")]
LINK_STATES = [
    ("sent", "sent, waiting for the payment"),
    ("paid", "paid"),
    ("cancelled", "cancelled"),
    ("expired", "expired unpaid"),
]
LINK_DAYS = timedelta(days=payments.LINK_DAYS)
TODAY_KEYS = [  # Finance today's rows, in the order FINANCE works through them
    *["refunds_to_approve", "bank_refunds", "offline_to_approve", "stuck_payments", "b2b_to_post"],
    *["settlement_lines", "settlements_mismatched", "cod_receivable", "cod_overdue", "cod_mismatched"],
    *["credit_notes_refused", "sync_differences", "disputes"],
]


def decimal(**kwargs):
    return serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, **kwargs)


class FinanceSchema(AutoSchema):
    def get_tags(self):
        return ["finance (staff)"]


def money(source=None, **kwargs):
    return serializers.DecimalField(source=source, max_digits=12, decimal_places=2, read_only=True, **kwargs)


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def live_only(queryset, field="livemode"):
    """The site's own mode on the live site: test rows only when asked (`?livemode=false`)."""
    return queryset.filter(**{field: True}) if live_mode() else queryset


def test_keys(model, path):
    """The ids, as text, of `model`'s rows of a test order (`path`: to its live mode): change requests and inbox
    items name their target by its id."""
    return model.objects.filter(**{path: False}).annotate(key=Cast("pk", CharField())).values("key")


def waiting_requests(action_name, user):
    """The change requests of an action on orders waiting for a second person (test orders out on the live site)."""
    found = ChangeRequest.objects.filter(
        action=action_name, status=ChangeRequest.Status.PENDING, target_type="shop.order"
    )
    found = scoped(found, user, "staff.view_changerequest")
    return found.exclude(target_id__in=Subquery(test_keys(Order, "livemode"))) if live_mode() else found


def stuck_q(now=None):
    """A stuck payment: an online one created or authorised SHOP_STUCK_PAYMENT_MINUTES ago that reached Razorpay (its
    checkout opened; a link only once past its life, a link waiting for the customer being no stuck payment) on an
    order still unpaid; or one captured on an order still pending (the order's webhook missed, or its refund under
    way)."""
    now = now or timezone.now()
    old = now - timedelta(minutes=settings.SHOP_STUCK_PAYMENT_MINUTES)
    unpaid = Q(order__status=Order.Status.PENDING, order__placed_at__isnull=True)
    checkout = Q(razorpay_order_id__isnull=False, razorpay_payment_link_id__isnull=True)
    stale_link = Q(razorpay_payment_link_id__isnull=False, created__lt=now - LINK_DAYS)
    waiting = Q(status__in=[Payment.Status.CREATED, Payment.Status.AUTHORIZED], created__lt=old) & unpaid
    missed = Q(status=Payment.Status.CAPTURED, order__status=Order.Status.PENDING)
    return Q(method=Order.Method.RAZORPAY) & ((waiting & (checkout | stale_link)) | missed)


def with_stuck(queryset):
    return queryset.annotate(stuck=ExpressionWrapper(stuck_q(), output_field=BooleanField()))


def today_permission(view, request):
    """Finance today: shop.view_payment, or staff.view_cod (the brief's either)."""
    user = getattr(request, "user", None)
    return VIEW_PAYMENT if user is not None and user.has_perm(VIEW_PAYMENT) else "staff.view_cod"


# ---- Serializers (explicit fields; no one's details) ----


class FinanceSettlementRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    settlement_id = serializers.CharField()
    date = serializers.DateField()
    utr = serializers.CharField()
    state = serializers.ChoiceField(choices=Settlement.State.choices)


def settled(line):
    """A payment line's settlement, as FinanceSettlementRefSerializer has it; None when not settled yet."""
    if line is None:
        return None
    settlement = line.settlement
    return {
        "id": settlement.pk,
        "settlement_id": settlement.settlement_id,
        "date": settlement.date,
        "utr": settlement.utr,
        "state": settlement.state,
    }


def payment_line(payment):
    """Its settlement line (type payment), prefetched as `payment_lines` by the lists."""
    lines = getattr(payment, "payment_lines", None)
    if lines is None:
        lines = list(payment.settlement_lines.filter(type=SettlementLine.Type.PAYMENT).select_related("settlement"))
    return lines[0] if lines else None


class FinancePaymentSerializer(serializers.ModelSerializer):
    """A payment in the list (no query a row: the view prefetches)."""

    order = serializers.CharField(source="order.number", read_only=True)
    order_status = serializers.ChoiceField(source="order.status", choices=Order.Status.choices, read_only=True)
    amount = money("amount.amount")
    is_test = serializers.SerializerMethodField(help_text="made with test keys on the live site: TEST")
    stuck = serializers.BooleanField(read_only=True, help_text="waiting on Razorpay too long: ask it again")
    is_link = serializers.SerializerMethodField(help_text="a staff order's payment link")
    fee = serializers.SerializerMethodField(help_text="Razorpay's fee without its GST, once settled")
    tax = serializers.SerializerMethodField(help_text="the GST on the fee, once settled")
    settlement = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            *["id", "order", "order_status", "method", "status", "amount", "razorpay_order_id", "razorpay_payment_id"],
            *["razorpay_payment_link_id", "reference", "error", "livemode", "is_test", "stuck", "is_link", "fee"],
            *["tax", "settlement", "created", "modified"],
        ]
        read_only_fields = fields

    def get_is_test(self, payment) -> bool:
        return not payment.livemode and live_mode()

    def get_is_link(self, payment) -> bool:
        return payment.razorpay_payment_link_id is not None

    @extend_schema_field(decimal())
    def get_fee(self, payment):
        line = payment_line(payment)
        return f"{line.fee.amount:.2f}" if line else None

    @extend_schema_field(decimal())
    def get_tax(self, payment):
        line = payment_line(payment)
        return f"{line.tax.amount:.2f}" if line else None

    @extend_schema_field(FinanceSettlementRefSerializer(allow_null=True))
    def get_settlement(self, payment):
        return settled(payment_line(payment))


class FinancePaymentRefundSerializer(serializers.ModelSerializer):
    amount = money("amount.amount")

    class Meta:
        model = Refund
        fields = ["id", "amount", "status", "method", "speed", "razorpay_refund_id", "arn", "created", "processed_at"]
        read_only_fields = fields


class FinanceWebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField()
    name = serializers.CharField(help_text="payment.captured, payment.failed, order.paid, payment_link.paid, refund.…")
    received_at = serializers.DateTimeField()


class FinancePaymentDetailSerializer(FinancePaymentSerializer):
    """A payment as its record shows it: its order's facts, refunds, the webhooks seen (kept 7 days), what the last
    webhook said of it (no card, bank or contact field; kept 180 days), and its timeline."""

    order_id = serializers.IntegerField(read_only=True)
    order_total = money("order.total.amount")
    order_placed_at = serializers.DateTimeField(source="order.placed_at", read_only=True)
    payment_link_url = serializers.URLField(read_only=True)
    refunds = FinancePaymentRefundSerializer(many=True, read_only=True)
    webhooks = serializers.SerializerMethodField()
    last_webhook = serializers.JSONField(source="raw_payload", read_only=True, help_text="its allowed fields only")
    timeline = serializers.SerializerMethodField()

    class Meta(FinancePaymentSerializer.Meta):
        fields = [
            *FinancePaymentSerializer.Meta.fields,
            *["order_id", "order_total", "order_placed_at", "payment_link_url", "refunds", "webhooks"],
            *["last_webhook", "timeline"],
        ]
        read_only_fields = fields

    @extend_schema_field(FinanceWebhookSerializer(many=True))
    def get_webhooks(self, payment):
        events = payment.webhook_events.order_by("received_at", "pk")
        return FinanceWebhookSerializer(events, many=True).data

    @extend_schema_field(OrderTimelineEntrySerializer(many=True))
    def get_timeline(self, payment):
        return payment_timeline(payment, self.context["request"].user)


def payment_timeline(payment, user):
    """The payment's story, oldest first: its status changes (its history), the webhooks seen, its refunds, its
    settlement; for whoever reads the audit log, the audit events about it (a read of the log, itself recorded)."""
    rows = []

    def add(at, kind, label, actor="", **details):
        if at is not None:
            rows.append({"at": at, "kind": kind, "label": label, "actor": actor, "details": details})

    seen, labels = None, dict(Payment.Status.choices)
    for row in payment.history.select_related("history_user").order_by("history_date", "history_id"):
        if row.status != seen:
            actor = staff_name(row.history_user) if row.history_user and row.history_user.is_staff else ""
            add(row.history_date, "payment", f"Payment {labels.get(row.status, row.status)}", actor or "the site")
            seen = row.status
    for event in payment.webhook_events.order_by("received_at", "pk"):
        add(event.received_at, "webhook", f"Razorpay's webhook {event.name}", "Razorpay", event=event.event_id)
    for refund in payment.refunds.all():
        add(refund.created, "refund", f"Refund #{refund.pk} of ₹{refund.amount.amount} asked", "", refund=refund.pk)
        if refund.processed_at:
            add(refund.processed_at, "refund", f"Refund #{refund.pk} made", "", refund=refund.pk)
    if line := payment_line(payment):
        settlement = line.settlement
        label = f"Settled in {settlement.settlement_id} (UTR {settlement.utr or 'not given'})"
        add(day_start(settlement.date), "settlement", label, "Razorpay", settlement=settlement.pk)
    if user.has_perm("staff.view_auditlog"):
        from staff.models import AuditEvent

        events = list(AuditEvent.objects.filter(target_type="shop.payment", target_id=str(payment.pk)).order_by("id"))
        from django.contrib.auth import get_user_model

        people = {person.pk: person for person in get_user_model().objects.filter(pk__in={e.actor_id for e in events})}
        for event in events:
            add(event.ts, "audit", event.action, staff_name(people.get(event.actor_id)) or event.actor_type)
        audit.record("audit.read", target=payment, details={"what": "payment timeline"})
    rows.sort(key=lambda row: row["at"])
    return OrderTimelineEntrySerializer(rows, many=True).data


class FinanceReconciledSerializer(serializers.Serializer):
    paid = serializers.BooleanField(allow_null=True, help_text="Razorpay had a captured payment for the order")
    detail = serializers.CharField(help_text="what Razorpay's answer changed, in words")
    changes = serializers.DictField(help_text="{what: [before, after]}: the order's status, each payment's, refunds")
    payment = FinancePaymentDetailSerializer()


class FinanceRequestRowSerializer(serializers.Serializer):
    """A row of the offline payments' or the refunds' lists: a change request waiting for a second person (`request`),
    or the payment or refund itself."""

    kind = serializers.ChoiceField(choices=["request", "payment", "refund"])
    id = serializers.IntegerField(help_text="the change request's, the payment's or the refund's")
    order = serializers.CharField()
    amount = decimal()
    status = serializers.CharField(help_text="the change request's status, or the payment's or the refund's")
    reference = serializers.CharField(allow_blank=True, help_text="an offline payment's UTR or UPI reference")
    method = serializers.CharField(allow_blank=True, help_text="a refund's: source, bank or none")
    speed = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    arn = serializers.CharField(allow_blank=True, help_text="the bank's reference of a refund, from Razorpay")
    utr = serializers.CharField(allow_blank=True, help_text="a bank refund's transfer")
    razorpay_refund_id = serializers.CharField(allow_blank=True)
    credit_note = serializers.CharField(allow_null=True)
    payee_masked = serializers.CharField(allow_blank=True)
    payment_method = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True)
    change_request = serializers.IntegerField(allow_null=True, help_text="its approval (the console's /approvals/)")
    change_request_status = serializers.CharField(allow_blank=True)
    checker = serializers.CharField(allow_blank=True, help_text="the permission its approver needs")
    rule = serializers.CharField(allow_blank=True)
    by = serializers.CharField(allow_blank=True, help_text="who asked for it or recorded it")
    created = serializers.DateTimeField()
    done_at = serializers.DateTimeField(allow_null=True, help_text="a refund made, a payment recorded")
    livemode = serializers.BooleanField()


def request_row(change_request, people):
    from staff.approvals import ACTIONS

    payload = change_request.payload or {}
    return {
        "kind": "request",
        "id": change_request.pk,
        "order": change_request.target_label,
        "amount": change_request.amount,
        "status": change_request.status,
        "reference": str(payload.get("reference") or ""),
        "method": str(payload.get("method") or ""),
        "speed": str(payload.get("speed") or ""),
        "reason": change_request.reason,
        "arn": "",
        "utr": "",
        "razorpay_refund_id": "",
        "credit_note": None,
        "payee_masked": str(payload.get("payee_masked") or ""),
        "payment_method": "",
        "error": "",
        "change_request": change_request.pk,
        "change_request_status": change_request.status,
        "checker": ACTIONS[change_request.action].checker_for(change_request),
        "rule": change_request.rule,
        "by": staff_name(people.get(change_request.maker_id)),
        "created": change_request.created,
        "done_at": None,
        "livemode": True,
    }


class FinanceLinkSerializer(serializers.Serializer):
    """A Razorpay Payment Link: a staff order's (its Payment) or a B2B invoice's (InvoicePaymentLink)."""

    kind = serializers.ChoiceField(choices=LINK_KINDS)
    id = serializers.IntegerField(help_text="the order link's payment, or the B2B link's own id")
    order = serializers.CharField(allow_null=True)
    invoice = serializers.CharField(allow_null=True, help_text="the ERPNext invoice's name")
    amount = decimal()
    state = serializers.ChoiceField(choices=LINK_STATES)
    url = serializers.CharField(allow_blank=True)
    razorpay_link_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField(allow_null=True)
    sent_at = serializers.DateTimeField(help_text="when it was made")
    last_sent_at = serializers.DateTimeField(allow_null=True, help_text="an order's: its last email to the customer")
    expires_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    created_by = serializers.CharField(allow_blank=True)
    posted_at = serializers.DateTimeField(allow_null=True, help_text="a B2B link's: its entry posted in ERPNext")
    erp_name = serializers.CharField(allow_blank=True, help_text="the Payment Entry FINANCE posted by hand")
    livemode = serializers.BooleanField()
    is_test = serializers.BooleanField()


def order_links():
    """The staff orders' links (their Payments), each with when it was last emailed (the order's messages)."""
    sent = OrderMessage.objects.filter(order=OuterRef("order"), kind="payment_link").order_by("-created")
    links = Payment.objects.exclude(razorpay_payment_link_id=None).select_related("order__created_by")
    return links.annotate(last_sent=Subquery(sent.values("created")[:1]))


def order_link_state(payment, now):
    if payment.status in (Payment.Status.CAPTURED, Payment.Status.REFUNDED):
        return "paid"
    if payment.status == Payment.Status.FAILED:
        return "cancelled"
    return "expired" if payment.created + LINK_DAYS <= now else "sent"


def order_link_row(payment, now):
    order = payment.order
    paid = order_link_state(payment, now) == "paid"
    return {
        "kind": "order",
        "id": payment.pk,
        "order": order.number,
        "invoice": None,
        "amount": payment.amount.amount,
        "state": order_link_state(payment, now),
        "url": payment.payment_link_url,
        "razorpay_link_id": payment.razorpay_payment_link_id,
        "razorpay_payment_id": payment.razorpay_payment_id,
        "sent_at": payment.created,
        "last_sent_at": getattr(payment, "last_sent", None),
        "expires_at": payment.created + LINK_DAYS,
        "paid_at": order.placed_at if paid else None,
        "created_by": staff_name(order.created_by),
        "posted_at": None,
        "erp_name": "",
        "livemode": payment.livemode,
        "is_test": not payment.livemode and live_mode(),
    }


def invoice_link_row(link, now):
    state = link.status
    if state == InvoicePaymentLink.Status.SENT and link.expires_at <= now:
        state = "expired"
    return {
        "kind": "invoice",
        "id": link.pk,
        "order": None,
        "invoice": link.invoice,
        "amount": link.amount.amount,
        "state": state,
        "url": link.url,
        "razorpay_link_id": link.razorpay_payment_link_id,
        "razorpay_payment_id": link.razorpay_payment_id,
        "sent_at": link.created,
        "last_sent_at": None,
        "expires_at": link.expires_at,
        "paid_at": link.paid_at,
        "created_by": staff_name(link.created_by),
        "posted_at": link.posted_at,
        "erp_name": link.erp_name,
        "livemode": link.livemode,
        "is_test": not link.livemode and live_mode(),
    }


def answered(row, detail, code=status.HTTP_200_OK):
    """A link's answer after an action: its row and what was done, in words."""
    return Response(FinanceLinkAnswerSerializer({**row, "detail": detail}).data, status=code)


class FinanceLinkAskSerializer(serializers.Serializer):
    order = serializers.CharField(required=False, allow_blank=True, help_text="a staff order's number")
    invoice = serializers.CharField(required=False, allow_blank=True, max_length=140, help_text="an ERPNext invoice")
    action = serializers.ChoiceField(choices=["send", "cancel"], help_text="send: made once, then sent again")

    def validate(self, data):
        if bool(data.get("order", "").strip()) == bool(data.get("invoice", "").strip()):
            raise serializers.ValidationError({"non_field_errors": ["Name one: an order, or a B2B invoice."]})
        return data


class FinanceLinkAnswerSerializer(FinanceLinkSerializer):
    detail = serializers.CharField()


class FinanceLinkPostedSerializer(serializers.Serializer):
    erp_name = serializers.CharField(max_length=140, help_text="the Payment Entry's name in ERPNext")


class FinanceSettlementSerializer(serializers.ModelSerializer):
    gross = money("gross.amount")
    fees = money("fees.amount", help_text="Razorpay's fees without their GST")
    tax = money("tax.amount", help_text="the GST on the fees")
    adjustments = money("adjustments.amount")
    net = money("net.amount", help_text="what reached the bank")
    is_test = serializers.SerializerMethodField()

    class Meta:
        model = Settlement
        fields = [
            *["id", "settlement_id", "date", "utr", "gross", "fees", "tax", "adjustments", "net", "state", "problem"],
            *["livemode", "is_test", "matched_at", "posted_at", "created", "modified"],
        ]
        read_only_fields = fields

    def get_is_test(self, settlement) -> bool:
        return not settlement.livemode and live_mode()


class FinanceSettlementErpSerializer(serializers.Serializer):
    outbox = serializers.IntegerField(help_text="its outbox row (System → sync)")
    state = serializers.CharField(help_text="the row's: pending, sending, sent, failed, dead, discarded")
    attempts = serializers.IntegerField()
    last_error = serializers.CharField(allow_blank=True)
    sent_at = serializers.DateTimeField(allow_null=True)
    name = serializers.CharField(allow_null=True, help_text="the Journal Entry ERPNext made")


class FinanceSettlementDetailSerializer(FinanceSettlementSerializer):
    counts = serializers.SerializerMethodField(help_text="its lines: in all, not yet ours, by type")
    erp = serializers.SerializerMethodField()

    class Meta(FinanceSettlementSerializer.Meta):
        fields = [*FinanceSettlementSerializer.Meta.fields, "counts", "erp"]
        read_only_fields = fields

    @extend_schema_field(
        serializers.DictField(child=serializers.IntegerField(), help_text="lines, unmatched, payment, refund, …")
    )
    def get_counts(self, settlement):
        found = settlement.lines.aggregate(
            lines=Count("pk"),
            unmatched=Count("pk", filter=Q(matched_at=None)),
            payment=Count("pk", filter=Q(type=SettlementLine.Type.PAYMENT)),
            refund=Count("pk", filter=Q(type=SettlementLine.Type.REFUND)),
            adjustment=Count("pk", filter=Q(type=SettlementLine.Type.ADJUSTMENT)),
        )
        return found

    @extend_schema_field(FinanceSettlementErpSerializer(allow_null=True))
    def get_erp(self, settlement):
        from erp.models import ErpLink

        row = settlement.erp_outbox
        if row is None:
            return None
        link = ErpLink.objects.filter(examleaf_ref=row.examleaf_ref).first()
        return {
            "outbox": row.pk,
            "state": row.state,
            "attempts": row.attempts,
            "last_error": row.last_error,
            "sent_at": row.sent_at,
            "name": link.name if link else None,
        }


class FinanceLineRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.CharField(allow_null=True)
    amount = decimal()


class FinanceSettlementLineSerializer(serializers.ModelSerializer):
    amount = money("amount.amount")
    fee = money("fee.amount", help_text="Razorpay's, without its GST")
    tax = money("tax.amount")
    credit = money("credit.amount")
    debit = money("debit.amount")
    order = serializers.CharField(source="order.number", read_only=True, allow_null=True)
    payment = serializers.SerializerMethodField()
    refund = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField(help_text="a B2B invoice's link it paid")
    matched = serializers.SerializerMethodField()
    matched_by = serializers.SerializerMethodField(help_text="empty: matched by Razorpay's id")

    class Meta:
        model = SettlementLine
        fields = [
            *["id", "type", "entity_id", "amount", "fee", "tax", "credit", "debit", "settled_at", "order_receipt"],
            *["order", "payment", "refund", "link", "matched", "matched_at", "matched_by", "note"],
        ]
        read_only_fields = fields

    @extend_schema_field(FinanceLineRefSerializer(allow_null=True))
    def get_payment(self, line):
        payment = line.payment
        return None if payment is None else {"id": payment.pk, "order": line.order and line.order.number,
                                             "amount": f"{payment.amount.amount:.2f}"}  # fmt: skip

    @extend_schema_field(FinanceLineRefSerializer(allow_null=True))
    def get_refund(self, line):
        refund = line.refund
        return None if refund is None else {"id": refund.pk, "order": line.order and line.order.number,
                                            "amount": f"{refund.amount.amount:.2f}"}  # fmt: skip

    @extend_schema_field(
        serializers.DictField(allow_null=True, help_text="{id, invoice, amount} of the B2B link it paid")
    )
    def get_link(self, line):
        link = line.link
        return None if link is None else {"id": link.pk, "invoice": link.invoice, "amount": f"{link.amount.amount:.2f}"}

    def get_matched(self, line) -> bool:
        return line.matched_at is not None

    def get_matched_by(self, line) -> str:
        return staff_name(line.matched_by)


class FinanceMatchSerializer(serializers.Serializer):
    line = serializers.IntegerField(help_text="the line's id")
    payment = serializers.IntegerField(required=False, allow_null=True, help_text="a payment's id")
    refund = serializers.IntegerField(required=False, allow_null=True, help_text="a refund's id")
    accept = serializers.BooleanField(default=False, help_text="an adjustment accepted as it is (no target)")
    note = serializers.CharField(max_length=300, help_text="why: kept in the audit log")


class FinanceFetchSerializer(serializers.Serializer):
    day = serializers.DateField(help_text="a day of Razorpay's settlements (India), today at the latest")
    dry_run = serializers.BooleanField(default=False, help_text="fetch and match, keep nothing")


class FinanceTodayRowSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=TODAY_KEYS)
    count = serializers.IntegerField(allow_null=True, help_text="null: not configured")
    oldest = serializers.DateField(allow_null=True, help_text="the day of the oldest (India)")
    amount = decimal()
    configured = serializers.BooleanField()


class FinanceTodaySerializer(serializers.Serializer):
    livemode = serializers.BooleanField(help_text="the site runs on live keys: test rows are left out")
    as_of = serializers.DateTimeField()
    rows = FinanceTodayRowSerializer(many=True)


class FinanceDocumentErpSerializer(serializers.Serializer):
    number = serializers.CharField()
    kind = serializers.ChoiceField(choices=DOCUMENT_KINDS)
    state = serializers.ChoiceField(
        choices=["mirrored", "waiting", "failed", "dead", "discarded", "not_sent", "off", "test"],
        help_text="mirrored (ERPNext has it), waiting, failed (tried again), dead (staff replay or discard it), "
        "discarded, not_sent (no outbox row: the reconciliation reports it), off (its flow is off), test",
    )
    doctype = serializers.CharField(allow_null=True)
    name = serializers.CharField(allow_null=True, help_text="ERPNext's name of it")
    synced_at = serializers.DateTimeField(allow_null=True)
    outbox = serializers.ListField(child=serializers.DictField(), help_text="its outbox rows, oldest first")


# ---- Filters ----


class FinancePaymentFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Payment.Status.choices)
    method = django_filters.ChoiceFilter(choices=Order.Method.choices)
    created_from = django_filters.DateFilter(method="filter_from", help_text="a day (India time), from it on")
    created_to = django_filters.DateFilter(method="filter_to", help_text="a day (India time), up to its end")
    stuck = django_filters.BooleanFilter(help_text="true: the stuck ones (SHOP_STUCK_PAYMENT_MINUTES)")
    livemode = django_filters.BooleanFilter(help_text="default: the site's own mode (test ones only when asked)")
    q = django_filters.CharFilter(
        method="search", help_text="an order's number, a Razorpay payment, order or link id, an offline reference"
    )

    class Meta:
        model = Payment
        fields = []

    def filter_from(self, queryset, name, value):
        return queryset.filter(created__gte=day_start(value))

    def filter_to(self, queryset, name, value):
        return queryset.filter(created__lt=day_start(value + timedelta(days=1)))

    def search(self, queryset, name, value):
        return queryset.filter(search_payments(value))

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return live_only(queryset) if self.form.cleaned_data.get("livemode") is None else queryset


def search_payments(value, prefix=""):
    """A search of payments (a Q, `prefix` the path to the payment): an order's number, Razorpay's payment (pay_),
    order (order_) or link (plink_) id, else an offline reference exactly. Never a person: no lookup to record."""
    value = " ".join(str(value or "").split())[:60]
    if not value:
        return Q()
    if NUMBER.fullmatch(value):
        return Q(**{f"{prefix}order__number__iexact": value})
    for start, field in (("pay_", "razorpay_payment_id"), ("order_", "razorpay_order_id")):
        if value.startswith(start):
            return Q(**{f"{prefix}{field}": value})
    if value.startswith("plink_"):
        return Q(**{f"{prefix}razorpay_payment_link_id": value})
    return Q(**{f"{prefix}reference__iexact": value})


class FinanceRowFilter(django_filters.FilterSet):
    """The offline payments' and the refunds' lists: `state` picks the change requests waiting (`waiting`) or the
    rows themselves; `livemode` is the view's (the rows' order's mode)."""

    q = django_filters.CharFilter(method="search", help_text="an order's number")

    class Meta:
        fields = []

    def search(self, queryset, name, value):
        value = " ".join(str(value or "").split())[:40]
        if queryset.model is ChangeRequest:
            return queryset.filter(target_label__iexact=value)
        return queryset.filter(order__number__iexact=value)


class FinanceLinkFilter(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(choices=LINK_KINDS, method="noop", help_text="order (by default) or invoice")
    state = django_filters.ChoiceFilter(choices=LINK_STATES, method="filter_state")
    livemode = django_filters.BooleanFilter(help_text="default: the site's own mode (test ones only when asked)")
    q = django_filters.CharFilter(method="search", help_text="an order's number, or an ERPNext invoice's name")

    class Meta:
        fields = []

    def noop(self, queryset, name, value):
        return queryset

    def filter_state(self, queryset, name, value):
        now = timezone.now()
        open_ = [Payment.Status.CREATED, Payment.Status.AUTHORIZED]
        if queryset.model is Payment:
            return queryset.filter(
                {
                    "sent": Q(status__in=open_, created__gt=now - LINK_DAYS),
                    "expired": Q(status__in=open_, created__lte=now - LINK_DAYS),
                    "paid": Q(status__in=[Payment.Status.CAPTURED, Payment.Status.REFUNDED]),
                    "cancelled": Q(status=Payment.Status.FAILED),
                }[value]
            )
        Status = InvoicePaymentLink.Status
        return queryset.filter(
            {
                "sent": Q(status=Status.SENT, expires_at__gt=now),
                "expired": Q(status=Status.EXPIRED) | Q(status=Status.SENT, expires_at__lte=now),
                "paid": Q(status=Status.PAID),
                "cancelled": Q(status=Status.CANCELLED),
            }[value]
        )

    def search(self, queryset, name, value):
        value = " ".join(str(value or "").split())[:140]
        if queryset.model is Payment:
            return queryset.filter(order__number__iexact=value)
        return queryset.filter(invoice__iexact=value)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return live_only(queryset) if self.form.cleaned_data.get("livemode") is None else queryset


class FinanceSettlementFilter(django_filters.FilterSet):
    state = django_filters.ChoiceFilter(choices=Settlement.State.choices)
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    livemode = django_filters.BooleanFilter(help_text="default: the site's own mode (test ones only when asked)")
    q = django_filters.CharFilter(method="search", help_text="Razorpay's settlement id (setl_…) or its UTR")

    class Meta:
        model = Settlement
        fields = []

    def search(self, queryset, name, value):
        value = " ".join(str(value or "").split())[:60]
        return queryset.filter(Q(settlement_id=value) | Q(utr__iexact=value))

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return live_only(queryset) if self.form.cleaned_data.get("livemode") is None else queryset


class FinanceLineFilter(django_filters.FilterSet):
    matched = django_filters.BooleanFilter(field_name="matched_at", lookup_expr="isnull", exclude=True)
    type = django_filters.ChoiceFilter(choices=SettlementLine.Type.choices)

    class Meta:
        model = SettlementLine
        fields = []


# ---- Views ----


class FinanceView(StaffView):
    schema = FinanceSchema()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return scoped(self.queryset.all(), self.request.user, self.required_permission(self.request))

    def filter_queryset(self, queryset):
        """The list's filters (its default to the site's own mode among them) are the list's: a record, and every
        action on one, opens whatever its mode, so a test row found with ?livemode=false opens too."""
        return super().filter_queryset(queryset) if getattr(self, "action", None) == "list" else queryset

    def log(self, action_name, target, **kwargs):
        return audit.record(action_name, request=self.request, target=target, **kwargs)


class Dated(Cursor):
    """Settlements: newest day first."""

    ordering = ("-date", "-pk")


class InOrder(Cursor):
    """A settlement's lines: in Razorpay's order."""

    ordering = "pk"


def payment_rows(queryset):
    lines = SettlementLine.objects.filter(type=SettlementLine.Type.PAYMENT).select_related("settlement")
    return with_stuck(queryset.select_related("order")).prefetch_related(
        Prefetch("settlement_lines", queryset=lines, to_attr="payment_lines")
    )


class PaymentViewSet(FinanceView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Payments, newest first, with their Razorpay ids and, once settled, Razorpay's fee and its GST; the stuck ones
    (`?stuck=true`); one with its refunds, webhooks and timeline; asked of Razorpay again (POST …/reconcile/,
    staff.replay_webhook): a payment it captured is recorded, an authorised one captured first (the late-authorised
    case), answered with what changed."""

    queryset = Payment.objects.all()
    serializer_class = FinancePaymentSerializer
    filterset_class = FinancePaymentFilter
    permissions = {"list": VIEW_PAYMENT, "retrieve": VIEW_PAYMENT, "reconcile": "staff.replay_webhook"}
    throttle_scopes = {"list": "staff_search"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            return payment_rows(queryset)
        if self.action == "retrieve":
            return payment_rows(queryset).select_related("order__user").prefetch_related("refunds")
        return queryset.select_related("order")

    def get_serializer_class(self):
        return FinancePaymentDetailSerializer if self.action == "retrieve" else FinancePaymentSerializer

    def retrieve(self, request, *args, **kwargs):
        """The record; a child's order's payment opened is a logged read, as the child's order is."""
        payment = self.get_object()
        user = payment.order.user
        if user is not None and user.is_minor:
            audit.record("sensitive_read", request=request, target=payment, details={"what": "payment", "child": True})
        return Response(self.get_serializer(payment).data)

    @extend_schema(request=None, responses=FinanceReconciledSerializer)
    @action(detail=True, methods=["post"])
    def reconcile(self, request, *args, **kwargs):
        """Ask Razorpay what became of the payment's order (shop.payments.reconcile): a captured payment recorded, an
        authorised one captured first, a second payment refunded; 503 while Razorpay cannot be asked."""
        payment = self.get_object()
        if payment.method != Order.Method.RAZORPAY:
            raise refused(f"Payment #{payment.pk} was not made online: Razorpay knows nothing of it.")
        if payment.livemode != live_mode():
            mode = "live" if payment.livemode else "test"
            raise refused(f"Payment #{payment.pk} was made with {mode} keys: the keys in force cannot ask about it.")
        if not payments.configured():
            raise Unavailable("Online payment is not set up yet.")
        order = payment.order
        before = snapshot(order)
        paid = payments.reconcile(order)
        after = snapshot(Order.objects.get(pk=order.pk))
        changes = {key: [before.get(key), after.get(key)] for key in sorted(set(before) | set(after))}
        changes = {key: value for key, value in changes.items() if value[0] != value[1]}
        self.log("payment.reconciled", payment, details={"paid": paid, "changes": changes})
        if paid is None:
            raise Unavailable("Razorpay could not be asked: try again in a few minutes.")
        fresh = payment_rows(Payment.objects.filter(pk=payment.pk)).get()
        body = {
            "paid": paid,
            "detail": reconciled_words(paid, changes),
            "changes": changes,
            "payment": FinancePaymentDetailSerializer(fresh, context=self.get_serializer_context()).data,
        }
        return Response(body)


def snapshot(order):
    """What Razorpay's answer may change: the order's status, each payment's status, the refunds started."""
    found = {"order": order.status, "refunds": order.refunds.count()}
    for pk, payment_status in order.payments.values_list("pk", "status"):
        found[f"payment {pk}"] = payment_status
    return found


def reconciled_words(paid, changes):
    if not paid:
        return "Razorpay has no captured payment for this order: nothing changed."
    if not changes:
        return "Razorpay's answer is what the site knew already: nothing changed."
    words = []
    if "order" in changes:
        words.append(f"the order is {changes['order'][1]} now")
    if "refunds" in changes:
        words.append("a payment the order could not take is being refunded")
    paid_now = [key for key, (_, after) in changes.items() if key.startswith("payment ") and after == "captured"]
    if paid_now:
        words.append(f"{', '.join(paid_now)} recorded as captured")
    return f"Razorpay had the payment: {'; '.join(words) or 'recorded'}."


class RowList(FinanceView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """A list of change requests waiting (`?state=waiting`) or of the rows themselves, as FinanceRequestRowSerializer
    has them (a page of either)."""

    serializer_class = FinanceRequestRowSerializer
    filterset_class = FinanceRowFilter
    action_name = ""  # the approvals action whose requests wait

    def waiting(self):
        return self.request.query_params.get("state") == "waiting"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChangeRequest.objects.none()
        if self.waiting():
            return waiting_requests(self.action_name, self.request.user)
        return self.rows()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.waiting():
            return queryset  # test orders' requests are left out by waiting_requests
        asked = self.request.query_params.get("livemode", "").lower()
        if asked in ("true", "1", "false", "0"):
            return queryset.filter(order__livemode=asked in ("true", "1"))
        return live_only(queryset, "order__livemode")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        if self.waiting():
            people = staff_people({row.maker_id for row in page})
            rows = [request_row(row, people) for row in page]
        else:
            rows = self.as_rows(page)
        return self.get_paginated_response(FinanceRequestRowSerializer(rows, many=True).data)


def staff_people(ids):
    from django.contrib.auth import get_user_model

    return {person.pk: person for person in get_user_model().objects.filter(pk__in=[pk for pk in ids if pk])}


STATE = OpenApiParameter("state", str, enum=["waiting", "recorded"], description="waiting: the change requests")
LIVEMODE = OpenApiParameter("livemode", bool, description="default: the site's own mode (test ones only when asked)")


class OfflinePaymentViewSet(RowList):
    """Payments received offline (bank transfer, UPI): waiting for FINANCE's approval (`?state=waiting`: the change
    requests of order.offline_payment, approved at /change-requests/{id}/approve/) or recorded (the default)."""

    queryset = Payment.objects.all()
    permissions = {"list": VIEW_PAYMENT}
    action_name = "order.offline_payment"

    def rows(self):
        payments_ = Payment.objects.filter(method=Order.Method.OFFLINE).select_related("order")
        return scoped(payments_, self.request.user, VIEW_PAYMENT)

    @extend_schema(parameters=[STATE, LIVEMODE])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def as_rows(self, page):
        orders = {str(payment.order_id) for payment in page}
        executed = ChangeRequest.objects.filter(
            action=self.action_name, status=ChangeRequest.Status.EXECUTED, target_id__in=orders
        )
        asked = {(row.target_id, str((row.payload or {}).get("reference"))): row for row in executed}
        people = staff_people({row.maker_id for row in asked.values()})
        rows = []
        for payment in page:
            request_ = asked.get((str(payment.order_id), payment.reference))
            rows.append(
                {
                    **(request_row(request_, people) if request_ else blank_row()),
                    "kind": "payment",
                    "id": payment.pk,
                    "order": payment.order.number,
                    "amount": payment.amount.amount,
                    "status": payment.status,
                    "reference": payment.reference,
                    "created": payment.created,
                    "done_at": payment.created,
                    "livemode": payment.livemode,
                }
            )
        return rows


def blank_row():
    keys = ["reference", "method", "speed", "reason", "arn", "utr", "razorpay_refund_id", "payee_masked"]
    keys += ["payment_method", "error", "change_request_status", "checker", "rule", "by"]
    return {**dict.fromkeys(keys, ""), "credit_note": None, "change_request": None, "done_at": None}


class RefundViewSet(RowList):
    """Refunds, newest first, by state (`?state=pending|processed|failed`) and method (`?method=source|bank|none`),
    with their ARN, the bank transfer's UTR and the credit note; `?state=waiting`: the change requests of order.refund
    waiting for FINANCE (approved at /change-requests/{id}/approve/). Bank refunds are marked paid by Orders'
    POST orders/refunds/{id}/mark-paid/."""

    queryset = Refund.objects.all()
    permissions = {"list": VIEW_REFUND}
    action_name = "order.refund"

    def rows(self):
        refunds = Refund.objects.select_related("order", "payment", "credit_note", "change_request", "created_by")
        params = self.request.query_params
        if params.get("state") in Refund.Status.values:
            refunds = refunds.filter(status=params["state"])
        if params.get("method") in Refund.Method.values:
            refunds = refunds.filter(method=params["method"])
        return scoped(refunds, self.request.user, VIEW_REFUND)

    @extend_schema(
        parameters=[
            OpenApiParameter("state", str, enum=["waiting", *Refund.Status.values], description="waiting: approvals"),
            OpenApiParameter("method", str, enum=Refund.Method.values),
            LIVEMODE,
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def as_rows(self, page):
        rows = []
        for refund in page:
            note = getattr(refund, "credit_note", None)
            change_request = refund.change_request
            rows.append(
                {
                    **blank_row(),
                    "kind": "refund",
                    "id": refund.pk,
                    "order": refund.order.number,
                    "amount": refund.amount.amount,
                    "status": refund.status,
                    "method": refund.method,
                    "speed": refund.speed,
                    "reason": refund.reason,
                    "arn": refund.arn,
                    "utr": refund.utr,
                    "razorpay_refund_id": refund.razorpay_refund_id or "",
                    "credit_note": note.number if note else None,
                    "payee_masked": refund.payee_masked,
                    "payment_method": refund.payment.method,
                    "error": refund.error,
                    "change_request": change_request.pk if change_request else None,
                    "change_request_status": change_request.status if change_request else "",
                    "by": staff_name(refund.created_by) or "the site",
                    "created": refund.created,
                    "done_at": refund.processed_at,
                    "livemode": refund.payment.livemode,
                }
            )
        return rows


class LinkViewSet(FinanceView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Payment links: a staff order's (`?kind=order`, the default) or a B2B invoice's (`?kind=invoice`), by state
    (sent, paid, cancelled, expired). POST makes or sends again an order's link (emailed to the customer) or a B2B
    invoice's (its address answered: staff send it), or cancels one (shop.change_order); links live LINK_DAYS."""

    queryset = Payment.objects.all()
    serializer_class = FinanceLinkSerializer
    filterset_class = FinanceLinkFilter
    permissions = {"list": VIEW_PAYMENT, "create": "shop.change_order"}

    def invoices(self):
        return self.request.query_params.get("kind") == "invoice"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        if self.invoices():
            return scoped(InvoicePaymentLink.objects.select_related("created_by"), self.request.user, VIEW_PAYMENT)
        return scoped(order_links(), self.request.user, VIEW_PAYMENT)

    @extend_schema(parameters=[OpenApiParameter("kind", str, enum=["order", "invoice"])])
    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        now = timezone.now()
        make = invoice_link_row if self.invoices() else order_link_row
        return self.get_paginated_response(FinanceLinkSerializer([make(row, now) for row in page], many=True).data)

    @extend_schema(
        request=FinanceLinkAskSerializer, responses={200: FinanceLinkAnswerSerializer, 201: FinanceLinkAnswerSerializer}
    )
    def create(self, request, *args, **kwargs):
        """An order's link (a staff order still waiting for its online payment): `send` makes it once and emails it,
        later the same link again; `cancel` cancels it (the next one is new). A B2B invoice's (its read-only copy
        in the platform, something outstanding): `send` makes it (201) or answers the open one (200); `cancel`
        cancels the open one. 503 while Razorpay cannot be reached."""
        user = self.human()
        asked = FinanceLinkAskSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        try:
            if data.get("invoice", "").strip():
                return self.invoice_link(data["invoice"].strip(), data["action"], user)
            return self.order_link(data["order"].strip(), data["action"], user)
        except payments.Unavailable as error:
            raise Unavailable(str(error)) from error
        except ValueError as error:
            raise refused(error) from error

    def order_link(self, number, action_name, user):
        order = scoped(Order.objects.filter(number__iexact=number), user, "shop.change_order").first()
        if order is None:
            raise exceptions.NotFound("No such order (or not one you may see).")
        if order.created_by_id is None:
            raise ValueError(f"Order {order.number} was placed on the website: its payment page is its link.")
        if order.status != Order.Status.PENDING or order.placed_at or order.is_cod:
            raise ValueError(f"Order {order.number} is not waiting for an online payment.")
        if action_name == "cancel":
            payment = payments.cancel_payment_link(order)
            self.log("order.payment_link_cancelled", order, details={"payment": payment.pk})
            detail = "The payment link is cancelled."
        else:
            payment = payments.send_payment_link(order)
            self.log("order.payment_link_sent", order, details={"payment": payment.pk})
            detail = "Emailed to the customer."
        fresh = order_links().get(pk=payment.pk)  # the one just acted on: whoever acted may read its answer
        return answered(order_link_row(fresh, timezone.now()), detail)

    def invoice_link(self, name, action_name, user):
        if action_name == "cancel":
            link = InvoicePaymentLink.objects.filter(invoice=name, status=InvoicePaymentLink.Status.SENT).first()
            if link is None:
                raise ValueError(f"No open link for invoice {name}.")
            link = payments.cancel_invoice_link(link, by=user, request=self.request)
            return answered(invoice_link_row(link, timezone.now()), "The payment link is cancelled.")
        link, made = payments.send_invoice_link(name, by=user, request=self.request)
        detail = "Made: send its address to the customer." if made else "This invoice's link is open already."
        row = invoice_link_row(link, timezone.now())
        return answered(row, detail, status.HTTP_201_CREATED if made else status.HTTP_200_OK)


class InvoiceLinkViewSet(FinanceView, viewsets.GenericViewSet):
    """A B2B invoice's link: asked of Razorpay again (its webhook lost: staff.replay_webhook), and its payment recorded
    as posted in ERPNext by hand, with the Payment Entry's name (staff.reconcile_settlements; its inbox item done)."""

    queryset = InvoicePaymentLink.objects.select_related("created_by")
    serializer_class = FinanceLinkSerializer
    permissions = {"reconcile": "staff.replay_webhook", "posted": RECONCILE}
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InvoicePaymentLink.objects.none()
        return scoped(self.queryset.all(), self.request.user, VIEW_PAYMENT)

    @extend_schema(request=None, responses=FinanceLinkAnswerSerializer)
    @action(detail=True, methods=["post"])
    def reconcile(self, request, *args, **kwargs):
        link = self.get_object()
        paid = payments.reconcile_invoice_link(link)
        self.log("payment.link_reconciled", link, details={"invoice": link.invoice, "paid": paid})
        if paid is None:
            raise Unavailable("Razorpay could not be asked: try again in a few minutes.")
        link.refresh_from_db()
        detail = "Paid: post its entry in ERPNext." if paid else "Razorpay has no payment for this link yet."
        return answered(invoice_link_row(link, timezone.now()), detail)

    @extend_schema(request=FinanceLinkPostedSerializer, responses=FinanceLinkAnswerSerializer)
    @action(detail=True, methods=["post"])
    def posted(self, request, *args, **kwargs):
        asked = FinanceLinkPostedSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        erp_name = " ".join(asked.validated_data["erp_name"].split())
        from django.db import transaction

        with transaction.atomic():
            link = InvoicePaymentLink.objects.select_for_update().get(pk=self.get_object().pk)
            if link.status != InvoicePaymentLink.Status.PAID:
                raise refused(f"The link for {link.invoice} is not paid: nothing to post.")
            if link.posted_at:
                raise refused(f"Posted already, as {link.erp_name}.")
            link.posted_at, link.posted_by, link.erp_name = timezone.now(), self.human(), erp_name
            link.save(update_fields=["posted_at", "posted_by", "erp_name", "modified"])
            close_items(link, InboxItem.Kind.B2B_PAYMENT)
            self.log("payment.link_posted", link, details={"invoice": link.invoice, "erp_name": erp_name})
        return answered(invoice_link_row(link, timezone.now()), "Recorded as posted.")


class SettlementViewSet(FinanceView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Razorpay's settlements, newest day first (`?state=&date_from=&date_to=&q=`), one with its counts and its ERPNext
    entry; a line matched by hand (POST …/match/: a payment, a refund, or an adjustment accepted, with a note:
    staff.reconcile_settlements); a day fetched as a job (POST settlements/fetch/)."""

    queryset = Settlement.objects.select_related("erp_outbox")
    serializer_class = FinanceSettlementSerializer
    filterset_class = FinanceSettlementFilter
    pagination_class = Dated
    permissions = {
        "list": VIEW_SETTLEMENT,
        "retrieve": VIEW_SETTLEMENT,
        "match": RECONCILE,
        "fetch": RECONCILE,
    }
    throttle_scopes = {"fetch": "staff_export"}

    def get_serializer_class(self):
        return FinanceSettlementDetailSerializer if self.action == "retrieve" else FinanceSettlementSerializer

    @extend_schema(request=FinanceMatchSerializer, responses=FinanceSettlementLineSerializer)
    @action(detail=True, methods=["post"])
    def match(self, request, *args, **kwargs):
        asked = FinanceMatchSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        settlement, user = self.get_object(), self.human()
        payment = refund = None
        if data.get("payment"):
            found = scoped(Payment.objects.select_related("order"), user, VIEW_PAYMENT).filter(pk=data["payment"])
            if (payment := found.first()) is None:
                raise serializers.ValidationError({"payment": ["No such payment (or not one you may see)."]})
        if data.get("refund"):
            found = scoped(Refund.objects.select_related("order", "payment"), user, VIEW_REFUND)
            if (refund := found.filter(pk=data["refund"]).first()) is None:
                raise serializers.ValidationError({"refund": ["No such refund (or not one you may see)."]})
        try:
            line = settlements.manual_match(
                settlement,
                data["line"],
                payment=payment,
                refund=refund,
                accept=data["accept"],
                note=data["note"],
                by=user,
                request=request,
            )
        except SettlementLine.DoesNotExist as error:
            raise serializers.ValidationError({"line": ["No such line in this settlement."]}) from error
        except ValueError as error:
            raise refused(error) from error
        return Response(FinanceSettlementLineSerializer(line).data)

    @extend_schema(request=FinanceFetchSerializer, responses={202: JobSerializer})
    @action(detail=False, methods=["post"])
    def fetch(self, request, *args, **kwargs):
        """A day of Razorpay's settlements fetched, matched and posted, as a background job (settlement_fetch): 202
        with the job (jobs/{id}/), its result the counts. The same job is POST jobs/ {"kind": "settlement_fetch"}."""
        user = self.human()
        asked = FinanceFetchSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        try:
            params = settlements.job_params({"day": asked.validated_data["day"].isoformat()})
        except serializers.ValidationError as error:  # this body's own field
            raise serializers.ValidationError(error.detail["params"]) from None
        job = jobs.start(
            Job.Kind.SETTLEMENT_FETCH, params, user=user, dry_run=asked.validated_data["dry_run"], request=request
        )
        return Response(JobSerializer(job, context={"request": request}).data, status=status.HTTP_202_ACCEPTED)


class SettlementLineViewSet(FinanceView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """A settlement's lines in Razorpay's order (`?matched=false`: those not ours yet; `?type=`)."""

    queryset = SettlementLine.objects.all()
    serializer_class = FinanceSettlementLineSerializer
    filterset_class = FinanceLineFilter
    pagination_class = InOrder
    permissions = {"list": "shop.view_settlementline"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SettlementLine.objects.none()
        settlement = Settlement.objects.filter(pk=self.kwargs["settlement"]).first()
        if settlement is None or not self.request.user.has_perm(VIEW_SETTLEMENT):
            raise Http404
        lines = settlement.lines.select_related("payment", "refund", "link", "order", "matched_by")
        return scoped(lines, self.request.user, "shop.view_settlementline")


class TodayView(FinanceView, generics.GenericAPIView):
    """What FINANCE has to do today, each row a duty (its count, the day of the oldest, the amount): refunds to
    approve, bank refunds to transfer, offline payments to approve, stuck payments, B2B payments to post in ERPNext,
    settlement lines not ours and settlements that do not match, cash on delivery receivable, overdue and mismatched,
    credit notes the cut-off refused, the sync's differences, and disputes (not configured). Each row only for whoever
    may see its records; test mode left out."""

    serializer_class = FinanceTodaySerializer
    permissions = {"GET": today_permission}

    def get(self, request, *args, **kwargs):
        return Response(FinanceTodaySerializer(today(request.user)).data)


def today(user):
    from erp.models import ErpReconciliationDifference
    from shipping.models import CodRemittance

    live, rows = live_mode(), []

    def add(key, perm, queryset, when="created", amount="amount"):
        if not user.has_perm(perm):
            return
        sums = {"amount": Sum(amount)} if amount else {}
        found = queryset.aggregate(count=Count("pk"), oldest=Min(when), **sums)
        oldest = found["oldest"]
        if isinstance(oldest, datetime):
            oldest = timezone.localdate(oldest)
        row = {"key": key, "count": found["count"], "oldest": oldest, "configured": True}
        rows.append({**row, "amount": found.get("amount")})

    S = Settlement.State
    cod = CodRemittance.objects.filter(shipment__order__livemode=True) if live else CodRemittance.objects.all()
    refused_notes = InboxItem.objects.filter(kind=InboxItem.Kind.CREDIT_NOTE_MISSING, done_at=None)
    if live:
        refused_notes = refused_notes.exclude(target_id__in=Subquery(test_keys(Refund, "order__livemode")))
    add("refunds_to_approve", VIEW_REFUND, waiting_requests("order.refund", user))
    bank = Refund.objects.filter(method=Refund.Method.BANK, status=Refund.Status.PENDING)
    add("bank_refunds", VIEW_REFUND, live_only(bank, "order__livemode"))
    add("offline_to_approve", VIEW_PAYMENT, waiting_requests("order.offline_payment", user))
    add("stuck_payments", VIEW_PAYMENT, live_only(Payment.objects.filter(stuck_q())))
    paid_links = InvoicePaymentLink.objects.filter(status=InvoicePaymentLink.Status.PAID, posted_at=None, livemode=live)
    add("b2b_to_post", VIEW_PAYMENT, paid_links, when="paid_at")
    lines = SettlementLine.objects.filter(
        matched_at=None, settlement__livemode=live, settlement__state__in=[S.FETCHED, S.MISMATCHED]
    )
    add("settlement_lines", VIEW_SETTLEMENT, lines, when="settlement__date")
    mismatched = Settlement.objects.filter(state=S.MISMATCHED, livemode=live)
    add("settlements_mismatched", VIEW_SETTLEMENT, mismatched, when="date", amount="net")
    open_cod = [CodRemittance.State.EXPECTED, CodRemittance.State.OVERDUE]
    add("cod_receivable", "staff.view_cod", cod.filter(state__in=open_cod), "expected_on", "expected_amount")
    overdue = cod.filter(state=CodRemittance.State.OVERDUE)
    add("cod_overdue", "staff.view_cod", overdue, "expected_on", "expected_amount")
    mismatch = cod.filter(state=CodRemittance.State.MISMATCH)
    add("cod_mismatched", "staff.view_cod", mismatch, "expected_on", "remitted_amount")
    add("credit_notes_refused", "shop.view_creditnote", refused_notes, amount=None)
    unresolved = ErpReconciliationDifference.objects.filter(resolved_at=None)
    add("sync_differences", "erp.view_sync", unresolved, when="run__started_at", amount=None)
    if user.has_perm(VIEW_PAYMENT):  # Razorpay's disputes: not fetched yet (plan 5.8: should)
        rows.append({"key": "disputes", "count": None, "oldest": None, "amount": None, "configured": False})
    return {"livemode": live, "as_of": timezone.now(), "rows": rows}


class DocumentErpView(FinanceView, generics.GenericAPIView):
    """An invoice's or credit note's ERPNext mirror (its number, dashes for its slashes): the document ERPNext made
    (ErpLink) and its outbox rows, in one word: mirrored, waiting, failed, dead, discarded, not sent, off (its flow
    switched off) or test (never synced)."""

    serializer_class = FinanceDocumentErpSerializer
    permissions = {"GET": "shop.view_invoice"}

    def get(self, request, number, *args, **kwargs):
        from erp import contract
        from erp.models import ErpLink, ErpOutbox
        from erp.producers import enabled

        found = tax.parse_key(number)
        document = None
        if found:
            document = scoped(Invoice.objects.filter(number=found), request.user, "shop.view_invoice").first()
            if document is None:
                notes = CreditNote.objects.filter(number=found).select_related("invoice")
                document = scoped(notes, request.user, "shop.view_creditnote").first()
        if document is None:
            raise Http404
        kind = "credit_note" if isinstance(document, CreditNote) else "invoice"
        ref = contract.credit_note_ref(document) if kind == "credit_note" else contract.invoice_ref(document)
        link = ErpLink.objects.filter(examleaf_ref=ref).first()
        rows = list(ErpOutbox.objects.filter(examleaf_ref=ref).order_by("pk"))
        if document.is_test:
            state = "test"
        elif link is not None:
            state = "mirrored"
        elif rows:
            state = {"pending": "waiting", "sending": "waiting", "sent": "mirrored"}.get(rows[-1].state, rows[-1].state)
        else:
            state = "not_sent" if enabled("invoices") else "off"
        outbox = [
            {
                "id": row.pk,
                "event": row.event,
                "state": row.state,
                "attempts": row.attempts,
                "last_error": row.last_error,
                "created": row.created,
                "sent_at": row.sent_at,
            }
            for row in rows
        ]
        body = {
            "number": document.number,
            "kind": kind,
            "state": state,
            "doctype": link.doctype if link else None,
            "name": link.name if link else None,
            "synced_at": link.synced_at if link else None,
            "outbox": outbox,
        }
        return Response(FinanceDocumentErpSerializer(body).data)


router = SimpleRouter()
router.register("payments", PaymentViewSet, basename="payment")
router.register("offline-payments", OfflinePaymentViewSet, basename="offline-payment")
router.register("payment-links/invoices", InvoiceLinkViewSet, basename="invoice-link")
router.register("payment-links", LinkViewSet, basename="payment-link")
router.register("refunds", RefundViewSet, basename="refund")
router.register(r"settlements/(?P<settlement>\d+)/lines", SettlementLineViewSet, basename="settlement-line")
router.register("settlements", SettlementViewSet, basename="settlement")
app_name = "finance"
urlpatterns = [  # under /api/v1/staff/finance/ (staff/urls.py), namespace "staff:finance"
    path("today/", TodayView.as_view(), name="today"),
    path("documents/<str:number>/erp/", DocumentErpView.as_view(), name="document-erp"),
    *router.urls,
]
