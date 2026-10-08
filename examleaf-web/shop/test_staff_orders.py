"""Phase 6 E3: orders made by staff in the admin, Razorpay Payment Links (payment_link.paid, once), payments recorded
offline with their reference on the invoice, internal order notes, the customer page."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.core import mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from shop import invoices, payments, services, tasks
from shop.cart import Line
from shop.factories import ADDRESS, WEBHOOK_SECRET, ProductFactory, sign, verified_user
from shop.models import Address, Invoice, Order, OrderNote, Payment, QuoteRequest, Review

pytestmark = pytest.mark.django_db
LINK = {"id": "plink_1", "short_url": "https://rzp.io/i/abc"}


@pytest.fixture
def staff(client):
    user = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(user)
    return user


def staff_order(by, *lines, **fields):
    lines = lines or [Line(ProductFactory(), 2)]
    return services.create_staff_order(lines, by=by, email="school@example.com", address=ADDRESS, **fields)


def form_data(product, **changes):
    data = {
        **{f"lines-{name}": value for name, value in (("TOTAL_FORMS", 3), ("INITIAL_FORMS", 0))},
        "lines-0-product": product.pk,
        "lines-0-quantity": 30,
        "lines-1-product": product.pk,
        "lines-1-quantity": 10,
        "email": "teacher@example.com",
        "discount": "100",
        "send_link": "on",
        "note": "Phoned on Monday; purchase order 17.",
        **{f"address-{name}": value for name, value in ADDRESS.items()},
    }
    return {**data, **changes}


def test_staff_make_an_order_in_the_admin_and_email_its_payment_link(client, staff, rzp, commit):
    rzp.payment_link.create.return_value = LINK
    product = ProductFactory(title="Physics", price=Decimal("299.00"), stock=100)
    teacher = verified_user("teacher@example.com")
    assert client.get(reverse("admin:shop_order_add")).status_code == 200
    with commit():
        response = client.post(reverse("admin:shop_order_add"), form_data(product))
    order = Order.objects.get()
    assert response.status_code == 302 and response["Location"] == reverse("admin:shop_order_change", args=[order.pk])
    assert (order.created_by, order.user, order.items.get().quantity) == (staff, teacher, 40)  # the two rows merged
    assert order.savings == [("Discount", order.discount)] and order.total.amount == Decimal("11860.00")
    assert order.notes.get().author == staff and order.status == Order.Status.PENDING
    sent = rzp.payment_link.create.call_args.args[0]
    assert (sent["amount"], sent["reference_id"], sent["notify"]) == (
        1186000,
        order.number,
        {"sms": False, "email": False},
    )
    link = order.payments.get(razorpay_payment_link_id="plink_1")
    assert link.payment_link_url == LINK["short_url"] and order.payments.count() == 2  # the website's, and the link's
    assert (
        mail.outbox[-1].subject.endswith(f"Pay for order {order.number}") and LINK["short_url"] in mail.outbox[-1].body
    )
    with commit():  # the action again: the same link, emailed again
        client.post(reverse("admin:shop_order_changelist"), {"action": "payment_link", "_selected_action": [order.pk]})
    assert rzp.payment_link.create.call_count == 1 and len(mail.outbox) == 2
    too_many = form_data(product, **{"lines-0-quantity": 95})
    assert "Only 100 copies" in client.post(reverse("admin:shop_order_add"), too_many).content.decode()


def link_paid(client, order, event_id="evt_link", **changes):
    """Razorpay's payment_link.paid webhook for the order's link: the link made its own Razorpay order."""
    payment = {"id": "pay_link", "order_id": "order_link", "amount": int(order.total.amount * 100)}
    payment = {**payment, "currency": "INR", "status": "captured", **changes}
    body = json.dumps(
        {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {"entity": {"id": "plink_1", "status": "paid"}},
                "payment": {"entity": payment},
            },
        }
    )
    headers = {"HTTP_X_RAZORPAY_SIGNATURE": sign(body, WEBHOOK_SECRET), "HTTP_X_RAZORPAY_EVENT_ID": event_id}
    return client.post(reverse("shop:razorpay_webhook"), body, content_type="application/json", **headers)


def test_a_paid_payment_link_pays_the_order_once(client, rzp, commit):
    rzp.payment_link.create.return_value = LINK
    product = ProductFactory(stock=10)
    order = staff_order(UserFactory(is_staff=True), Line(product, 3))
    payments.send_payment_link(order)
    with commit():
        assert link_paid(client, order).status_code == 200
        assert link_paid(client, order, event_id="evt_again").status_code == 200  # the same body again: a replay
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.PAID and product.stock == 7
    link = order.payments.get(razorpay_payment_link_id="plink_1")
    assert (link.status, link.razorpay_order_id, link.razorpay_payment_id) == ("captured", "order_link", "pay_link")
    assert order.payments.get(razorpay_payment_link_id=None).status == Payment.Status.CREATED  # the website's: unused
    with commit():  # Razorpay's payment.captured for the same payment: nothing more happens
        services.record_capture({"id": "pay_link", "order_id": "order_link", "amount": 0, "currency": "INR"})
    assert Order.objects.get().status == Order.Status.PAID and not order.refunds.exists()


def test_an_offline_payment_pays_the_order_and_its_reference_is_on_the_invoice(client, staff, rzp, commit):
    order = staff_order(staff)
    url = reverse("admin:shop_order_changelist")
    page = client.post(url, {"action": "offline_payment", "_selected_action": [order.pk]}).content.decode()
    assert "Bank or UPI reference" in page
    with commit():
        client.post(
            url, {"action": "offline_payment", "_selected_action": [order.pk], "apply": "1", "reference": "UTR123"}
        )
    order.refresh_from_db()
    assert (order.status, order.payment_method, order.payment_reference) == ("paid", "offline", "UTR123")
    assert f"Thank you for your order {order.number}" in mail.outbox[-1].body
    html = render_to_string("shop/invoice.html", invoices.context(Invoice.objects.get(order=order)))
    assert "bank transfer or UPI to our account, reference UTR123" in html
    with pytest.raises(services.ShopError, match="not waiting"):
        services.record_offline_payment(order, "UTR124")


def test_staff_orders_wait_for_their_link_and_a_lost_link_webhook_is_found(rzp, commit):
    by = UserFactory(is_staff=True)
    waiting, old = staff_order(by), staff_order(by)
    Order.objects.filter(pk=waiting.pk).update(created=timezone.now() - timedelta(days=3))
    Order.objects.filter(pk=old.pk).update(created=timezone.now() - timedelta(days=17))
    rzp.payment_link.create.return_value = LINK
    payments.send_payment_link(old)
    rzp.payment_link.fetch.return_value = {"status": "paid", "payments": [{"payment_id": "pay_link"}]}
    rzp.payment.fetch.return_value = {
        **{"id": "pay_link", "order_id": "order_link", "currency": "INR", "status": "captured"},
        "amount": int(old.total.amount * 100),
    }
    with commit():
        tasks.clean_up()
    assert Order.objects.get(pk=waiting.pk).status == Order.Status.PENDING  # 16 days for staff orders
    assert Order.objects.get(pk=old.pk).status == Order.Status.PAID  # paid through its link: found, not cancelled


def test_notes_are_signed_and_the_customer_page_gathers_what_the_shop_knows(client, staff, rzp):
    buyer = verified_user("buyer@example.com")
    order = staff_order(staff, user=buyer)
    Address.objects.create(user=buyer, **{**ADDRESS, "city": "Jorhat"})
    Review.objects.create(product=order.items.get().product, user=buyer, rating=4)
    QuoteRequest.objects.create(
        school="Cotton School",
        contact_name="A",
        email="BUYER@example.com",
        phone="+919864012345",
        items=[],
        delivery_pin="781001",
    )
    prefixes = ["items", "discount_lines", "payments", "shipments", "refunds", "notes"]
    data = {f"{prefix}-{name}": "0" for prefix in prefixes for name in ("TOTAL_FORMS", "INITIAL_FORMS")}
    data.update({"notes-TOTAL_FORMS": "1", "notes-0-text": "Will collect from the office.", "notes-0-order": order.pk})
    response = client.post(reverse("admin:shop_order_change", args=[order.pk]), data)
    assert response.status_code == 302, response.content.decode()[:2000]
    note = OrderNote.objects.get(text="Will collect from the office.")
    assert note.author == staff and note.history.count() == 1
    page = client.get(reverse("admin:shop_customer", args=[buyer.pk])).content.decode()
    assert order.number in page and "Jorhat" in page and "4/5 for" in page and "Cotton School" in page
    clerk = UserFactory(is_staff=True)
    client.force_login(clerk)
    assert client.get(reverse("admin:shop_customer", args=[buyer.pk])).status_code == 403
    clerk.user_permissions.add(Permission.objects.get(codename="view_order"))
    page = client.get(reverse("admin:shop_customer", args=[buyer.pk])).content.decode()
    assert order.number in page and "Jorhat" not in page  # addresses need their own permission
