"""Checkout, stock, cash on delivery, the order state machine, cancellation and refunds, invoices, guest lookup,
the session cart, and account deletion."""

from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from allauth.account.models import EmailAddress
from celery.exceptions import Retry
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django_fsm import TransitionNotAllowed
from razorpay.errors import BadRequestError

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

pytestmark = pytest.mark.django_db
GUEST = {
    "email": "guest@example.com",
    "name": "Rahul Das",
    "phone": "98640 12345",
    "line1": "House 4",
    "city": "Guwahati",
    "district": "Kamrup Metro",
    "state": "AS",
    "pin": "781 001",
    "payment_method": "razorpay",
}


def test_guest_checkout_checks_email_pin_and_mobile_then_makes_a_pending_order(client):
    product = ProductFactory(price=299)
    client.post(reverse("shop:cart_add", args=[product.pk]), {"quantity": 2})
    bad = client.post(reverse("shop:checkout"), {**GUEST, "email": "x", "pin": "012345", "phone": "12345"})
    assert bad.context["form"].errors["email"] and not Order.objects.exists()
    assert bad.context["address_form"].errors == {
        "pin": ["Enter the 6-digit PIN code."],
        "phone": ["Enter a 10-digit Indian mobile number."],
    }
    empty = client.post(reverse("shop:checkout"), {"payment_method": "cod"}).text  # each problem named and linked
    assert '<a href="#id_name">Full name: Enter the name of the person who receives the parcel.</a>' in empty
    assert '<a href="#id_email">Email address: Enter your email address: the order&#x27;s emails go there.</a>' in empty
    assert '<a href="#id_payment_method_0">Payment: Choose one of the ways to pay shown.</a>' in empty  # a radio group
    assert 'href="#"' not in empty
    response = client.post(reverse("shop:checkout"), GUEST)
    order = Order.objects.get()
    assert response.url == reverse("shop:pay", args=[order.number])
    assert order.status == Order.Status.PENDING and not order.placed_at and order.email == "guest@example.com"
    assert order.shipping_address["pin"] == "781001" and order.shipping_address["phone"] == "+919864012345"
    assert order.items.get().quantity == 2 and order.total.amount == Decimal("598.00")


def test_logged_in_checkout_saves_the_address_once_and_offers_it_next_time(client):
    user = UserFactory()
    client.force_login(user)
    product = ProductFactory(stock=1)
    client.post(reverse("shop:cart_add", args=[product.pk]), {"quantity": 2})
    fields = {k: v for k, v in GUEST.items() if k != "email"}
    assert "Only 1 copy" in client.post(reverse("shop:checkout"), {**fields, "save_address": "on"}).content.decode()
    assert not Address.objects.exists()  # nothing saved for an order that was not made
    client.post(reverse("shop:cart"), {"action": "update", f"qty-{product.pk}": "1", "remove": "x"})
    client.post(reverse("shop:checkout"), {**fields, "save_address": "on"})
    address = Address.objects.get()
    assert address.user == user and address.is_default and Order.objects.get().email == user.email
    page = client.get(reverse("shop:checkout"))
    assert page.context["form"].fields["saved_address"].initial == address


def test_checkout_charges_todays_price_not_the_carts(client, rzp):
    product = ProductFactory(price=299)
    client.post(reverse("shop:cart_add", args=[product.pk]))
    Product.objects.filter(pk=product.pk).update(price=Decimal("319.00"))  # changed while the cart page was open
    client.post(reverse("shop:checkout"), GUEST)
    order = Order.objects.get()
    assert order.items.get().unit_price.amount == Decimal("319.00") and order.total.amount == Decimal("319.00")
    page = client.get(reverse("shop:pay", args=[order.number]))
    assert page.context["checkout"]["amount"] == 31900 and rzp.order.create.call_args.args[0]["amount"] == 31900


def test_stock_is_checked_at_checkout_and_never_goes_negative(client):
    product = ProductFactory(stock=1)
    client.post(reverse("shop:cart_add", args=[product.pk]), {"quantity": 3})
    response = client.post(reverse("shop:checkout"), GUEST)
    assert "Only 1 copy of" in response.content.decode() and not Order.objects.exists()
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


def test_cash_on_delivery(client, settings, commit):
    settings.SHOP_COD_ENABLED = True
    product = ProductFactory(stock=2)
    client.force_login(verified_user("rahul@example.com"))  # an account with a confirmed address (M8)
    client.post(reverse("shop:cart_add", args=[product.pk]))
    client.post(reverse("shop:checkout"), {**GUEST, "email": "", "payment_method": "cod"})
    order = Order.objects.get()
    with commit():
        response = client.post(reverse("shop:pay", args=[order.number]))
    assert response.url == reverse("shop:done", args=[order.number])
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.placed_at and order.status_label == "placed (pay on delivery)" and product.stock == 1
    assert (
        mail.outbox[0].subject == f"[ExamLeaf] Order {order.number} confirmed"
        and "pay on delivery" in mail.outbox[0].body
    )
    assert client.session["shop_cart_count"] == 0 and not Cart.objects.exists()
    with commit():
        services.pack_order(order)
        services.ship_order(order, "India Post", "EA123456789IN")
        services.deliver_order(order)
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED and order.payments.get().status == Payment.Status.CAPTURED
    assert order.invoice.pdf  # made at dispatch for cash on delivery


def test_cash_on_delivery_can_be_switched_off(client, settings):
    settings.SHOP_COD_ENABLED = False
    client.post(reverse("shop:cart_add", args=[ProductFactory().pk]))
    response = client.post(reverse("shop:checkout"), {**GUEST, "payment_method": "cod"})
    assert "payment_method" in response.context["form"].errors and not Order.objects.exists()


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
    user = UserFactory()
    product = ProductFactory(stock=5)
    order = make_order((product, 2), user=user, email=user.email)
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    client.force_login(user)
    assert order.number in client.get(reverse("shop:orders")).content.decode()
    with commit():
        response = client.post(reverse("shop:order_cancel", args=[order.number]), follow=True)
    order.refresh_from_db()
    product.refresh_from_db()
    assert "will be refunded" in response.content.decode() and product.stock == 5
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
    assert client.post(reverse("shop:order_cancel", args=[order.number])).status_code == 302  # too late: nothing
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


def test_invoice_link_appears_once_the_pdf_exists(client, rzp, monkeypatch):
    user = UserFactory()
    order = make_order((ProductFactory(), 1), user=user, email=user.email)
    client.force_login(user)
    monkeypatch.setattr(invoices, "render_pdf", lambda invoice: 1 / 0)
    services.record_capture(captured(order))
    with pytest.raises(ZeroDivisionError):  # called directly the task raises; a worker retries it
        tasks.generate_invoice(order.pk)
    page = client.get(order.get_absolute_url()).content.decode()
    assert (
        "invoice will appear here" in page
        and client.get(reverse("shop:invoice", args=[order.number])).status_code == 404
    )
    monkeypatch.setattr(invoices, "render_pdf", lambda invoice: b"%PDF-1.7 ok")
    tasks.generate_invoice(order.pk)
    assert "Download the invoice" in client.get(order.get_absolute_url()).content.decode()
    response = client.get(reverse("shop:invoice", args=[order.number]))
    assert response["Content-Type"] == "application/pdf" and Invoice.objects.count() == 1
    invoice = Invoice.objects.get()
    invoice.pdf.storage.delete(invoice.pdf.name)  # the file lost (or the storage down): a 404, not a server error
    assert client.get(reverse("shop:invoice", args=[order.number])).status_code == 404


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
    client.force_login(user)
    assert f"Credit note {note.number}" in client.get(order.get_absolute_url()).content.decode()
    response = client.get(reverse("shop:credit_note", args=[order.number, note.pk]))
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


def test_the_order_lookup_says_what_it_needs(client):
    page = client.post(reverse("shop:lookup"), {"number": "", "email": ""}).text  # as a browser sends it
    assert "Order number: Enter the order number from its email, such as EL-2026-000123." in page
    assert "Email address used for the order: Enter the email address you ordered with." in page
    assert "This field is required" not in page


def test_guest_gets_the_orders_link_by_email_never_in_the_browser(client, commit):
    order = make_order((ProductFactory(), 1), email="guest@example.com")
    owned = make_order((ProductFactory(), 1), user=UserFactory(), email="owner@example.com")
    assert client.get(order.get_absolute_url()).status_code == 404  # another browser
    with commit():
        for number, email in [
            (order.number, "other@example.com"),
            (owned.number, "owner@example.com"),  # an account's order: its owner logs in
            (order.number.lower(), "GUEST@example.com"),
        ]:
            response = client.post(reverse("shop:lookup"), {"number": number, "email": email})
            assert "If an order matches, we have emailed you a link." in response.text and "781001" not in response.text
    [sent] = mail.outbox  # the guest order only: owners of accounts log in
    assert sent.to == ["guest@example.com"] and order.get_link_url() in sent.body
    assert client.get(order.get_absolute_url()).status_code == 404  # the browser that asked got nothing
    page = client.get(order.get_link_url())
    assert page.status_code == 200 and "Rahul Das" in page.text and "Pay now" not in page.text  # read-only
    for _ in range(8):
        response = client.post(reverse("shop:lookup"), {"number": "EL-2026-999999", "email": "x@example.com"})
    assert response.status_code == 429  # 10 an hour from one address


def test_guest_cart_joins_the_account_cart_at_log_in(client):
    user = UserFactory()
    mine, both = ProductFactory(), ProductFactory()
    client.force_login(user)
    client.post(reverse("shop:cart_add", args=[both.pk]))
    client.logout()
    client.post(reverse("shop:cart_add", args=[mine.pk]), {"quantity": 2})
    client.post(reverse("shop:cart_add", args=[both.pk]))
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    client.post(reverse("account_login"), {"login": user.email, "password": PASSWORD})
    cart = Cart.objects.get()
    assert cart.user == user and {i.product_id: i.quantity for i in cart.items.all()} == {mine.pk: 2, both.pk: 2}
    assert client.session["shop_cart_count"] == 4


def test_guest_orders_join_the_account_of_their_address_once_it_is_confirmed(client):
    order = make_order((ProductFactory(), 1), email="Guest@Example.com")  # as typed at the checkout
    someone = make_order((ProductFactory(), 1), email="someone@example.com")
    signup(client, "guest@example.com")
    assert Order.objects.get(pk=order.pk).user is None  # not before the address is confirmed
    confirm_own_address(client, "guest@example.com")
    user = User.objects.get(email="guest@example.com")
    assert list(user.orders.all()) == [order] and Order.objects.get(pk=someone.pk).user is None
    assert order.number in client.get(reverse("shop:orders")).text  # My orders
    later = make_order((ProductFactory(), 1), email="GUEST@example.com")  # bought again without logging in
    client.logout()
    client.post(reverse("account_login"), {"login": "guest@example.com", "password": "Brahmaputra-2027"})
    assert Order.objects.get(pk=later.pk).user == user


def test_address_book_on_my_account(client):
    user, other = UserFactory(), UserFactory()
    theirs = Address.objects.create(user=other, **{**ADDRESS, "phone": "+919864012345"})
    client.force_login(user)
    page = client.get(reverse("account")).content.decode()
    assert reverse("shop:orders") in page and "No saved addresses" in page  # My orders is linked
    data = {**ADDRESS, "phone": "98640 12345", "pin": "781 001", "is_default": "on"}
    assert client.post(reverse("shop:address_add"), {**data, "pin": "012345"}).status_code == 200  # refused
    assert client.post(reverse("shop:address_add"), data).url == reverse("account")
    address = user.addresses.get()
    assert address.is_default and address.pin == "781001" and "Zoo Road" in client.get(reverse("account")).text
    client.post(reverse("shop:address_edit", args=[address.pk]), {**data, "city": "Jorhat"})
    address.refresh_from_db()
    assert address.city == "Jorhat"
    assert client.get(reverse("shop:address_edit", args=[theirs.pk])).status_code == 404  # someone else's
    assert client.post(reverse("shop:address_delete", args=[theirs.pk])).status_code == 404
    client.post(reverse("shop:address_delete", args=[address.pk]))
    assert not user.addresses.exists() and Address.objects.filter(pk=theirs.pk).exists()


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
