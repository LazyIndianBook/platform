"""The Orders module's staff API, under /api/v1/staff/orders/ (API.md "Orders (staff)", shop/README.md), on the staff
app's rules (staff.api.StaffView): a member of staff on the panel's session with a second factor, or an API key with a
view_ permission; the permission each action names (none named: refused); its objects through `scoped()` with that
permission (a PACKER's orders are those to pack and on their way); cursor pages; every change an audit event; money
and discounts through staff.approvals (a 202 and a change request above the maker's limit). Every rule is the shop's
own (shop.services, its state machine): a refusal is its words, `400 {"non_field_errors": [...]}`.

- orders/: the list (filters, the panel's tabs, `q`: a number, a name, an email, a phone's last digits, an AWB, an
  invoice or credit note, a book code; a person looked up is an audit event with the query's keyed hash), a staff
  order (POST), the packing queue, a pick list, a record with its timeline, and the actions on it;
- orders/returns/: returns asked for, decided, received, inspected (the refund: orders/{number}/refunds/);
- orders/refunds/{id}/: a refund by bank or UPI marked paid (FINANCE), its payee shown with a reason;
- orders/quotes/: the schools' quotation requests, made into staff orders."""

import re
from datetime import datetime, time, timedelta
from decimal import Decimal

import django_filters
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from django_fsm import TransitionNotAllowed, can_proceed
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import exceptions, mixins, pagination, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from api.shop import AnyAccept, ShippingAddressSerializer
from shipping.api_serializers import ParcelSerializer, ShipmentEventSerializer
from staff import approvals, audit
from staff.api import IDEMPOTENCY, StaffView, accepted
from staff.backends import scoped
from staff.models import ChangeRequest
from staff.privacy import mask_email, mask_phone
from staff.serializers import ChangeRequestSerializer

from . import invoices, payments, services
from .models import (
    CreditNote,
    Order,
    OrderItem,
    Payment,
    Product,
    QuoteRequest,
    Refund,
    ReturnRequest,
    Shipment,
    SlugHistory,
    live_mode,
)
from .views import pdf_response

VIEW = "shop.view_order"
PDF = {(200, "application/pdf"): OpenApiTypes.BINARY}
SIX_MONTHS = timedelta(days=182)  # Razorpay: a normal refund of a payment older than this fails
NUMBER = re.compile(r"(?i)(el|t)-\d{4}-\d{6,}")
DOCUMENT = re.compile(r"(?i)(el|t|cn|tc)/\d{4}-\d{2}/\d{5}")
LOOKUPS = ("email", "phone", "name", "book_code")  # a search that finds a person: an audit event
CHANNELS = [("phone", "by phone"), ("whatsapp", "on WhatsApp"), ("school", "for a school"), ("email", "by email")]


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["orders (staff)"]


def refused(message):
    return exceptions.ValidationError({"non_field_errors": [str(message)]})


class Unavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The payment service could not be reached: try again in a few minutes."
    default_code = "unavailable"


def money(source=None, **kwargs):
    return serializers.DecimalField(source=source, max_digits=12, decimal_places=2, read_only=True, **kwargs)


def staff_name(user):
    return (user.full_name or user.email) if user else ""


# ---- Serializers (explicit fields; contacts masked) ----


class OrderCustomerSerializer(serializers.Serializer):
    """The buyer, masked: the account (its full view is users/{id}/), or a guest."""

    id = serializers.IntegerField(allow_null=True, help_text="the account; null: a guest (or an account erased)")
    name = serializers.CharField(help_text="as on the delivery address")
    email = serializers.CharField(help_text="masked")
    phone = serializers.CharField(help_text="masked")
    is_minor = serializers.BooleanField()


def customer_of(order):
    address, user = order.shipping_address or {}, order.user
    return {
        "id": order.user_id,
        "name": str(address.get("name", "")),
        "email": mask_email(order.email),
        "phone": mask_phone(address.get("phone", "")),
        "is_minor": bool(user and user.is_minor),
    }


class OrderRowSerializer(serializers.ModelSerializer):
    """An order in the list: what a row shows, with no query per row (the view prefetches)."""

    status_label = serializers.CharField(read_only=True)
    total = money("total.amount")
    items = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    courier = serializers.SerializerMethodField()
    parcel = serializers.SerializerMethodField(help_text="the latest parcel's status (the shipping app's), or null")
    tags = serializers.SerializerMethodField()
    held = serializers.SerializerMethodField()
    is_test = serializers.BooleanField(read_only=True, help_text="made with test keys on the live site: TEST")
    is_cod = serializers.BooleanField(read_only=True)
    has_returns = serializers.BooleanField(read_only=True, default=False)
    staff_order = serializers.SerializerMethodField(help_text="made by staff: a phone, WhatsApp or school order")

    class Meta:
        model = Order
        fields = [
            *["number", "created", "placed_at", "status", "status_label", "payment_method", "total", "items"],
            *["customer", "courier", "parcel", "tags", "held", "hold_reason", "risk_bucket", "is_test", "is_cod"],
            *["has_returns", "staff_order", "livemode"],
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_items(self, order):
        return [str(item) for item in order.items.all()]

    @extend_schema_field(OrderCustomerSerializer)
    def get_customer(self, order):
        return customer_of(order)

    def _latest(self, order):
        shipments = list(order.shipments.all())  # prefetched, newest first
        return shipments[0] if shipments else None

    @extend_schema_field(
        inline_serializer("OrderCourier", {"name": serializers.CharField(), "tracking_number": serializers.CharField()})
    )
    def get_courier(self, order):
        latest = self._latest(order)
        if latest is None:
            return None
        detail = getattr(latest, "detail", None)
        return {
            "name": (detail.courier_name if detail else "") or latest.courier,
            "tracking_number": latest.tracking_number,
        }

    def get_parcel(self, order) -> str | None:
        latest = self._latest(order)
        detail = getattr(latest, "detail", None) if latest else None
        return detail.status if detail else None

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_tags(self, order):
        return sorted(tag.name for tag in order.tags.all())

    def get_held(self, order) -> bool:
        return order.held_at is not None

    def get_staff_order(self, order) -> bool:
        return order.created_by_id is not None


class OrderLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product = serializers.CharField(help_text="its slug")
    title = serializers.CharField()
    isbn = serializers.CharField()
    hsn_code = serializers.CharField()
    gst_rate = serializers.DecimalField(max_digits=4, decimal_places=2)
    mrp = money()
    unit_price = money()
    quantity = serializers.IntegerField()
    line_total = money()
    discount = money(help_text="its share of the order's discounts")
    invoiced = money(help_text="its total less its discount: what a refund of it is worth")
    refunded = serializers.IntegerField(help_text="copies refunded already (refunds under way or made)")
    returnable = serializers.IntegerField(help_text="copies not yet asked back")
    digital = serializers.BooleanField()


class OrderPaymentSerializer(serializers.ModelSerializer):
    amount = money("amount.amount")
    refundable = serializers.SerializerMethodField(help_text="what is left of it to refund")
    older_than_6_months = serializers.SerializerMethodField(help_text="Razorpay may refuse a normal refund")

    class Meta:
        model = Payment
        fields = [
            *["id", "method", "amount", "status", "razorpay_order_id", "razorpay_payment_id", "payment_link_url"],
            *["reference", "error", "created", "modified", "refundable", "older_than_6_months"],
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_refundable(self, payment):
        return services.refundable(payment)

    def get_older_than_6_months(self, payment) -> bool:
        return payment.method == Order.Method.RAZORPAY and payment.created < timezone.now() - SIX_MONTHS


class OrderRefundLineSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    quantity = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderRefundSerializer(serializers.ModelSerializer):
    amount = money("amount.amount")
    shipping_amount = money("shipping_amount.amount")
    lines = OrderRefundLineSerializer(many=True, read_only=True)
    credit_note = serializers.SerializerMethodField()
    payment_method = serializers.CharField(source="payment.method", read_only=True)

    class Meta:
        model = Refund
        fields = [
            *["id", "amount", "status", "reason", "method", "speed", "lines", "shipping_amount", "restock"],
            *["payee_masked", "utr", "arn", "razorpay_refund_id", "change_request", "created", "processed_at"],
            *["error", "credit_note", "payment_method"],
        ]
        read_only_fields = fields

    def get_credit_note(self, refund) -> str | None:
        note = getattr(refund, "credit_note", None)
        return note.number if note else None


class OrderDocumentSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["invoice", "credit_note"])
    id = serializers.IntegerField()
    number = serializers.CharField()
    created = serializers.DateTimeField()
    ready = serializers.BooleanField(help_text="its PDF is made: GET its url")
    url = serializers.CharField(help_text="the PDF, for staff (this API's)")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)


class OrderParcelSerializer(ParcelSerializer):
    """A parcel of the order (the shipping app's) and its last scan."""

    last_event = serializers.SerializerMethodField()

    class Meta(ParcelSerializer.Meta):
        fields = [*ParcelSerializer.Meta.fields, "last_event"]
        read_only_fields = fields

    @extend_schema_field(ShipmentEventSerializer(allow_null=True))
    def get_last_event(self, shipment):
        events = list(shipment.events.all())  # prefetched, oldest first
        return ShipmentEventSerializer(events[-1]).data if events else None


class PickLineSerializer(serializers.Serializer):
    title = serializers.CharField()
    isbn = serializers.CharField()
    quantity = serializers.IntegerField()


class PackingRowSerializer(serializers.Serializer):
    """An order of the packing queue."""

    number = serializers.CharField()
    placed_at = serializers.DateTimeField()
    payment_method = serializers.CharField()
    is_cod = serializers.BooleanField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="the cash to collect, if COD")
    risk_bucket = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField())
    destination = serializers.CharField(help_text="town, district and PIN code")
    weight_g = serializers.IntegerField(allow_null=True, help_text="the books' and the packing; null: a book has none")
    pick = PickLineSerializer(many=True, help_text="each book once, with its copies (a bundle's books)")


class ReturnRowSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    order = serializers.CharField(source="order.number", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    lines = serializers.SerializerMethodField()
    refund = serializers.PrimaryKeyRelatedField(read_only=True)
    photos = serializers.SerializerMethodField(help_text="how many: GET photos/{index}/ each")

    class Meta:
        model = ReturnRequest
        fields = [
            *["id", "number", "order", "status", "status_label", "reason", "reason_label", "lines", "by_customer"],
            *["decision_note", "return_courier", "return_awb", "photos", "received_at", "inspected_at", "refund"],
            *["created", "modified"],
        ]
        read_only_fields = fields

    @extend_schema_field(
        inline_serializer(
            "ReturnLine",
            {
                "item": serializers.IntegerField(),
                "title": serializers.CharField(),
                "quantity": serializers.IntegerField(),
            },
            many=True,
        )
    )
    def get_lines(self, back):
        titles = {item.pk: item.title for item in back.order.items.all()}
        return [
            {"item": line["item"], "title": titles.get(line["item"], ""), "quantity": line["quantity"]}
            for line in back.lines
        ]

    def get_photos(self, back) -> int:
        return len(back.photos)


class ReturnDetailSerializer(ReturnRowSerializer):
    note = serializers.CharField(read_only=True, help_text="the customer's words")
    next = serializers.SerializerMethodField(help_text="the moves it may make now, as the actions' names")

    class Meta(ReturnRowSerializer.Meta):
        fields = [*ReturnRowSerializer.Meta.fields, "note", "next"]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_next(self, back):
        moves = {
            "approve": "approve",
            "decline": "decline",
            "send_label": "label",
            "receive": "receive",
            "restock": "inspect",
            "mark_damaged": "inspect",
        }
        found = [name for transition, name in moves.items() if can_proceed(getattr(back, transition))]
        if back.status in ReturnRequest.INSPECTED and not back.refund_id:
            found.append("refund")
        return list(dict.fromkeys(found))


class OrderActionSerializer(serializers.Serializer):
    name = serializers.CharField(
        help_text="pack, ship, deliver, cancel, hold, release, payment_link, offline_payment, …"
    )
    permission = serializers.CharField()
    primary = serializers.BooleanField(help_text="the one next action: the header's button")


class OrderRefundOptionsSerializer(serializers.Serializer):
    payment = serializers.IntegerField(allow_null=True)
    payment_method = serializers.CharField(allow_null=True)
    refundable = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="what is left to refund")
    shipping_left = serializers.DecimalField(max_digits=12, decimal_places=2)
    methods = serializers.ListField(child=serializers.CharField(), help_text="source and bank, or bank only")
    cancels = serializers.BooleanField(help_text="not sent yet: a refund cancels it and gives back everything")
    payment_age_days = serializers.IntegerField(allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField())


class OrderTimelineEntrySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.CharField(
        help_text="status, payment, refund, parcel, scan, message, note, hold, return, audit, erp"
    )
    label = serializers.CharField()
    actor = serializers.CharField(help_text="a member of staff's name, the customer, the site, or empty")
    details = serializers.DictField()


class OrderErpLinkSerializer(serializers.Serializer):
    model = serializers.CharField()
    object_id = serializers.CharField()
    doctype = serializers.CharField()
    name = serializers.CharField()
    synced_at = serializers.DateTimeField()


class OrderDetailSerializer(OrderRowSerializer):
    """An order as its record shows it (GET orders/{number}/)."""

    subtotal = money("subtotal.amount")
    discount = money("discount.amount")
    shipping_fee = money("shipping_fee.amount")
    savings = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    payments = OrderPaymentSerializer(many=True, read_only=True)
    refunds = OrderRefundSerializer(many=True, read_only=True)
    documents = serializers.SerializerMethodField()
    shipments = OrderParcelSerializer(many=True, read_only=True)
    returns = ReturnRowSerializer(many=True, read_only=True)
    hold = serializers.SerializerMethodField()
    risk_reasons = serializers.ListField(child=serializers.CharField(), read_only=True)
    is_digital = serializers.BooleanField(read_only=True)
    quote = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    refund = serializers.SerializerMethodField()
    erp = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta(OrderRowSerializer.Meta):
        fields = [
            *OrderRowSerializer.Meta.fields,
            *["subtotal", "discount", "shipping_fee", "coupon_code", "savings", "address", "lines", "payments"],
            *["refunds", "documents", "shipments", "returns", "hold", "risk_reasons", "is_digital", "quote"],
            *["created_by", "actions", "refund", "erp", "timeline", "modified"],
        ]
        read_only_fields = fields

    @extend_schema_field(
        inline_serializer(
            "OrderSaving", {"label": serializers.CharField(), "amount": serializers.DecimalField(12, 2)}, many=True
        )
    )
    def get_savings(self, order):
        return [{"label": label, "amount": amount.amount} for label, amount in order.savings]

    @extend_schema_field(
        inline_serializer(
            "OrderAddress",
            {
                name: serializers.CharField()
                for name in ["name", "phone", "line1", "line2", "city", "district", "state", "pin"]
            },
        )
    )
    def get_address(self, order):
        """The delivery address as copied at checkout, its phone masked (the packing slip prints it whole)."""
        address = {name: str((order.shipping_address or {}).get(name, "")) for name in ["name", "line1", "line2"]}
        address |= {
            name: str((order.shipping_address or {}).get(name, "")) for name in ["city", "district", "state", "pin"]
        }
        return {**address, "phone": mask_phone((order.shipping_address or {}).get("phone", ""))}

    @extend_schema_field(OrderLineSerializer(many=True))
    def get_lines(self, order):
        known, left = services.refund_lines(order), services.returnable(order)
        rows = []
        for pk, entry in known.items():
            item = entry["item"]
            rows.append(
                {
                    "id": pk,
                    "product": item.product.slug,
                    "title": item.title,
                    "isbn": item.product.isbn,
                    "hsn_code": item.hsn_code,
                    "gst_rate": item.gst_rate,
                    "mrp": item.mrp.amount,
                    "unit_price": item.unit_price.amount,
                    "quantity": item.quantity,
                    "line_total": item.line_total.amount,
                    "discount": item.line_total.amount - entry["value"],
                    "invoiced": entry["value"],
                    "refunded": entry["refunded"],
                    "returnable": max(left.get(pk, 0), 0),
                    "digital": item.product.digital_only,
                }
            )
        return OrderLineSerializer(rows, many=True).data

    @extend_schema_field(OrderDocumentSerializer(many=True))
    def get_documents(self, order):
        invoice = getattr(order, "invoice", None)
        if invoice is None:
            return []
        base = f"/api/v1/staff/orders/{order.number}/"
        rows = [
            {
                "kind": "invoice",
                "id": invoice.pk,
                "number": invoice.number,
                "created": invoice.created,
                "ready": bool(invoice.pdf),
                "url": f"{base}invoice/",
                "amount": order.total.amount,
            }
        ]
        for note in invoice.credit_notes.select_related("refund"):
            rows.append(
                {
                    "kind": "credit_note",
                    "id": note.pk,
                    "number": note.number,
                    "created": note.created,
                    "ready": bool(note.pdf),
                    "url": f"{base}credit-notes/{note.pk}/",
                    "amount": note.refund.amount.amount,
                }
            )
        return OrderDocumentSerializer(rows, many=True).data

    @extend_schema_field(
        inline_serializer(
            "OrderHold",
            {"at": serializers.DateTimeField(), "by": serializers.CharField(), "reason": serializers.CharField()},
            allow_null=True,
        )
    )
    def get_hold(self, order):
        if order.held_at is None:
            return None
        return {"at": order.held_at, "by": staff_name(order.held_by) or "the site", "reason": order.hold_reason}

    def get_quote(self, order) -> str | None:
        quote = getattr(order, "quote", None)
        return quote.number if quote else None

    def get_created_by(self, order) -> str | None:
        return staff_name(order.created_by) or None

    @extend_schema_field(OrderActionSerializer(many=True))
    def get_actions(self, order):
        return actions_for(order, self.context["request"].user)

    @extend_schema_field(OrderRefundOptionsSerializer)
    def get_refund(self, order):
        return refund_options(order)

    @extend_schema_field(OrderErpLinkSerializer(many=True))
    def get_erp(self, order):
        return erp_links(order)

    @extend_schema_field(OrderTimelineEntrySerializer(many=True))
    def get_timeline(self, order):
        return timeline(order, self.context["request"].user)


def actions_for(order, user):
    """What this person may do to the order now: the state machine's moves crossed with their permissions, and the
    one next action (pay, pack, send, deliver; release a held order first)."""
    awaiting = order.status == Order.Status.PENDING and not order.placed_at and not order.is_cod
    moves = [
        ("release", "shop.change_order", order.held_at is not None),
        ("hold", "shop.change_order", order.held_at is None and order.status in services.HOLDABLE),
        ("payment_link", "shop.change_order", awaiting and order.created_by_id is not None),
        ("offline_payment", "staff.record_offline_payment", awaiting),
        ("pack", "staff.pack_order", can_proceed(order.pack)),
        ("ship", "staff.pack_order", can_proceed(order.ship)),
        ("deliver", "staff.pack_order", can_proceed(order.deliver)),
        ("refund", "staff.refund_order", services.refundable_payment(order) is not None),
        ("return", "staff.handle_return", order.status == Order.Status.DELIVERED and not order.is_digital),
        ("cancel", "shop.change_order", can_proceed(order.cancel) or can_proceed(order.cancel_returned)),
        ("tags", "shop.change_order", True),
        ("notify", "shop.change_order", order.placed_at is not None or order.status == Order.Status.CANCELLED),
        ("invoice", "shop.change_order", services.invoiceable(order)),
    ]
    allowed = [(name, perm) for name, perm, possible in moves if possible and user.has_perm(perm)]
    first = next((name for name, _ in allowed if name in ("release", "payment_link", "pack", "ship", "deliver")), None)
    return [{"name": name, "permission": perm, "primary": name == first} for name, perm in allowed]


def refund_options(order):
    """What a refund of the order may be, before the agent confirms: the payment it goes against and what is left of
    it, the shipping left, the methods (Razorpay's to the source; bank or UPI, the only one for cash on delivery and
    transfers, for an online payment only with the customer's agreement), whether it cancels, and the warnings."""
    payment = services.refundable_payment(order)
    online = payment is not None and payment.method == Order.Method.RAZORPAY
    warnings = []
    age = (timezone.now() - payment.created).days if payment else None
    if online and payment.created < timezone.now() - SIX_MONTHS:
        warnings.append(
            "The payment is older than 6 months: Razorpay may refuse a normal refund. Refund by bank or UPI to an "
            "account the customer gives, with their agreement."
        )
    return {
        "payment": payment.pk if payment else None,
        "payment_method": payment.method if payment else None,
        "refundable": services.refundable(payment) if payment else Decimal("0.00"),
        "shipping_left": services.shipping_left(order),
        "methods": (["source", "bank"] if online else ["bank"]) if payment else [],
        "cancels": payment is not None and can_proceed(order.cancel),
        "payment_age_days": age,
        "warnings": warnings,
    }


def erp_links(order):
    """The ERPNext documents made for the order and its invoice, credit notes, payments, parcels and refunds."""
    from erp.models import ErpLink

    objects = [("shop.order", order.pk), ("shop.invoice", getattr(getattr(order, "invoice", None), "pk", None))]
    objects += [("shop.payment", payment.pk) for payment in order.payments.all()]
    objects += [("shop.shipment", shipment.pk) for shipment in order.shipments.all()]
    objects += [("shop.refund", refund.pk) for refund in order.refunds.all()]
    notes = CreditNote.objects.filter(invoice__order=order).values_list("pk", flat=True)
    objects += [("shop.creditnote", pk) for pk in notes]
    wanted = Q(pk__in=[])
    for model, pk in objects:
        if pk is not None:
            wanted |= Q(model=model, object_id=str(pk))
    links = ErpLink.objects.filter(wanted).order_by("synced_at")
    return [
        {
            "model": link.model,
            "object_id": link.object_id,
            "doctype": link.doctype,
            "name": link.name,
            "synced_at": link.synced_at,
        }
        for link in links
    ]


def who(user, staff_ids):
    if user is None:
        return "the site"
    return staff_name(user) if user.pk in staff_ids or user.is_staff else "the customer"


def timeline(order, user):
    """The order's story, oldest first: its status changes and holds (its history), its payments' (theirs), its
    refunds, parcels and their scans, the emails and SMS sent (OrderMessage), the legacy internal notes, its returns,
    its ERPNext documents, and for whoever reads the audit log, the audit events about it (a read of the log, itself
    recorded)."""
    rows = []

    def add(at, kind, label, actor="", **details):
        if at is not None:
            rows.append({"at": at, "kind": kind, "label": label, "actor": actor, "details": details})

    labels = dict(Order.Status.choices)
    previous = None
    for row in order.history.select_related("history_user").order_by("history_date", "history_id"):
        actor = who(row.history_user, ())
        if previous is None or row.status != previous.status:
            add(row.history_date, "status", f"Status: {labels.get(row.status, row.status)}", actor, status=row.status)
        if previous is not None and row.held_at != previous.held_at:
            add(row.history_date, "hold", f"Held: {row.hold_reason}" if row.held_at else "Released", actor)
        previous = row
    for payment in order.payments.all():
        seen = None
        for row in payment.history.select_related("history_user").order_by("history_date", "history_id"):
            if row.status != seen:
                label = f"Payment #{payment.pk} ({payment.get_method_display()}): {row.status}"
                add(row.history_date, "payment", label, who(row.history_user, ()), payment=payment.pk)
                seen = row.status
    for refund in order.refunds.all():
        by = staff_name(refund.created_by) or "the site"
        add(
            refund.created,
            "refund",
            f"Refund #{refund.pk} of ₹{refund.amount.amount} asked ({refund.get_method_display()})",
            by,
            refund=refund.pk,
        )
        if refund.status == Refund.Status.PROCESSED:
            add(refund.processed_at, "refund", f"Refund #{refund.pk} made", "", refund=refund.pk)
        elif refund.status == Refund.Status.FAILED:
            add(refund.modified, "refund", f"Refund #{refund.pk} failed: {refund.error}", "", refund=refund.pk)
    for shipment in order.shipments.all():
        add(
            shipment.shipped_at,
            "parcel",
            f"Sent by {shipment.courier} ({shipment.tracking_number})",
            "",
            shipment=shipment.pk,
        )
        if shipment.delivered_at:
            add(shipment.delivered_at, "parcel", "Delivered", "", shipment=shipment.pk)
        for event in shipment.events.all():
            label = event.carrier_label or event.get_status_display() or event.activity
            add(event.occurred_at, "scan", label, "", shipment=shipment.pk, location=event.location)
    for message in order.messages.all():
        sms = {"sent": ", and an SMS", "held": ", the SMS held for the morning", "dropped": ", the SMS dropped"}
        add(message.created, "message", f"Told the customer: {message.kind} (email{sms.get(message.sms, '')})", "")
    for note in order.notes.select_related("author"):
        add(note.created, "note", note.text, staff_name(note.author))
    for back in order.returns.all():
        add(
            back.created,
            "return",
            f"Return {back.number} asked for: {back.get_reason_display()}",
            "the customer" if back.by_customer else "",
            back=back.pk,
        )
    for link in erp_links(order):
        add(link["synced_at"], "erp", f"In ERPNext: {link['doctype']} {link['name']}", "")
    if user.has_perm("staff.view_auditlog"):
        from staff.models import AuditEvent

        events = list(AuditEvent.objects.filter(target_type="shop.order", target_id=str(order.pk)).order_by("id"))
        people = get_user_model().objects.filter(pk__in={event.actor_id for event in events})
        people = {person.pk: person for person in people}
        for event in events:
            add(
                event.ts,
                "audit",
                event.action,
                staff_name(people.get(event.actor_id)) or event.actor_type,
                outcome=event.outcome,
            )
        audit.record("audit.read", target=order, details={"what": "order timeline"})
    rows.sort(key=lambda row: row["at"])
    return OrderTimelineEntrySerializer(rows, many=True).data


# ---- Requests ----


class OrderLineAskSerializer(serializers.Serializer):
    item = serializers.IntegerField(help_text="an order line's id")
    quantity = serializers.IntegerField(min_value=0, max_value=5000, help_text="copies; 0: not this line")


class RefundPayeeSerializer(serializers.Serializer):
    upi = serializers.CharField(required=False, allow_blank=True, max_length=300, help_text="name@bank")
    account = serializers.CharField(required=False, allow_blank=True, max_length=30)
    ifsc = serializers.CharField(required=False, allow_blank=True, max_length=11)
    name = serializers.CharField(required=False, allow_blank=True, max_length=120, help_text="the account holder")


class OrderRefundAskSerializer(serializers.Serializer):
    lines = OrderLineAskSerializer(many=True, required=False, help_text="the copies refunded; quantities start at 0")
    shipping = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=Decimal(0))
    restock = serializers.BooleanField(required=False, default=False, help_text="the copies go back into stock")
    method = serializers.ChoiceField(choices=["source", "bank"], required=False, help_text="default: the payment's")
    speed = serializers.ChoiceField(choices=Refund.Speed.choices, required=False, default=Refund.Speed.NORMAL)
    payee = RefundPayeeSerializer(required=False, help_text="method bank: the customer's UPI ID, or bank account")
    customer_agreed = serializers.BooleanField(required=False, default=False, help_text="bank for an online payment")
    reason = serializers.CharField(max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["return"] = serializers.IntegerField(  # (a keyword: added here)
            required=False, help_text="a return of the order, inspected: its refund (its lines by default)"
        )

    def payload(self):
        data = {**self.validated_data}
        data.pop("reason")
        if "lines" in data:
            data["lines"] = [dict(line) for line in data["lines"]]
        if "shipping" in data:
            data["shipping"] = str(data["shipping"])
        if "payee" in data:
            data["payee"] = {key: value for key, value in dict(data["payee"]).items() if value}
        data.setdefault("lines", [])
        return data


class OrderRefundAskedSerializer(ChangeRequestSerializer):
    warnings = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta(ChangeRequestSerializer.Meta):
        fields = [*ChangeRequestSerializer.Meta.fields, "warnings"]


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, help_text="told to the customer")
    customer_requested = serializers.BooleanField(required=False, default=False, help_text="the customer asked")
    restock = serializers.BooleanField(required=False, default=True, help_text="a parcel back: its copies sellable")


class OrderHoldReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, help_text="an address to check, a payment to confirm …")


class OrderTagsSerializer(serializers.Serializer):
    add = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)
    remove = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)


class OrderShipSerializer(serializers.Serializer):
    courier = serializers.ChoiceField(choices=Shipment.Courier.choices)
    tracking_number = serializers.CharField(max_length=80)
    tracking_url = serializers.URLField(required=False, allow_blank=True, default="")


class OrderNotifySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["placed", "paid", "packed", "shipped", "delivered", "cancelled", "refunded"]
    )


class OrderPaymentLinkSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["send", "cancel"], default="send")


class OrderOfflinePaymentSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=60, help_text="the UTR or UPI reference, as on the bank statement")
    reason = serializers.CharField(max_length=500)


class ReturnAskSerializer(serializers.Serializer):
    lines = OrderLineAskSerializer(many=True)
    reason = serializers.ChoiceField(choices=ReturnRequest.Reason.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, help_text="the customer's words")


class StaffOrderLineSerializer(serializers.Serializer):
    product = serializers.SlugField(help_text="a product on sale")
    quantity = serializers.IntegerField(min_value=1, max_value=5000)


class StaffOrderSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=CHANNELS)
    lines = StaffOrderLineSerializer(many=True, allow_empty=False)
    email = serializers.EmailField(help_text="the customer's: the order, the payment link and the invoice go there")
    address = ShippingAddressSerializer(help_text="the PIN code's state is checked against India Post's directory")
    discount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal(0),
        required=False,
        default=Decimal(0),
        help_text="rupees off the books, after the offers",
    )
    shipping = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal(0),
        required=False,
        allow_null=True,
        default=None,
        help_text="null: the shipping rates'",
    )
    send_link = serializers.BooleanField(required=False, default=True, help_text="email a Razorpay payment link")
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, help_text="an internal note")
    reason = serializers.CharField(max_length=500, help_text="why (the approvals' and the audit log's)")

    def validate_lines(self, lines):
        copies = {}
        for line in lines:
            copies[line["product"]] = copies.get(line["product"], 0) + line["quantity"]
        on_sale = set(Product.objects.filter(slug__in=copies, is_active=True).values_list("slug", flat=True))
        if missing := sorted(set(copies) - on_sale):
            raise serializers.ValidationError(f"Not on sale: {', '.join(missing)}.")
        return [{"product": slug, "quantity": quantity} for slug, quantity in copies.items()]


class QuoteConvertSerializer(serializers.Serializer):
    address = ShippingAddressSerializer(help_text="where the books go (the quote has only its PIN code)")
    email = serializers.EmailField(required=False, help_text="default: the quote's")
    send_link = serializers.BooleanField(required=False, default=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    reason = serializers.CharField(max_length=500, required=False, default="A school's quotation accepted.")


class RefundMarkPaidSerializer(serializers.Serializer):
    utr = serializers.CharField(max_length=60, help_text="the transfer's UTR or UPI reference")


class PickListSerializer(serializers.Serializer):
    orders = serializers.ListField(child=serializers.CharField(max_length=20), min_length=1, max_length=500)


class ReturnInspectSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["restocked", "damaged"])


class ReturnLabelSerializer(serializers.Serializer):
    courier = serializers.CharField(max_length=80)
    awb = serializers.CharField(max_length=80)


class ReturnDeclineSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=300, help_text="why: the customer is told")


class ReturnPhotoSerializer(serializers.Serializer):
    photo = serializers.ImageField(help_text="JPEG, PNG or WebP, 5 MB at most")


# ---- Filters ----


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


TABS = {
    "to_pack": "paid, or placed to pay on delivery, not packed, not on hold",
    "shipped": "on their way",
    "returns": "a parcel coming back or back, or a return asked for",
    "cancelled": "cancelled",
    "drafts": "made by staff and waiting for their payment",
}


class OrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Order.Status.choices)
    method = django_filters.ChoiceFilter(field_name="payment_method", choices=Order.Method.choices)
    courier = django_filters.CharFilter(method="filter_courier", help_text="a courier's name, as on its parcels")
    created_from = django_filters.DateFilter(method="filter_from", help_text="a day (India time), from it on")
    created_to = django_filters.DateFilter(method="filter_to", help_text="a day (India time), up to its end")
    shipping = django_filters.CharFilter(method="filter_shipping", help_text="a parcel status, or none (no parcel)")
    tag = django_filters.CharFilter(field_name="tags__name", lookup_expr="iexact")
    hold = django_filters.BooleanFilter(field_name="held_at", lookup_expr="isnull", exclude=True)
    risk = django_filters.ChoiceFilter(field_name="risk_bucket", choices=Order.Risk.choices)
    livemode = django_filters.BooleanFilter(help_text="default: the live site's own (test orders only when asked)")
    tab = django_filters.ChoiceFilter(choices=list(TABS.items()), method="filter_tab", help_text="the panel's tabs")
    q = django_filters.CharFilter(method="search", help_text="a number, name, email, phone digits, AWB, document, code")

    class Meta:
        model = Order
        fields = []

    def filter_courier(self, queryset, name, value):
        named = Q(shipments__courier__iexact=value) | Q(shipments__detail__courier_name__icontains=value)
        return queryset.filter(named).distinct()

    def filter_from(self, queryset, name, value):
        return queryset.filter(created__gte=day_start(value))

    def filter_to(self, queryset, name, value):
        return queryset.filter(created__lt=day_start(value + timedelta(days=1)))

    def filter_shipping(self, queryset, name, value):
        if value == "none":
            return queryset.filter(shipments__isnull=True)
        return queryset.filter(shipments__detail__status=value).distinct()

    def filter_tab(self, queryset, name, value):
        S = Order.Status
        if value == "to_pack":
            placed = Q(status=S.PAID) | Q(status=S.PENDING, payment_method=Order.Method.COD, placed_at__isnull=False)
            return queryset.filter(placed, held_at__isnull=True)
        if value == "shipped":
            return queryset.filter(status=S.SHIPPED)
        if value == "returns":
            back = Q(shipments__detail__status__in=["returning", "returned"]) | Q(returns__isnull=False)
            return queryset.filter(back).distinct()
        if value == "cancelled":
            return queryset.filter(status=S.CANCELLED)
        return queryset.filter(status=S.PENDING, placed_at__isnull=True, created_by__isnull=False)

    def search(self, queryset, name, value):
        kind, query = classify(value)
        self.lookup = (kind, query)
        if kind == "number":
            return queryset.filter(number__iexact=query)
        if kind == "document":
            return queryset.filter(Q(invoice__number__iexact=query) | Q(invoice__credit_notes__number__iexact=query))
        if kind == "email":
            return queryset.filter(email__iexact=query)
        if kind == "phone":
            found = Q(shipping_address__phone__endswith=query) | Q(shipments__tracking_number__iexact=query)
            return queryset.filter(found | Q(number__endswith=query)).distinct()
        if kind == "book_code":
            from learn.models import BookCode, code_digest

            user = BookCode.objects.filter(digest=code_digest(query)).values_list("redeemed_by", flat=True).first()
            return queryset.filter(user=user) if user else queryset.none()
        if kind == "name":
            found = Q(shipping_address__name__icontains=query) | Q(shipments__tracking_number__iexact=query)
            return queryset.filter(found).distinct()
        return queryset.none()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.form.cleaned_data.get("livemode") is None and live_mode():
            queryset = queryset.filter(livemode=True)  # test orders only when asked (?livemode=false)
        return queryset


def classify(value):
    """(kind, the query as matched) of a search: an order's number, an invoice's or credit note's, an email address,
    digits (a phone's last ones, an AWB), a book code (12 of its letters), a name (3 letters or more), or nothing."""
    from learn.models import CODE_ALPHABET, CODE_LENGTH, clean_code

    value = " ".join(str(value or "").split())[:100]
    digits = re.sub(r"\D", "", value)
    code = clean_code(value)
    if NUMBER.fullmatch(value):
        return "number", value.upper()
    if DOCUMENT.fullmatch(value):
        return "document", value.upper()
    if "@" in value:
        return "email", value.lower()
    if digits and len(digits) >= 4 and re.fullmatch(r"[\d\s+-]+", value):
        return "phone", digits[-10:]
    if len(code) == CODE_LENGTH and all(char in CODE_ALPHABET for char in code) and any(c.isdigit() for c in code):
        return "book_code", code
    if len(value) >= 3:
        return "name", value
    return "none", value


class Oldest(pagination.CursorPagination):
    """The packing queue: oldest first (the first placed is the first packed)."""

    page_size, page_size_query_param, max_page_size, ordering = 50, "page_size", 200, ("placed_at", "pk")


# ---- Views ----


class OrdersView(StaffView):
    schema = StaffSchema()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return scoped(self.queryset.all(), self.request.user, self.required_permission(self.request))

    def log(self, action, target, **kwargs):
        return audit.record(action, request=self.request, target=target, **kwargs)


def call(function, *args, **kwargs):
    """A shop service, its refusals as the API's errors (400, its words)."""
    try:
        return function(*args, **kwargs)
    except services.ShopError as error:
        raise refused(error) from error
    except TransitionNotAllowed as error:
        raise refused("Not possible for this order in its present state.") from error


ROWS = [
    Prefetch("items", queryset=OrderItem.objects.select_related("product")),
    Prefetch("shipments", queryset=Shipment.objects.select_related("detail").order_by("-shipped_at", "-pk")),
    "tags",
]


def with_returns(queryset):
    return queryset.annotate(has_returns=Exists(ReturnRequest.objects.filter(order=OuterRef("pk"))))


class OrderViewSet(OrdersView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Orders: the list, a staff order (POST), the packing queue, a pick list, a record with its timeline, and the
    actions on one (each its permission; the state machine refuses what cannot happen now)."""

    queryset = Order.objects.all()
    lookup_field = "number"
    filterset_class = OrderFilter
    serializer_class = OrderRowSerializer
    permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "packing": VIEW,
        "create": "shop.add_order",
        "pick_list": "staff.pack_order",
        "packing_slip": "staff.pack_order",
        "label": "staff.pack_order",
        "pack": "staff.pack_order",
        "ship": "staff.pack_order",
        "deliver": "staff.pack_order",
        "invoice": "shop.view_invoice",
        "credit_note": "shop.view_creditnote",
        **dict.fromkeys(["cancel", "hold", "release", "tags", "notify", "payment_link"], "shop.change_order"),
        **dict.fromkeys(["invoice_regenerate", "invoice_resend"], "shop.change_order"),
        "refunds": "staff.refund_order",
        "offline_payment": "staff.record_offline_payment",
        "returns": "staff.handle_return",
    }
    throttle_scopes = {
        "list": "staff_search",
        **dict.fromkeys(["create", "refunds", "offline_payment"], "staff_money"),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            return with_returns(queryset.select_related("user").prefetch_related(*ROWS))
        if self.action == "retrieve":
            parcels = (
                Shipment.objects.select_related("detail").prefetch_related("events").order_by("-shipped_at", "-pk")
            )
            return (
                with_returns(queryset)
                .select_related("user", "invoice", "held_by", "created_by")
                .prefetch_related(
                    Prefetch("items", queryset=OrderItem.objects.select_related("product")),
                    Prefetch("shipments", queryset=parcels),
                    "tags",
                    "payments",
                    Prefetch("refunds", queryset=Refund.objects.select_related("credit_note", "payment", "created_by")),
                    Prefetch("returns", queryset=ReturnRequest.objects.select_related("order")),
                    "messages",
                )
            )
        return queryset

    def get_serializer_class(self):
        return OrderDetailSerializer if self.action == "retrieve" else OrderRowSerializer

    def order(self):
        return self.get_object()

    def retrieve(self, request, *args, **kwargs):
        """The record; opening a child's order (its account under 18) is a logged read, as the child's record is."""
        order = self.get_object()
        if order.user is not None and order.user.is_minor:
            audit.record("sensitive_read", request=request, target=order, details={"what": "order", "child": True})
        return Response(self.get_serializer(order).data)

    # The list, with its person lookups audited

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if query := request.query_params.get("q", "").strip():
            kind, value = classify(query)
            if kind in LOOKUPS:  # one event per search of a person: its keyed hash, what it found (no query itself)
                found = self.filter_queryset(self.get_queryset()).count()
                details = {"kind": kind, "query": audit.mask(value, "contact"), "found": found, "list": "orders"}
                audit.record("customer.lookup", request=request, details=details)
        return response

    @extend_schema(
        request=StaffOrderSerializer,
        responses={201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def create(self, request, *args, **kwargs):
        """A phone, WhatsApp or school order at today's prices with the offers: 201 with the change request run at
        once (its result names the order) within your discount limit; 202 beyond it, or for a ₹0 total: nothing is
        made until a second person approves."""
        data = StaffOrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return ask_staff_order(self, request, data.validated_data)

    # The packing room

    @extend_schema(responses=PackingRowSerializer(many=True))
    @action(detail=False, filter_backends=[])
    def packing(self, request, *args, **kwargs):
        """The packing queue: paid (or placed to pay on delivery) and not packed, not on hold, not a test order, not
        courses alone; oldest first, each with its books to pick, a weight hint, the COD badge and its risk."""
        S = Order.Status
        placed = Q(status=S.PAID) | Q(status=S.PENDING, payment_method=Order.Method.COD, placed_at__isnull=False)
        queue = self.get_queryset().filter(placed, held_at__isnull=True)
        if live_mode():
            queue = queue.filter(livemode=True)
        books = Prefetch(
            "items",
            queryset=OrderItem.objects.select_related("product").prefetch_related("product__bundle_items__product"),
        )
        queue = queue.prefetch_related(books, "tags")
        paginator = Oldest()
        page = paginator.paginate_queryset(queue, request, view=self)
        rows = [packing_row(order) for order in page if pick_lines(order)]  # courses alone: nothing to pack
        return paginator.get_paginated_response(rows)

    @extend_schema(request=PickListSerializer, responses=PDF)
    @action(
        detail=False, methods=["post"], url_path="pick-list", filter_backends=[], content_negotiation_class=AnyAccept
    )
    def pick_list(self, request, *args, **kwargs):
        """The pick list of these orders (numbers): each book once, with its copies and the orders it goes in."""
        data = PickListSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        numbers = list(dict.fromkeys(number.upper() for number in data.validated_data["orders"]))
        found = list(
            self.get_queryset().filter(number__in=numbers).prefetch_related("items__product__bundle_items__product")
        )
        if missing := sorted(set(numbers) - {order.number for order in found}):
            raise serializers.ValidationError(
                {"orders": [f"No such order (or not one you may see): {', '.join(missing)}."]}
            )
        self.log("order.pick_list_printed", None, details={"orders": len(found)})
        return pdf(invoices.render_pdf(invoices.Print("pick_list", sorted(found, key=lambda o: o.pk))), "pick-list")

    @extend_schema(responses=PDF)
    @action(detail=True, url_path="documents/packing-slip", content_negotiation_class=AnyAccept)
    def packing_slip(self, request, *args, **kwargs):
        """The order's A4 packing slip: its books (title, ISBN, copies), the school or class, its number as a QR."""
        order = self.order()
        if not pick_lines(order):
            raise refused("Courses alone: nothing to pack.")
        self.log("order.packing_slip_printed", order)
        return pdf(invoices.render_pdf(invoices.Print("packing_slip", [order])), f"slip-{order.number}")

    @extend_schema(responses=PDF)
    @action(detail=True, url_path="documents/label", content_negotiation_class=AnyAccept)
    def label(self, request, *args, **kwargs):
        """The 4 × 6 inch label of a parcel sent by hand (India Post, a courier without an API): to and from, the
        number as a QR, the cash to collect. A courier's own label is the shipping app's."""
        order = self.order()
        if not pick_lines(order):
            raise refused("Courses alone: nothing to send.")
        self.log("order.label_printed", order)
        return pdf(invoices.render_pdf(invoices.Print("label", [order])), f"label-{order.number}")

    @extend_schema(responses=PDF)
    @action(detail=True, content_negotiation_class=AnyAccept)
    def invoice(self, request, *args, **kwargs):
        """The invoice's PDF (404 until it is made)."""
        return pdf_response(getattr(self.order(), "invoice", None))

    @extend_schema(responses=PDF, parameters=[OpenApiParameter("note", int, OpenApiParameter.PATH)])
    @action(detail=True, url_path=r"credit-notes/(?P<note>\d+)", content_negotiation_class=AnyAccept)
    def credit_note(self, request, note, *args, **kwargs):
        """A credit note's PDF (404 until it is made)."""
        return pdf_response(CreditNote.objects.filter(invoice__order=self.order(), pk=note).first())

    # Moves

    def answer(self, order):
        order = with_returns(Order.objects.filter(pk=order.pk)).prefetch_related(*ROWS).get()
        return Response(OrderRowSerializer(order, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def pack(self, request, *args, **kwargs):
        """Packed (the customer is told). Refused for a held order, a test order, one not paid or placed."""
        order = self.order()
        if order.held_at:
            raise refused(f"Order {order.number} is on hold ({order.hold_reason}): release it first.")
        order = call(services.pack_order, order)
        self.log("order.packed", order)
        return self.answer(order)

    @extend_schema(request=OrderShipSerializer, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def ship(self, request, *args, **kwargs):
        """Sent by hand at the counter (India Post, a courier without an API): the courier and the number; the
        customer is told with the tracking link. A courier booked through Shiprocket is the shipping app's."""
        from shipping import services as shipping

        data = OrderShipSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order, values = self.order(), data.validated_data
        try:
            shipping.ship_by_hand(
                order, values["courier"], values["tracking_number"], values["tracking_url"], by=self.human()
            )
        except TransitionNotAllowed as error:
            raise refused(
                f"Order {order.number} is {order.get_status_display()}: only a packed order is sent."
            ) from error
        self.log("shipping.shipped_by_hand", order, details={"courier": values["courier"]})
        return self.answer(order)

    @extend_schema(request=None, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def deliver(self, request, *args, **kwargs):
        """Delivered (a parcel sent by hand: a courier's scans deliver theirs): a COD payment is captured."""
        order = call(services.deliver_order, self.order())
        self.log("order.delivered", order)
        return self.answer(order)

    @extend_schema(
        request=OrderCancelSerializer,
        responses={200: OrderRowSerializer, 201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        """Cancel before it leaves (its stock back; the customer told; no fee). Paid online: through its refund
        (staff.approvals "order.refund": your refund limit, FINANCE above it). Paid by transfer: refund it by bank or
        UPI (refunds/), which cancels it. A cash-on-delivery parcel back undelivered (RTO): cancelled, its copies back
        unless damaged (`restock`), its invoice credited."""
        data = OrderCancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order, values, user = self.order(), data.validated_data, self.human()
        reason = values["reason"].strip()
        details = {"customer_requested": values["customer_requested"]}
        if can_proceed(order.cancel_returned):
            order = call(services.cancel_returned, order, reason, by=user, restock=values["restock"], request=request)
            return self.answer(order)
        if not can_proceed(order.cancel):
            raise refused(f"Order {order.number} is {order.get_status_display()}: refund it, or ask for a return.")
        if services.online_payment(order) is not None:
            change_request, created = approvals.ask(
                "order.refund",
                maker=user,
                target=order.number,
                payload={},
                reason=reason,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                request=request,
            )
            response = accepted(change_request, self)
            if created and response.status_code == status.HTTP_200_OK:
                response.status_code = status.HTTP_201_CREATED
            return response
        if order.payments.filter(method=Order.Method.OFFLINE, status__in=services.PAID).exists():
            raise refused("Paid by transfer: refund it by bank or UPI to the customer's account, which cancels it.")
        order = call(services.cancel_order, order, reason, by=user)
        self.log("order.cancelled", order, reason=reason, details=details)
        return self.answer(order)

    @extend_schema(request=OrderHoldReasonSerializer, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def hold(self, request, *args, **kwargs):
        """Hold it, with the reason (it leaves the packing queue until released)."""
        data = OrderHoldReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.answer(call(services.hold, self.order(), data.validated_data["reason"], self.human(), request))

    @extend_schema(request=None, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, *args, **kwargs):
        """Release a held order: back in the packing queue."""
        return self.answer(call(services.release, self.order(), self.human(), request))

    @extend_schema(request=OrderTagsSerializer, responses=OrderRowSerializer)
    @action(detail=True, methods=["post"])
    def tags(self, request, *args, **kwargs):
        """Add and remove tags (school, awaiting reprint …)."""
        data = OrderTagsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        order = self.order()
        call(services.set_tags, order, values["add"], values["remove"], self.human(), request)
        return self.answer(order)

    @extend_schema(
        request=OrderNotifySerializer, responses=inline_serializer("OrderNotified", {"detail": serializers.CharField()})
    )
    @action(detail=True, methods=["post"])
    def notify(self, request, *args, **kwargs):
        """Send a status message again (the email, and an SMS where the customer asked for them), when it is true."""
        data = OrderNotifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order, kind = self.order(), data.validated_data["kind"]
        context = call(services.renotify, order, kind)
        self.log("order.notified", order, details={"kind": kind})
        return Response({"detail": f"Sent again: {context}."})

    @extend_schema(
        request=OrderPaymentLinkSerializer,
        responses=inline_serializer(
            "OrderPaymentLinkSent", {"detail": serializers.CharField(), "url": serializers.CharField(allow_blank=True)}
        ),
    )
    @action(detail=True, methods=["post"], url_path="payment-link")
    def payment_link(self, request, *args, **kwargs):
        """A staff order's Razorpay Payment Link: sent (made once; then the same link again), or cancelled (the next
        one sent is new). 503 while Razorpay cannot be reached."""
        data = OrderPaymentLinkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = self.order()
        if order.status != Order.Status.PENDING or order.placed_at or order.is_cod:
            raise refused(f"Order {order.number} is not waiting for an online payment.")
        try:
            if data.validated_data["action"] == "cancel":
                payment = payments.cancel_payment_link(order)
                self.log("order.payment_link_cancelled", order, details={"payment": payment.pk})
                return Response({"detail": "The payment link is cancelled.", "url": ""})
            payment = payments.send_payment_link(order)
        except payments.Unavailable as error:
            raise Unavailable(str(error)) from error
        except ValueError as error:
            raise refused(error) from error
        self.log("order.payment_link_sent", order, details={"payment": payment.pk})
        return Response({"detail": "Emailed to the customer.", "url": payment.payment_link_url})

    @extend_schema(
        request=OrderOfflinePaymentSerializer,
        responses={201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    @action(detail=True, methods=["post"], url_path="offline-payment")
    def offline_payment(self, request, *args, **kwargs):
        """A payment received by transfer or UPI: staff.approvals "order.offline_payment" (above your limit, or a ₹0
        order, FINANCE approves)."""
        data = OrderOfflinePaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        change_request, created = approvals.ask(
            "order.offline_payment",
            maker=self.human(),
            target=self.order().number,
            payload={"reference": data.validated_data["reference"]},
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        response = accepted(change_request, self)
        if created and response.status_code == status.HTTP_200_OK:
            response.status_code = status.HTTP_201_CREATED
        return response

    @extend_schema(
        request=OrderRefundAskSerializer,
        responses={201: OrderRefundAskedSerializer, 202: OrderRefundAskedSerializer},
        parameters=[IDEMPOTENCY],
    )
    @action(detail=True, methods=["post"])
    def refunds(self, request, *args, **kwargs):
        """A refund: its lines with quantities (from 0) and the shipping, the copies back into stock or not, to the
        way it was paid (Razorpay, normal or optimum) or by bank or UPI (cash on delivery and transfers; an online
        payment with the customer's agreement), or a return's (`return`); not sent yet: cancelled and refunded in
        full. Through staff.approvals "order.refund": within your refund limit it runs at once (201), above it FINANCE
        approves (202). `warnings`: a payment older than 6 months."""
        data = OrderRefundAskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = self.order()
        payload = data.payload()
        change_request, created = approvals.ask(
            "order.refund",
            maker=self.human(),
            target=order.number,
            payload=payload,
            reason=data.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request=request,
        )
        body = {
            **ChangeRequestSerializer(change_request, context=self.get_serializer_context()).data,
            "warnings": refund_options(order)["warnings"],
        }
        if change_request.status == ChangeRequest.Status.FAILED:
            return Response(
                {**body, "detail": change_request.result.get("error", "")}, status=status.HTTP_400_BAD_REQUEST
            )
        if change_request.status == ChangeRequest.Status.PENDING:
            return Response(body, status=status.HTTP_202_ACCEPTED)
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=ReturnAskSerializer, responses={201: ReturnDetailSerializer})
    @action(detail=True, methods=["post"])
    def returns(self, request, *args, **kwargs):
        """A return asked for by staff for the customer (a delivered order; no window: the website's is
        SHOP_RETURN_DAYS)."""
        data = ReturnAskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        lines = [dict(line) for line in values["lines"]]
        back = call(
            services.request_return,
            self.order(),
            lines,
            values["reason"],
            values.get("note", ""),
            by=self.human(),
            request=request,
        )
        return Response(ReturnDetailSerializer(back).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None, responses={202: inline_serializer("OrderDocumentsQueued", {"detail": serializers.CharField()})}
    )
    @action(detail=True, methods=["post"], url_path="invoice/regenerate")
    def invoice_regenerate(self, request, *args, **kwargs):
        """Make what is missing of the order's invoice and credit notes (RUNBOOK's shell step, as a button): queued
        for the worker (202); refused while SELLER_* holds a placeholder, or when nothing is missing."""
        order = self.order()
        made = call(services.regenerate_documents, order)
        self.log("order.documents_regenerated", order, details={"documents": made})
        return Response({"detail": "Being made: the documents appear on the order within a minute."}, status=202)

    @extend_schema(request=None, responses=inline_serializer("OrderInvoiceSent", {"detail": serializers.CharField()}))
    @action(detail=True, methods=["post"], url_path="invoice/resend")
    def invoice_resend(self, request, *args, **kwargs):
        """Email the customer the invoice's link again (the order's page, where its PDF is)."""
        order = self.order()
        invoice = getattr(order, "invoice", None)
        if invoice is None or not invoice.pdf:
            raise refused(f"Order {order.number} has no invoice yet: make it first.")
        services.notify(order, "invoice", sms=False, invoice=invoice)
        self.log("order.invoice_sent", order, details={"invoice": invoice.number})
        return Response({"detail": "Sent to the customer's address."})


def ask_staff_order(view, request, data, quote=None):
    """A staff order through staff.approvals "order.staff_discount" (made at once within the maker's discount limit,
    else a 202 and its change request), its lines checked first: a second person is never asked for an order that
    could not be made."""
    from allauth.account.models import EmailAddress

    email = data["email"].lower()
    confirmed = EmailAddress.objects.filter(email__iexact=email, verified=True).values_list("user", flat=True)
    address = {name: str(value) for name, value in data["address"].items()}
    payload = {
        "channel": data.get("channel", "school"),
        "lines": data["lines"],
        "discount": str(data.get("discount") or 0),
        "shipping": None if data.get("shipping") is None else str(data["shipping"]),
        "send_link": data.get("send_link", True),
        "user": confirmed.first(),
        "quote": quote.pk if quote else None,
        "customer": {"email": email, "address": address, "note": data.get("note", "")},
    }
    check_lines(payload, email, address)
    change_request, created = approvals.ask(
        "order.staff_discount",
        maker=view.human(),
        target=None,
        payload=payload,
        reason=data["reason"],
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request=request,
    )
    response = accepted(change_request, view)
    if created and response.status_code == status.HTTP_200_OK:
        response.status_code = status.HTTP_201_CREATED
    return response


def check_lines(payload, email, address):
    """What the order could not be made with, said before a second person is asked: sold out, off sale, a course
    without an account."""
    from .cart import Line, price

    products = Product.objects.in_bulk([line["product"] for line in payload["lines"]], field_name="slug")
    lines = [Line(products[line["product"]], line["quantity"]) for line in payload["lines"]]
    if problems := price(lines, state=address["state"], email=email).problems():
        raise serializers.ValidationError({"lines": problems})
    if payload["user"] is None and any(line.product.has_digital for line in lines):
        raise serializers.ValidationError(
            {"email": ["A course opens in an account: give the address of the customer's account."]}
        )


def pdf(content, name):
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="ExamLeaf-{name}.pdf"'
    return response


pick_lines = invoices.books_of  # the books to pick for an order, each once with its copies


def packing_row(order):
    lines = pick_lines(order)
    weights = [line["product"].weight_grams * line["quantity"] for line in lines]
    address = order.shipping_address or {}
    return {
        "number": order.number,
        "placed_at": order.placed_at,
        "payment_method": order.payment_method,
        "is_cod": order.is_cod,
        "total": order.total.amount,
        "risk_bucket": order.risk_bucket,
        "tags": sorted(tag.name for tag in order.tags.all()),
        "destination": ", ".join(
            str(address.get(name, "")) for name in ("city", "district", "pin") if address.get(name)
        ),
        "weight_g": sum(weights) + settings.SHIPPING_PACKING_GRAMS if all(weights) else None,
        "pick": [
            {"title": line["product"].title, "isbn": line["product"].isbn, "quantity": line["quantity"]}
            for line in lines
        ],
    }


class ReturnFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ReturnRequest.Status.choices)
    open = django_filters.BooleanFilter(method="filter_open", help_text="true: not decided, received or inspected yet")
    order = django_filters.CharFilter(field_name="order__number", lookup_expr="iexact")

    class Meta:
        model = ReturnRequest
        fields = ["reason", "by_customer"]

    def filter_open(self, queryset, name, value):
        return (
            queryset.filter(status__in=ReturnRequest.OPEN) if value else queryset.exclude(status__in=ReturnRequest.OPEN)
        )


class ReturnViewSet(OrdersView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Returns: asked for (by the customer on the website, or staff), decided (staff.handle_return), received and
    inspected (staff.receive_return: the packing room), then refunded through the order's refunds/ naming it."""

    queryset = ReturnRequest.objects.select_related("order").prefetch_related("order__items")
    filterset_class = ReturnFilter
    serializer_class = ReturnRowSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "photo"], "shop.view_returnrequest"),
        **dict.fromkeys(["approve", "decline", "label"], "staff.handle_return"),
        **dict.fromkeys(["receive", "inspect", "photos"], "staff.receive_return"),
    }

    def get_serializer_class(self):
        return ReturnRowSerializer if self.action == "list" else ReturnDetailSerializer

    def moved(self, function, *args, **kwargs):
        back = self.get_object()
        try:
            back = function(back, *args, by=self.human(), request=self.request, **kwargs)
        except TransitionNotAllowed as error:
            raise refused(f"Return {back.number} is {back.get_status_display()}: not possible now.") from error
        except services.ShopError as error:
            raise refused(error) from error
        return Response(ReturnDetailSerializer(ReturnRequest.objects.select_related("order").get(pk=back.pk)).data)

    @extend_schema(request=None, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        """Approved: the customer is told how to send it back."""
        return self.moved(services.decide_return, True)

    @extend_schema(request=ReturnDeclineSerializer, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request, *args, **kwargs):
        """Declined, with the reason the customer is told."""
        data = ReturnDeclineSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.moved(services.decide_return, False, data.validated_data["note"])

    @extend_schema(request=ReturnLabelSerializer, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"])
    def label(self, request, *args, **kwargs):
        """The return label sent: the courier and the AWB the customer hands the parcel over with."""
        data = ReturnLabelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.moved(services.send_return_label, data.validated_data["courier"], data.validated_data["awb"])

    @extend_schema(request=None, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request, *args, **kwargs):
        """The parcel is back with us."""
        return self.moved(services.receive_return)

    @extend_schema(request=ReturnInspectSerializer, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"])
    def inspect(self, request, *args, **kwargs):
        """Inspected: back into stock (its copies added, the return the reason) or damaged."""
        data = ReturnInspectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.moved(services.inspect_return, data.validated_data["outcome"] == "restocked")

    @extend_schema(request={"multipart/form-data": ReturnPhotoSerializer}, responses=ReturnDetailSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def photos(self, request, *args, **kwargs):
        """A photograph of what came back (5 at most; the private storage)."""
        data = ReturnPhotoSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.moved(services.add_return_photo, data.validated_data["photo"])

    @extend_schema(
        responses={(200, "image/*"): OpenApiTypes.BINARY},
        parameters=[OpenApiParameter("index", int, OpenApiParameter.PATH)],
    )
    @action(detail=True, url_path=r"photos/(?P<index>\d+)", content_negotiation_class=AnyAccept)
    def photo(self, request, index, *args, **kwargs):
        """One of its photographs (by its place, from 0)."""
        back = self.get_object()
        if int(index) >= len(back.photos):
            raise Http404
        try:
            return FileResponse(default_storage.open(back.photos[int(index)], "rb"))
        except OSError as error:
            raise Http404 from error


class RefundViewSet(OrdersView, viewsets.GenericViewSet):
    """A refund by bank or UPI: its payee shown to FINANCE with a reason (logged, re-authenticated, limited), and
    marked paid with the transfer's UTR (the refund processed, the credit note made, the customer told; once)."""

    queryset = Refund.objects.select_related("order", "payment")
    serializer_class = OrderRefundSerializer
    permissions = {"mark_paid": "staff.approve_refund", "payee": "staff.approve_refund"}
    throttle_scopes = {"mark_paid": "staff_money", "payee": "staff_reveal"}

    @extend_schema(request=RefundMarkPaidSerializer, responses=OrderRefundSerializer)
    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, *args, **kwargs):
        data = RefundMarkPaidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        refund = call(
            services.mark_bank_refund_paid, self.get_object(), data.validated_data["utr"], self.human(), request
        )
        return Response(OrderRefundSerializer(refund).data)

    @extend_schema(
        request=inline_serializer("RefundPayeeReason", {"reason": serializers.CharField(max_length=500)}),
        responses=RefundPayeeSerializer,
    )
    @action(detail=True, methods=["post"])
    def payee(self, request, *args, **kwargs):
        """The customer's bank account or UPI ID, for the transfer: a reason, logged (sensitive_read)."""
        import json

        from integrations.crypto import decrypt

        refund, reason = self.get_object(), str(request.data.get("reason", "")).strip()
        if not reason:
            raise serializers.ValidationError({"reason": ["Say why: it is kept in the audit log."]})
        if refund.method != Refund.Method.BANK or not refund.payee:
            raise refused(f"Refund #{refund.pk} goes back the way it was paid: there is no account to show.")
        details = {
            "what": "refund payee",
            "refund": refund.pk,
            "child": bool(refund.order.user and refund.order.user.is_minor),
        }
        audit.record("sensitive_read", request=request, target=refund.order, reason=reason[:500], details=details)
        return Response(RefundPayeeSerializer(json.loads(decrypt(refund.payee))).data)


class QuoteRowSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    copies = serializers.IntegerField(read_only=True)
    order = serializers.CharField(source="order.number", read_only=True, allow_null=True)
    email = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    valid_until = serializers.DateField(read_only=True, allow_null=True)
    has_quotation = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRequest
        fields = [
            *["id", "number", "school", "contact_name", "email", "phone", "gstin", "delivery_pin", "copies", "status"],
            *["discount_percent", "shipping_fee", "quoted_at", "valid_until", "has_quotation", "order", "created"],
        ]
        read_only_fields = fields

    def get_email(self, quote) -> str:
        return mask_email(quote.email)

    def get_phone(self, quote) -> str:
        return mask_phone(quote.phone)

    def get_has_quotation(self, quote) -> bool:
        return bool(quote.quotation)


class QuoteDetailSerializer(QuoteRowSerializer):
    items = serializers.ListField(child=serializers.DictField(), read_only=True, help_text="product, title, quantity")
    note = serializers.CharField(read_only=True)
    waiting = serializers.SerializerMethodField(help_text="a conversion waiting for approval: its change request")

    class Meta(QuoteRowSerializer.Meta):
        fields = [*QuoteRowSerializer.Meta.fields, "items", "note", "waiting"]
        read_only_fields = fields

    def get_waiting(self, quote) -> int | None:
        return waiting_conversion(quote)


def waiting_conversion(quote):
    """The change request that would make the quote's order, while it waits (pending or approved), or None."""
    open_ = [ChangeRequest.Status.PENDING, ChangeRequest.Status.APPROVED]
    rows = ChangeRequest.objects.filter(action="order.staff_discount", status__in=open_, payload__quote=quote.pk)
    return rows.values_list("pk", flat=True).first()


class QuoteFilter(django_filters.FilterSet):
    class Meta:
        model = QuoteRequest
        fields = ["status"]


class QuoteViewSet(OrdersView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Schools' and booksellers' quotation requests (the website's form), and their conversion to a staff order:
    the quote's books, its discount and shipping, the address given; once (the quote keeps its order)."""

    queryset = QuoteRequest.objects.select_related("order")
    filterset_class = QuoteFilter
    serializer_class = QuoteRowSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "quotation"], "shop.view_quoterequest"),
        "convert": "shop.change_quoterequest",
    }
    throttle_scopes = {"convert": "staff_money"}

    def get_serializer_class(self):
        return QuoteRowSerializer if self.action == "list" else QuoteDetailSerializer

    @extend_schema(responses=PDF)
    @action(detail=True, content_negotiation_class=AnyAccept)
    def quotation(self, request, *args, **kwargs):
        """The quotation's PDF, once made (the admin's "Make the quotation PDF")."""
        quote = self.get_object()
        if not quote.quotation:
            raise Http404
        try:
            return FileResponse(quote.quotation.open("rb"), as_attachment=True, filename=f"ExamLeaf-{quote.number}.pdf")
        except OSError as error:
            raise Http404 from error

    @extend_schema(
        request=QuoteConvertSerializer,
        responses={201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    @action(detail=True, methods=["post"])
    def convert(self, request, *args, **kwargs):
        """A staff order from the quote: its books (at today's prices, with the offers), its discount and shipping,
        the address given; through the staff order's approval. Refused once it has an order, or one waits."""
        quote = self.get_object()
        if quote.order_id:
            raise refused(f"Quotation {quote.number} is order {quote.order.number} already.")
        if pending := waiting_conversion(quote):
            raise refused(f"Quotation {quote.number} waits for approval as change request #{pending}.")
        data = QuoteConvertSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        slugs = [item["product"] for item in quote.items]
        products = Product.objects.in_bulk(slugs, field_name="slug")
        for old in SlugHistory.objects.filter(slug__in=set(slugs) - products.keys()).select_related("product"):
            products[old.slug] = old.product  # renamed since the request
        lines = [
            {"product": products[item["product"]].slug, "quantity": item["quantity"]}
            for item in quote.items
            if item["product"] in products
        ]
        if len(lines) != len(quote.items) or not all(products[item["product"]].is_active for item in quote.items):
            raise refused("A book of the quote is no longer on sale: make the order by hand (orders/new).")
        books = sum((products[item["product"]].price.amount * item["quantity"] for item in quote.items), Decimal(0))
        order = {
            "channel": "school",
            "lines": lines,
            "email": values.get("email") or quote.email,
            "address": values["address"],
            "discount": (books * quote.discount_percent / 100).quantize(Decimal("0.01")),
            "shipping": quote.shipping_fee,
            "send_link": values["send_link"],
            "note": values.get("note", ""),
            "reason": values["reason"],
        }
        return ask_staff_order(self, request, order, quote=quote)


router = SimpleRouter()
router.register("returns", ReturnViewSet, basename="return")
router.register("refunds", RefundViewSet, basename="refund")
router.register("quotes", QuoteViewSet, basename="quote")
router.register("", OrderViewSet, basename="order")
app_name = "orders"
urlpatterns = router.urls  # under /api/v1/staff/orders/ (staff/urls.py): returns, refunds and quotes before numbers
