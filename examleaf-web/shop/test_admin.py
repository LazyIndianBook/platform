"""Staff side: SALES and SUPPORT permissions, the order actions, the export, the dashboard and seed_shop."""

from io import StringIO

import pytest
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

pytestmark = pytest.mark.django_db
CHANGELIST = reverse("admin:shop_order_changelist")


def staff(role):
    user = UserFactory(is_staff=True)
    user.groups.set([Group.objects.get(name=role)])
    return user


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


def test_sales_packs_ships_and_delivers(client, paid, commit):
    client.force_login(staff(roles.SALES))
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
    sales = staff(roles.SALES)
    client.force_login(sales)
    assert "Reason" in act(client, "refund", [paid]).content.decode()
    with commit():
        act(client, "refund", [paid], apply="1", reason="Damaged in transit.")
    refund = Refund.objects.get()
    paid.refresh_from_db()
    assert refund.created_by == sales and refund.reason == "Damaged in transit."
    assert paid.status == Order.Status.REFUNDED and rzp.payment.refund.called  # paid, not shipped: cancelled too
    response = act(client, "refund", [paid], apply="1", reason="again")
    assert "Nothing refunded for" in response.content.decode() and Refund.objects.count() == 1


def test_partial_refund_of_a_refused_parcel(client, paid, rzp, commit):
    client.force_login(staff(roles.SALES))
    with commit():
        services.pack_order(paid)
        services.ship_order(paid, "India Post", "EA1IN")
        act(client, "refund", [paid], apply="1", reason="Parcel refused: books less shipping.", amount="259.00")
    paid.refresh_from_db()
    assert paid.refunds.get().amount.amount == 259 and rzp.payment.refund.call_args.args[1]["amount"] == 25900
    assert paid.status == Order.Status.REFUNDED


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
