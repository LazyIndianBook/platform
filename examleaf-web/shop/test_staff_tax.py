"""The tax module's staff API (shop/staff_tax.py, /api/v1/staff/tax/): the HSN and SAC master and its new rates, the
products that disagree with it, the documents with their PDF and cancellation, Table 13, the thresholds card, the
calendar and the GSTR-1 job, with their permissions, audit events and query counts. Who may call what: the matrix
(staff/tests/test_matrix.py). The checkout's billing state: the website's API."""

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from shop import tax
from shop.factories import ProductFactory, captured, make_order, verified_user
from shop.models import Address, Cart, HsnRate, Invoice, Order, Product
from shop.test_tax import book, course, paid
from staff.models import AuditEvent, Job
from staff.tests.conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
TAX = STAFF + "tax/"
D = Decimal


@pytest.fixture
def live(settings, real_seller):
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    return settings


@pytest.fixture
def finance():
    return signed_in(make_staff(roles.FINANCE))


def events(action):
    return AuditEvent.objects.filter(action=action).order_by("id")


# The master


def test_finance_reads_the_master_with_todays_rates_and_a_change_to_come(finance):
    HsnRate.objects.create(
        hsn_id="4903", rate=D("5"), taxability="taxable", effective_from=timezone.localdate() + timedelta(days=30),
        notification="99/2026-Central Tax (Rate)", serial="7",
    )  # fmt: skip
    page = finance.get(TAX + "hsn/?page_size=50").json()
    codes = {row["code"]: row for row in page["results"]}
    assert len(codes) == 11 and [row["code"] for row in page["results"]] == sorted(codes)
    assert codes["4901"]["today"] == {
        "rate": "0.00",
        "taxability": "exempt",
        "effective_from": "2025-09-22",
        "notification": "10/2025-Central Tax (Rate)",
    }
    assert codes["4903"]["next_change"]["rate"] == "5.00" and codes["4901"]["next_change"] is None
    assert finance.get(TAX + "hsn/?kind=sac").json()["results"][0]["code"] == "9968"
    assert [row["code"] for row in finance.get(TAX + "hsn/?taxability=exempt").json()["results"]] == [
        "4820",
        "4901",
        "4903",
        "4905",
    ]
    assert [row["code"] for row in finance.get(TAX + "hsn/?q=coach").json()["results"]] == ["999293"]
    notebooks = finance.get(TAX + "hsn/4820/").json()
    assert [(row["rate"], row["until"]) for row in notebooks["rates"]] == [("12.00", "2025-09-21"), ("0.00", None)]
    assert finance.get(TAX + "hsn/4911/").status_code == 404


def test_a_code_is_added_with_its_first_rate_and_audited(finance):
    body = {
        "code": "4911",
        "kind": "hsn",
        "description": "Other printed matter",
        "first_rate": {
            "rate": "18.00",
            "taxability": "taxable",
            "effective_from": "2025-09-22",
            "notification": "9/2025-Central Tax (Rate)",
            "serial": "",
        },
    }
    made = finance.post(TAX + "hsn/", body, format="json")
    assert made.status_code == 201 and made.json()["today"]["rate"] == "18.00" and made.json()["uqc"] == "NOS"
    (event,) = events("tax.code_added")
    assert (event.target_type, event.target_id, event.details["rate"]) == ("shop.hsncode", "4911", "18.00")
    again = finance.post(TAX + "hsn/", body, format="json")
    assert again.status_code == 400 and "code" in again.json()
    service = finance.post(TAX + "hsn/", {**body, "code": "9985", "kind": "hsn"}, format="json")
    assert service.json() == {"code": ["A SAC code begins with 99, an HSN code never does."]}


def test_a_new_rate_starts_after_the_latest_and_never_rewrites_the_history(finance):
    rate = {"rate": "5.00", "taxability": "taxable", "notification": "99/2026-Central Tax (Rate)", "serial": "3"}
    earlier = finance.post(TAX + "hsn/4901/rates/", {**rate, "effective_from": "2025-09-22"}, format="json")
    assert (
        earlier.status_code == 400 and "after the latest one (22 September 2025)" in earlier.json()["effective_from"][0]
    )
    wrong = finance.post(
        TAX + "hsn/4901/rates/", {**rate, "rate": "0.00", "effective_from": "2027-04-01"}, format="json"
    )
    assert wrong.json() == {"rate": ["A taxable supply has a rate above 0."]}
    made = finance.post(TAX + "hsn/4901/rates/", {**rate, "effective_from": "2027-04-01"}, format="json")
    assert made.status_code == 201
    assert [row["effective_from"] for row in made.json()["rates"]] == ["2025-09-22", "2027-04-01"]
    assert made.json()["rates"][0]["until"] == "2027-03-31" and made.json()["next_change"]["rate"] == "5.00"
    assert events("tax.rate_added").get().details["effective_from"] == "2027-04-01"
    assert tax.rate_on("4901", date(2027, 4, 1)).rate == D("5.00")
    assert tax.rate_on("4901", date(2027, 3, 31)).rate == D("0.00")


def test_the_problems_report_lists_the_products_that_disagree(finance):
    agreeing, stale = book(), ProductFactory(hsn_id="4820", title="Lab notebook")
    Product.objects.filter(pk=stale.pk).update(gst_rate=12)
    ProductFactory(is_active=False)  # off sale: only with ?all=true
    rows = finance.get(TAX + "problems/").json()
    assert [row["title"] for row in rows] == ["Lab notebook"]
    assert rows[0]["problem"].startswith("GST 12.00% here, 0.00% in the master")
    assert len(finance.get(TAX + "problems/?all=true").json()) == 2
    assert agreeing.pk not in [row["id"] for row in rows]


# Documents


def test_documents_by_kind_series_month_and_state(live, rzp, commit, finance):
    books, mixed = paid((book(), 1)), paid((book(), 1), (course(), 1))
    online = make_order((book(), 2), email="online@example.com")
    from shop import services, tasks

    services.record_capture(captured(online))
    tasks.generate_invoice(online.pk)
    with commit():
        services.refund_order(Order.objects.get(pk=online.pk), "Changed my mind.")
        tax.cancel(books.invoice, "Issued twice.")
    listed = finance.get(TAX + "documents/").json()["results"]
    assert [row["number"] for row in listed] == [online.invoice.number, mixed.invoice.number, books.invoice.number]
    row = listed[1]
    assert (row["kind"], row["document_type"], row["key"], row["order"]) == (
        "invoice",
        "invoice_cum_bill_of_supply",
        mixed.invoice.number.replace("/", "-"),
        mixed.number,
    )
    assert (row["total"], row["taxable_value"], row["tax_amount"]) == ("1298.00", "846.61", "152.39")
    notes = finance.get(TAX + "documents/?kind=credit_note").json()["results"]
    assert [(note["against"], note["total"]) for note in notes] == [(online.invoice.number, "598.00")]
    month = f"{timezone.localdate():%Y-%m}"
    assert len(finance.get(TAX + f"documents/?month={month}&series=EL").json()["results"]) == 3
    cancelled = finance.get(TAX + "documents/?cancelled=true").json()["results"]
    assert [row["number"] for row in cancelled] == [books.invoice.number] and cancelled[0]["cancel_reason"]
    assert [row["number"] for row in finance.get(TAX + "documents/?document_type=bill_of_supply").json()["results"]]
    assert finance.get(TAX + f"documents/?search={mixed.number}").json()["results"][0]["order"] == mixed.number
    assert finance.get(TAX + "documents/?test=true").json()["results"] == []
    assert finance.get(TAX + "documents/?month=October").json() == {"month": ["A month: YYYY-MM."]}
    assert finance.get(TAX + "documents/?kind=receipt").status_code == 400


def test_a_document_with_its_lines_and_its_pdf_whose_look_is_audited(live, finance):
    order = paid((book(), 2), (course(), 1))
    key = order.invoice.number.replace("/", "-")
    detail = finance.get(TAX + f"documents/{key}/").json()
    assert detail["title"] == "Invoice-cum-bill of supply" and detail["checks"] == []
    assert [(line["hsn_code"], line["rate"], line["amount"]) for line in detail["lines"]] == [
        ("4901", "0.00", "598.00"),
        ("999293", "18.00", "999.00"),
    ]
    assert detail["round_off"] == "0.00" and detail["credit_notes"] == []
    pdf = finance.get(TAX + f"documents/{key}/pdf/", HTTP_ACCEPT="application/pdf")
    assert pdf.status_code == 200 and b"".join(pdf.streaming_content).startswith(b"%PDF")
    (read,) = events("sensitive_read")
    assert (read.target_type, read.target_label, read.details) == (
        "shop.invoice",
        order.invoice.number,
        {"what": "pdf"},
    )
    assert finance.get(TAX + "documents/EL-2026-27-99999/").status_code == 404
    assert finance.get(TAX + "documents/not-a-number/").status_code == 404


def test_cancelling_asks_who_is_there_and_why_and_keeps_the_number(live, finance, commit):
    order = paid((book(), 1))
    key = order.invoice.number.replace("/", "-")
    user = make_staff(roles.FINANCE)
    stale = signed_in(user, reauth=False).post(TAX + f"documents/{key}/cancel/", {"reason": "Twice."}, format="json")
    assert stale.status_code == 403 and stale.json()["code"] == "reauthentication_required"
    assert finance.post(TAX + f"documents/{key}/cancel/", {}, format="json").json() == {
        "reason": ["This field is required."]
    }
    with commit():
        done = finance.post(TAX + f"documents/{key}/cancel/", {"reason": "Issued twice."}, format="json")
    assert done.status_code == 200 and done.json()["number"] == order.invoice.number and done.json()["cancelled_at"]
    event = events("tax.document_cancelled").get()
    assert (event.target_id, event.target_label, event.reason) == (
        str(order.invoice.pk),
        order.invoice.number,
        "Issued twice.",
    )
    assert event.permission == "staff.cancel_document"
    again = finance.post(TAX + f"documents/{key}/cancel/", {"reason": "Issued twice."}, format="json")
    assert again.status_code == 400 and "cancelled already" in again.json()["non_field_errors"][0]


# Table 13, the card, the calendar


def test_table_13_counts_each_series_and_its_cancelled(live, finance, commit):
    first, second = paid((book(), 1)), paid((book(), 1))
    with commit():
        tax.cancel(first.invoice, "Issued in error.")
    register = finance.get(TAX + "series/").json()
    (row,) = register["rows"]
    assert (row["series"], row["nature"], row["first"], row["last"], row["total"], row["cancelled"]) == (
        "EL",
        "Invoices for outward supply",
        first.invoice.number,
        second.invoice.number,
        2,
        1,
    )
    assert (
        row["next_number"] == 3 and register["series_from"] == "2027-28" and register["prefixes"]["tax_invoice"] == "TI"
    )
    month = finance.get(TAX + f"series/?month={timezone.localdate():%Y-%m}").json()
    assert month["rows"][0]["total"] == 2
    assert finance.get(TAX + "series/?financial_year=2019-20").json()["rows"] == []
    assert finance.get(TAX + "series/?financial_year=2019").status_code == 400


def test_the_threshold_card_and_the_calendar(finance, settings):
    card = finance.get(TAX + "thresholds/").json()
    assert card["as_of"] is None and card["rows"] == [] and card["qrmp"] is True and card["hsn_digits"] == 4
    tax.watch_thresholds()
    card = finance.get(TAX + "thresholds/").json()
    assert card["as_of"] == timezone.localdate().isoformat() and len(card["rows"]) == 6
    assert {row["line"]: row["count"] for row in card["rows"]}["b2c_large"] is True
    calendar = finance.get(TAX + "calendar/?month=2026-11").json()
    assert [item["key"] for item in calendar["items"]] == ["iff", "pmt06", "credit_note_cutoff"]
    assert calendar["qrmp"] is True and calendar["crossed"] == []
    assert finance.get(TAX + "calendar/?month=11-2026").status_code == 400


# The GSTR-1 job


def test_the_gstr1_job_gives_the_months_files_zipped(live, finance, django_capture_on_commit_callbacks):
    paid((book(), 1), (course(), 1))
    month = f"{timezone.localdate():%Y-%m}"
    with django_capture_on_commit_callbacks(execute=True):
        started = finance.post(TAX + "gstr1/", {"month": month}, format="json")
    assert started.status_code == 202 and started.json()["kind"] == "gstr1_export"
    job = Job.objects.get()
    assert (job.state, job.total, job.result["invoices"]) == ("done", 1, 1)
    link = finance.get(STAFF + f"jobs/{job.pk}/").json()["result_url"]
    answer = finance.get(link)
    archive = zipfile.ZipFile(io.BytesIO(b"".join(answer.streaming_content)))
    assert sorted(name.split("-", 3)[3] for name in archive.namelist()) == sorted(
        f"{name}.csv" for name in ("b2cl", "b2cs", "cdnur", "exemp", "hsn-b2b", "hsn-b2c", "docs", "credit-notes")
    )
    assert events("tax.gstr1_exported").get().details["invoices"] == 1
    quarter = finance.post(TAX + "gstr1/", {"month": "2026-09", "months": 3}, format="json")
    assert quarter.status_code == 202 and quarter.json()["params"] == {"month": "2026-09", "months": 3}
    later = f"{timezone.localdate() + timedelta(days=40):%Y-%m}"
    assert finance.post(TAX + "gstr1/", {"month": later}, format="json").json() == {
        "params": {"month": ["A month that has begun."]}
    }
    assert finance.post(TAX + "gstr1/", {"month": "2026-08", "months": 3}, format="json").json() == {
        "params": {"months": ["A quarter ends with June, September, December or March."]}
    }


def test_a_gstr1_job_above_the_export_limit_waits_for_an_approver(live, settings):
    settings.STAFF_TEST_MODE = False
    paid((book(), 1))
    paid((book(), 1), user=verified_user("second@example.com"))
    from accounts.roles import ROLE_LIMITS

    limits = {**ROLE_LIMITS[roles.FINANCE], "export_rows": 1}
    settings_patch = {**ROLE_LIMITS, roles.FINANCE: limits}
    from unittest.mock import patch

    with patch.dict("accounts.roles.ROLE_LIMITS", settings_patch):
        started = signed_in(make_staff(roles.FINANCE)).post(
            TAX + "gstr1/", {"month": f"{timezone.localdate():%Y-%m}"}, format="json"
        )
    assert started.status_code == 202 and started.json()["change_request_id"]
    assert Job.objects.get().state == "queued"


# Query counts


def queries(client, path):
    client.get(path)
    with CaptureQueriesContext(connection) as captured_queries:
        assert client.get(path).status_code == 200
    return len(captured_queries)


def test_the_lists_read_their_rows_at_once(live, finance):
    paid((book(), 1))
    documents, codes = queries(finance, TAX + "documents/"), queries(finance, TAX + "hsn/")
    for email in ("b@example.com", "c@example.com", "d@example.com"):
        paid((book(), 1), (course(), 1), user=verified_user(email))
    HsnRate.objects.create(
        hsn_id="4903", rate=D("5"), taxability="taxable", effective_from=date(2030, 4, 1), notification="x"
    )
    assert queries(finance, TAX + "documents/") == documents
    assert queries(finance, TAX + "hsn/") == codes


# The checkout's billing state (the website's API)


def test_a_course_alone_takes_the_billing_state_given_at_checkout_and_books_refuse_another(live):
    buyer = verified_user("riya@example.com")
    address = Address.objects.create(
        user=buyer, name="Riya Das", phone="+919864012210", line1="House 4", city="Guwahati",
        district="Kamrup Metro", state="AS", pin="781001",
    )  # fmt: skip
    api = APIClient()
    api.force_authenticate(buyer)
    api.post("/api/v1/cart/items/", {"product": course().slug}, format="json")
    made = api.post(
        "/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay", "billing_state": "WB"}, format="json"
    )
    assert made.status_code == 201, made.content
    assert Order.objects.get(number=made.json()["number"]).billing_state == "WB"
    Cart.objects.filter(user=buyer).delete()
    api.post("/api/v1/cart/items/", {"product": book().slug}, format="json")
    refused = api.post(
        "/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay", "billing_state": "WB"}, format="json"
    )
    assert refused.status_code == 400
    assert "taxed in the state they are delivered to" in refused.json()["non_field_errors"][0]
    same = api.post(
        "/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay", "billing_state": "AS"}, format="json"
    )
    assert same.status_code == 201 and Order.objects.get(number=same.json()["number"]).billing_state == "AS"
    unknown = api.post(
        "/api/v1/orders/", {"address": address.pk, "payment_method": "razorpay", "billing_state": "ZZ"}, format="json"
    )
    assert unknown.status_code == 400 and "billing_state" in unknown.json()
    assert Invoice.objects.count() == 0
