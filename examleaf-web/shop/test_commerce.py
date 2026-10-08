"""Phase 5 B: tracking links, reviews, school quotations, stock alerts and the GSTR-1 export (the website's forms post
to the API, as here; the bot check: shop/test_api_contract.py, test_api_guest.py)."""

import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import DeletionRequest
from ops import sms
from shop import invoices, services, tasks
from shop.factories import ProductFactory, ShippingRateFactory, captured, make_order, verified_user
from shop.models import Product, QuoteRequest, Review, Shipment, StockAlert

pytestmark = pytest.mark.django_db


@pytest.fixture
def cod(settings):
    settings.SHOP_COD_ENABLED = True


def placed(*lines, **kwargs):
    """A cash-on-delivery order, placed (stock taken)."""
    return services.place_cod(make_order(*lines, method="cod", **kwargs))


def test_shipping_fills_in_the_couriers_tracking_page(cod, commit):
    order = services.pack_order(placed((ProductFactory(), 1)))
    with commit():
        services.ship_order(order, "Delhivery", "1234567")
    assert order.shipments.get().tracking_url == "https://www.delhivery.com/track-v2/package/1234567"
    assert "Track it: https://www.delhivery.com/track-v2/package/1234567" in mail.outbox[-1].body
    assert Shipment.tracking_url_for("India Post", "EA123456789IN") == "https://t.17track.net/en#nums=EA123456789IN"
    assert Shipment.tracking_url_for("Blue Dart", " 12/34 ").endswith("trackNo=12%2F34")


def delivered(product, user):
    """`user`'s cash-on-delivery order of `product`, delivered."""
    order = services.pack_order(placed((product, 1), user=user, email=user.email))
    services.ship_order(order, "India Post", "EA1IN")
    return services.deliver_order(order)


def test_buyers_review_after_delivery_and_staff_approve(client, cod):
    product, buyer = ProductFactory(slug="physics"), verified_user("buyer@example.com")
    url = "/api/v1/products/physics/reviews/"  # the product page's reviews and form

    def write(rating, text):
        return client.post(url, {"rating": rating, "text": text}, content_type="application/json")

    client.force_login(buyer)
    order = placed((product, 1), user=buyer, email=buyer.email)
    assert client.get(url).json()["can_review"] is False  # not delivered yet
    write(5, "Too early")
    assert not Review.objects.exists()
    services.ship_order(services.pack_order(order), "India Post", "EA1IN")
    services.deliver_order(order)
    assert client.get(url).json()["can_review"] is True
    write(4, "Good <b>papers</b>")
    write(1, "Twice")  # one review per book and account
    review = Review.objects.get()
    assert (review.rating, review.status) == (4, Review.Status.PENDING)
    assert client.get(url).json()["count"] == 0  # not approved yet
    admin = UserFactory(is_staff=True, is_superuser=True)  # with an authenticator app
    client.force_login(admin)
    changelist = reverse("admin:shop_review_changelist")
    assert client.get(reverse("admin:shop_review_change", args=[review.pk])).status_code == 200
    client.post(changelist, {"action": "approve", "_selected_action": [review.pk]})
    shown = client.get(url)
    assert (shown.json()["average"], shown.json()["count"]) == ("4.0", 1)  # the page's rating
    assert shown.json()["results"][0]["text"] == "Good <b>papers</b>" and "buyer@example.com" not in shown.text
    assert Review.history.filter(status=Review.Status.APPROVED, history_user=admin).exists()


def test_reviews_go_with_the_account(cod):
    buyer = verified_user("buyer@example.com")
    product = ProductFactory()
    delivered(product, buyer)
    Review.objects.create(product=product, user=buyer, rating=5, text="Mine")
    DeletionRequest.objects.create(user=buyer, due_at=timezone.now()).complete()
    assert not Review.objects.exists() and not Review.history.exists()


QUOTE = {
    "school": "Cotton Collegiate H.S. School",
    "contact_name": "Anjali Bora",
    "email": "office@school.example",
    "phone": "98640 12345",
    "gstin": " 27aapfu0939f1zv ",
    "delivery_pin": "781 001",
}


def test_schools_ask_for_a_quotation_and_staff_are_emailed(client, commit):
    ProductFactory(slug="physics", title="Physics Sample Papers")
    sales = UserFactory(email="sales@examleaf.in", is_staff=True)
    sales.groups.set([Group.objects.get(name=roles.SALES)])
    url = "/api/v1/quotes/"  # the website's school orders page

    def ask(**data):
        return client.post(url, {**QUOTE, **data}, content_type="application/json")

    ProductFactory(slug="pass", title="Physics Revision Pass", kind=Product.Kind.DIGITAL, stock=0)
    course = ask(items=[{"product": "pass", "quantity": 40}])  # courses go by book code
    assert course.json() == {"non_field_errors": ["Enter the number of copies of at least one book."]}
    books = [{"product": "physics", "quantity": 40}]
    assert "Enter a valid 15-character GSTIN" in ask(gstin="27AAPFU0939F1ZX", items=books).text
    assert not QuoteRequest.objects.exists()
    with commit():
        response = ask(items=books)
    assert response.status_code == 201
    quote = QuoteRequest.objects.get()
    assert (quote.gstin, quote.delivery_pin, quote.status) == ("27AAPFU0939F1ZV", "781001", QuoteRequest.Status.NEW)
    assert quote.items == [{"product": "physics", "title": "Physics Sample Papers", "quantity": 40}]
    assert mail.outbox[-1].to == ["sales@examleaf.in"] and "40 x Physics Sample Papers" in mail.outbox[-1].body
    assert f"/admin/shop/quoterequest/{quote.pk}/change/" in mail.outbox[-1].body


def test_a_quotation_follows_a_product_renamed_since_the_request():
    product = ProductFactory(slug="physics-2026", price=299)
    product.slug = "physics-2027"
    product.save()
    quote = QuoteRequest.objects.create(
        **{**QUOTE, "gstin": "", "phone": "+919864012345", "delivery_pin": "781001"},
        items=[{"product": "physics-2026", "title": "Physics", "quantity": 40}],
    )
    assert [line["product"] for line in invoices.quotation_context(quote)["lines"]] == [product]


def test_staff_make_a_quotation_pdf_valid_15_days(client):
    ProductFactory(slug="physics", price=299)
    items = [
        {"product": "physics", "title": "Physics", "quantity": 40},
        {"product": "gone", "title": "Old", "quantity": 1},
    ]
    fields = {**QUOTE, "gstin": "", "delivery_pin": "781001", "phone": "+919864012345"}
    quote = QuoteRequest.objects.create(**fields, items=items, discount_percent=10, shipping_fee=150)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    client.post(
        reverse("admin:shop_quoterequest_changelist"), {"action": "make_quotation", "_selected_action": [quote.pk]}
    )
    quote.refresh_from_db()
    assert quote.status == QuoteRequest.Status.QUOTED and quote.quotation.name.startswith("quotations/QT-")
    assert quote.valid_until == timezone.localdate() + timedelta(days=15)
    page = client.get(reverse("admin:shop_quoterequest_change", args=[quote.pk])).content.decode()
    assert "40 × Physics" in page and f"{quote.number}.pdf</a>, valid until" in page
    download = client.get(reverse("admin:shop_quoterequest_quotation", args=[quote.pk]))
    assert download["Content-Disposition"] == f'attachment; filename="ExamLeaf-{quote.number}.pdf"'
    context = invoices.quotation_context(quote)  # the book no longer sold is left out
    assert (context["books"], context["discount"], context["total"]) == (
        Decimal("11960.00"),
        Decimal("1196.00"),
        Decimal("10914.00"),
    )
    client.logout()
    assert client.get(reverse("admin:shop_quoterequest_quotation", args=[quote.pk])).status_code == 302  # log in


@pytest.mark.real_pdf
def test_quotation_pdf(real_seller):
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("WeasyPrint's system libraries (Pango) are not installed")
    ProductFactory(slug="physics")
    quote = QuoteRequest.objects.create(
        **{**QUOTE, "gstin": "", "delivery_pin": "781001"}, items=[{"product": "physics", "title": "P", "quantity": 2}]
    )
    assert services.make_quotation(quote).quotation.read().startswith(b"%PDF")


def test_stock_alerts_email_once_when_the_book_is_back(client, settings):
    product = ProductFactory(slug="physics", stock=0)
    url = "/api/v1/products/physics/stock-alert/"  # the product page's "Email me when it is back"

    def ask(**data):
        return client.post(url, data, content_type="application/json")

    assert ask(email="stranger@example.com").status_code in (401, 403) and not StockAlert.objects.exists()  # L3
    client.force_login(verified_user("member@example.com"))
    ask(email="ignored@example.com")  # an account: its own address
    client.force_login(verified_user("Rahul@Example.com"))
    ask()
    ask()  # once per address
    assert sorted(StockAlert.objects.values_list("email", flat=True)) == ["member@example.com", "rahul@example.com"]
    tasks.send_stock_alerts()
    assert not mail.outbox  # still out of stock
    Product.objects.filter(pk=product.pk).update(stock=3)
    tasks.send_stock_alerts()
    assert sorted(m.to[0] for m in mail.outbox) == ["member@example.com", "rahul@example.com"]
    assert "http://localhost:8000/shop/physics/" in mail.outbox[0].body and not StockAlert.objects.exists()
    tasks.send_stock_alerts()
    assert len(mail.outbox) == 2


def test_sales_hear_each_morning_of_books_running_out(settings, commit):
    settings.SHOP_LOW_STOCK = 5
    ProductFactory(title="Physics", stock=2)
    ProductFactory(title="Chemistry", stock=5)
    ProductFactory(title="Biology", stock=0, is_active=False)
    sales = UserFactory(email="sales@examleaf.in", is_staff=True)
    sales.groups.set([Group.objects.get(name=roles.SALES)])
    with commit():
        tasks.low_stock_report()
    assert mail.outbox[0].to == ["sales@examleaf.in"] and "2 left: Physics" in mail.outbox[0].body
    assert "Chemistry" not in mail.outbox[0].body and "Biology" not in mail.outbox[0].body
    Product.objects.update(stock=50)
    with commit():
        tasks.low_stock_report()
    assert len(mail.outbox) == 1  # nothing to report: no email


def read_csv(path):
    with open(path, newline="") as file:
        return list(csv.reader(file))


def test_gstr1_export_for_the_accountant(rzp, settings, commit, real_seller, tmp_path):
    ShippingRateFactory(name="Rest of India", states=[], fee=50, free_above=None)
    test_series = make_order((ProductFactory(), 1))  # Razorpay test keys: the T series, never exported
    services.record_capture(captured(test_series))
    tasks.generate_invoice(test_series.pk)
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    stationery = ProductFactory(price=Decimal("112.00"), mrp=Decimal("112.00"), gst_rate=12, hsn_code="4820")
    assam = make_order((stationery, 1), (ProductFactory(price=299), 2), state="AS", pin="781001")
    delhi = make_order((ProductFactory(price=299), 1), state="DL", pin="110001")
    for order in (assam, delhi):
        services.record_capture(captured(order))
        tasks.generate_invoice(order.pk)
    with commit():
        services.cancel_order(delhi, "Changed my mind.")  # refunded in full: a credit note
    today, out = timezone.localdate().isoformat(), io.StringIO()
    call_command("export_gstr1", "--from", today, "--to", today, "--out", str(tmp_path), stdout=out)
    assert "2 invoices, 1 credit notes" in out.getvalue()
    prefix = tmp_path / f"gstr1-{today.replace('-', '')}-{today.replace('-', '')}"
    assert read_csv(f"{prefix}-b2c.csv") == [
        ["place_of_supply", "rate", "invoices", "taxable_value", "igst", "cgst", "sgst", "shipping"],
        ["07-Delhi", "0.00", "1", "299.00", "0.00", "0.00", "0.00", "50.00"],
        ["18-Assam", "0.00", "0", "598.00", "0.00", "0.00", "0.00", "0"],
        ["18-Assam", "12.00", "1", "100.00", "0.00", "6.00", "6.00", "50.00"],  # its shipping: the highest rate
    ]
    assert read_csv(f"{prefix}-hsn.csv")[1:] == [
        ["4820", "NOS", "12.00", "1", "112.00", "100.00", "0.00", "6.00", "6.00"],
        ["4901", "NOS", "0.00", "3", "897.00", "897.00", "0.00", "0.00", "0.00"],
    ]
    (note,) = read_csv(f"{prefix}-credit-notes.csv")[1:]
    assert note[4:] == ["07-Delhi", "0.00", "299.00", "0.00", "0.00", "0.00", "50.00"]
    assert note[0].startswith("CN/") and note[2] == delhi.invoice.number


def test_order_sms_go_out_from_the_notification_path(cod, commit, monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "send_order_sms", lambda order, kind: sent.append((order.number, kind)))
    with commit():
        order = placed((ProductFactory(), 1))
    with commit():
        delivered_order = services.pack_order(order)
        services.ship_order(delivered_order, "Delhivery", "1234567")
        services.deliver_order(delivered_order)
    assert sent == [(order.number, "confirmation"), (order.number, "shipped"), (order.number, "delivered")]
