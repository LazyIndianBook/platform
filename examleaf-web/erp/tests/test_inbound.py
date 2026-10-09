"""What ERPNext tells the platform: its signed doorbells (a valid, a wrong, a missing and a replayed signature; the
previous secret for a day), the B2B documents read again and mirrored, the stock read with get_stock and kept as
snapshots, the projection of the copies for sale on and off, and the 15-minute pull page by page from its cursor."""

from datetime import timedelta

import pytest
from django.utils import timezone

from erp import contract, inbound
from erp.client import client
from erp.fake import FAKE
from erp.models import ErpCursor, ErpMirror, ErpStockSnapshot
from integrations.models import InboundEvent, IntegrationAccount

from .helpers import WEBHOOK_SECRET, code, ordered, pay_offline, relay, row, ship_by_hand, stock_in

pytestmark = pytest.mark.django_db
HOOK = "/api/hooks/erp-events/"


def ring(client_, raw, signature):
    return client_.post(HOOK, raw, content_type="application/json", HTTP_X_FRAPPE_WEBHOOK_SIGNATURE=signature)


def school(name="St. Mary's School, Jorhat", **fields):
    return FAKE.add_b2b("Customer", customer_name=name, customer_group="School", territory="Jorhat", **fields)


def test_a_signed_doorbell_is_kept_answered_at_once_and_read_again(on, client, django_capture_on_commit_callbacks):
    name = FAKE.add_b2b("Quotation", party_name="St. Mary's School", grand_total=12000, status="Open")
    raw, signature = FAKE.webhook("Quotation", name, WEBHOOK_SECRET)
    with django_capture_on_commit_callbacks(execute=True):
        assert ring(client, raw, signature).json() == {"detail": "Received."}
    mirror = ErpMirror.objects.get(doctype="Quotation", name=name)
    assert (mirror.status, mirror.data["party_name"], mirror.data["grand_total"]) == (
        "Open",
        "St. Mary's School",
        12000,
    )
    event = InboundEvent.objects.get(provider="erpnext")
    assert event.state == "accepted" and event.processed_at and event.error == ""
    assert "X-Frappe-Webhook-Signature" not in event.headers  # never kept
    with django_capture_on_commit_callbacks(execute=True):  # the same ring again (Frappe's retry, or a replay)
        assert ring(client, raw, signature).status_code == 200
    assert InboundEvent.objects.filter(provider="erpnext").count() == 1


def test_a_wrong_or_missing_signature_is_refused(on, client):
    raw, signature = FAKE.webhook("Quotation", "SAL-QTN-00001", "not the secret")
    assert ring(client, raw, signature).status_code == 403
    assert ring(client, raw, "").status_code == 403
    tampered, good = FAKE.webhook("Quotation", "SAL-QTN-00001", WEBHOOK_SECRET)
    assert ring(client, tampered.replace(b"Quotation", b"Customer"), good).status_code == 403
    rejected = InboundEvent.objects.filter(provider="erpnext")
    assert rejected.count() == 3 and {e.state for e in rejected} == {"rejected"} and not any(e.body for e in rejected)


def test_the_previous_secret_works_for_a_day_after_a_rotation(on, client):
    raw, old = FAKE.webhook("Quotation", "SAL-QTN-00001", WEBHOOK_SECRET)
    new_secret = on.rotate_webhook_token()
    assert ring(client, raw, old).status_code == 200
    IntegrationAccount.objects.filter(pk=on.pk).update(webhook_rotated_at=timezone.now() - timedelta(hours=25))
    other, old = FAKE.webhook("Quotation", "SAL-QTN-00002", WEBHOOK_SECRET)
    assert ring(client, other, old).status_code == 403
    other, new = FAKE.webhook("Quotation", "SAL-QTN-00002", new_secret)
    assert ring(client, other, new).status_code == 200


def test_doorbells_are_refused_while_erpnext_is_switched_off(erp_account, client):
    raw, signature = FAKE.webhook("Quotation", "SAL-QTN-00001", WEBHOOK_SECRET)
    assert ring(client, raw, signature).status_code == 403  # ERP_ENABLED off


def test_what_is_not_b2b_or_not_read_is_ignored(on):
    assert inbound.apply("Sales Order", "SAL-ORD-1") == "ignored: Sales Order is not read"
    ours = FAKE.add_b2b("Sales Invoice", customer="Online Customers (B2C)")
    assert inbound.apply("Sales Invoice", ours) == "ignored: not a B2B document"
    parent = FAKE.add_b2b("Customer", customer_name="A parent", customer_group="Online B2C")
    assert inbound.apply("Customer", parent) == "ignored: not a B2B document"
    gone = school()
    assert inbound.apply("Customer", gone) == ""
    del FAKE.docs[("Customer", gone)]
    assert inbound.apply("Customer", gone) == "gone: its mirror deleted" and not ErpMirror.objects.exists()


def test_a_b2b_invoice_is_mirrored_without_contacts(on):
    name = FAKE.add_b2b(
        "Sales Invoice",
        customer="St. Mary's School",
        customer_group="School",
        grand_total=45000,
        outstanding_amount=45000,
        status="Unpaid",
        contact_email="principal@stmarys.example",
        contact_mobile="9864012345",
        items=[{"item_code": "EL-00001", "qty": 150, "rate": 300, "amount": 45000}],
    )
    assert inbound.apply("Sales Invoice", name) == ""
    mirror = ErpMirror.objects.get(name=name)
    assert mirror.status == "Unpaid" and mirror.data["items"] == [
        {"item_code": "EL-00001", "item_name": None, "qty": 150, "rate": 300, "amount": 45000}
    ]
    assert "contact_email" not in mirror.data and "contact_mobile" not in mirror.data


def test_a_stock_doorbell_reads_the_stock_once_for_a_burst(on, book, client, django_capture_on_commit_callbacks):
    relay()  # the book's item in ERPNext
    stock_in(book, 50)
    sle = FAKE.changes[-1][2]
    raw, signature = FAKE.webhook("Stock Ledger Entry", sle, WEBHOOK_SECRET, event="after_insert")
    with django_capture_on_commit_callbacks(execute=True):
        assert ring(client, raw, signature).status_code == 200
    snapshot = ErpStockSnapshot.objects.get(item_code=code(book))
    assert (snapshot.actual, snapshot.warehouse, snapshot.product) == (50, "Main", book)
    assert snapshot.batches[0]["batch_no"] == "PR-2026-1"
    book.refresh_from_db()
    assert book.stock == 20  # shadow mode: the copies for sale are the platform's own
    assert inbound.stock_soon() == "a stock read is queued already"  # the next rings of the burst
    reads = [call for call in FAKE.calls if call[0] == "get_stock"]
    assert len(reads) == 1 and reads[0][1] == {"warehouse": "Main", "by_batch": True}
    assert not [call for call in FAKE.calls if call[0].startswith("/api/resource/Stock")]  # never read over REST


def test_the_projection_follows_erpnext_less_what_is_held(on, book, customer, settings):
    relay()
    stock_in(book, 50)
    FAKE.reserve(code(book), 5)  # a school's order holds 5 in ERPNext
    order = pay_offline(ordered((book, 2), user=customer))  # 2 taken here (20 → 18), not shipped yet
    erp = client()
    inbound.refresh_stock(erp)
    book.refresh_from_db()
    assert book.stock == 18  # off: only kept and compared
    settings.ERP_STOCK_PROJECTION = True
    inbound.refresh_stock(erp)
    book.refresh_from_db()
    assert book.stock == 50 - 5 - 2
    ship_by_hand(order)  # gone from here; its delivery note not yet in ERPNext: still counted
    inbound.refresh_stock(erp)
    book.refresh_from_db()
    assert book.stock == 43 and row("parcel.dispatched").state == "pending"
    relay()  # the delivery note: ERPNext's copies go down, nothing is held here any more
    inbound.refresh_stock(erp)
    book.refresh_from_db()
    assert book.stock == 48 - 5 - 0 and ErpStockSnapshot.objects.get(item_code=code(book)).actual == 48
    FAKE.reserve(code(book), 100)
    inbound.refresh_stock(erp)
    book.refresh_from_db()
    assert book.stock == 0  # never below nothing


def test_the_pull_reads_page_by_page_from_its_cursor(on, monkeypatch):
    monkeypatch.setattr(inbound, "PAGE", 2)
    names = [school(f"School {index}") for index in range(5)]
    FAKE.add_b2b("Customer", customer_name="A parent", customer_group="Online B2C")  # read, not mirrored
    assert inbound.pull(["Customer"]) == {"Customer": 6}
    assert set(ErpMirror.objects.values_list("name", flat=True)) == set(names)
    pages = [body for method, body in FAKE.calls if method == "get_changes_since"]
    assert len(pages) == 3 and pages[0] == {"doctype": "Customer", "modified_after": contract.START, "limit": 2}
    assert pages[1]["modified_after"] == FAKE.doc("Customer", names[1])["modified"] and pages[1]["after_name"]
    cursor = ErpCursor.objects.get(doctype="Customer")
    assert cursor.rows_read == 6 and cursor.last_run_at and not cursor.last_error
    assert inbound.pull(["Customer"]) == {"Customer": 0}
    school("School 6")
    assert inbound.pull(["Customer"]) == {"Customer": 1}


def test_the_pull_keeps_its_cursor_when_erpnext_cannot_be_asked(on):
    school()
    FAKE.fail("get_changes_since", 503)
    assert inbound.pull(["Customer"])["Customer"].startswith("error: ")
    cursor = ErpCursor.objects.get(doctype="Customer")
    assert cursor.modified_after == "" and "503" in cursor.last_error
    assert inbound.pull(["Customer"]) == {"Customer": 1}


def test_the_stock_pull_reads_the_stock_once(on, book):
    relay()
    stock_in(book, 12)
    stock_in(book, 3, batch="PR-2026-2")
    assert inbound.pull(["Stock Ledger Entry"]) == {"Stock Ledger Entry": 2}
    assert [call[0] for call in FAKE.calls].count("get_stock") == 1
    assert ErpStockSnapshot.objects.get(item_code=code(book)).actual == 15
