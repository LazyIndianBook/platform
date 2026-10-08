"""The fixes of SECURITY_REVIEW.md for the shop (phase 4), one test or more per finding."""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

import pytest
import requests
import yaml
from allauth.account.models import EmailAddress
from django.apps import apps
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_fsm import TransitionNotAllowed
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from shop import invoices, payments, services, tasks
from shop.factories import CouponFactory, ProductFactory, captured, make_order, post_webhook, verified_user
from shop.models import Cart, Invoice, Order, Payment, Refund
from shop.test_api import customer

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
PERSONAL = {"email": "rahul@example.com", "contact": "+919864012345", "vpa": "rahul@okaxis", "card": {"last4": "1111"}}


def test_m6_only_the_payments_allowed_fields_are_kept_hidden_from_staff_and_purged(client, rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        post_webhook(client, "payment.captured", captured(order, method="upi", **PERSONAL))
    payment = order.payments.get()
    assert payment.raw_payload == captured(order, method="upi")  # no email, phone, UPI ID or card
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:shop_payment_change", args=[payment.pk])).text
    assert payment.razorpay_payment_id in page and "Last webhook" not in page

    old = {"event": "payment.captured", "payload": {"payment": {"entity": captured(order, **PERSONAL)}}}
    Payment.objects.update(raw_payload=old)  # stored before the fix: the whole event
    import_module("shop.migrations.0005_payment_payload_allowlist").strip_payloads(apps, None)
    payment.refresh_from_db()
    assert payment.raw_payload == captured(order)

    Payment.objects.update(created=timezone.now() - timedelta(days=Payment.PAYLOAD_DAYS - 1))
    tasks.clean_up()
    assert Payment.objects.get().raw_payload == captured(order)  # kept for disputes for a while
    Payment.objects.update(created=timezone.now() - timedelta(days=Payment.PAYLOAD_DAYS + 1))
    tasks.clean_up()
    assert Payment.objects.get().raw_payload is None


def test_m3_orders_keep_their_mode_and_test_ones_change_nothing_once_live(client, rzp, commit, settings, caplog):
    caplog.set_level("WARNING", logger="shop")
    paid, pending, packed, unopened = [make_order((ProductFactory(), 1)) for _ in range(4)]  # with test keys
    with commit():
        services.record_capture(captured(paid))
    services.record_capture(captured(packed))  # its invoice task has not run yet
    services.pack_order(packed)
    Payment.objects.filter(order=unopened).update(razorpay_order_id=None)  # its payment page was never opened
    assert not Order.objects.filter(livemode=True).exists() and not Payment.objects.filter(livemode=True).exists()

    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # gone live
    payments.razorpay_order_id(unopened.payments.get())  # the Razorpay order is made with live keys: a live order
    assert Order.objects.get(pk=unopened.pk).livemode and unopened.payments.get().livemode
    assert post_webhook(client, "payment.captured", captured(pending)).status_code == 400  # the test secret
    with commit():
        live_signed = post_webhook(client, "payment.captured", captured(pending), secret="live-webhook-secret")
        services.record_capture(captured(pending))
    assert live_signed.status_code == 200 and "(test mode) ignored" in caplog.text
    pending.refresh_from_db()
    assert pending.status == Order.Status.PENDING and payments.reconcile(pending) is False
    assert not rzp.order.payments.called  # live keys see no test payment: the order expires
    tasks.generate_invoice(packed.pk)  # after the switch, with the seller's placeholders still in place
    assert Invoice.objects.get(order=packed).number.startswith("T/")  # the series of its payment's mode
    with pytest.raises(TransitionNotAllowed):
        services.ship_order(packed, "India Post", "EA1")
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    changelist = reverse("admin:shop_order_changelist")
    assert f"{paid.number} <strong>TEST</strong>" in client.get(changelist).text
    response = client.post(changelist, {"action": "mark_packed", "_selected_action": [paid.pk]}, follow=True)
    assert f"Not possible for {paid.number} (a test order)" in response.text
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID

    caplog.clear()
    live = make_order((ProductFactory(), 1))
    services.record_capture(captured(live))
    live = services.pack_order(live)
    assert live.livemode and live.status == Order.Status.PACKED and "ignored" not in caplog.text


def test_m3_a_closed_shop_shows_its_books_and_lets_only_staff_buy(client, settings):
    settings.SHOP_OPEN = False  # Razorpay's review on test keys
    product = ProductFactory()
    assert client.get("/api/v1/config/").json()["shop"]["open"] is False  # the website says "Shop opens soon"
    assert client.get(f"/api/v1/products/{product.slug}/").status_code == 200  # the books are shown
    refused = client.post("/api/v1/cart/items/", {"product": product.slug}, content_type="application/json")
    assert refused.status_code == 403  # a visitor's cart
    api = APIClient()
    customer(api)
    assert api.get("/api/v1/cart/").status_code == 200
    refused = api.post("/api/v1/cart/items/", {"product": product.slug})
    assert refused.status_code == 403 and refused.json() == {"detail": "The shop opens soon."}
    assert api.post("/api/v1/orders/", {"address": 1, "payment_method": "razorpay"}).status_code == 403
    assert not Cart.objects.exists()
    client.force_login(verified_user(UserFactory(is_staff=True).email))  # staff try the shop out
    response = client.post("/api/v1/cart/items/", {"product": product.slug}, content_type="application/json")
    assert response.status_code == 200 and Cart.objects.exists()


def test_m2_the_emails_link_shows_the_order_and_cancels_it_only_until_it_is_packed(client, rzp, commit):
    order, shipped = [make_order((ProductFactory(), 1), email="guest@example.com") for _ in range(2)]
    with commit():
        services.record_capture(captured(order))  # paid: the confirmation is emailed and the invoice made
        services.record_capture(captured(shipped))
        services.ship_order(services.pack_order(shipped), "India Post", "EA1")
    assert order.get_link_url() in mail.outbox[0].body and len(order.token) == 22 and order.token not in order.number
    link = f"/api/v1/orders/t/{order.token}/"  # what the website's page of the emails' link asks
    invoice = client.get(link).json()["invoice"]["url"]
    assert invoice == f"http://testserver{link}invoice/" and client.get(invoice)["Content-Type"] == "application/pdf"
    assert client.get(f"/api/v1/orders/t/{'A' * 22}/").status_code == 404
    with commit():
        response = client.post(link + "cancel/")
    order.refresh_from_db()
    assert response.status_code == 200 and order.status == Order.Status.REFUNDED
    response = client.post(f"/api/v1/orders/t/{shipped.token}/cancel/")
    assert "can no longer be cancelled" in response.text and Order.objects.get(pk=shipped.pk).status == "shipped"
    assert client.get(f"/api/v1/orders/{shipped.number}/").status_code in (401, 403)  # the link opens only its own


def test_m2_lookups_are_limited_per_email_and_number_and_refused_when_they_cannot_be_counted(rzp, monkeypatch):
    def ask(number, email, address):
        lookup = {"number": number, "email": email}
        return APIClient(REMOTE_ADDR=address).post("/api/v1/orders/lookup/", lookup).status_code

    assert [ask(f"EL-2026-{n:06d}", "child@example.com", f"10.0.0.{n}") for n in range(11)] == [200] * 10 + [429]
    assert [ask("EL-2026-000777", f"guess{n}@example.com", f"10.0.1.{n}") for n in range(11)] == [200] * 10 + [429]
    order = make_order((ProductFactory(), 1))
    monkeypatch.setattr(cache, "incr", lambda *args, **kwargs: None)  # Redis down: django-redis answers None
    assert ask("EL-2026-000001", "someone@example.com", "10.0.2.1") == 429
    api = APIClient(REMOTE_ADDR="10.0.2.2")
    assert api.post("/api/v1/orders/lookup/", {"number": "EL-2026-1", "email": "a@example.com"}).status_code == 429
    assert post_webhook(Client(), "payment.captured", captured(order)).status_code == 200  # webhooks go on


def test_m8_cash_on_delivery_for_confirmed_accounts_two_at_a_time_up_to_a_value(settings):
    settings.SHOP_COD_ENABLED = True  # never for a visitor's checkout: shop/test_api.py
    with pytest.raises(services.ShopError, match="confirmed email address"):
        make_order((ProductFactory(), 1), method="cod", user=UserFactory())  # its address not confirmed
    with pytest.raises(services.ShopError, match="up to ₹1,500"):
        make_order((ProductFactory(price=1501), 1), method="cod", email="ann@example.com")
    first, second, third = [make_order((ProductFactory(), 1), method="cod", email="ann@example.com") for _ in "abc"]
    services.place_cod(first)
    services.place_cod(second)
    with pytest.raises(services.ShopError, match="2 cash-on-delivery orders on their way"):
        services.place_cod(third)  # made while the others were not placed yet: checked again
    with pytest.raises(services.ShopError, match="on their way"):
        make_order((ProductFactory(), 1), method="cod", email="ann@example.com")
    services.cancel_order(first, "Changed my mind.")
    assert services.place_cod(third).placed_at


def test_m8_checkout_is_limited_per_address_and_refused_uncounted(client, monkeypatch):
    statuses = [client.post("/api/v1/orders/", {}, content_type="application/json").status_code for _ in range(11)]
    assert statuses == [400] * 10 + [429]  # the cart is empty: refused, ten times in ten minutes
    monkeypatch.setattr(cache, "incr", lambda *args, **kwargs: None)  # Redis down
    assert Client().post("/api/v1/orders/", {}, content_type="application/json").status_code == 429


def test_l1_a_refund_whose_answer_was_lost_is_found_at_razorpay_not_sent_again(rzp, commit):
    order = make_order((ProductFactory(), 1))
    services.record_capture(captured(order))
    rzp.payment.refund.side_effect = requests.ReadTimeout  # Razorpay made the refund; its answer was lost
    with commit():  # the task asks Celery to try again (eager here: logged)
        services.cancel_order(order, "Changed my mind.")
    refund = order.refunds.get()
    assert rzp.payment.refund.call_count == 1 and refund.status == Refund.Status.PENDING
    made = {"id": "rfnd_lost", "status": "processed", "notes": {"order": order.number, "refund_id": str(refund.pk)}}
    rzp.payment.fetch_multiple_refund.return_value = {"items": [{"id": "rfnd_other", "notes": []}, made]}
    tasks.refund_payment(refund.pk)  # the retry, or the clean-up's re-queue
    refund.refresh_from_db()
    assert rzp.payment.refund.call_count == 1  # not sent again
    assert (refund.razorpay_refund_id, refund.status) == ("rfnd_lost", Refund.Status.PROCESSED)
    assert rzp.payment.fetch_multiple_refund.call_args.args == (f"pay_{order.pk}",)


def test_l3_a_second_payment_for_a_paid_order_is_recorded_and_refunded_once(client, rzp, commit, caplog):
    order = make_order((ProductFactory(), 1))
    first, second = captured(order), captured(order, id="pay_again")  # two payments of one Razorpay order
    with commit():
        post_webhook(client, "payment.captured", first)
        post_webhook(client, "payment.captured", second, event_id="evt_2")
        services.record_capture(second)  # reported again: nothing more
    again = Payment.objects.get(razorpay_payment_id="pay_again")
    assert again.status == Payment.Status.REFUNDED and again.refunds.get().amount.amount == 299
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and order.payments.count() == 2  # the first payment still pays it
    assert "second payment for order" in caplog.text
    assert mail.outbox[-1].subject == f"[ExamLeaf] Refund for order {order.number}"

    twice = make_order((ProductFactory(), 1))
    first, second = captured(twice), captured(twice, id="pay_twice")
    rzp.payment.refund.side_effect = lambda payment_id, data, **kw: {"id": f"rfnd_{payment_id}", "status": "pending"}
    with commit():
        services.record_capture(first)
        services.record_capture(second)  # its refund is still pending at Razorpay when the customer cancels
        services.cancel_order(twice, "Changed my mind.")
    refunded = set(twice.refunds.values_list("payment__razorpay_payment_id", flat=True))
    assert refunded == {"pay_twice", f"pay_{twice.pk}"}  # the cancellation refunds the first payment too


def test_l4_coupon_codes_are_refused_alike_and_tried_ten_times_an_hour(client, monkeypatch):
    product = ProductFactory()
    client.post("/api/v1/cart/items/", {"product": product.slug}, content_type="application/json")
    CouponFactory(code="OLD", valid_until=timezone.now() - timedelta(days=1))
    CouponFactory(code="BIG", min_order=Decimal("1000"))
    CouponFactory(code="WELCOME10")

    def try_code(code):  # the website's cart page
        return client.post("/api/v1/cart/coupon/", {"code": code}, content_type="application/json")

    assert all("This code cannot be applied to this cart." in try_code(code).text for code in ["NOPE", "OLD", "BIG"])
    for _ in range(7):
        try_code("GUESS")
    assert try_code("WELCOME10").status_code == 429  # the eleventh in the hour, even a good one
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "coupon", "2/hour")
    api = APIClient()
    customer(api)
    api.post("/api/v1/cart/items/", {"product": product.slug})
    assert [api.post("/api/v1/cart/coupon/", {"code": "OLD"}).status_code for _ in range(3)] == [400, 400, 429]
    assert api.delete("/api/v1/cart/coupon/").status_code == 200  # removing a coupon is not counted


def test_m10_orders_never_paid_lose_the_customers_details_30_days_after_cancellation(rzp):
    unsold, recent, sold = [make_order((ProductFactory(), 1)) for _ in range(3)]
    services.cancel_order(unsold, "Not paid within two days.", email=False)
    services.cancel_order(recent, "Cancelled by the customer.")
    services.record_capture(captured(sold))
    services.cancel_order(sold, "Changed my mind.")  # a sale (paid, then refunded): a tax record, kept
    Order.objects.exclude(pk=recent.pk).update(modified=timezone.now() - services.FORGET_UNSOLD_AFTER)
    tasks.clean_up()
    unsold.refresh_from_db()
    assert unsold.email == "deleted" and not unsold.history.exclude(email="deleted").exists()
    assert {key: unsold.shipping_address[key] for key in ("name", "phone", "line1", "pin")} == {
        "name": "deleted",
        "phone": "deleted",
        "line1": "deleted",
        "pin": "781001",
    }
    assert Order.objects.get(pk=recent.pk).email == "rahul@example.com"  # cancelled today: kept for now
    assert Order.objects.get(pk=sold.pk).shipping_address["name"] == "Rahul Das"
    assert services.forget_orders(Order.objects.all()) == 2  # by hand (RUNBOOK.md): the others; once each


def test_i4_products_and_addresses_sort_only_by_the_fields_named(client):
    ProductFactory(title="B", price=Decimal("199"))
    ProductFactory(title="A", price=Decimal("299"))
    api = APIClient()
    assert [p["title"] for p in api.get("/api/v1/products/?ordering=-price").json()["results"]] == ["A", "B"]
    assert api.get("/api/v1/products/?ordering=mrp__amount").status_code == 200  # an unknown name is ignored
    customer(api)
    assert api.get("/api/v1/addresses/?ordering=user__password").status_code == 200


def test_i6_pdfs_take_static_files_and_data_urls_only(settings):
    try:
        fetcher = invoices.static_files_only()
    except OSError:
        pytest.skip("WeasyPrint's system libraries (Pango) are not installed")
    css = settings.BASE_DIR / "static" / "css" / "staff.css"
    assert fetcher(css.as_uri()).read().strip() and fetcher("data:text/plain,ok").read() == b"ok"
    for url in [
        (settings.BASE_DIR / ".env.example").as_uri(),  # a file outside the static folders
        css.as_uri().replace("/css/staff.css", "/css/../../.env.example"),
        "http://169.254.169.254/latest/meta-data/",  # the network
        "ftp://example.com/x",
    ]:
        with pytest.raises(ValueError, match="Not fetched|disallowed"):
            fetcher(url)


def test_l8_the_cache_has_a_redis_of_its_own_that_evicts_and_the_queue_never_does(settings):
    compose = yaml.safe_load((settings.BASE_DIR / "docker-compose.yml").read_text())
    cache_redis, queue_redis = compose["services"]["redis-cache"]["command"], compose["services"]["redis"]["command"]
    assert {"256mb", "allkeys-lru"} <= set(cache_redis) and "noeviction" in queue_redis
    environment = compose["x-app"]["environment"]
    assert environment["CACHE_URL"].startswith("redis://redis-cache:")
    assert environment["CELERY_BROKER_URL"].startswith("redis://redis:")


def test_m10_the_yearly_purge_of_invoiced_orders_keeps_their_pdfs_gone(rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        services.record_capture(captured(order))  # paid and invoiced
    Order.objects.update(modified=timezone.now() - timedelta(hours=2))
    order.invoice.pdf.delete()  # RUNBOOK.md, "Purging old orders"
    assert services.forget_orders(Order.objects.all()) == 1
    tasks.clean_up()
    order.refresh_from_db()
    assert not order.invoice.pdf and order.shipping_address["line1"] == "deleted"  # not made again from the purged


def test_m9_a_student_whose_parent_has_not_confirmed_cannot_check_out(client, settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    api = APIClient()
    book = ProductFactory()
    user = UserFactory(date_of_birth=timezone.localdate() - timedelta(days=16 * 365))
    assert user.consent_pending
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    api.post("/api/v1/cart/items/", {"product": book.slug})
    response = api.post("/api/v1/orders/", {"address": 1, "payment_method": "razorpay"})
    assert response.status_code == 403 and "has not confirmed this account yet" in response.json()["detail"]
    assert not Order.objects.exists()
    settings.PARENTAL_CONSENT_MODE = "declared"
    del user.consent_pending
    assert not user.consent_pending
