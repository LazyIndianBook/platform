"""Tax (plan 5.9; shop/tax.py, shop/invoices.py, shop/gstr1.py): the HSN and SAC master read by date, the bundles'
treatments, the billing state, the shipping that follows the goods, the coupon's share of each line, the documents'
types and series (gapless, a new year from 1, never given twice), credit notes' cut-off, cancelling a document, the
GSTR-1 sections, the threshold monitor, the calendar, the products that disagree with the master, the records kept.
The staff API: shop/test_staff_tax.py."""

import csv
import io
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import connection, connections, transaction
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from erp import contract
from shop import gstr1, invoices, services, tasks, tax
from shop.factories import CouponFactory, ProductFactory, ShippingRateFactory, captured, make_order, verified_user
from shop.models import (
    BundleItem,
    Cart,
    CreditNote,
    DocumentSeries,
    DocumentType,
    HsnCode,
    Invoice,
    Order,
    Product,
    Refund,
    SeriesFull,
    TaxThreshold,
    financial_year,
)
from staff.models import InboxItem

pytestmark = pytest.mark.django_db
INDIA = ZoneInfo("Asia/Kolkata")
D = Decimal


@pytest.fixture
def live(settings, real_seller):
    """Razorpay's live keys: orders and their documents in the real series, by a seller whose details are set."""
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    return settings


def book(price="299.00", mrp=None, **fields):
    """A printed book on the master (HSN 4901: exempt)."""
    return ProductFactory(hsn_id="4901", price=D(price), mrp=D(mrp or price), weight_grams=300, **fields)


def course(price="999.00", **fields):
    """The revision course on the master (SAC 999293: 18 %)."""
    fields = {"kind": Product.Kind.DIGITAL, "stock": 0, **fields}
    return ProductFactory(hsn_id="999293", price=D(price), mrp=D(fields.pop("mrp", price)), **fields)


def bundle(*components, price, treatment=Product.TaxTreatment.SPLIT):
    made = ProductFactory(kind=Product.Kind.BUNDLE, price=D(price), mrp=D(price), tax_treatment=treatment, stock=0)
    for component, quantity in components:
        BundleItem.objects.create(bundle=made, product=component, quantity=quantity)
    return made


def paid(*lines, user=None, **kwargs):
    """An order paid (offline, as staff record it) and invoiced, as the task after the payment does."""
    user = user or verified_user("rahul@example.com")
    order = make_order(*lines, user=user, email=user.email, **kwargs)
    services.record_offline_payment(order, "NEFT UTR 401234567890")
    tasks.generate_invoice(order.pk)
    Cart.objects.filter(user=user).delete()  # the next order is made from a new cart
    return Order.objects.get(pk=order.pk)


def paid_online(*lines, **kwargs):
    """An order paid through Razorpay (the `rzp` fixture's) and invoiced: refunds go back through it."""
    order = make_order(*lines, **kwargs)
    services.record_capture(captured(order))
    tasks.generate_invoice(order.pk)
    return Order.objects.get(pk=order.pk)


def at(moment):
    """A fixed `timezone.now()` (India's wall clock)."""
    fixed = moment.replace(tzinfo=INDIA)
    return lambda: fixed


# The HSN and SAC master


def test_the_master_is_seeded_with_its_sources():
    codes = dict(HsnCode.objects.values_list("code", "kind"))
    assert {"4901", "4903", "4905", "4820", "998431", "999293", "9988", "4802", "4810", "9968", "9971"} <= set(codes)
    assert codes["999293"] == "sac" and codes["4901"] == "hsn"
    books = tax.rate_on("4901", date(2026, 10, 9))
    assert (books.rate, books.taxability, books.notification, books.serial) == (
        D("0.00"),
        "exempt",
        "10/2025-Central Tax (Rate)",
        "132",
    )
    assert tax.rate_on("999293", date(2026, 10, 9)).rate == D("18.00")
    assert tax.rate_on("998431", date(2026, 10, 9)).rate == D("5.00")
    assert tax.rate_on("9988", date(2026, 10, 9)).rate == D("5.00")
    assert tax.rate_on("4802", date(2026, 10, 9)).rate == tax.rate_on("9971", date(2026, 10, 9)).rate == D("18.00")


def test_the_hsn_rate_is_read_by_date_across_the_22_september_2025_change():
    before, after = tax.rate_on("4820", date(2025, 9, 21)), tax.rate_on("4820", date(2025, 9, 22))
    assert (before.rate, before.taxability) == (D("12.00"), "taxable")
    assert (after.rate, after.taxability, after.serial) == (D("0.00"), "exempt", "130")
    assert [row.until for row in tax.history("4820")] == [date(2025, 9, 21), None]
    assert tax.rate_on("4901", date(2025, 9, 21)) is None  # the master begins with that day for unchanged codes
    notebook = ProductFactory(hsn_id="4820", gst_rate=12)  # saved: today's rate and the code's text from the master
    assert (notebook.gst_rate, notebook.hsn_code) == (0, "4820")
    assert tax.order_line(notebook, date(2025, 9, 21)) == {"hsn_code": "4820", "gst_rate": D("12.00"), "parts": None}
    assert tax.order_line(notebook, date(2025, 9, 22))["gst_rate"] == 0
    # a code the master does not know keeps the product's own fields (and its chip says so)
    loose = ProductFactory(hsn_code="4911", gst_rate=12)
    assert tax.order_line(loose, date(2026, 10, 9))["gst_rate"] == 12


def test_a_rate_that_has_ended_gives_no_rate_until_the_next_one():
    from shop.models import HsnRate

    HsnRate.objects.create(
        hsn_id="4903", rate=0, taxability="exempt", effective_from=date(2030, 1, 1), effective_to=date(2030, 6, 30),
        notification="test", serial="1",
    )  # fmt: skip
    assert tax.rate_on("4903", date(2030, 3, 1)).effective_from == date(2030, 1, 1)
    assert tax.rate_on("4903", date(2030, 7, 1)) is None
    assert tax.rates_on(["4903", "4901"], date(2030, 7, 1)).keys() == {"4901"}


def test_the_products_that_disagree_with_the_master_get_a_red_chip(settings):
    agreeing, stale, loose = book(), ProductFactory(hsn_id="4820"), ProductFactory()
    Product.objects.filter(pk=stale.pk).update(gst_rate=12)  # the rate changed after it was saved
    stale.refresh_from_db()
    wrong_kind = ProductFactory(kind=Product.Kind.DIGITAL, hsn_id="4901", stock=0)  # a course on a goods code
    mixed = bundle((book(), 1), (course(), 1), price="1100.00", treatment=Product.TaxTreatment.MIXED)
    split = bundle((loose, 1), (course(), 1), price="1100.00")
    found = tax.problems([agreeing, stale, loose, wrong_kind, mixed, split])
    assert agreeing.pk not in found and agreeing.tax_problem == ""
    assert (
        found[stale.pk] == "GST 12.00% here, 0.00% in the master from 22 September 2025 (10/2025-Central Tax (Rate))."
    )
    assert stale.tax_problem == found[stale.pk]
    assert found[loose.pk] == "Not on the HSN and SAC master: choose its code."
    assert found[wrong_kind.pk].startswith("4901 is a goods code: choose a SAC code")
    assert found[mixed.pk] == "Its treatment (mixed) taxes it at 18.00%; its rate here is 0.00%."
    assert found[split.pk] == f"{loose.title}: Not on the HSN and SAC master: choose its code."
    settings.SHOP_HSN_DIGITS = 6
    assert tax.problems([agreeing])[agreeing.pk] == "4901 has 4 digits; documents need 6 (SHOP_HSN_DIGITS)."


def test_the_chips_of_a_whole_catalogue_take_a_few_queries():
    products = [book() for _ in range(3)] + [bundle((book(), 1), (course(), 1), price="900.00")]
    with CaptureQueriesContext(connection) as few:
        tax.problems(products[:1])
    with CaptureQueriesContext(connection) as many:
        tax.problems(products)
    assert len(many) <= len(few) + 1 and len(many) <= 4


# Bundles


def test_a_price_shared_over_copies_adds_up_exactly():
    assert tax.apportion(D("1000.00"), [D("249"), D("999")], [1, 1]) == [(D("199.52"), D("0")), (D("800.48"), D("0"))]
    # two copies of one book and one course: the paisa the copies cannot share goes to the single copy
    shares = tax.apportion(D("1000.01"), [D("498"), D("999")], [2, 1])
    assert sum(unit * quantity for (unit, _extra), quantity in zip(shares, [2, 1], strict=True)) == D("1000.01")
    assert all(extra == 0 for _unit, extra in shares)
    # every component of several copies and an odd price: rounded up, the paisa given back as a discount
    assert tax.apportion(D("599.99"), [D("599.98")], [2]) == [(D("300.00"), D("0.01"))]


def test_a_split_bundle_invoices_its_components_with_the_price_shared_by_their_mrps(live):
    papers, pass_ = book("249.00"), course("999.00")
    pack = bundle((papers, 1), (pass_, 1), price="1000.00")
    order = paid((pack, 1), coupon=CouponFactory(value=10))  # 10 % off: 100.00 over the bundle's parts
    data = invoices.context(order.invoice)
    assert [(line["item"].title, line["value"], line["discount"], line["item"].gst_rate) for line in data["lines"]] == [
        (papers.title, D("199.52"), D("19.95"), D("0.00")),
        (pass_.title, D("800.48"), D("80.05"), D("18.00")),
    ]
    assert all(line["bundle"] == pack.title for line in data["lines"])
    assert order.invoice.document_type == DocumentType.INVOICE_CUM_BILL
    assert sum(line["amount"] for line in data["lines"]) == order.total.amount  # nothing to ship: a course and a book
    item = order.items.get()
    assert (item.hsn_code, item.gst_rate, len(item.parts)) == (pack.hsn_code, pack.gst_rate, 2)  # the line itself
    # ERPNext receives the components, and its lines add up to the total
    payload = contract.invoice(order.invoice)
    assert [line["item_code"] for line in payload["items"]] == [contract.item_code(papers), contract.item_code(pass_)]
    charged = sum(D(line["rate"]) * line["qty"] - D(line["discount"]) for line in payload["items"])
    assert (
        charged + D(payload["shipping_fee"]) == D(payload["total"])
        and payload["doc_kind"] == "invoice_cum_bill_of_supply"
    )


def test_composite_and_mixed_bundles_invoice_one_line_at_their_treatments_rate(live):
    papers, pass_ = book("249.00"), course("999.00")
    composite = bundle((papers, 1), (pass_, 1), price="1000.00", treatment=Product.TaxTreatment.COMPOSITE)
    mixed = bundle((papers, 1), (pass_, 1), price="1000.00", treatment=Product.TaxTreatment.MIXED)
    heavy_book = bundle((book("1499.00"), 1), (pass_, 1), price="1800.00", treatment=Product.TaxTreatment.COMPOSITE)
    lines = {product: tax.order_line(product, date(2026, 10, 9)) for product in (composite, mixed, heavy_book)}
    assert lines[composite] == {"hsn_code": "999293", "gst_rate": D("18.00"), "parts": None}  # the course: most of it
    assert lines[mixed] == {"hsn_code": "999293", "gst_rate": D("18.00"), "parts": None}  # the highest rate
    assert lines[heavy_book] == {"hsn_code": "4901", "gst_rate": D("0.00"), "parts": None}  # the book: most of it
    order = paid((heavy_book, 1))
    assert [line["item"].title for line in invoices.context(order.invoice)["lines"]] == [heavy_book.title]
    assert order.invoice.document_type == DocumentType.BILL_OF_SUPPLY


# The billing state, the shipping, the coupon


def test_a_course_alone_is_supplied_in_the_state_the_buyer_gives_else_their_address_else_assam(live):
    buyer = verified_user("riya@example.com")
    elsewhere = make_order((course(), 1), user=buyer, email=buyer.email, state="WB", pin="700001")
    assert elsewhere.billing_state == "WB"
    lines = [type("Line", (), {"product": course()})()]
    assert tax.billing_state(lines, {"state": "MH"}, "KA") == "KA"
    assert tax.billing_state(lines, {"state": "MH"}) == "MH"
    assert tax.billing_state(lines, None) == "AS"
    assert tax.billing_state([type("Line", (), {"product": book()})()], {"state": "MH"}, "KA") == "MH"
    services.record_offline_payment(elsewhere, "UPI 123456789012")
    tasks.generate_invoice(elsewhere.pk)
    data = invoices.context(Invoice.objects.get(order=elsewhere))
    assert (data["place_of_supply"], data["intra_state"], data["lines"][0]["igst"]) == (
        "West Bengal (19)",
        False,
        D("152.39"),
    )


def test_the_shipping_follows_the_goods_it_carries(live):
    ShippingRateFactory(name="Everywhere", states=[], fee=D("40.00"), free_above=None)
    books = paid((book(), 2))
    data = invoices.context(books.invoice)
    assert [(c["rate"], c["amount"], c["taxable"]) for c in data["charges"]] == [(D("0.00"), D("40.00"), D("40.00"))]
    assert (books.invoice.taxable_value, books.invoice.exempt_value, books.invoice.tax_amount) == (0, D("638.00"), 0)
    # a book and the course: the course ships nothing, so the shipping is the book's, exempt like it
    mixed = paid((book(), 1), (course(), 1))
    assert [(c["rate"], c["amount"]) for c in invoices.context(mixed.invoice)["charges"]] == [(D("0.00"), D("40.00"))]
    assert mixed.invoice.tax_amount == D("152.39")
    # goods at two rates: the shipping shared by their values and taxed with each
    taxed_goods = ProductFactory(price=D("100.00"), mrp=D("100.00"), gst_rate=12)  # not on the master: its own rate
    both = paid((book(), 1), (taxed_goods, 1))
    charges = invoices.context(both.invoice)["charges"]
    assert [(c["rate"], c["amount"], c["taxable"]) for c in charges] == [
        (D("0.00"), D("29.97"), D("29.97")),
        (D("12.00"), D("10.03"), D("8.96")),
    ]
    data = invoices.context(both.invoice)
    assert sum(line["amount"] for line in data["lines"]) + sum(c["amount"] for c in charges) == both.total.amount
    assert data["round_off"] == 0


def test_a_cart_coupon_is_shared_over_the_lines_in_proportion_and_shown_on_each(live):
    order = paid((book("299.00"), 1), (course("999.00"), 1), coupon=CouponFactory(value=10))
    lines = invoices.context(order.invoice)["lines"]
    assert [line["discount"] for line in lines] == [D("29.90"), D("99.90")]
    assert sum(line["discount"] for line in lines) == order.discount.amount == D("129.80")
    assert (lines[1]["amount"], lines[1]["taxable"]) == (D("899.10"), D("761.95"))  # the course's taxable value
    html = render_to_string("shop/invoice.html", invoices.pdf_context(order.invoice))
    assert "29.90" in html and "99.90" in html


# Document types and the PDF


def test_books_alone_get_a_bill_of_supply_a_mixed_cart_an_invoice_cum_bill_of_supply(live):
    books, mixed, course_alone = paid((book(), 2)), paid((book(), 1), (course(), 1)), paid((course(), 1))
    kinds = [order.invoice.document_type for order in (books, mixed, course_alone)]
    assert kinds == ["bill_of_supply", "invoice_cum_bill_of_supply", "tax_invoice"]
    assert [invoices.context(order.invoice)["title"] for order in (books, mixed, course_alone)] == [
        "Bill of supply",
        "Invoice-cum-bill of supply",
        "Tax invoice",
    ]
    html = render_to_string("shop/invoice.html", invoices.pdf_context(mixed.invoice))
    assert "Invoice-cum-bill of supply" in html and "Reverse charge" in html and "Assam (18)" in html
    for mark in ["Original for recipient", "Duplicate for transporter", "Triplicate for supplier"]:
        assert mark in html  # goods: three copies (Rule 48)
    assert "Printed books, including Braille books (HSN 4901): exempt under Notification 10/2025-Central Tax" in html
    assert "serial number 132" in html
    services_only = render_to_string("shop/invoice.html", invoices.pdf_context(course_alone.invoice))
    assert "Duplicate for supplier" in services_only and "transporter" not in services_only
    assert ">9992<" in services_only  # SAC 999293 printed to SHOP_HSN_DIGITS (4)


@pytest.mark.real_pdf
def test_the_pdf_renders_with_its_copies(live):
    order = paid((book(), 1), (course(), 1))
    invoice = Invoice.objects.get(order=order)
    assert invoice.pdf.read().startswith(b"%PDF")


# Number series


def test_numbers_run_on_without_a_gap_when_a_document_is_rolled_back():
    day = date(2026, 10, 9)
    with pytest.raises(RuntimeError), transaction.atomic():
        tax.number(Invoice, DocumentType.BILL_OF_SUPPLY, day=day)
        raise RuntimeError("the document failed")
    assert tax.number(Invoice, DocumentType.BILL_OF_SUPPLY, day=day)["number"] == "EL/2026-27/00001"
    assert tax.number(Invoice, DocumentType.TAX_INVOICE, day=day)["number"] == "EL/2026-27/00002"  # one EL series
    assert tax.number(CreditNote, DocumentSeries.Type.CREDIT_NOTE, day=day)["number"] == "CN/2026-27/00001"
    assert tax.number(Invoice, DocumentType.TAX_INVOICE, live=False, day=day)["number"] == "T/2026-27/00001"
    assert tax.number(CreditNote, DocumentSeries.Type.CREDIT_NOTE, live=False, day=day)["number"] == "TC/2026-27/00001"


def test_a_series_made_after_its_documents_goes_on_after_their_last_number(live):
    order = paid((book(), 1))
    DocumentSeries.objects.all().delete()  # numbered before the series existed (the EL series of 2026-27)
    Invoice.objects.filter(pk=order.invoice.pk).update(serial=7, number="EL/2026-27/00007")
    assert tax.number(Invoice, DocumentType.BILL_OF_SUPPLY, day=date(2026, 10, 9))["serial"] == 8


def test_a_new_financial_year_starts_its_series_at_1(live, monkeypatch):
    live.SHOP_SERIES_FROM_FY = "2030-31"  # the shared EL series both years
    monkeypatch.setattr(timezone, "now", at(datetime(2027, 3, 31, 23, 30)))
    march = paid((book(), 1))
    monkeypatch.setattr(timezone, "now", at(datetime(2027, 4, 1, 0, 10)))
    april = paid((book(), 1))
    assert (march.invoice.number, april.invoice.number) == ("EL/2026-27/00001", "EL/2027-28/00001")
    assert (march.invoice.financial_year, april.invoice.financial_year) == ("2026-27", "2027-28")


def test_from_the_series_year_each_type_has_its_own_series(settings):
    day = date(2027, 4, 1)  # SHOP_SERIES_FROM_FY: 2027-28
    numbers = [
        tax.number(Invoice, DocumentType.TAX_INVOICE, day=day)["number"],
        tax.number(Invoice, DocumentType.BILL_OF_SUPPLY, day=day)["number"],
        tax.number(Invoice, DocumentType.INVOICE_CUM_BILL, day=day)["number"],
        tax.number(CreditNote, DocumentSeries.Type.CREDIT_NOTE, day=day)["number"],
    ]
    assert numbers == ["TI/2027-28/00001", "BS/2027-28/00001", "IB/2027-28/00001", "CN/2027-28/00001"]
    assert all(len(number) == 16 for number in numbers)
    settings.SHOP_SERIES_PREFIXES = {**settings.SHOP_SERIES_PREFIXES, "tax_invoice": "SI"}  # the CA's prefix
    assert tax.number(Invoice, DocumentType.TAX_INVOICE, day=day)["number"] == "SI/2027-28/00001"


def test_a_full_series_refuses_a_number_longer_than_16_characters():
    tax.number(Invoice, DocumentType.TAX_INVOICE, day=date(2026, 10, 9))
    DocumentSeries.objects.update(next_number=DocumentSeries.MAX_SERIAL + 1)
    with pytest.raises(SeriesFull):
        tax.number(Invoice, DocumentType.TAX_INVOICE, day=date(2026, 10, 9))


postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs row locks (select_for_update)")


@postgres_only
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_invoices_numbered_at_once_take_consecutive_numbers(settings, real_seller):
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    orders = []
    for email in ("a@example.com", "b@example.com"):
        order = make_order((book(), 1), email=email)
        services.record_offline_payment(order, "NEFT 401234567890")
        orders.append(order)
    barrier, numbers = threading.Barrier(2), []

    def number(order):
        try:
            barrier.wait()
            numbers.append(Invoice.for_order(order).number)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=number, args=(order,)) for order in orders]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    year = Invoice.objects.first().financial_year
    assert sorted(numbers) == [f"EL/{year}/00001", f"EL/{year}/00002"]
    assert DocumentSeries.objects.get(prefix="EL").next_number == 3


# Credit notes and cancelling


def test_a_credit_note_is_refused_after_30_november_and_the_refund_still_goes_out(live, rzp, monkeypatch, commit):
    order = paid_online((book(), 1))
    invoice = order.invoice
    deadline = tax.credit_note_deadline(invoice.financial_year)
    assert deadline == date(tax.year_start(invoice.financial_year) + 1, 11, 30)
    monkeypatch.setattr(timezone, "now", at(datetime.combine(deadline + timedelta(days=1), datetime.min.time())))
    with commit():
        refund = services.refund_order(Order.objects.get(pk=order.pk), "The parcel came back.")
    refund.refresh_from_db()
    assert refund.status == Refund.Status.PROCESSED  # the money went out
    assert not CreditNote.objects.filter(refund=refund).exists()
    item = InboxItem.objects.get(kind=InboxItem.Kind.CREDIT_NOTE_MISSING)
    assert (item.target_type, item.target_id, item.permission) == (
        "shop.refund",
        str(refund.pk),
        "staff.cancel_document",
    )
    assert "30 November" in item.data["reason"] and order.number in item.title
    assert tax.refund_problem(refund) == item.data["reason"]
    tasks.generate_credit_note(refund.pk)  # the nightly clean-up asks again: one item, no note
    assert InboxItem.objects.filter(kind=InboxItem.Kind.CREDIT_NOTE_MISSING).count() == 1


def test_a_cancelled_document_keeps_its_number(live, commit):
    first = paid((book(), 1))
    with commit():
        cancelled = tax.cancel(first.invoice, "Issued twice for one parcel.")
    assert (cancelled.number, cancelled.cancel_reason) == (first.invoice.number, "Issued twice for one parcel.")
    second = paid((book(), 1))
    assert second.invoice.serial == first.invoice.serial + 1  # never given again
    with pytest.raises(ValueError, match="cancelled already"):
        tax.cancel(cancelled, "Again.")
    assert tax.credit_note_problem(cancelled).startswith(f"Invoice {cancelled.number} is cancelled")


def test_an_invoice_with_a_credit_note_is_cancelled_after_its_note(live, rzp, commit):
    order = paid_online((book(), 1))
    with commit():
        services.refund_order(order, "Damaged.")
    invoice, note = Invoice.objects.get(order=order), CreditNote.objects.get()
    with pytest.raises(ValueError, match=f"Cancel its credit notes first: {note.number}"):
        tax.cancel(invoice, "Wrong buyer.")
    with commit():
        tax.cancel(note, "Raised in error.")
        tax.cancel(invoice, "Wrong buyer.")
    assert Invoice.objects.get(pk=invoice.pk).cancelled_at is not None


# GSTR-1


def read(path):
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.reader(file))


def test_the_gstr1_sections_of_a_month(live, rzp, commit, tmp_path, settings):
    ShippingRateFactory(name="Everywhere", states=[], fee=D("40.00"), free_above=None)
    settings.RAZORPAY_KEY_ID = "rzp_test_key"  # made with test keys: the T series, never exported
    test_series = paid((book(), 1), user=verified_user("tester@example.com"))
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    assam = paid((book(), 2), (course(), 1))  # intra-state: CGST and SGST on the course; the books and shipping exempt
    bengal = paid_online((course(), 1), user=verified_user("wb@example.com"), email="wb@example.com", state="WB",
                         pin="700001")  # fmt: skip
    machines = ProductFactory(price=D("60000.00"), mrp=D("60000.00"), gst_rate=18, hsn_code="8471", stock=5)
    delhi = paid((machines, 2), user=verified_user("dl@example.com"), state="DL", pin="110001")  # B2C large
    void = paid((book(), 1), user=verified_user("void@example.com"))
    with commit():
        services.refund_order(bengal, "Changed my mind.")  # a B2C small credit note, netted in b2cs
        tax.cancel(void.invoice, "Issued in error.")
    today = timezone.localdate()
    paths, counts = gstr1.export(today, today, tmp_path)
    assert counts == {"invoices": 3, "credit_notes": 1, "cancelled": 1}
    files = {path.name.split("-", 3)[3].removesuffix(".csv"): read(path) for path in paths}
    assert files["b2cl"][1:] == [
        [delhi.invoice.number, f"{today:%d-%b-%Y}", f"{delhi.total.amount:.2f}", "07-Delhi", "", "18.00",
         f"{delhi.invoice.taxable_value:.2f}", "0.00", ""],
    ]  # fmt: skip
    b2cs = {(row[1], row[3]): row[4] for row in files["b2cs"][1:]}
    assert b2cs == {("18-Assam", "18.00"): "846.61", ("19-West Bengal", "18.00"): "0.00"}  # Bengal's netted out
    exemp = {row[0]: row[1:] for row in files["exemp"][1:]}
    assert exemp["Intra-State supplies to unregistered persons"] == ["0.00", "638.00", "0.00"]  # 2 books + shipping
    assert exemp["Inter-State supplies to unregistered persons"] == ["0.00", "0.00", "0.00"]
    hsn = {(row[0], row[5]): row for row in files["hsn-b2c"][1:]}
    assert hsn["4901", "0.00"][2:5] == ["NOS", "2", "638.00"]
    assert hsn["9992", "18.00"][2:4] == ["NA", "2"] and hsn["9992", "18.00"][6] == "846.61"  # Bengal's back out
    assert hsn["8471", "18.00"][3] == "2"
    assert files["hsn-b2b"] == [gstr1.HEADERS["hsn-b2b"]]
    docs = {row[0]: row[1:] for row in files["docs"][1:]}
    first, last = sorted([assam.invoice.number, delhi.invoice.number, void.invoice.number, bengal.invoice.number])[::3]
    assert docs["Invoices for outward supply"] == [first, last, "4", "1"]
    assert docs["Credit Note"][2:] == ["1", "0"]
    assert files["cdnur"] == [gstr1.HEADERS["cdnur"]]
    (note_row,) = files["credit-notes"][1:]
    assert note_row[2] == bengal.invoice.number and note_row[4] == "19-West Bengal"
    assert all(test_series.invoice.number not in row for rows in files.values() for row in rows)


def test_a_credit_note_against_a_b2c_large_invoice_goes_to_cdnur(live, rzp, commit, tmp_path):
    machines = ProductFactory(price=D("60000.00"), mrp=D("60000.00"), gst_rate=18, hsn_code="8471", stock=5)
    order = paid_online((machines, 2), state="DL", pin="110001")
    shipped = services.ship_order(services.pack_order(order), "India Post", "EA123456789IN")
    with commit():
        services.refund_order(shipped, "One damaged.", amount=D("60000"))
    today = timezone.localdate()
    paths, _counts = gstr1.export(today, today, tmp_path)
    cdnur = read(next(path for path in paths if path.name.endswith("-cdnur.csv")))[1:]
    note = CreditNote.objects.get()
    assert [row[:6] for row in cdnur] == [["B2CL", note.number, f"{today:%d-%b-%Y}", "C", "07-Delhi", "60000.00"]]


def test_the_export_reads_its_documents_in_chunks_whatever_their_number(live, tmp_path):
    def queries():
        with CaptureQueriesContext(connection) as captured:
            gstr1.build(timezone.localdate(), timezone.localdate())
        return len(captured)

    for email in ("a@example.com", "b@example.com"):
        paid((book(), 1), (course(), 1), user=verified_user(email))
    few = queries()
    for email in ("c@example.com", "d@example.com", "e@example.com", "f@example.com"):
        paid((book(), 1), (course(), 1), user=verified_user(email))
    assert queries() == few


def test_the_command_writes_the_files(live, tmp_path):
    paid((book(), 1))
    today = timezone.localdate().isoformat()
    out = io.StringIO()
    call_command("export_gstr1", "--from", today, "--to", today, "--out", str(tmp_path / "out"), stdout=out)
    assert "1 invoices, 0 credit notes, 0 cancelled" in out.getvalue()
    assert sorted(path.name.split("-", 3)[3] for path in (tmp_path / "out").iterdir()) == sorted(
        f"{name}.csv" for name in gstr1.HEADERS
    )


# The threshold monitor and the calendar


def turnover_of(amount, day):
    """An invoice of the real series worth `amount` (exempt) on `day`'s financial year, its totals kept."""
    order = make_order((book(), 1))
    label = financial_year(day)
    serial = Invoice.objects.count() + 1
    return Invoice.objects.create(
        order=order, number=f"EL/{label}/{serial:05d}", financial_year=label, serial=serial, series="EL",
        document_type="bill_of_supply", taxable_value=0, exempt_value=D(amount), tax_amount=0,
    )  # fmt: skip


def test_crossing_4_crore_opens_one_inbox_item(monkeypatch):
    night = date(2026, 10, 9)
    turnover_of("30000000.00", night)  # ₹3 crore: past GSTR-9's ₹2 crore
    tax.watch_thresholds(night)
    assert list(InboxItem.objects.values_list("title", flat=True)) == ["Turnover of FY 2026-27 passed ₹2 crore"]
    turnover_of("11000000.00", night)  # ₹4.1 crore the next night
    tax.watch_thresholds(night + timedelta(days=1))
    tax.watch_thresholds(night + timedelta(days=1))  # run again: nothing new
    tax.watch_thresholds(night + timedelta(days=2))  # still past it: nothing new
    warned = InboxItem.objects.filter(kind=InboxItem.Kind.TAX_THRESHOLD, title__contains="₹4 crore")
    assert warned.count() == 1 and warned.get().permission == "shop.change_hsncode"
    assert InboxItem.objects.filter(kind=InboxItem.Kind.TAX_THRESHOLD).count() == 2
    rows = {row.line: row for row in TaxThreshold.objects.filter(date=night + timedelta(days=1))}
    assert rows["warning"].crossed and not rows["e_invoice"].crossed and rows["warning"].value == D("41000000.00")


def test_the_counts_of_large_invoices_and_parcels_needing_an_e_way_bill(live):
    machines = ProductFactory(price=D("60000.00"), mrp=D("60000.00"), gst_rate=18, hsn_code="8471", stock=5)
    delhi = paid((machines, 2), state="DL", pin="110001")
    paid((book(), 1), user=verified_user("small@example.com"))
    rows = {row.line: row for row in tax.watch_thresholds()}
    assert rows["b2c_large"].detail == {"numbers": [delhi.invoice.number]} and rows["b2c_large"].value == 1
    assert rows["eway_bill"].detail == {"numbers": [delhi.invoice.number]}
    assert InboxItem.objects.filter(kind=InboxItem.Kind.TAX_THRESHOLD).count() == 2


def test_the_turnover_fills_the_totals_of_documents_numbered_before_they_were_kept(live):
    order = paid((book(), 2), (course(), 1))
    Invoice.objects.update(taxable_value=None, exempt_value=None, tax_amount=None)
    assert tax.turnover(order.invoice.financial_year) == D("846.61") + D("598.00")
    assert Invoice.objects.get().taxable_value == D("846.61")


def test_the_calendar_of_a_month_under_qrmp_and_monthly(settings):
    october = tax.calendar(2026, 10, qrmp=True, today=date(2026, 10, 15))
    assert [(item["key"], item["due"].day, item["past"]) for item in october] == [
        ("gstr1", 13, True),
        ("gstr3b", 24, False),
        ("rule42", 24, False),
        ("tds", 31, False),
    ]
    assert october[0]["covers"] == "July to September 2026"
    monthly = tax.calendar(2026, 10, qrmp=False, today=date(2026, 10, 1))
    assert [(item["key"], item["due"].day) for item in monthly] == [("gstr1", 11), ("gstr3b", 20), ("rule42", 20),
                                                                      ("tds", 31)]  # fmt: skip
    november = tax.calendar(2026, 11, qrmp=True)
    assert [(item["key"], item["due"].day) for item in november] == [("iff", 13), ("pmt06", 25),
                                                                       ("credit_note_cutoff", 30)]  # fmt: skip
    assert november[-1]["covers"] == "Invoices of FY 2025-26"
    december = tax.calendar(2026, 12, qrmp=True)
    gstr9 = next(item for item in december if item["key"] == "gstr9")
    assert gstr9["due"] == date(2026, 12, 31) and gstr9["applies"] is False  # not past ₹2 crore
    settings.SHOP_SELLER = {**settings.SHOP_SELLER, "state": "MH"}
    assert next(item for item in tax.calendar(2027, 1, qrmp=True) if item["key"] == "gstr3b")["due"].day == 22


# Records kept


def test_tax_records_are_not_forgotten_before_their_72_months(live):
    kept = paid((book(), 1))
    old = paid((book(), 1), user=verified_user("old@example.com"))
    Invoice.objects.filter(pk=old.invoice.pk).update(financial_year="2017-18")  # kept until 31 December 2024
    assert tax.retained_until("2025-26") == date(2032, 12, 31)
    assert services.forget_orders(Order.objects.filter(pk__in=[kept.pk, old.pk])) == 1
    assert Order.objects.get(pk=kept.pk).email == "rahul@example.com"
    assert Order.objects.get(pk=old.pk).email == services.DELETED
