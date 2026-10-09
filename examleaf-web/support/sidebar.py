"""The sidebar beside a ticket (plan 5.14, research lms 4.5): the requester's account, orders with their Razorpay ids
and status, shipments, invoices and refunds, course entitlements (source, valid until), book codes redeemed, devices,
past tickets and consents, each part only for whoever may read it (its model's view_ permission, in their scope) and
masked as the customer record is (staff.api's UserViewSet). A part the reader may not see is null. The queries are
the same few however many rows (support/tests/test_query_counts.py)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django_fsm import can_proceed
from rest_framework import serializers

from staff.backends import scoped
from staff.privacy import mask_ip
from staff.serializers import CustomerSerializer

from .models import Ticket

User = get_user_model()
NORMAL_REFUND_DAYS = 180  # Razorpay refuses a normal refund of a payment older than 6 months (research lms 4.6)


class SidebarPaymentSerializer(serializers.Serializer):
    method = serializers.CharField()
    paid_with = serializers.CharField(help_text="Razorpay's method: upi, card, netbanking … (180 days)")
    status = serializers.CharField()
    amount = serializers.CharField()
    razorpay_order_id = serializers.CharField(allow_null=True)
    razorpay_payment_id = serializers.CharField(allow_null=True)
    created = serializers.DateTimeField()


class SidebarLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.CharField()
    discount = serializers.CharField(allow_null=True)


class SidebarRefundSerializer(serializers.Serializer):
    amount = serializers.CharField()
    status = serializers.CharField()
    razorpay_refund_id = serializers.CharField(allow_null=True)
    created = serializers.DateTimeField()


class OrderShipmentSerializer(serializers.Serializer):
    courier = serializers.CharField()
    tracking_number = serializers.CharField()
    tracking_url = serializers.CharField()
    shipped_at = serializers.DateTimeField()
    delivered_at = serializers.DateTimeField(allow_null=True)


class SidebarOrderSerializer(serializers.Serializer):
    number = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    total = serializers.CharField()
    payment_method = serializers.CharField()
    created = serializers.DateTimeField()
    placed_at = serializers.DateTimeField(allow_null=True)
    is_test = serializers.BooleanField()
    refund_mode = serializers.CharField(help_text="cancel: refunded in full with its cancellation; partial: shipped")
    refund_warning = serializers.CharField(help_text="why a refund through Razorpay may not go, or empty")
    linked = serializers.BooleanField(help_text="the ticket's own order")
    payments = SidebarPaymentSerializer(many=True)
    refunds = SidebarRefundSerializer(many=True)
    shipments = OrderShipmentSerializer(many=True)
    invoice = serializers.CharField(allow_null=True)
    credit_notes = serializers.ListField(child=serializers.CharField())
    items = SidebarLineSerializer(many=True)


class EntitlementRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject = serializers.CharField()
    source = serializers.CharField()
    reference = serializers.CharField()
    valid_until = serializers.DateField(allow_null=True)
    active = serializers.BooleanField()


class CodeRowSerializer(serializers.Serializer):
    batch = serializers.CharField()
    subject = serializers.CharField()
    redeemed_at = serializers.DateTimeField()


class DeviceRowSerializer(serializers.Serializer):
    kind = serializers.CharField(help_text="app (the reminders' phone) or browser (a signed-in session)")
    label = serializers.CharField()
    ip = serializers.CharField(help_text="masked")
    last_seen = serializers.DateTimeField(allow_null=True)


class PastTicketSerializer(serializers.Serializer):
    number = serializers.CharField()
    subject = serializers.CharField()
    category = serializers.CharField()
    status = serializers.CharField()
    received_at = serializers.DateTimeField()


class ConsentRowSerializer(serializers.Serializer):
    event = serializers.CharField()
    method = serializers.CharField()
    by_parent = serializers.BooleanField()
    verified_at = serializers.DateTimeField(allow_null=True)
    notice_version = serializers.CharField()
    created = serializers.DateTimeField()


class SidebarSerializer(serializers.Serializer):
    account = CustomerSerializer(allow_null=True)
    orders = SidebarOrderSerializer(many=True, allow_null=True)
    entitlements = EntitlementRowSerializer(many=True, allow_null=True)
    codes = CodeRowSerializer(many=True, allow_null=True)
    devices = DeviceRowSerializer(many=True, allow_null=True)
    tickets = PastTicketSerializer(many=True, allow_null=True)
    consents = ConsentRowSerializer(many=True, allow_null=True)


def money(value):
    return str(value.amount) if value is not None else None


def order_row(order, ticket):
    from shop.models import Order, Payment

    captured = [payment for payment in order.payments.all() if payment.status == Payment.Status.CAPTURED]
    online = [payment for payment in captured if payment.method == Order.Method.RAZORPAY]
    old = online and online[0].created < timezone.now() - timedelta(days=NORMAL_REFUND_DAYS)
    invoice = getattr(order, "invoice", None)
    return {
        "number": order.number,
        "status": order.status,
        "status_label": order.status_label,
        "total": money(order.total),
        "payment_method": order.payment_method,
        "created": order.created,
        "placed_at": order.placed_at,
        "is_test": order.is_test,
        "refund_mode": "cancel" if can_proceed(order.cancel) else "partial",
        "refund_warning": "Paid more than 6 months ago: Razorpay refuses a normal refund; refund by bank transfer."
        if old
        else "",
        "linked": order.pk == ticket.order_id,
        "payments": [
            {
                "method": payment.method,
                "paid_with": str((payment.raw_payload or {}).get("method") or ""),
                "status": payment.status,
                "amount": money(payment.amount),
                "razorpay_order_id": payment.razorpay_order_id,
                "razorpay_payment_id": payment.razorpay_payment_id,
                "created": payment.created,
            }
            for payment in order.payments.all()
        ],
        "refunds": [
            {
                "amount": money(refund.amount),
                "status": refund.status,
                "razorpay_refund_id": refund.razorpay_refund_id,
                "created": refund.created,
            }
            for refund in order.refunds.all()
        ],
        "shipments": [
            {
                "courier": shipment.courier,
                "tracking_number": shipment.tracking_number,
                "tracking_url": shipment.tracking_url
                or shipment.tracking_url_for(shipment.courier, shipment.tracking_number),
                "shipped_at": shipment.shipped_at,
                "delivered_at": shipment.delivered_at,
            }
            for shipment in order.shipments.all()
        ],
        "invoice": invoice.number if invoice else None,
        "credit_notes": [note.number for note in invoice.credit_notes.all()] if invoice else [],
        "items": [
            {
                "id": item.pk,
                "title": item.title,
                "quantity": item.quantity,
                "unit_price": money(item.unit_price),
                "discount": money(item.discount),
            }
            for item in order.items.all()
        ],
    }


def sidebar(ticket, reader):
    """The parts of the sidebar `reader` may see (None for the others)."""
    from learn.models import BookCode, Device, Entitlement

    from .services import requester_orders

    can = reader.has_perm
    found = dict.fromkeys(["account", "orders", "entitlements", "codes", "devices", "tickets", "consents"])
    account = None
    if ticket.user_id and can("accounts.view_user"):
        people = User.objects.filter(pk=ticket.user_id).select_related("board")
        people = people.prefetch_related("emailaddress_set", "consents", "deletion_requests")
        account = scoped(people, reader, "accounts.view_user").first()
    if account is not None:
        found["account"] = CustomerSerializer(account).data
        found["consents"] = list(
            account.consents.order_by("-created").values(
                "event", "method", "by_parent", "verified_at", "notice_version", "created"
            )
        )
        sessions = [
            {
                "kind": "browser",
                "label": row["user_agent"][:80],
                "ip": mask_ip(row["ip"]),
                "last_seen": row["last_seen_at"],
            }
            for row in account.usersession_set.order_by("-last_seen_at").values("ip", "user_agent", "last_seen_at")[:10]
        ]
        apps = [
            {
                "kind": "app",
                "label": device.get_platform_display() or "the app",
                "ip": "",
                "last_seen": device.last_seen,
            }
            for device in Device.objects.filter(user=account).order_by("-last_seen")[:10]
        ]
        found["devices"] = [*apps, *sessions]
    if can("shop.view_order"):
        orders = scoped(requester_orders(ticket), reader, "shop.view_order").select_related("invoice")
        orders = orders.prefetch_related("payments", "refunds", "shipments", "items", "invoice__credit_notes")
        found["orders"] = [order_row(order, ticket) for order in orders.order_by("-created", "-pk")[:10]]
    if ticket.user_id and can("learn.view_entitlement"):
        rows = scoped(Entitlement.objects.filter(user_id=ticket.user_id), reader, "learn.view_entitlement")
        today = timezone.localdate()
        found["entitlements"] = [
            {
                "id": row.pk,
                "subject": row.subject.name if row.subject_id else "every subject",
                "source": row.source,
                "reference": row.reference,
                "valid_until": row.valid_until,
                "active": row.valid_until is None or row.valid_until >= today,
            }
            for row in rows.select_related("subject").order_by("-created")[:20]
        ]
    if ticket.user_id and can("learn.view_bookcode"):
        codes = scoped(BookCode.objects.filter(redeemed_by_id=ticket.user_id), reader, "learn.view_bookcode")
        found["codes"] = [
            {"batch": code.batch, "subject": code.subject.name if code.subject_id else "every subject",
             "redeemed_at": code.redeemed_at}
            for code in codes.select_related("subject").order_by("-redeemed_at")[:20]
        ]  # fmt: skip
    same = Q(pk__in=[])
    if ticket.user_id:
        same |= Q(user_id=ticket.user_id)
    for name in ("requester_email_hash", "requester_phone_hash"):
        if value := getattr(ticket, name):
            same |= Q(**{name: value})
    past = scoped(Ticket.objects.filter(same), reader, "support.view_ticket").exclude(pk=ticket.pk)
    found["tickets"] = list(
        past.exclude(status=Ticket.Status.SPAM)
        .order_by("-received_at", "-pk")
        .values("number", "subject", "category", "status", "received_at")[:10]
    )
    return found
