"""When things overlap or go wrong: a coupon's last use taken by two open orders, a payment that arrives after the
coupon ran out, the return page after such a payment, abandoned review pages, and (on PostgreSQL only: SQLite has no
row locks) the last copy, the coupon's last use and a webhook with the return page, each at the very same instant."""

import io
import os
import threading
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
import requests
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, connections
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from shop import invoices, services, tasks
from shop.cart import set_quantity
from shop.factories import (
    ADDRESS,
    CouponFactory,
    ProductFactory,
    ShippingRateFactory,
    captured,
    make_order,
    post_webhook,
)
from shop.models import Address, Cart, CartItem, Invoice, Order, Payment, Product
from shop.templatetags.shop import shop_stats
from shop.test_api import customer
from shop.test_razorpay import as_customer, return_from_checkout

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs row locks (select_for_update)")


def two_open_orders(product, coupon, **kwargs):
    """Two orders, each made while the coupon still had its use left (neither is paid or placed yet)."""
    return [make_order((product, 1), coupon=coupon, email=f"{who}@example.com", **kwargs) for who in ("ann", "bob")]


def test_a_coupons_last_use_goes_to_the_first_order_placed_not_the_first_made(settings):
    settings.SHOP_COD_ENABLED = True
    product, coupon = ProductFactory(stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon, method="cod")
    services.place_cod(second)
    with pytest.raises(services.CouponUsedUp, match="used up"):
        services.place_cod(first)
    first.refresh_from_db()
    product.refresh_from_db()
    assert first.placed_at is None and not first.stock_reserved and product.stock == 4  # nothing taken


def test_one_customer_cannot_use_a_once_only_coupon_in_two_open_orders(settings):
    settings.SHOP_COD_ENABLED = True
    coupon = CouponFactory(max_uses=None, max_uses_per_customer=1)
    a, b = [make_order((ProductFactory(), 1), coupon=coupon, method="cod", email="Ann@example.com") for _ in "ab"]
    services.place_cod(a)
    with pytest.raises(services.CouponUsedUp, match="already used"):
        services.place_cod(b)
    assert coupon.orders.counted().count() == 1


def test_a_payment_after_the_coupon_ran_out_is_refunded_and_the_customer_told(client, rzp, commit):
    product, coupon = ProductFactory(stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon)
    with commit():
        post_webhook(client, "payment.captured", captured(first))
        post_webhook(client, "payment.captured", captured(second))
    first.refresh_from_db()
    second.refresh_from_db()
    product.refresh_from_db()
    assert first.status == Order.Status.PAID and product.stock == 4
    assert second.status == Order.Status.REFUNDED and second.refunds.get().status == "processed"
    cancelled = [m for m in mail.outbox if second.number in m.subject and "cancelled" in m.subject]
    assert "the coupon was used up while you were paying" in cancelled[0].body


def test_the_payment_page_takes_no_payment_for_a_coupon_that_is_gone(client, rzp, commit):
    product, coupon = ProductFactory(), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon)
    as_customer(client, second)
    assert "razorpay-options" in client.get(reverse("shop:pay", args=[second.number])).text
    with commit():
        post_webhook(client, "payment.captured", captured(first))
    page = client.get(reverse("shop:pay", args=[second.number])).text
    assert "used up" in page and "Nothing has been charged" in page and "razorpay-options" not in page


def test_the_return_after_a_payment_that_could_not_be_used_says_so_and_keeps_the_cart(client, rzp, commit):
    product, coupon = ProductFactory(stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon)
    with commit():
        post_webhook(client, "payment.captured", captured(first))
    client.post(reverse("shop:cart_add", args=[product.pk]))  # the customer's cart
    as_customer(client, second)
    rzp.payment.fetch.return_value = captured(second)
    with commit():
        response = return_from_checkout(client, second)
    assert response.url == reverse("shop:done", args=[second.number])
    page = client.get(response.url).text
    assert "We could not complete this order" in page and "Thank you" not in page
    assert client.session["shop_cart_count"] == 1  # not emptied: the order did not go through


def test_a_cash_on_delivery_order_that_cannot_be_placed_is_cancelled_with_a_message(client, settings):
    settings.SHOP_COD_ENABLED = True
    product, coupon = ProductFactory(stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon, method="cod")
    services.place_cod(first)
    as_customer(client, second)
    response = client.post(reverse("shop:pay", args=[second.number]), follow=True)
    assert response.redirect_chain[-1][0] == reverse("shop:cart")
    assert "used up. Please remove the coupon from your cart." in response.text
    second.refresh_from_db()
    assert second.status == Order.Status.CANCELLED and not Payment.objects.filter(order=second, status="captured")


def test_the_api_refuses_a_payment_and_a_cash_order_for_a_coupon_that_is_gone(settings):
    settings.SHOP_COD_ENABLED = True
    api = APIClient()
    product, coupon = ProductFactory(slug="physics", stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    user = customer(api)
    address = Address.objects.create(user=user, **ADDRESS)
    other = make_order((product, 1), coupon=coupon, email="other@example.com", method="cod")
    api.post("/api/v1/cart/items/", {"product": "physics"})
    api.post("/api/v1/cart/coupon/", {"code": coupon.code})
    online = api.post("/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay"}).json()
    services.place_cod(other)  # the coupon's only use goes meanwhile
    refused = api.post(f"/api/v1/orders/{online['number']}/payment/")
    assert refused.status_code == 400 and "used up" in refused.json()["non_field_errors"][0]
    cod = api.post("/api/v1/orders/", {"address": address.pk, "payment_method": "cod"})
    assert cod.status_code == 400 and "used up" in cod.json()["non_field_errors"][0]
    assert Cart.objects.filter(user=user).exists()
    assert not Order.objects.filter(user=user, placed_at__isnull=False).exists()
    assert Order.objects.get(number=online["number"]).status == Order.Status.PENDING


def test_review_pages_nobody_finished_are_cancelled_after_two_days(settings):
    settings.SHOP_COD_ENABLED = True
    product = ProductFactory(stock=5)
    abandoned, placed, online = [make_order((product, 1), method=m) for m in ("cod", "cod", "razorpay")]
    services.place_cod(placed)
    Order.objects.update(created=timezone.now() - services.UNPAID_ORDERS_EXPIRE - timedelta(minutes=1))
    assert services.expire_unpaid_orders() == 2
    statuses = {o.pk: Order.objects.get(pk=o.pk).status for o in (abandoned, placed, online)}
    assert statuses == {abandoned.pk: "cancelled", placed.pk: "pending", online.pk: "cancelled"}
    product.refresh_from_db()
    assert product.stock == 4  # only the placed order holds a copy


# Several requests at once. Each job runs in its own thread with its own database connection; they start together.


def at_once(*jobs):
    barrier, results = threading.Barrier(len(jobs)), [None] * len(jobs)

    def run(index, job):
        try:
            barrier.wait()
            results[index] = job()
        except Exception as error:  # reported to the test
            results[index] = error
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run, args=(i, job)) for i, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not any(isinstance(r, Exception) for r in results), results
    return results


real_commits = pytest.mark.django_db(transaction=True, serialized_rollback=True)  # migration data restored after


@postgres_only
@real_commits
def test_two_payments_for_the_last_copy_at_once_sell_it_once(rzp):
    product = ProductFactory(stock=1)
    first, second = make_order((product, 1)), make_order((product, 1), email="other@example.com")
    at_once(lambda: services.record_capture(captured(first)), lambda: services.record_capture(captured(second)))
    product.refresh_from_db()
    states = sorted(Order.objects.get(pk=o.pk).status for o in (first, second))
    assert product.stock == 0 and states == ["paid", "refunded"]


@postgres_only
@real_commits
def test_two_payments_for_a_coupons_last_use_at_once_use_it_once(rzp):
    product, coupon = ProductFactory(stock=5), CouponFactory(max_uses=1, max_uses_per_customer=None)
    first, second = two_open_orders(product, coupon)
    at_once(lambda: services.record_capture(captured(first)), lambda: services.record_capture(captured(second)))
    assert sorted(Order.objects.get(pk=o.pk).status for o in (first, second)) == ["paid", "refunded"]
    assert coupon.orders.counted().count() == 1 and Product.objects.get(pk=product.pk).stock == 4


@postgres_only
@real_commits
def test_the_webhook_and_the_return_page_at_once_pay_the_order_once(rzp):
    product = ProductFactory(stock=3)
    order = make_order((product, 2))
    entity = captured(order)
    at_once(lambda: services.record_capture(entity), lambda: services.record_capture(dict(entity)))
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and Product.objects.get(pk=product.pk).stock == 1
    assert [m.subject for m in mail.outbox].count(f"[ExamLeaf] Order {order.number} confirmed") == 1


def test_no_real_invoice_is_numbered_while_the_sellers_details_are_placeholders(rzp, settings):
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # the real series: its numbers and details cannot be changed later
    order = make_order((ProductFactory(), 1))
    services.record_capture(captured(order))
    with pytest.raises(ImproperlyConfigured, match="address, email, phone"):
        tasks.generate_invoice.run(order.pk)
    assert not Invoice.objects.exists()  # no number was used up
    settings.DEBUG = True  # development is not held up
    tasks.generate_invoice.run(order.pk)
    assert Invoice.objects.get().number.startswith("EL/")


def test_an_invoice_lines_amount_is_what_is_payable_after_the_discount():
    order = make_order((ProductFactory(price=299), 2), coupon=CouponFactory(value=10))
    [line] = invoices.context(Invoice.for_order(order))["lines"]
    assert (line["value"], line["discount"], line["taxable"], line["amount"]) == (
        Decimal("598.00"),
        Decimal("59.80"),
        Decimal("538.20"),
        Decimal("538.20"),
    )
    assert line["amount"] == line["taxable"] + line["cgst"] + line["sgst"] + line["igst"]


def test_the_dashboards_revenue_leaves_out_what_was_refunded_in_part(rzp, commit):
    ShippingRateFactory()  # Assam: 40 below 499
    order = make_order((ProductFactory(price=299), 1))  # 299 + 40 shipping
    with commit():
        services.record_capture(captured(order))
        shipped = services.ship_order(services.pack_order(order), "India Post", "EA1")
        services.refund_order(shipped, "Parcel refused.", amount=Decimal("299"))  # the books, not the shipping
    assert shop_stats()["rows"] == [
        ("Orders", 0, 0),
        ("Revenue", "₹40.00", "₹40.00"),
    ]  # "refunded", but the shipping stays
    whole = make_order((ProductFactory(price=299), 1))
    with commit():
        services.record_capture(captured(whole))
        services.cancel_order(whole, "Changed my mind.")  # paid, then refunded in full
    assert shop_stats()["rows"] == [("Orders", 0, 0), ("Revenue", "₹40.00", "₹40.00")]


def test_a_refund_made_in_the_razorpay_dashboard_is_recorded_once_and_the_order_follows(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        post_webhook(client, "payment.captured", captured(order))
    assert order.refunds.count() == 0
    entity = {"id": "rfnd_dash", "payment_id": f"pay_{order.pk}", "amount": 29900, "notes": []}
    with commit():
        post_webhook(client, "refund.processed", entity, kind="refund", event_id="evt_1")
        post_webhook(client, "refund.processed", entity, kind="refund", event_id="evt_2")  # again, under another id
    order.refresh_from_db()
    refund = order.refunds.get()  # one row
    assert (refund.amount.amount, refund.status, refund.razorpay_refund_id) == (299, "processed", "rfnd_dash")
    assert refund.reason == "Refunded in the Razorpay dashboard." and order.status == Order.Status.REFUNDED
    assert sum(f"Refund for order {order.number}" in m.subject for m in mail.outbox) == 1  # the customer is told


def test_refund_events_for_payments_this_shop_does_not_know_change_nothing(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        post_webhook(client, "payment.captured", captured(order))
        stranger = {"id": "rfnd_x", "payment_id": "pay_of_another_shop", "amount": 100, "notes": []}
        assert post_webhook(client, "refund.processed", stranger, kind="refund").status_code == 200
        assert post_webhook(client, "refund.failed", stranger, kind="refund", event_id="e2").status_code == 200
        odd = {"id": "rfnd_y", "amount": 100, "notes": {"refund_id": "not-a-number"}}  # no payment at all
        assert post_webhook(client, "refund.processed", odd, kind="refund", event_id="e3").status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and not order.refunds.exists()


def stale(*orders):
    Order.objects.filter(pk__in=[o.pk for o in orders]).update(created=timezone.now() - services.UNPAID_ORDERS_EXPIRE)


def test_a_payment_nobody_reported_is_found_at_expiry_instead_of_the_order_being_cancelled(rzp, commit):
    product = ProductFactory(stock=5)
    order = make_order((product, 1))  # paid at Razorpay, but the customer never came back and the webhook was lost
    stale(order)
    rzp.order.payments.return_value = {"items": [captured(order, status="failed"), captured(order)]}
    with commit():
        tasks.clean_up()
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.PAID and order.placed_at and product.stock == 4
    assert [m.subject for m in mail.outbox] == [f"[ExamLeaf] Order {order.number} confirmed"]


def test_an_authorized_payment_is_captured_when_reconciling(rzp, commit):
    order = make_order((ProductFactory(), 1))
    stale(order)
    rzp.order.payments.return_value = {"items": [captured(order, status="authorized")]}
    rzp.payment.capture.return_value = captured(order)
    with commit():
        tasks.clean_up()
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and rzp.payment.capture.call_args.args[:2] == (f"pay_{order.pk}", 29900)


def test_an_order_is_not_cancelled_while_razorpay_cannot_be_asked(rzp, commit):
    order = make_order((ProductFactory(), 1))
    stale(order)
    rzp.order.payments.side_effect = requests.Timeout("slow")
    with commit():
        assert tasks.clean_up() is None
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING  # nothing is known: wait for the next run
    rzp.order.payments.side_effect = None
    rzp.order.payments.return_value = {"items": []}  # Razorpay answers: nobody paid
    with commit():
        tasks.clean_up()
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_an_order_paid_while_the_sweep_runs_is_left_alone(rzp, commit):
    order = make_order((ProductFactory(), 1))
    stale(order)

    def paid_meanwhile(order):  # the customer's payment lands between the sweep's query and its lock
        services.record_capture(captured(order))
        return False

    assert services.expire_unpaid_orders(reconcile=paid_meanwhile) == 0
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


def test_reconcile_payments_records_what_razorpay_took_and_the_site_missed(rzp, commit):
    paid, unpaid, never = [make_order((ProductFactory(), 1)) for _ in range(3)]
    Payment.objects.filter(order=never).update(razorpay_order_id=None)  # never reached the payment page

    def razorpay_has(order_id, **kwargs):
        return {"items": [captured(paid)] if order_id == f"order_{paid.pk}" else []}

    rzp.order.payments.side_effect = razorpay_has
    Order.objects.update(created=timezone.now() - timedelta(minutes=30))
    out = StringIO()
    with commit():
        call_command("reconcile_payments", stdout=out)
    assert f"{paid.number}: paid now" in out.getvalue() and f"{unpaid.number}: no payment at Razorpay" in out.getvalue()
    assert never.number not in out.getvalue()
    assert [Order.objects.get(pk=o.pk).status for o in (paid, unpaid, never)] == ["paid", "pending", "pending"]
    out = StringIO()
    call_command("reconcile_payments", "--older-than", "60", stdout=out)  # too young: left to their customers
    assert out.getvalue() == "Done.\n"


def product_form_data(product, **changes):
    """What the browser posts for the product's change form (the page showed its stock as `initial-stock`)."""
    data = {
        "title": product.title,
        "slug": product.slug,
        "kind": product.kind,
        "is_active": "on",
        "mrp_0": "349.00",
        "mrp_1": "INR",
        "price_0": "299.00",
        "price_1": "INR",
        "stock": str(product.stock),
        "initial-stock": str(product.stock),
        "gst_rate": "0",
        "hsn_code": "4901",
        "weight_grams": "0",
    }
    return {**data, **changes}


def test_saving_a_product_page_opened_before_a_sale_keeps_the_copies_left(client):
    product = ProductFactory(stock=10)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:shop_product_change", args=[product.pk]))
    assert 'name="initial-stock"' in page.text  # the stock the page was opened with travels with it
    Product.objects.filter(pk=product.pk).update(stock=8)  # two copies sold while the page was open
    response = client.post(
        reverse("admin:shop_product_change", args=[product.pk]),
        {**product_form_data(product, title="A better title"), **ADMIN_INLINES},
    )
    assert response.status_code == 302
    product.refresh_from_db()
    assert (product.title, product.stock) == ("A better title", 8)  # not put back to 10
    client.post(  # stock typed on purpose is set: the books came in
        reverse("admin:shop_product_change", args=[product.pk]),
        {**product_form_data(product, stock="30", **{"initial-stock": "8"}), **ADMIN_INLINES},
    )
    product.refresh_from_db()
    assert product.stock == 30


ADMIN_INLINES = {  # the inline formsets (books in the bundle, attributes, pictures, earlier slugs), empty
    f"{prefix}-{name}": value
    for prefix in ("bundle_items", "attribute_values", "images", "old_slugs")
    for name, value in (("TOTAL_FORMS", "0"), ("INITIAL_FORMS", "0"), ("MIN_NUM_FORMS", "0"), ("MAX_NUM_FORMS", "1000"))
}


def test_a_picture_over_2_mb_is_refused_in_the_admin_with_a_reason(client):
    product = ProductFactory()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    noise = io.BytesIO()
    Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3)).save(noise, "PNG")  # a real image, about 2.4 MB
    big = SimpleUploadedFile("cover.png", noise.getvalue(), content_type="image/png")
    assert big.size > 2 * 1024 * 1024
    response = client.post(
        reverse("admin:shop_product_change", args=[product.pk]),
        {**product_form_data(product), **ADMIN_INLINES, "cover": big},
    )
    assert response.status_code == 200 and "Make it smaller than 2 MB first" in response.text
    product.refresh_from_db()
    assert not product.cover


@postgres_only
@real_commits
def test_two_clicks_on_add_to_cart_at_once_do_not_crash_the_second(monkeypatch):
    product, cart = ProductFactory(), Cart.objects.create()
    both_looked = threading.Barrier(2)
    first = QuerySet.first

    def first_then_wait(self):  # each request looks for the book in the cart and finds none, before either adds it
        found = first(self)
        if self.model is CartItem:
            both_looked.wait(timeout=10)
        return found

    monkeypatch.setattr(QuerySet, "first", first_then_wait)
    at_once(lambda: set_quantity(cart, product, 1, add=True), lambda: set_quantity(cart, product, 1, add=True))
    assert CartItem.objects.get(cart=cart, product=product).quantity in (1, 2)  # one row, no IntegrityError


def test_one_orders_failed_reconcile_does_not_stop_the_clean_up(rzp, commit, caplog):
    broken, unpaid = make_order((ProductFactory(), 1)), make_order((ProductFactory(), 1))
    stale(broken, unpaid)

    def razorpay_says(order_id, **kwargs):
        if order_id == f"order_{broken.pk}":
            raise KeyError("an answer that is not what Razorpay documents")
        return {"items": []}

    rzp.order.payments.side_effect = razorpay_says
    with commit():
        tasks.clean_up()  # does not raise
    assert Order.objects.get(pk=broken.pk).status == Order.Status.PENDING  # left for the next run
    assert Order.objects.get(pk=unpaid.pk).status == Order.Status.CANCELLED  # the others go on
    assert "Reconciling order" in caplog.text
