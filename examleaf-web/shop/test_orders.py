"""Checkout, stock, cash on delivery, the order state machine, cancellation and refunds, invoices, guest lookup,
the session cart, and account deletion. The website's pages do these through the API (examleaf-frontend), as here."""

from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from celery.exceptions import Retry
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django_fsm import TransitionNotAllowed
from razorpay.errors import BadRequestError
from rest_framework.test import APIClient

from accounts.factories import PASSWORD, UserFactory
from accounts.models import DeletionRequest, User
from accounts.test_export_and_signup import signup
from accounts.test_security import confirm_own_address
from shop import invoices, payments, services, tasks
from shop.factories import (
    ADDRESS,
    ProductFactory,
    ShippingRateFactory,
    captured,
    make_order,
    post_webhook,
    verified_user,
)
from shop.models import Address, BundleItem, Cart, CreditNote, Invoice, Order, Payment, Product, Refund, WebhookEvent
from shop.test_api import checkout as account_checkout
from shop.test_api import customer

pytestmark = pytest.mark.django_db
GUEST = {
    "email": "guest@example.com",
    "shipping_address": {**ADDRESS, "line1": "House 4", "phone": "98640 12345"},
    "payment_method": "razorpay",
}


def add_to_cart(client, product, quantity=1):
    """The website's cart: this browser's session, through the API."""
    data = {"product": product.slug, "quantity": quantity}
    return client.post("/api/v1/cart/items/", data, content_type="application/json")


def check_out(client, data):
    return client.post("/api/v1/orders/", data, content_type="application/json")


def test_guest_checkout_checks_email_pin_and_mobile_then_makes_a_pending_order(client):
    product = ProductFactory(price=299)
    add_to_cart(client, product, 2)
    address = {**GUEST["shipping_address"], "pin": "012345", "phone": "12345"}
    bad = check_out(client, {**GUEST, "email": "x", "shipping_address": address}).json()
    assert set(bad) == {"email", "shipping_address"} and set(bad["shipping_address"]) == {"pin", "phone"}
    assert not Order.objects.exists()
    response = check_out(client, GUEST)
    order = Order.objects.get()
    assert response.status_code == 201 and response.json()["number"] == order.number
    assert order.status == Order.Status.PENDING and not order.placed_at and order.email == "guest@example.com"
    assert order.shipping_address["pin"] == "781001" and order.shipping_address["phone"] == "+919864012345"
    assert order.items.get().quantity == 2 and order.total.amount == Decimal("598.00")


def test_checkout_charges_todays_price_not_the_carts(client, rzp):
    product = ProductFactory(price=299)
    add_to_cart(client, product)
    Product.objects.filter(pk=product.pk).update(price=Decimal("319.00"))  # changed while the cart page was open
    check_out(client, GUEST)
    order = Order.objects.get()
    assert order.items.get().unit_price.amount == Decimal("319.00") and order.total.amount == Decimal("319.00")
    start = client.post(f"/api/v1/orders/t/{order.token}/payment/").json()  # the pay page's Checkout options
    assert start["amount"] == 31900 and rzp.order.create.call_args.args[0]["amount"] == 31900


def test_stock_is_checked_at_checkout_and_never_goes_negative(client):
    product = ProductFactory(stock=1)
    add_to_cart(client, product, 3)
    response = check_out(client, GUEST)
    assert response.status_code == 400 and "Only 1 copy of" in response.text and not Order.objects.exists()
    first, second = make_order((product, 1)), make_order((product, 1))
    services.reserve_stock(first)
    with pytest.raises(services.OutOfStock):
        services.reserve_stock(second)
    product.refresh_from_db()
    assert product.stock == 0


def test_a_bundle_sells_its_books_copies():
    papers, solutions = ProductFactory(stock=4), ProductFactory(stock=2)
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, stock=0)
    BundleItem.objects.create(bundle=bundle, product=papers)
    BundleItem.objects.create(bundle=bundle, product=solutions)
    assert bundle.available == 2
    order = make_order((bundle, 2))
    services.reserve_stock(order)
    order.save()
    papers.refresh_from_db()
    solutions.refresh_from_db()
    assert (papers.stock, solutions.stock) == (2, 0)
    services.cancel_order(order, "test")
    papers.refresh_from_db()
    assert papers.stock == 4


def test_cash_on_delivery(settings, commit):
    settings.SHOP_COD_ENABLED = True
    product, api = ProductFactory(stock=2), APIClient()
    customer(api)  # an account with a confirmed address (M8)
    add_to_cart(api, product)
    with commit():
        response = account_checkout(api, "cod")  # placed at once
    order = Order.objects.get()
    assert response.status_code == 201 and response.json()["number"] == order.number
    product.refresh_from_db()
    assert order.placed_at and order.status_label == "placed (pay on delivery)" and product.stock == 1
    assert (
        mail.outbox[0].subject == f"[ExamLeaf] Order {order.number} confirmed"
        and "pay on delivery" in mail.outbox[0].body
    )
    assert not Cart.objects.exists()
    with commit():
        services.pack_order(order)
        services.ship_order(order, "India Post", "EA123456789IN")
        services.deliver_order(order)
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED and order.payments.get().status == Payment.Status.CAPTURED
    assert order.invoice.pdf  # made at dispatch for cash on delivery


def test_state_machine_guards():
    order = make_order((ProductFactory(), 1))
    for step in (order.pack, order.ship, order.deliver, order.mark_refunded):
        with pytest.raises(TransitionNotAllowed):
            step()
    with pytest.raises(AttributeError):
        order.status = Order.Status.PAID  # only through transitions
    order.pay()
    order.pack()
    order.ship()
    with pytest.raises(TransitionNotAllowed):
        order.cancel()  # shipped: refund instead
    payment = order.payments.get()
    with pytest.raises(TransitionNotAllowed):
        payment.refund()  # never captured


def test_customer_cancels_a_paid_order_and_is_refunded(client, rzp, commit):
    api = APIClient()
    user = customer(api)
    product = ProductFactory(stock=5)
    order = make_order((product, 2), user=user, email=user.email)
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    assert [o["number"] for o in api.get("/api/v1/orders/").json()["results"]] == [order.number]  # My orders
    with commit():
        response = api.post(f"/api/v1/orders/{order.number}/cancel/")
    order.refresh_from_db()
    product.refresh_from_db()
    assert response.status_code == 200 and product.stock == 5
    assert order.status == Order.Status.REFUNDED and order.payments.get().status == Payment.Status.REFUNDED
    rzp.payment.refund.assert_called_once()
    assert rzp.payment.refund.call_args.args[:2] == (
        f"pay_{order.pk}",
        {
            "amount": 59800,
            "speed": "normal",
            "receipt": f"refund-{order.refunds.get().pk}",
            "notes": {"order": order.number, "refund_id": str(order.refunds.get().pk)},
        },
    )
    subjects = [m.subject for m in mail.outbox]
    assert subjects[-2:] == [
        f"[ExamLeaf] Order {order.number} cancelled",
        f"[ExamLeaf] Refund for order {order.number}",
    ]
    labels = [label for label, when in order.timeline()]
    assert labels == ["ordered", "paid", "cancelled", "refunded"]
    assert api.post(f"/api/v1/orders/{order.number}/cancel/").status_code == 400  # too late: nothing
    assert order.refunds.count() == 1


def test_refund_is_retried_while_razorpay_is_down_and_stops_when_refused(rzp, commit):
    order = make_order((ProductFactory(), 1))
    services.record_capture(captured(order))
    rzp.payment.refund.side_effect = requests.ConnectionError
    with commit():  # the task asks Celery to try again later (logged here: eager tasks raise Retry)
        services.cancel_order(order, "test")
    refund = order.refunds.get()
    assert refund.status == Refund.Status.PENDING and rzp.payment.refund.call_count == 1
    with pytest.raises(Retry):
        tasks.refund_payment.delay(refund.pk)
    rzp.payment.refund.side_effect = BadRequestError("The payment has been fully refunded already")
    tasks.refund_payment.delay(refund.pk)
    refund.refresh_from_db()
    assert refund.status == Refund.Status.FAILED and "fully refunded" in refund.error


@pytest.mark.real_pdf
def test_invoice_and_credit_note_are_pdfs_with_gst_columns_even_at_zero(rzp, settings, commit, real_seller):
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("WeasyPrint's system libraries (Pango) are not installed")
    order = make_order((ProductFactory(price=299), 2), state="DL")
    services.record_capture(captured(order))
    tasks.generate_invoice(order.pk)
    invoice = Invoice.objects.get()
    year = invoice.financial_year.removeprefix("T")
    assert invoice.number == f"T/{year}/00001" and invoice.is_test  # Razorpay test keys: the test series
    assert invoice.pdf.read().startswith(b"%PDF")
    context = invoices.context(invoice)
    assert context["title"] == "Bill of supply" and not context["intra_state"]  # Delhi: IGST at 0 %
    assert context["lines"][0]["taxable"] == Decimal("598.00") and context["lines"][0]["igst"] == 0
    with commit():
        services.cancel_order(order, "Changed my mind.")
    assert CreditNote.objects.get().pdf.read().startswith(b"%PDF")
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # live: the real series starts at 00001
    second = make_order((ProductFactory(price=100, gst_rate=12), 1))
    services.record_capture(captured(second))
    tasks.generate_invoice(second.pk)
    line = invoices.context(second.invoice)["lines"][0]
    assert second.invoice.number == f"EL/{year}/00001" and len(second.invoice.number) == 16
    assert invoices.context(second.invoice)["title"] == "Tax invoice"
    assert (line["taxable"], line["cgst"], line["sgst"]) == (Decimal("89.29"), Decimal("5.36"), Decimal("5.35"))


def test_invoice_link_appears_once_the_pdf_exists(rzp, monkeypatch):
    api = APIClient()
    user = customer(api)
    order = make_order((ProductFactory(), 1), user=user, email=user.email)
    url = f"/api/v1/orders/{order.number}/"
    monkeypatch.setattr(invoices, "render_pdf", lambda invoice: 1 / 0)
    services.record_capture(captured(order))
    with pytest.raises(ZeroDivisionError):  # called directly the task raises; a worker retries it
        tasks.generate_invoice(order.pk)
    assert api.get(url).json()["invoice"] is None and api.get(url + "invoice/").status_code == 404
    monkeypatch.setattr(invoices, "render_pdf", lambda invoice: b"%PDF-1.7 ok")
    tasks.generate_invoice(order.pk)
    assert api.get(url).json()["invoice"]["url"] == f"http://testserver{url}invoice/"
    response = api.get(url + "invoice/", HTTP_ACCEPT="application/pdf")
    assert response["Content-Type"] == "application/pdf" and Invoice.objects.count() == 1
    invoice = Invoice.objects.get()
    invoice.pdf.storage.delete(invoice.pdf.name)  # the file lost (or the storage down): a 404, not a server error
    assert api.get(url + "invoice/").status_code == 404


def test_refunds_of_invoiced_orders_get_credit_notes(client, rzp, commit, settings, real_seller):
    ShippingRateFactory()  # Assam: ₹40 below ₹499
    user = UserFactory()
    order = make_order((ProductFactory(price=299), 1), user=user, email=user.email)
    with commit():
        services.record_capture(captured(order))  # paid: the invoice is made
        services.pack_order(order)
        shipped = services.ship_order(order, "India Post", "EA123456789IN")
        services.refund_order(shipped, "Parcel refused.", amount=Decimal("299"))  # the books, not the shipping
    note = CreditNote.objects.get()
    year = note.financial_year.removeprefix("T")
    assert note.number == f"TC/{year}/00001" and note.invoice.order == order and note.pdf  # test keys: test series
    context = invoices.credit_note_context(note)
    assert (context["books_credit"], context["shipping_credit"], context["total_credit"]) == (299, 0, 299)
    api = APIClient()
    api.force_authenticate(verified_user(user.email))
    assert api.get(f"/api/v1/orders/{order.number}/").json()["credit_notes"][0]["number"] == note.number
    response = api.get(f"/api/v1/orders/{order.number}/credit-notes/{note.pk}/", HTTP_ACCEPT="application/pdf")
    assert response["Content-Type"] == "application/pdf"
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert note.number in client.get(reverse("admin:shop_order_change", args=[order.pk])).content.decode()
    assert note.number in client.get(reverse("admin:shop_creditnote_changelist")).content.decode()

    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    late = make_order((ProductFactory(price=299), 1), (ProductFactory(price=100, gst_rate=12), 1))
    services.record_capture(captured(late))  # its invoice task has not run yet
    with commit():
        services.cancel_order(late, "Changed my mind.")
    assert not CreditNote.objects.filter(refund__order=late).exists()  # nothing to credit before the invoice
    tasks.generate_invoice(late.pk)
    late_note = CreditNote.objects.get(refund__order=late)  # made once the invoice was
    assert late_note.number == f"CN/{year}/00001" and len(late_note.number) == 16
    context = invoices.credit_note_context(late_note)
    assert (context["books_credit"], context["shipping_credit"]) == (399, 40)  # in full: the shipping too
    assert [line["taxable"] for line in context["lines"]] == [Decimal("299.00"), Decimal("89.29")]
    assert context["tax_total"] == Decimal("10.71")


def test_guest_gets_the_orders_link_by_email_never_in_the_browser(client, commit):
    """The per-address limit: shop/test_api.py."""
    order = make_order((ProductFactory(), 1), email="guest@example.com")
    owned = make_order((ProductFactory(), 1), user=UserFactory(), email="owner@example.com")
    with commit():
        for number, email in [
            (order.number, "other@example.com"),
            (owned.number, "owner@example.com"),  # an account's order: its owner logs in
            (order.number.lower(), "GUEST@example.com"),
        ]:
            response = client.post("/api/v1/orders/lookup/", {"number": number, "email": email}, "application/json")
            assert response.json() == {"detail": "If an order matches, we have emailed you a link."}
    [sent] = mail.outbox  # the guest order only: owners of accounts log in
    assert sent.to == ["guest@example.com"] and order.get_link_url() in sent.body
    assert client.get(f"/api/v1/orders/{order.number}/").status_code in (401, 403)  # the browser that asked: nothing
    assert client.get(f"/api/v1/orders/t/{order.token}/").json()["shipping_address"]["name"] == "Rahul Das"


def test_guest_cart_joins_the_account_cart_at_log_in(client):
    user = verified_user("rahul@example.com")
    mine, both = ProductFactory(), ProductFactory()
    client.force_login(user)
    add_to_cart(client, both)
    client.logout()
    add_to_cart(client, mine, 2)
    add_to_cart(client, both)
    log_in = {"email": user.email, "password": PASSWORD}
    assert client.post("/_allauth/browser/v1/auth/login", log_in, "application/json").status_code == 200
    cart = Cart.objects.get()
    assert cart.user == user and {i.product_id: i.quantity for i in cart.items.all()} == {mine.pk: 2, both.pk: 2}


def test_guest_orders_join_the_account_of_their_address_once_it_is_confirmed(client):
    order = make_order((ProductFactory(), 1), email="Guest@Example.com")  # as typed at the checkout
    someone = make_order((ProductFactory(), 1), email="someone@example.com")
    signup(client, "guest@example.com")
    assert Order.objects.get(pk=order.pk).user is None  # not before the address is confirmed
    confirm_own_address(client, "guest@example.com")
    user = User.objects.get(email="guest@example.com")
    assert list(user.orders.all()) == [order] and Order.objects.get(pk=someone.pk).user is None
    assert [o["number"] for o in client.get("/api/v1/orders/").json()["results"]] == [order.number]  # My orders
    later = make_order((ProductFactory(), 1), email="GUEST@example.com")  # bought again without logging in
    client.logout()
    log_in = {"email": "guest@example.com", "password": "Brahmaputra-2027"}
    assert client.post("/_allauth/browser/v1/auth/login", log_in, "application/json").status_code == 200
    assert Order.objects.get(pk=later.pk).user == user


def test_account_deletion_removes_addresses_and_keeps_orders(client):
    user = UserFactory()
    Address.objects.create(user=user, **{**ADDRESS, "phone": "+919864012345"})
    order = make_order((ProductFactory(), 1), user=user, email=user.email)
    DeletionRequest.objects.create(user=user, due_at=timezone.now()).complete()
    order.refresh_from_db()
    assert not Address.objects.exists() and order.user == user and order.shipping_address["name"] == "Rahul Das"


def test_daily_clean_up(client, rzp, commit):
    unpaid, paid = make_order((ProductFactory(), 1)), make_order((ProductFactory(), 1))
    services.record_capture(captured(paid))  # its invoice task was lost (not run here)
    Order.objects.update(
        created=timezone.now() - services.UNPAID_ORDERS_EXPIRE, modified=timezone.now() - timedelta(hours=2)
    )
    WebhookEvent.objects.create(event_id="evt_old", digest="0" * 64, name="payment.captured")
    WebhookEvent.objects.update(received_at=timezone.now() - payments.WEBHOOK_MAX_AGE - timedelta(minutes=1))
    with commit():
        tasks.clean_up()
    unpaid.refresh_from_db()
    assert unpaid.status == Order.Status.CANCELLED and not mail.outbox  # expired quietly
    assert Invoice.objects.get().order == paid and paid.invoice.pdf
    assert not WebhookEvent.objects.exists()  # too old to be accepted again anyway


def test_the_order_confirmation_has_its_own_html_part(rzp, commit):
    order = make_order((ProductFactory(title="Physics Sample Papers"), 2))
    with commit():
        services.record_capture(captured(order))
    message = mail.outbox[-1]
    html = dict((mimetype, content) for content, mimetype in message.alternatives)["text/html"]
    assert f"Thank you for your order {order.number}" in message.body  # the text part stays the body
    assert "2 × Physics Sample Papers" in html and order.get_link_url() in html and "Open your order" in html
