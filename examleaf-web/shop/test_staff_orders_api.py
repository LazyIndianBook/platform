"""The Orders module's staff API (shop/staff_orders.py) and its flows (shop.services, staff.approvals): the exit
criteria of Phase B's Orders package, one test each, beside the authorization matrix (staff/tests/test_matrix.py).
A partial refund by line, its amount from the invoiced values, waiting above the maker's cap; the bank path marked
paid by FINANCE (refused to SALES) with its credit note once; the Idempotency-Key; every return transition's
permission and the restock; the customer's return refused late and before delivery; a staff discount above the cap
making no order until approved; a bulk cancel of 251 refused; the packing queue scoped for PACKER and without held
orders; the COD risk hold; the print endpoints' PDFs; test orders out of the default list; the weekly email once;
a person's lookup audited by its hash; the lists' queries not growing with their rows."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from shipping.models import ShipmentDetail
from shop import invoices, services, tasks
from shop.cart import Line
from shop.factories import ADDRESS, CouponFactory, ProductFactory, captured, make_order, verified_user
from shop.models import CreditNote, Order, OrderMessage, Product, QuoteRequest, Refund, ReturnRequest, Shipment
from staff.models import AuditEvent, InboxItem, Job, Note
from staff.tests.conftest import STAFF, events, make_staff, signed_in

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
ORDERS = STAFF + "orders/"


@pytest.fixture(autouse=True)
def quick_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def cod(settings):
    settings.SHOP_COD_ENABLED = True


def paid(*lines, **fields):
    order = make_order(*lines, **fields)
    services.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def delivered(order):
    services.pack_order(order)
    services.ship_order(order, "India Post", "EA123456789IN")
    services.deliver_order(order)
    return Order.objects.get(pk=order.pk)


def approve_and_run(change, checker, commit):
    client = signed_in(checker)
    assert (
        client.post(
            f"{STAFF}change-requests/{change['id']}/approve/",
            {"payload_sha256": change["payload_sha256"]},
            format="json",
        ).status_code
        == 200
    )
    with commit():
        return client.post(f"{STAFF}change-requests/{change['id']}/execute/").json()


def three_books():
    return [ProductFactory(price=Decimal(price), mrp=Decimal(price), stock=10) for price in ("800", "900", "1000")]


# Refunds


def test_a_partial_refund_of_two_lines_of_three_is_their_invoiced_value_and_waits_above_the_cap(rzp, commit):
    books = three_books()
    with commit():  # its invoice made
        order = delivered(paid(*[(book, 1) for book in books], coupon=CouponFactory(value=Decimal(10))))  # 10 %: 270
    a, b, c = order.items.order_by("pk")
    support, finance = make_staff(roles.SUPPORT), make_staff(roles.FINANCE)
    lines = [{"item": a.pk, "quantity": 0}, {"item": b.pk, "quantity": 1}, {"item": c.pk, "quantity": 1}]
    asked = signed_in(support).post(
        f"{ORDERS}{order.number}/refunds/", {"lines": lines, "reason": "Damaged"}, format="json"
    )
    assert asked.status_code == 202, asked.content  # ₹1,710 is above SUPPORT's ₹1,000
    change = asked.json()
    assert change["amount"] == "1710.00" and change["payload"]["lines"] == [
        {"item": b.pk, "quantity": 1, "amount": "810.00"},  # 900 less its 90 of the coupon
        {"item": c.pk, "quantity": 1, "amount": "900.00"},
    ]
    assert change["warnings"] == [] and not Refund.objects.exists()
    done = approve_and_run(change, finance, commit)
    assert done["status"] == "executed", done
    refund = Refund.objects.get()
    assert (refund.amount.amount, refund.method, refund.change_request_id) == (
        Decimal("1710.00"),
        "source",
        change["id"],
    )
    assert rzp.payment.refund.call_args.args[1]["amount"] == 171000
    note = CreditNote.objects.get(refund=refund)  # the credit note credits those two lines, a copy each
    context = invoices.credit_note_context(note)
    assert [(line["item"].pk, line["amount"], line["quantity"]) for line in context["lines"]] == [
        (a.pk, Decimal("0.00"), 0),
        (b.pk, Decimal("810.00"), 1),
        (c.pk, Decimal("900.00"), 1),
    ]
    again = signed_in(support).post(
        f"{ORDERS}{order.number}/refunds/", {"lines": [{"item": b.pk, "quantity": 1}], "reason": "Again"}, format="json"
    )
    assert again.status_code == 400 and "0 of 1 copies are left" in json.dumps(again.json())


def test_the_bank_path_is_refused_to_sales_and_marked_paid_by_finance_with_its_credit_note_once(cod, commit):
    book = ProductFactory(price=Decimal("400"), mrp=Decimal("400"), stock=5)
    order = make_order((book, 1), method="cod")
    with commit():
        services.place_cod(order)
        order = delivered(Order.objects.get(pk=order.pk))
    item, sales = order.items.get(), make_staff(roles.SALES)
    body = {
        "lines": [{"item": item.pk, "quantity": 1}],
        "method": "bank",
        "payee": {"upi": "rahul.das@okicici"},
        "reason": "Pages missing",
    }
    with commit():
        asked = signed_in(sales).post(f"{ORDERS}{order.number}/refunds/", body, format="json")
    assert asked.status_code == 201, asked.content  # ₹400 within SALES' ₹2,000
    refund = Refund.objects.get()
    assert (refund.method, refund.status, refund.payee_masked) == ("bank", "pending", "UPI ra•••@okicici")
    assert "rahul.das" not in json.dumps(asked.json()) and "rahul.das" not in refund.payee  # encrypted at rest
    assert not AuditEvent.objects.filter(details__icontains="rahul.das").exists()
    item_ = InboxItem.objects.get(kind="bank_refund", done_at=None)
    assert item_.permission == "staff.approve_refund" and item_.due_at > timezone.now()
    mark = f"{ORDERS}refunds/{refund.pk}/mark-paid/"
    assert signed_in(sales).post(mark, {"utr": "UTR12345678"}, format="json").status_code == 403
    finance = make_staff(roles.FINANCE)
    shown = signed_in(finance).post(f"{ORDERS}refunds/{refund.pk}/payee/", {"reason": "To transfer it"}, format="json")
    assert shown.json() == {"upi": "rahul.das@okicici"}
    assert events("sensitive_read", target_id=str(order.pk)).get().details["what"] == "refund payee"
    with commit():
        marked = signed_in(finance).post(mark, {"utr": "UTR12345678"}, format="json")
    assert (
        marked.status_code == 200 and marked.json()["status"] == "processed" and marked.json()["utr"] == "UTR12345678"
    )
    assert CreditNote.objects.filter(refund=refund).count() == 1
    assert Order.objects.get(pk=order.pk).status == "refunded" and InboxItem.objects.get(pk=item_.pk).done_at
    with commit():
        twice = signed_in(finance).post(mark, {"utr": "UTR12345678"}, format="json")
    assert twice.status_code == 400 and "marked paid already" in twice.json()["non_field_errors"][0]
    assert CreditNote.objects.filter(refund=refund).count() == 1
    assert any("UTR12345678" in message.body for message in mail.outbox)  # the customer told, with the reference


def test_an_online_payment_goes_to_a_bank_only_with_the_customers_agreement(rzp):
    order = paid((ProductFactory(), 1))
    services.pack_order(order)
    services.ship_order(order, "India Post", "EA1IN")
    item = order.items.get()
    body = {"lines": [{"item": item.pk, "quantity": 1}], "method": "bank", "payee": {"upi": "a.b@upi"}, "reason": "x"}
    client = signed_in(make_staff(roles.SALES))
    refused = client.post(f"{ORDERS}{order.number}/refunds/", body, format="json")
    assert refused.status_code == 400 and "customer_agreed" in refused.json()
    assert (
        client.post(f"{ORDERS}{order.number}/refunds/", {**body, "customer_agreed": True}, format="json").status_code
        == 201
    )


def test_the_idempotency_key_answers_the_first_request_again(rzp, commit):
    order = paid((ProductFactory(), 1))
    client, key = signed_in(make_staff(roles.SALES)), {"HTTP_IDEMPOTENCY_KEY": "refund-once-1"}
    with commit():
        first = client.post(f"{ORDERS}{order.number}/refunds/", {"reason": "Changed my mind"}, format="json", **key)
        second = client.post(f"{ORDERS}{order.number}/refunds/", {"reason": "Changed my mind"}, format="json", **key)
    assert first.status_code == 201 and second.status_code == 200 and first.json()["id"] == second.json()["id"]
    assert Refund.objects.count() == 1 and Order.objects.get(pk=order.pk).status == "refunded"  # cancelled, refunded


def test_a_payment_older_than_six_months_is_warned_of_before_and_after(rzp):
    order = paid((ProductFactory(), 1))
    order.payments.update(created=timezone.now() - timedelta(days=200))
    owner = make_staff(roles.OWNER)
    record = signed_in(owner).get(f"{ORDERS}{order.number}/").json()
    assert record["refund"]["warnings"][0].startswith("The payment is older than 6 months")
    assert record["payments"][0]["older_than_6_months"] is True


# Returns


def test_every_return_transition_has_its_permission_and_the_restock_puts_the_copies_back(rzp, commit):
    book = ProductFactory(price=Decimal("500"), mrp=Decimal("500"), stock=10)
    with commit():
        order = delivered(paid((book, 2)))
    stock = Product.objects.get(pk=book.pk).stock
    support, packer, sales = make_staff(roles.SUPPORT), make_staff(roles.PACKER), make_staff(roles.SALES)
    item = order.items.get()
    ask = {"lines": [{"item": item.pk, "quantity": 2}], "reason": "misprint", "note": "Pages 12 to 16 missing"}
    assert signed_in(packer).post(f"{ORDERS}{order.number}/returns/", ask, format="json").status_code == 403
    created = signed_in(support).post(f"{ORDERS}{order.number}/returns/", ask, format="json")
    assert created.status_code == 201, created.content
    back, base = created.json(), f"{ORDERS}returns/{created.json()['id']}/"
    inbox = InboxItem.objects.get(kind="return_request", done_at=None)
    assert inbox.permission == "staff.handle_return" and timedelta(
        hours=47
    ) < inbox.due_at - timezone.now() <= timedelta(hours=48)
    assert signed_in(packer).post(base + "approve/").status_code == 403  # PACKER receives, never decides
    assert signed_in(support).post(base + "approve/").json()["status"] == "approved"
    assert InboxItem.objects.get(pk=inbox.pk).done_at is not None
    assert signed_in(support).post(base + "receive/").status_code == 403  # SUPPORT decides, never receives
    assert signed_in(packer).post(base + "receive/").json()["status"] == "received"
    assert (
        signed_in(packer).post(base + "inspect/", {"outcome": "restocked"}, format="json").json()["status"]
        == "restocked"
    )
    assert Product.objects.get(pk=book.pk).stock == stock + 2
    assert events("order.restocked", target_id=str(order.pk)).get().reason == f"Return {back['number']}"
    with commit():
        refund = signed_in(sales).post(
            f"{ORDERS}{order.number}/refunds/", {"return": back["id"], "reason": "Misprint"}, format="json"
        )
    assert refund.status_code == 201, refund.content
    assert refund.json()["payload"]["lines"] == [{"item": item.pk, "quantity": 2, "amount": "1000.00"}]
    assert refund.json()["payload"]["restock"] is False  # its inspection put the copies back already
    assert ReturnRequest.objects.get(pk=back["id"]).status == "refunded"
    assert Product.objects.get(pk=book.pk).stock == stock + 2  # once
    decline = signed_in(support).post(base + "decline/", {"note": "Late"}, format="json")
    assert decline.status_code == 400  # refunded: not possible now


def test_a_forgotten_order_takes_its_returns_photographs_with_it(rzp, commit):
    from django.core.files.uploadedfile import SimpleUploadedFile

    with commit():
        order = delivered(paid((ProductFactory(), 1)))
    back = services.request_return(order, [{"item": order.items.get().pk, "quantity": 1}], "other")
    photo = SimpleUploadedFile("parcel.jpg", b"\xff\xd8\xff" + b"0" * 100, content_type="image/jpeg")
    name = services.add_return_photo(back, photo).photos[0]
    assert default_storage.exists(name)
    nine_years_on = timezone.localdate() + timedelta(days=365 * 9)  # past the books' eight years
    assert services.forget_orders(Order.objects.filter(pk=order.pk), today=nine_years_on) == 1
    back.refresh_from_db()
    assert back.photos == [] and not default_storage.exists(name)  # the evidence goes with the details


def test_a_return_is_declined_with_its_reason_and_needs_one(rzp, commit):
    with commit():
        order = delivered(paid((ProductFactory(), 1)))
    back = services.request_return(order, [{"item": order.items.get().pk, "quantity": 1}], "other")
    client = signed_in(make_staff(roles.SUPPORT))
    assert client.post(f"{ORDERS}returns/{back.pk}/decline/", {}, format="json").status_code == 400
    with commit():
        done = client.post(f"{ORDERS}returns/{back.pk}/decline/", {"note": "Opened and written in"}, format="json")
    assert done.json()["status"] == "declined" and "Opened and written in" in mail.outbox[-1].body


def customer_api(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_the_customers_return_is_refused_after_the_window_and_before_delivery(rzp, settings):
    user = verified_user("rahul@example.com")
    book = ProductFactory(slug="physics-papers")
    order = paid((book, 1), user=user)
    api = customer_api(user)
    body = {"lines": [{"product": "physics-papers", "quantity": 1}], "reason": "damaged", "note": "Torn cover"}
    early = api.post(f"/api/v1/orders/{order.number}/returns/", body, format="json")
    assert early.status_code == 400 and "only a delivered order" in early.json()["non_field_errors"][0]
    order = delivered(order)
    Shipment.objects.filter(order=order).update(
        delivered_at=timezone.now() - timedelta(days=settings.SHOP_RETURN_DAYS, hours=1)
    )
    late = api.post(f"/api/v1/orders/{order.number}/returns/", body, format="json")
    assert late.status_code == 400 and "within 15 days of delivery" in late.json()["non_field_errors"][0]
    assert api.get(f"/api/v1/orders/{order.number}/").json()["can_return"] is False
    Shipment.objects.filter(order=order).update(delivered_at=timezone.now() - timedelta(days=2))
    assert api.get(f"/api/v1/orders/{order.number}/").json()["can_return"] is True
    made = api.post(f"/api/v1/orders/{order.number}/returns/", body, format="json")
    assert made.status_code == 201, made.content
    answer = made.json()
    assert answer["can_return"] is False and answer["returns"][0]["status"] == "requested"
    assert answer["returns"][0]["lines"] == [{"product": "physics-papers", "title": book.title, "quantity": 1}]
    back = ReturnRequest.objects.get()
    assert back.by_customer and back.note == "Torn cover" and back.requested_by == user
    assert events("order.return_requested").get().actor_type == "user"
    other = customer_api(verified_user("someone@example.com"))
    assert other.post(f"/api/v1/orders/{order.number}/returns/", body, format="json").status_code == 404


# Staff orders and quotes


def test_a_staff_discount_above_the_cap_makes_no_order_until_approved(commit):
    book = ProductFactory(price=Decimal("299"), mrp=Decimal("349"), stock=10)
    rep, finance = make_staff(roles.SALES_REP), make_staff(roles.FINANCE)
    before = Order.objects.count()
    body = {
        "channel": "phone",
        "lines": [{"product": book.slug, "quantity": 2}],
        "email": "School@Example.com",
        "address": ADDRESS,
        "discount": "200.00",
        "send_link": False,
        "note": "Promised by Friday",
        "reason": "A school's order by phone",
    }
    asked = signed_in(rep).post(ORDERS, body, format="json")
    assert asked.status_code == 202, asked.content  # 33.4 % off: above SALES_REP's 10 %
    change = asked.json()
    assert "beyond the limit of 10%" in change["rule"] and Order.objects.count() == before
    assert "school@example.com" not in json.dumps(change) and "Promised" not in json.dumps(change)  # encrypted
    done = approve_and_run(change, finance, commit)
    order = Order.objects.get(number=done["result"]["order"])
    assert (order.created_by, order.total.amount, order.discount.amount) == (rep, Decimal("398.00"), Decimal("200.00"))
    assert order.email == "school@example.com" and order.shipping_address["pin"] == "781001"
    assert Note.objects.get(target_type="shop.order", target_id=str(order.pk)).body == "Promised by Friday"


def test_the_form_previews_the_price_and_the_rule_before_anything_is_asked():
    book = ProductFactory(title="Physics Sample Papers", price=Decimal("299"), mrp=Decimal("349"), stock=10)
    rep = signed_in(make_staff(roles.SALES_REP))
    found = rep.get(ORDERS + "products/", {"q": "physics"}).json()
    assert [(row["slug"], row["price"], row["available"]) for row in found] == [(book.slug, "299.00", 10)]
    assert rep.get(ORDERS + "products/", {"q": "p"}).json() == []
    body = {"lines": [{"product": book.slug, "quantity": 2}], "state": "AS", "discount": "200.00"}
    above = rep.post(ORDERS + "preview/", body, format="json").json()
    assert (above["subtotal"], above["discount"], above["percent"], above["limit"]) == (
        "598.00",
        "200.00",
        "33.44",
        "10.00",
    )
    assert above["approval"] == "33.44% off is beyond the limit of 10%." and above["problems"] == []
    within = rep.post(ORDERS + "preview/", {**body, "discount": "50.00"}, format="json").json()
    assert within["approval"] is None and within["total"] == str(Decimal("548.00") + Decimal(within["shipping"]))
    short = rep.post(ORDERS + "preview/", {**body, "lines": [{"product": book.slug, "quantity": 11}]}, format="json")
    assert short.json()["problems"] == [f"Only 10 copies of {book} left."]
    assert Order.objects.count() == 0 and not AuditEvent.objects.filter(action__startswith="order.").exists()


def test_a_free_order_always_waits_and_a_small_discount_runs_at_once(commit):
    book = ProductFactory(price=Decimal("299"), mrp=Decimal("349"), stock=10)
    sales = make_staff(roles.SALES)
    body = {
        "channel": "school",
        "lines": [{"product": book.slug, "quantity": 1}],
        "email": "a@example.com",
        "address": ADDRESS,
        "send_link": False,
        "reason": "Specimen",
    }
    free = signed_in(sales).post(ORDERS, {**body, "discount": "299.00"}, format="json")
    assert free.status_code == 202 and free.json()["rule"].startswith("A ₹0 order")
    with commit():
        small = signed_in(sales).post(ORDERS, {**body, "discount": "29.00"}, format="json")  # 9.7 %: within 20 %
    assert small.status_code == 201 and Order.objects.filter(number=small.json()["result"]["order"]).exists()
    refused = signed_in(sales).post(ORDERS, {**body, "lines": [{"product": book.slug, "quantity": 99}]}, format="json")
    assert refused.status_code == 400 and "lines" in refused.json()  # 10 in stock: said before anyone approves


def test_an_address_without_its_state_takes_an_addresss_own_default_not_a_failure(commit):
    """The state is optional in an address (Address.state's default); a staff order or a quote's order without one
    was priced from `address["state"]` and failed with a 500 (the audit trail's walk found it)."""
    book = ProductFactory(price=Decimal("349"), mrp=Decimal("349"), stock=10)
    address = {name: value for name, value in ADDRESS.items() if name != "state"}
    body = {"channel": "phone", "lines": [{"product": book.slug, "quantity": 1}], "email": "a@example.com",
            "address": address, "send_link": False, "reason": "By phone"}  # fmt: skip
    with commit():
        made = signed_in(make_staff(roles.SALES)).post(ORDERS, body, format="json")
    assert made.status_code == 201, made.content
    order = Order.objects.get(number=made.json()["result"]["order"])
    assert order.shipping_address["state"] == "AS"


def test_a_quote_becomes_a_staff_order_once(commit):
    book = ProductFactory(slug="chemistry", price=Decimal("300"), mrp=Decimal("300"), stock=50)
    quote = QuoteRequest.objects.create(
        school="Cotton Collegiate",
        contact_name="Anita Das",
        email="office@example.com",
        phone="+919864012345",
        delivery_pin="781001",
        items=[{"product": "chemistry", "title": book.title, "quantity": 10}],
        discount_percent=Decimal("10"),
        shipping_fee=Decimal("100"),
    )
    client = signed_in(make_staff(roles.SALES))
    with commit():
        made = client.post(
            f"{ORDERS}quotes/{quote.pk}/convert/", {"address": ADDRESS, "send_link": False}, format="json"
        )
    assert made.status_code == 201, made.content
    quote.refresh_from_db()
    order = Order.objects.get(number=made.json()["result"]["order"])
    assert quote.order == order and quote.status == "ordered"
    assert (order.subtotal.amount, order.discount.amount, order.shipping_fee.amount) == (3000, 300, 100)
    again = client.post(f"{ORDERS}quotes/{quote.pk}/convert/", {"address": ADDRESS}, format="json")
    assert again.status_code == 400 and "already" in again.json()["non_field_errors"][0]
    assert client.get(f"{ORDERS}quotes/{quote.pk}/").json()["order"] == order.number


# Bulk actions as jobs


def test_a_bulk_cancel_of_251_orders_is_refused():
    client = signed_in(make_staff(roles.SALES))
    targets = [f"EL-2026-{n:06d}" for n in range(251)]
    body = {"kind": "orders_cancel", "params": {"targets": targets, "reason": "Out of print"}}
    refused = client.post(STAFF + "jobs/", body, format="json")
    assert refused.status_code == 400 and "At most 250 orders" in json.dumps(refused.json())


def test_bulk_mark_packed_runs_as_a_job_row_by_row(rzp, commit):
    good, held = paid((ProductFactory(), 1)), paid((ProductFactory(), 1))
    services.hold(held, "address issue")
    packer = make_staff(roles.PACKER)
    body = {"kind": "orders_pack", "params": {"targets": [good.number, held.number, "EL-2026-999999"]}}
    with commit():
        started = signed_in(packer).post(STAFF + "jobs/", body, format="json")
    assert started.status_code == 202, started.content
    job = Job.objects.get(pk=started.json()["id"])
    assert job.state == "done" and job.result["packed"] == 1
    assert {error["id"] for error in job.errors} == {held.number, "EL-2026-999999"}
    assert Order.objects.get(pk=good.pk).status == "packed" and Order.objects.get(pk=held.pk).status == "paid"


def test_the_export_job_holds_the_gst_fields_and_is_logged_without_personal_data(rzp, commit):
    paid((ProductFactory(), 2))
    finance = make_staff(roles.FINANCE)
    body = {"kind": "orders_export", "params": {"filters": {"status": "paid"}}}
    with commit():
        started = signed_in(finance).post(STAFF + "jobs/", body, format="json")
    assert started.status_code == 202, started.content
    job = Job.objects.get(pk=started.json()["id"])
    assert job.state == "done", job.errors
    rows = default_storage.open(job.result_file).read().decode().splitlines()
    assert rows[0].startswith("number,created") and "hsn,gst rate" in rows[0] and len(rows) == 2
    event = events("order.exported").get()
    assert event.details["rows"] == 1 and "rahul" not in json.dumps(event.details)
    assert (
        signed_in(finance)
        .post(STAFF + "jobs/", {"kind": "orders_export", "params": {"filters": {"q": "x"}}}, format="json")
        .status_code
        == 400
    )


# The packing room


def test_the_packing_queue_is_scoped_for_packer_and_leaves_out_held_orders(rzp, cod):
    online = paid((ProductFactory(), 1))
    by_cash = make_order((ProductFactory(), 1), method="cod", email="cash@example.com")
    services.place_cod(by_cash)
    held = paid((ProductFactory(), 1))
    services.hold(held, "address issue")
    unpaid = make_order((ProductFactory(), 1))
    done = delivered(paid((ProductFactory(), 1)))
    packer = signed_in(make_staff(roles.PACKER))
    queue = packer.get(ORDERS + "packing/").json()["results"]
    assert [row["number"] for row in queue] == [online.number, by_cash.number]  # oldest first
    assert queue[1]["is_cod"] is True and queue[0]["pick"][0]["quantity"] == 1
    assert packer.get(f"{ORDERS}{done.number}/").status_code == 404  # delivered: out of PACKER's scope
    assert packer.get(f"{ORDERS}{unpaid.number}/").status_code == 404
    assert packer.get(f"{ORDERS}{by_cash.number}/").status_code == 200  # placed to pay on delivery: in scope
    refused = packer.post(f"{ORDERS}{held.number}/pack/")
    assert refused.status_code == 400 and "on hold" in refused.json()["non_field_errors"][0]
    signed_in(make_staff(roles.SALES)).post(f"{ORDERS}{held.number}/release/")
    assert held.number in [row["number"] for row in packer.get(ORDERS + "packing/").json()["results"]]
    assert packer.post(f"{ORDERS}{held.number}/pack/").json()["status"] == "packed"


def test_the_print_endpoints_answer_pdfs_and_the_slip_names_its_books(rzp):
    book = ProductFactory(title="Physics Sample Papers 2027", isbn="978-93-0000-000-1")
    order = paid((book, 3))
    packer = signed_in(make_staff(roles.PACKER))
    for path in ["documents/packing-slip/", "documents/label/"]:
        response = packer.get(f"{ORDERS}{order.number}/{path}")
        assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    pick = packer.post(ORDERS + "pick-list/", {"orders": [order.number]}, format="json")
    assert pick.status_code == 200 and pick["Content-Type"] == "application/pdf"
    html = invoices.print_html(invoices.Print("packing_slip", [order]))
    assert order.number in html and "978-93-0000-000-1" in html and "data:image/svg+xml;base64," in html
    assert ">3<" in html.replace(" ", "")  # its copies
    assert signed_in(make_staff(roles.SUPPORT)).get(f"{ORDERS}{order.number}/documents/label/").status_code == 403


# Risk, holds, the timeline


def returned_before(pin_orders, address):
    """COD parcels that came back from this address's PIN code (the shipping app's outcomes)."""
    book = ProductFactory(stock=100)
    for n in range(pin_orders):
        order = make_order((book, 1), email=f"past{n}@example.com", **address)
        shipment = Shipment.objects.create(order=order, courier="India Post", tracking_number=f"EA{n}")
        ShipmentDetail.objects.create(shipment=shipment, carrier="manual", status="returned", cod_amount=299)


def test_a_high_cod_risk_holds_the_order_for_a_payment_check(cod, settings, commit):
    returned_before(10, {"pin": "781005"})
    order = make_order((ProductFactory(), 1), method="cod", email="new@example.com", pin="781005")
    with commit():
        order = services.place_cod(order)
    order.refresh_from_db()
    assert order.risk_bucket == "high" and order.held_at and order.hold_reason == "payment check"
    assert order.risk_reasons[0].endswith("of COD parcels to this PIN code come back")
    assert InboxItem.objects.get(kind="order_hold").title == f"Order {order.number} is on hold"
    assert events("order.held").get().actor_type == "system"
    staff = signed_in(make_staff(roles.OWNER))
    assert order.number not in [row["number"] for row in staff.get(ORDERS + "packing/").json()["results"]]
    row = staff.get(f"{ORDERS}?tab=to_pack").json()["results"]
    assert order.number not in [r["number"] for r in row]
    settings.SHOP_COD_HIGH_RISK_HOLD = False
    other = make_order((ProductFactory(), 1), method="cod", email="other@example.com", pin="781005")
    other = services.place_cod(other)
    other.refresh_from_db()
    assert other.risk_bucket == "high" and other.held_at is None


def test_the_record_carries_its_timeline_and_its_next_action(rzp, commit):
    with commit():
        order = paid((ProductFactory(), 1))
    owner, support = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    services.hold(order, "address issue", by=owner)
    services.release(Order.objects.get(pk=order.pk), by=owner)
    record = signed_in(owner).get(f"{ORDERS}{order.number}/").json()
    kinds = {entry["kind"] for entry in record["timeline"]}
    assert {"status", "payment", "message", "hold", "audit"} <= kinds
    assert [action["name"] for action in record["actions"] if action["primary"]] == ["pack"]
    assert record["customer"]["email"].startswith("ra•••@") and "+91" not in record["address"]["phone"]
    assert events("audit.read", target_id=str(order.pk)).exists()  # the owner read the log's events about it
    seen = signed_in(support).get(f"{ORDERS}{order.number}/").json()
    assert "audit" not in {entry["kind"] for entry in seen["timeline"]}
    assert "pack" not in [action["name"] for action in seen["actions"]] and "refund" in [
        a["name"] for a in seen["actions"]
    ]


def test_a_childs_order_opened_is_a_logged_read(rzp):
    child = verified_user("young@example.com")
    child.date_of_birth = date.today().replace(year=date.today().year - 15)
    child.save(update_fields=["date_of_birth"])
    order = paid((ProductFactory(), 1), user=child, email=child.email)
    signed_in(make_staff(roles.SUPPORT)).get(f"{ORDERS}{order.number}/")
    assert events("sensitive_read", target_id=str(order.pk)).get().details == {"what": "order", "child": True}


def test_a_cod_parcel_back_undelivered_cancels_the_order_and_credits_its_invoice(cod, commit):
    book = ProductFactory(stock=5)
    order = make_order((book, 1), method="cod")
    with commit():
        services.place_cod(order)
        services.pack_order(order)
        services.ship_order(order, "India Post", "EA9IN")
    shipment = Shipment.objects.get(order=order)
    ShipmentDetail.objects.create(shipment=shipment, carrier="manual", status="returned", cod_amount=299)
    with commit():
        done = signed_in(make_staff(roles.SALES)).post(
            f"{ORDERS}{order.number}/cancel/",
            {"reason": "Came back: refused at the door", "restock": True},
            format="json",
        )
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    note = CreditNote.objects.get()
    assert note.refund.method == "none" and note.refund.amount == order.total
    assert Product.objects.get(pk=book.pk).stock == 5
    assert not order.payments.filter(status="captured").exists()


def test_holds_tags_and_messages_again(rzp, commit):
    order = paid((ProductFactory(), 1))
    sales = signed_in(make_staff(roles.SALES))
    assert sales.post(
        f"{ORDERS}{order.number}/tags/", {"add": ["School", " awaiting  reprint "]}, format="json"
    ).json()["tags"] == ["awaiting reprint", "school"]
    assert sales.get(f"{ORDERS}?tag=school").json()["results"][0]["number"] == order.number
    assert sales.post(f"{ORDERS}{order.number}/hold/", {"reason": "Address issue"}, format="json").json()["held"]
    assert sales.post(f"{ORDERS}{order.number}/hold/", {"reason": "Again"}, format="json").status_code == 400
    assert not sales.post(f"{ORDERS}{order.number}/release/").json()["held"]
    assert sales.post(f"{ORDERS}{order.number}/notify/", {"kind": "shipped"}, format="json").status_code == 400
    before = OrderMessage.objects.filter(order=order).count()
    with commit():
        again = sales.post(f"{ORDERS}{order.number}/notify/", {"kind": "paid"}, format="json")
    assert again.status_code == 200 and OrderMessage.objects.filter(order=order).count() == before + 1


def test_the_invoice_is_made_from_the_button_once(rzp, commit):
    order = paid((ProductFactory(), 1))
    client = signed_in(make_staff(roles.SALES))
    with commit():
        made = client.post(f"{ORDERS}{order.number}/invoice/regenerate/")
    assert made.status_code == 202 and Order.objects.get(pk=order.pk).invoice.pdf
    assert client.post(f"{ORDERS}{order.number}/invoice/regenerate/").status_code == 400
    with commit():
        assert client.post(f"{ORDERS}{order.number}/invoice/resend/").status_code == 200
    assert mail.outbox[-1].subject.endswith(f"The invoice of order {order.number}")


def test_a_payment_link_is_sent_and_cancelled(rzp, commit):
    book = ProductFactory(stock=5)
    order = services.create_staff_order(
        [Line(book, 1)], by=make_staff(roles.SALES), email="a@example.com", address=ADDRESS
    )
    rzp.payment_link.create.return_value = {"id": "plink_1", "short_url": "https://rzp.io/i/abc"}
    client = signed_in(make_staff(roles.SALES))
    with commit():
        sent = client.post(f"{ORDERS}{order.number}/payment-link/", {"action": "send"}, format="json")
    assert sent.json()["url"] == "https://rzp.io/i/abc"
    assert client.post(f"{ORDERS}{order.number}/payment-link/", {"action": "cancel"}, format="json").status_code == 200
    rzp.payment_link.cancel.assert_called_once()
    rzp.payment_link.create.return_value = {"id": "plink_2", "short_url": "https://rzp.io/i/def"}
    with commit():
        new = client.post(f"{ORDERS}{order.number}/payment-link/", {"action": "send"}, format="json")
    assert new.json()["url"] == "https://rzp.io/i/def"


# Test mode, lookups, the weekly email, queries


def test_test_orders_stay_out_of_the_default_list_and_the_queue(settings, rzp):
    test_order = paid((ProductFactory(), 1))  # the site on test keys: a test-mode order
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # the site goes live
    live = paid((ProductFactory(), 1))
    assert Order.objects.get(pk=test_order.pk).is_test and not Order.objects.get(pk=live.pk).is_test
    client = signed_in(make_staff(roles.OWNER))
    assert [row["number"] for row in client.get(ORDERS).json()["results"]] == [live.number]
    shown = client.get(ORDERS + "?livemode=false").json()["results"]
    assert [row["number"] for row in shown] == [test_order.number] and shown[0]["is_test"] is True
    record = client.get(f"{ORDERS}{test_order.number}/")  # found with ?livemode=false, its record opens
    assert record.status_code == 200 and record.json()["is_test"] is True
    assert client.get(f"{ORDERS}{test_order.pk}/").json()["number"] == test_order.number  # the inbox's link: its id
    assert [row["number"] for row in client.get(ORDERS + "packing/").json()["results"]] == [live.number]


def test_a_persons_lookup_is_audited_by_its_hash_never_the_query(rzp):
    order = paid((ProductFactory(), 1), email="rahul.das@example.com")
    client = signed_in(make_staff(roles.SUPPORT))
    found = client.get(ORDERS, {"q": "Rahul.Das@example.com"}).json()["results"]
    assert [row["number"] for row in found] == [order.number]
    event = events("customer.lookup").get()
    assert event.details["kind"] == "email" and event.details["found"] == 1
    assert event.details["query"].startswith("hash:") and "rahul" not in json.dumps(event.details).lower()
    client.get(ORDERS, {"q": "2345"})  # a phone's last digits
    client.get(ORDERS, {"q": order.number})  # a number: no person
    assert [e.details["kind"] for e in events("customer.lookup")] == ["email", "phone"]


def test_the_weekly_email_is_sent_once_under_two_overlapping_runs(settings, commit):
    settings.STAFF_ALERT_EMAILS = ["owner@example.com"]
    sales = make_staff(roles.SALES, full_name="Rina Sales")
    book = ProductFactory(price=Decimal("500"), mrp=Decimal("500"), stock=10)
    order = services.create_staff_order([Line(book, 2)], by=sales, email="a@example.com", address=ADDRESS, discount=250)
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    Order.objects.filter(pk=order.pk).update(created=timezone.now() - timedelta(days=7))
    lock = "single-run:shop.tasks.weekly_staff_grants"
    cache.add(lock, "running", 300)  # a run in progress: this one does nothing
    with commit():
        assert tasks.weekly_staff_grants(today=monday) is None
    cache.delete(lock)
    with commit():
        tasks.weekly_staff_grants(today=monday)
        tasks.weekly_staff_grants(today=monday)  # delivered again: the week is marked sent
    sent = [message for message in mail.outbox if message.to == ["owner@example.com"]]
    assert len(sent) == 1 and order.number in sent[0].body and "Rina Sales" in sent[0].body
    assert "₹250.00 off (25.0% of the books)" in sent[0].body


def test_a_held_sms_waits_for_the_morning_and_goes_once(monkeypatch, commit, cod):
    from shipping import messages

    monkeypatch.setattr(messages, "quiet", lambda now=None: True)
    sent = []
    monkeypatch.setattr("ops.sms.send_order_sms", lambda order, kind: sent.append((order.number, kind)))
    user = verified_user("night@example.com")
    user.login_phone, user.login_phone_verified, user.sms_updates = "+919864012345", True, True
    user.save()
    order = make_order((ProductFactory(), 1), method="cod", user=user, email=user.email)
    with commit():
        services.place_cod(order)
    assert sent == [] and OrderMessage.objects.get(order=order, kind="confirmation").sms == "held"
    unlocked = tasks.send_held_sms.run.__wrapped__  # as while Redis is down: the claims alone keep it once
    assert unlocked() == 1 and unlocked() == 0 and sent == [(order.number, "confirmation")]


def queries(client, path):
    client.get(path)
    with CaptureQueriesContext(connection) as captured_:
        assert client.get(path).status_code == 200
    return len(captured_)


def test_the_lists_read_their_rows_at_once(rzp, commit):
    owner = signed_in(make_staff(roles.OWNER))

    def more(n):  # a row more in each list: an order to pack (tagged), a return, a quote
        with commit():
            order, done = paid((ProductFactory(), 1), (ProductFactory(), 2)), delivered(paid((ProductFactory(), 1)))
        services.set_tags(order, ["school", f"tag {n}"])
        services.request_return(done, [{"item": done.items.get().pk, "quantity": 1}], "late")
        QuoteRequest.objects.create(
            school=f"S{n}",
            contact_name="B",
            email="c@example.com",
            phone="+919864012345",
            delivery_pin="781001",
            items=[{"product": "x", "title": "X", "quantity": 1}],
        )

    more(0)
    paths = [ORDERS, ORDERS + "packing/", ORDERS + "returns/", ORDERS + "quotes/"]
    one = {path: queries(owner, path) for path in paths}
    more(1), more(2)
    assert {path: queries(owner, path) for path in paths} == one
