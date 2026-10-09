"""The outbox: a row written in the transaction of the change it describes (or not at all), in order per aggregate,
only while its flow is on, once per document; and a producer that never breaks the change."""

import logging

import pytest
from django.db import transaction

from erp import contract, producers
from erp.models import ErpOutbox
from shop.factories import ProductFactory
from shop.models import BundleItem, Invoice, Product

from .helpers import invoiced, ordered, pay_offline, relay, row, rows, ship_by_hand

pytestmark = pytest.mark.django_db


def test_nothing_is_written_while_the_flows_are_off(book, customer):
    order = ship_by_hand(pay_offline(ordered((book, 1), user=customer)))
    book.mrp = 399
    book.save()
    assert order.invoice and order.shipments.exists()
    assert not ErpOutbox.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_a_row_exists_only_if_its_change_is_committed(switched_on):
    with pytest.raises(RuntimeError), transaction.atomic():
        ProductFactory(title="Never saved")
        raise RuntimeError("the change failed")
    assert not ErpOutbox.objects.exists()
    kept = ProductFactory(title="Saved")
    [written] = ErpOutbox.objects.all()
    assert (written.examleaf_ref, written.payload["item_name"]) == (f"item:{kept.pk}", "Saved")


@pytest.mark.django_db(transaction=True)
def test_an_invoice_and_its_rows_commit_together_from_the_payment_s_task(switched_on, customer):
    """As in production: the payment's transaction queues the invoice's task at its commit (eager here), whose
    transaction writes the invoice and its rows."""
    book = ProductFactory(stock=5)
    order = ordered((book, 1), user=customer)
    from shop import services as shop

    shop.record_offline_payment(order, "UTR 401234567890")
    invoice = Invoice.objects.get(order=order)
    events = [r.event for r in rows(aggregate_id=order.number)]
    assert events == ["invoice.issued", "payment.received"]
    assert row("invoice.issued").payload["invoice_number"] == invoice.number


def test_an_order_s_rows_follow_each_other_and_wait_for_its_invoice(switched_on, book, customer):
    order = ordered((book, 2), user=customer)
    from shop import services as shop

    shop.record_offline_payment(order, "UTR 401234567890")  # paid: no invoice yet, so no payment row either
    assert not rows(aggregate_id=order.number)
    order = ship_by_hand(invoiced(order))
    written = rows(aggregate_id=order.number)
    assert [(r.event, r.sequence) for r in written] == [
        ("invoice.issued", 1),
        ("payment.received", 2),
        ("parcel.dispatched", 3),
    ]
    assert {r.aggregate_type for r in written} == {"order"}
    assert [r.event for r in rows(aggregate_type="product")] == ["item.upserted"]


def test_a_document_is_written_once(switched_on, book, customer):
    order = pay_offline(ordered((book, 1), user=customer))
    invoice = order.invoice
    producers.invoice_issued(invoice)  # the initial load, or a repeated signal
    producers.payment_received(order.payments.get(status="captured"), order)
    assert [r.event for r in rows(aggregate_id=order.number)] == ["invoice.issued", "payment.received"]


def test_an_upsert_is_written_again_only_when_erpnext_would_see_a_change(switched_on, book):
    book.seo_title = "Physics, the sample papers"  # not something ERPNext keeps
    book.save()
    assert len(rows(event="item.upserted")) == 1
    book.mrp = 399
    book.save()
    assert [r.payload["mrp"] for r in rows(event="item.upserted")] == ["349.00", "399.00"]


def test_a_bundle_s_components_follow_its_item(switched_on, book):
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, title="Physics and Chemistry")
    assert [r.event for r in rows(aggregate_id=str(bundle.pk))] == ["item.upserted"]  # no components yet
    BundleItem.objects.create(bundle=bundle, product=book, quantity=1)
    written = rows(aggregate_id=str(bundle.pk))
    assert [(r.event, r.sequence) for r in written] == [("item.upserted", 1), ("bundle.upserted", 2)]
    assert written[1].payload == {
        "item_code": contract.item_code(bundle),
        "items": [{"item_code": contract.item_code(book), "qty": 1}],
        "is_active": True,
    }


def test_test_mode_orders_never_sync(switched_on, book, customer, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_key"
    order = ordered((book, 1), user=customer)  # made with test keys
    settings.RAZORPAY_KEY_ID = "rzp_live_the_site_went_live"  # the site runs on live keys now: a test order
    order = pay_offline(order)
    assert order.is_test and order.invoice.number.startswith("T/")
    assert not rows(aggregate_id=order.number)


def test_a_producer_that_fails_never_stops_the_change(switched_on, book, customer, monkeypatch, caplog):
    def broken(order):
        raise RuntimeError("a bug in the erp app")

    monkeypatch.setattr(producers, "invoice_written", broken)
    with caplog.at_level(logging.ERROR, logger="erp.producers"):
        order = pay_offline(ordered((book, 1), user=customer))
    assert Invoice.objects.filter(order=order).exists()  # the invoice was issued all the same
    assert not rows(aggregate_id=order.number)  # its rows undone with the producer's savepoint
    assert "the change goes on without its outbox row" in caplog.text


def test_a_payload_that_cannot_be_built_is_built_again_at_the_send(on, book, customer, monkeypatch):
    def broken(document):
        raise KeyError("state")

    monkeypatch.setitem(contract.BUILDERS, "invoice.issued", broken)
    order = pay_offline(ordered((book, 1), user=customer))
    written = row("invoice.issued")
    assert written.payload is None and written.last_error.startswith("Payload not built: KeyError")
    monkeypatch.setitem(contract.BUILDERS, "invoice.issued", contract.invoice)  # the bug fixed
    relay()
    written.refresh_from_db()
    assert written.state == "sent" and written.payload["invoice_number"] == order.invoice.number
