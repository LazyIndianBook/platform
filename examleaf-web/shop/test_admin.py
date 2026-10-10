"""Staff side: SALES and SUPPORT permissions, the order actions (packing and shipping: staff.pack_order, ADMIN's in
the admin; refunds there: ADMIN's), the export, the dashboard and seed_shop."""

import time
from io import StringIO

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from accounts import roles
from accounts.factories import UserFactory
from shop import services
from shop.admin import OrderResource
from shop.factories import ProductFactory, captured, make_order
from shop.models import BundleItem, Coupon, Invoice, Order, Product, Refund, Shipment, ShippingRate
from staff.models import AuditEvent, ChangeRequest

pytestmark = pytest.mark.django_db
CHANGELIST = reverse("admin:shop_order_changelist")


def staff(role):
    user = UserFactory(is_staff=True)
    user.groups.set([Group.objects.get(name=role)])
    return user


def sign_in(client, user):
    """Signed in a moment ago: a refund (staff.approvals' "order.refund") steps up, here as in the panel."""
    client.force_login(user)
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": time.time()}]
    session.save()


@pytest.fixture
def paid(rzp):
    order = make_order((ProductFactory(stock=5), 1))
    services.record_capture(captured(order))
    return order


def act(client, action, orders, **data):
    return client.post(CHANGELIST, {"action": action, "_selected_action": [o.pk for o in orders], **data}, follow=True)


def test_support_sees_orders_but_cannot_change_them(client, paid):
    client.force_login(staff(roles.SUPPORT))
    assert client.get(CHANGELIST).status_code == 200
    assert client.get(reverse("admin:shop_order_change", args=[paid.pk])).status_code == 200
    assert client.get(reverse("admin:shop_product_add")).status_code == 403
    act(client, "mark_packed", [paid])
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID  # the action is not offered to view-only staff
    invoice = Invoice.objects.create(order=paid, number="EL/2026-27/00001", financial_year="2026-27", serial=1)
    pdf = reverse("admin:shop_invoice_pdf", args=[invoice.pk])
    assert client.get(pdf).status_code == 404  # no PDF yet, but allowed
    client.force_login(staff(roles.CONTENT_EDITOR))
    assert client.get(pdf).status_code == 403  # staff who may not view invoices


def test_packing_shipping_and_delivery_need_the_packing_permission(client, paid, commit):
    client.force_login(staff(roles.SALES))  # SALES does not pack or ship (plan 4.1): PACKER's, and ADMIN's here
    act(client, "mark_packed", [paid])
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID
    client.force_login(staff(roles.ADMIN))
    act(client, "mark_packed", [paid])
    page = act(client, "mark_shipped", [paid]).content.decode()  # first the courier form
    assert "Tracking number" in page and paid.number in page
    with commit():
        response = act(
            client,
            "mark_shipped",
            [paid],
            apply="1",
            **{
                "ship-TOTAL_FORMS": "1",
                "ship-INITIAL_FORMS": "1",
                "ship-0-order": paid.pk,
                "ship-0-courier": "India Post",
                "ship-0-tracking_number": "EA123456789IN",
                "ship-0-tracking_url": "https://www.indiapost.gov.in/",
            },
        )
    assert "Shipped (customer emailed the tracking number): 1 order(s)." in response.content.decode()
    assert Shipment.objects.get().tracking_number == "EA123456789IN"
    assert "EA123456789IN" in mail.outbox[-1].body and "is on its way" in mail.outbox[-1].subject
    with commit():
        act(client, "mark_delivered", [paid])
    paid.refresh_from_db()
    assert paid.status == Order.Status.DELIVERED and "delivered" in mail.outbox[-1].subject
    labels = [label for label, when in paid.timeline()]
    assert labels == ["ordered", "paid", "packed", "shipped", "delivered"]
    response = act(client, "mark_packed", [paid])  # a guarded transition: refused, with a message
    assert "Not possible for" in response.content.decode()


def test_refund_action_needs_a_reason_and_refunds_through_razorpay(client, paid, rzp, commit):
    sign_in(client, staff(roles.SALES))  # SALES asks for refunds in the panel, where FINANCE approves (plan 4.1)
    with commit():
        act(client, "refund", [paid], apply="1", reason="Damaged in transit.")
    assert not Refund.objects.exists()
    admin = staff(roles.ADMIN)
    sign_in(client, admin)
    assert "Reason" in act(client, "refund", [paid]).content.decode()
    with commit():
        act(client, "refund", [paid], apply="1", reason="Damaged in transit.")
    refund = Refund.objects.get()
    paid.refresh_from_db()
    assert refund.created_by == admin and refund.reason == "Damaged in transit."
    assert paid.status == Order.Status.REFUNDED and rzp.payment.refund.called  # paid, not shipped: cancelled too
    response = act(client, "refund", [paid], apply="1", reason="again")
    assert "Nothing refunded for" in response.content.decode() and Refund.objects.count() == 1


def test_partial_refund_of_a_refused_parcel(client, paid, rzp, commit):
    sign_in(client, staff(roles.ADMIN))
    with commit():
        services.pack_order(paid)
        services.ship_order(paid, "India Post", "EA1IN")
        act(client, "refund", [paid], apply="1", reason="Parcel refused: books less shipping.", amount="259.00")
    paid.refresh_from_db()
    assert paid.refunds.get().amount.amount == 259 and rzp.payment.refund.call_args.args[1]["amount"] == 25900
    assert paid.status == Order.Status.REFUNDED


def dear(rzp):
    """A paid order of ₹12,000: above ADMIN's refund limit (₹10,000) and SALES' (₹2,000)."""
    order = make_order((ProductFactory(stock=5, mrp=12_000, price=12_000), 1))
    services.record_capture(captured(order))
    return order


def test_a_refund_above_the_makers_limit_waits_for_finance_as_in_the_panel(client, rzp, commit):
    order = dear(rzp)
    admin = staff(roles.ADMIN)
    sign_in(client, admin)
    with commit():
        page = act(client, "refund", [order], apply="1", reason="Damaged in transit.").content.decode()
    change = ChangeRequest.objects.get()
    assert (change.action, change.status, change.maker, change.amount) == ("order.refund", "pending", admin, 12_000)
    assert f"change request #{change.pk}" in page and "above the limit of ₹10,000" in page
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and not Refund.objects.exists() and not rzp.payment.refund.called
    assert AuditEvent.objects.filter(action="order.refund.requested", actor_id=admin.pk).exists()


def test_cancelling_an_order_paid_online_is_its_refund_with_the_makers_limit(client, rzp, paid, commit):
    order = dear(rzp)
    sales = staff(roles.SALES)  # cancels and asks for refunds; ₹2,000 at once
    sign_in(client, sales)
    with commit():
        act(client, "cancel", [paid, order])
    paid.refresh_from_db()
    order.refresh_from_db()
    assert paid.status == Order.Status.REFUNDED and paid.refunds.get().created_by == sales  # within the limit
    assert (
        order.status == Order.Status.PAID and ChangeRequest.objects.get(status="pending").target_label == order.number
    )
    unpaid = make_order((ProductFactory(stock=5), 1))  # nothing paid online: cancelled at once, as before
    act(client, "cancel", [unpaid])
    unpaid.refresh_from_db()
    assert unpaid.status == Order.Status.CANCELLED


def test_packing_shipping_and_delivery_are_offered_only_with_the_packing_permission(client, paid):
    names = ["mark_packed", "mark_shipped", "mark_delivered"]
    for role in (roles.SALES, roles.SUPPORT):  # SALES changes orders but does not pack them (plan 4.1)
        client.force_login(staff(role))
        assert not any(f'value="{name}"' in client.get(CHANGELIST).content.decode() for name in names), role
        for name in names:
            act(client, name, [paid])
        paid.refresh_from_db()
        assert paid.status == Order.Status.PAID, role
    client.force_login(staff(roles.ADMIN))  # staff.pack_order: ADMIN's in the admin (PACKER's in the panel)
    assert all(f'value="{name}"' in client.get(CHANGELIST).content.decode() for name in names)


def test_export_has_one_row_per_order_with_the_address_for_the_admin_role_only(client, paid):
    data = OrderResource().export(Order.objects.all())
    row = dict(zip(data.headers, data[0], strict=True))
    assert row["number"] == paid.number and row["pin"] == "781001" and row["total"] == "299.00"
    assert row["books"].startswith("1 x Sample Papers") and data.xlsx[:2] == b"PK"  # XLSX is a zip
    call_command("bootstrap_roles", stdout=StringIO())  # as every deploy does: ADMIN gets shop.export_order
    client.force_login(staff(roles.SALES))
    assert client.get(reverse("admin:shop_order_export")).status_code == 403  # every customer's address: ADMIN only
    client.force_login(staff(roles.ADMIN))
    page = client.get(reverse("admin:shop_order_export")).content.decode()
    assert "xlsx" in page.lower() and "csv" in page.lower()


def test_dashboard_shows_orders_and_revenue(client, paid):
    client.force_login(staff(roles.SALES))
    page = client.get(reverse("admin:index")).content.decode()
    assert "<caption>Shop</caption>" in page and "₹299.00" in page and "1 order to pack" in page


def test_seed_shop_is_idempotent():
    call_command("seed_shop", stdout=StringIO())
    Product.objects.filter(slug="physics-sample-papers-2027").update(price=279)  # changed in the admin
    out = StringIO()
    call_command("seed_shop", stdout=out)
    assert "Nothing to create" in out.getvalue()
    assert Product.objects.count() == 9 and BundleItem.objects.count() == 2
    assert Coupon.objects.get().code == "WELCOME10" and ShippingRate.objects.count() == 3
    assert Product.objects.get(slug="physics-sample-papers-2027").price.amount == 279
    assert Product.objects.get(slug="physics-sample-papers-2027").cover.name == "products/physics.png"
