"""The relay: in order per aggregate, idempotent (a lost answer sent again makes no second document), 429 and
Retry-After, the backoff, the dead letter after the limit with its aggregate held, replay and discard, the circuit
breaker, the lease of a claimed row, and the switches."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from erp import tasks
from erp.fake import FAKE
from erp.models import ErpLink, ErpOutbox
from integrations.models import IntegrationFailure
from integrations.signals import dead_letter_created
from shop.factories import ProductFactory
from shop.models import BundleItem, Product

from .helpers import due_now, ordered, pay_offline, relay, row, rows

pytestmark = pytest.mark.django_db
CONFLICT = {"message": {"ok": False, "error": {"code": "conflict", "message": "Item exists.", "field": "item_code"}}}


def test_a_sent_row_keeps_erpnext_s_answer_and_links_the_document(on, book, customer):
    order = pay_offline(ordered((book, 1), user=customer))
    assert relay() == {"sent": 3}  # the item, the invoice, its payment
    sent = row("invoice.issued")
    assert sent.state == "sent" and sent.sent_at and not sent.last_error
    assert sent.response["name"] == order.invoice.number and sent.response["log"].startswith("SYNC-LOG-")
    link = ErpLink.objects.get(examleaf_ref=f"invoice:{order.invoice.number}")
    assert (link.doctype, link.name, link.model, link.object_id) == (
        "Sales Invoice",
        order.invoice.number,
        "shop.invoice",
        str(order.invoice.pk),
    )
    document = FAKE.doc("Sales Invoice", order.invoice.number)
    assert document["customer"] == "Online Customers (B2C)" and document["examleaf_ref"] == sent.examleaf_ref
    method, body = next(call for call in FAKE.calls if call[0] == "create_sales_invoice")
    assert body["idempotency_key"] == str(sent.pk) and body["examleaf_ref"] == sent.examleaf_ref


def test_a_lost_answer_is_sent_again_and_erpnext_keeps_one_document(on, book, customer):
    order = pay_offline(ordered((book, 1), user=customer))
    FAKE.lose_answer("create_sales_invoice")  # ERPNext made it, its answer never came back
    relay()
    failed = row("invoice.issued")
    assert (failed.state, failed.attempts) == ("failed", 1) and "504" in failed.last_error
    assert row("payment.received").state == "pending"  # held behind it
    due_now()
    relay()
    failed.refresh_from_db()
    assert failed.state == "sent" and failed.response["duplicate"] is True
    assert failed.response["name"] == order.invoice.number
    assert len([d for d in FAKE.of("Sales Invoice") if not d["is_return"]]) == 1
    assert row("payment.received").state == "sent"


def test_a_reference_seen_under_another_key_answers_the_short_form(on, book, customer):
    pay_offline(ordered((book, 1), user=customer))
    relay()
    first = row("invoice.issued")
    again = ErpOutbox.objects.create(  # the same document written twice (it never is by the producers)
        aggregate_type="check", aggregate_id="1", sequence=1, event=first.event, examleaf_ref=first.examleaf_ref,
        model=first.model, object_id=first.object_id, payload=first.payload,
    )  # fmt: skip
    relay()
    again.refresh_from_db()
    assert again.state == "sent" and again.response["duplicate"] is True and again.response["docstatus"] == 1
    assert ErpLink.objects.get(examleaf_ref=first.examleaf_ref).name == first.response["name"]


def test_a_number_issued_again_for_another_order_is_dead_at_once(on, book, customer):
    # the shadow run (SHADOW-RUN.md): ERPNext answered such a row as the first order's duplicate, which would have
    # linked the second order's invoice to the first one's document
    one = pay_offline(ordered((book, 1), user=customer))
    two = pay_offline(ordered((book, 2), user=customer))
    first, other = rows(event="invoice.issued")
    reused = {**other.payload, "invoice_number": first.payload["invoice_number"]}  # a restored database's number
    ErpOutbox.objects.filter(pk=other.pk).update(examleaf_ref=first.examleaf_ref, payload=reused)
    relay()
    other.refresh_from_db()
    assert other.state == "dead" and "conflict" in other.last_error and "(order_number)" in other.last_error
    assert ErpLink.objects.get(examleaf_ref=first.examleaf_ref).object_id == first.object_id
    assert FAKE.doc("Sales Invoice", first.payload["invoice_number"])["order_number"] == one.number
    assert row("payment.received", aggregate_id=two.number).state == "pending"  # held behind it


def test_a_key_reused_with_another_body_is_dead_at_once(on, book):
    relay()
    sent = row("item.upserted")
    changed = {**sent.payload, "item_name": "Another title"}  # a bug: one id, two bodies
    ErpOutbox.objects.filter(pk=sent.pk).update(state="pending", payload=changed)
    due_now()
    relay()
    sent.refresh_from_db()
    assert (sent.state, sent.attempts) == ("dead", 1) and "idempotency_key_reused" in sent.last_error


def test_429_waits_as_long_as_retry_after_says_and_counts_no_try(on, book):
    FAKE.fail("upsert_item", 429, headers={"Retry-After": "120"})
    before = timezone.now()
    assert relay() == {"rate_limited": 1}  # and the run stops
    waiting = row("item.upserted")
    assert (waiting.state, waiting.attempts) == ("pending", 0)
    assert timedelta(seconds=115) < waiting.next_at - before < timedelta(seconds=125)
    due_now()
    relay()
    waiting.refresh_from_db()
    assert waiting.state == "sent"


def test_failures_are_tried_again_later_and_dead_after_the_limit(
    on, book, settings, django_capture_on_commit_callbacks
):
    settings.ERP_MAX_ATTEMPTS = 3
    FAKE.fail("upsert_item", 503, times=3)
    told = []
    dead_letter_created.connect(lambda sender, failure, **kwargs: told.append(failure), weak=False, dispatch_uid="t")
    try:
        before = timezone.now()
        relay()
        failing = row("item.upserted")
        assert (failing.state, failing.attempts) == ("failed", 1)
        assert timedelta(seconds=29) < failing.next_at - before < timedelta(seconds=61)  # a minute, jittered
        due_now()
        relay()
        failing.refresh_from_db()
        assert failing.attempts == 2 and failing.next_at - timezone.now() > timedelta(seconds=55)  # doubled
        due_now()
        with django_capture_on_commit_callbacks(execute=True):
            relay()
    finally:
        dead_letter_created.disconnect(dispatch_uid="t")
    failing.refresh_from_db()
    assert (failing.state, failing.attempts) == ("dead", 3)
    letter = failing.failure
    assert (letter.operation, letter.task_name, letter.args) == (
        "upsert_item",
        "erp.tasks.replay_row",
        {"args": [failing.pk], "kwargs": {}},
    )
    assert letter.state == IntegrationFailure.State.OPEN and told == [letter]


def test_a_dead_row_holds_its_aggregate_never_another_until_replayed(on, book):
    relay()  # the book's item
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, title="Physics and Chemistry")
    BundleItem.objects.create(bundle=bundle, product=book)
    other = ProductFactory(title="Chemistry Sample Papers 2027")
    FAKE.fail("upsert_item", 409, body=CONFLICT)  # the bundle's item: made by hand in ERPNext, without its reference
    relay()
    item, components = rows(aggregate_id=str(bundle.pk))
    assert (item.state, item.attempts, components.state) == ("dead", 1, "pending")
    assert row("item.upserted", aggregate_id=str(other.pk)).state == "sent"  # another aggregate goes on
    due_now()
    relay()
    components.refresh_from_db()
    assert components.state == "pending"  # still held
    staff = UserFactory(is_staff=True)
    assert item.replay(by=staff) and (item.state, item.attempts) == ("pending", 0)
    assert item.failure.state == IntegrationFailure.State.REPLAYED and item.failure.resolved_by == staff
    relay()
    assert [r.state for r in rows(aggregate_id=str(bundle.pk))] == ["sent", "sent"]
    assert FAKE.doc("Product Bundle", item.payload["item_code"])["items"][0]["qty"] == 1


def test_a_replay_from_the_dead_letter_list_sends_the_row_again(on, book, django_capture_on_commit_callbacks):
    FAKE.fail("upsert_item", 409, body=CONFLICT)
    relay()
    dead = row("item.upserted")
    with django_capture_on_commit_callbacks(execute=True):  # Admin → Integrations → Integration failures → Replay
        assert dead.failure.replay()
    dead.refresh_from_db()
    assert (dead.state, dead.attempts) == ("pending", 0)  # reset by its task, erp.tasks.replay_row
    relay()
    dead.refresh_from_db()
    assert dead.state == "sent"


def test_a_discarded_row_lets_its_aggregate_go_on(on, book, customer):
    relay()
    order = pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    relay()
    invoice = row("invoice.issued")
    assert invoice.state == "dead" and row("payment.received").state == "pending"
    FAKE.run("create_sales_invoice", {**invoice.payload, "examleaf_ref": invoice.examleaf_ref, "idempotency_key": "x"})
    with pytest.raises(ValueError):
        invoice.discard("  ")
    assert invoice.discard("Made by hand in ERPNext.")
    assert invoice.state == "discarded" and invoice.failure.discard_reason == "Made by hand in ERPNext."
    relay()
    assert row("payment.received").state == "sent"
    assert FAKE.doc("Sales Invoice", order.invoice.number)["outstanding_amount"] == 0


def test_a_dead_letter_discarded_in_the_integrations_admin_frees_its_aggregate(on, book, customer):
    relay()
    pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    relay()
    invoice = row("invoice.issued")
    invoice.failure.discard("Not for ERPNext.")
    relay()
    invoice.refresh_from_db()
    assert invoice.state == "discarded"


def test_a_newer_upsert_replaces_one_erpnext_refused(on, book):
    FAKE.fail(
        "upsert_item", 400, body={"message": {"ok": False, "error": {"code": "invalid_request", "field": "isbn"}}}
    )
    relay()
    refused = row("item.upserted")
    assert refused.state == "dead"
    book.mrp = 399  # staff fix the product
    book.save()
    refused.refresh_from_db()
    assert refused.state == "discarded" and refused.failure.state == IntegrationFailure.State.DISCARDED
    relay()
    assert [r.state for r in rows(event="item.upserted")] == ["discarded", "sent"]


def test_an_item_not_there_yet_is_tried_again_not_dead(on, book, customer):
    pay_offline(ordered((book, 1), user=customer))
    ErpOutbox.objects.filter(event="item.upserted").update(state="discarded")  # the item never reached ERPNext
    relay()
    waiting = row("invoice.issued")
    assert (waiting.state, waiting.attempts) == ("failed", 1) and "not_found" in waiting.last_error


def test_an_open_circuit_counts_no_try(on, book):
    on.force_open()
    assert relay() == {"waiting": 1}
    waiting = row("item.upserted")
    assert (waiting.state, waiting.attempts) == ("pending", 0) and waiting.next_at > timezone.now()


def test_refused_credentials_stop_the_run_a_refused_step_does_not(on, book):
    ProductFactory(title="Chemistry")
    FAKE.fail("upsert_item", 401, body={"exc_type": "AuthenticationError"})
    assert relay() == {"credentials_refused": 1}
    assert [r.state for r in rows(event="item.upserted")] == ["failed", "pending"]
    due_now()
    denied = {"message": {"ok": False, "error": {"code": "permission_denied", "message": "No Item Price write"}}}
    FAKE.fail("upsert_item", 403, body=denied)
    assert relay() == {"failed": 1, "sent": 1}


def test_a_row_whose_sender_died_is_sent_again_after_its_lease(on, book):
    stuck = row("item.upserted")
    ErpOutbox.objects.filter(pk=stuck.pk).update(state="sending", next_at=timezone.now() + tasks.LEASE)
    assert relay() == {}
    ErpOutbox.objects.filter(pk=stuck.pk).update(next_at=timezone.now() - timedelta(seconds=1))
    assert relay() == {"sent": 1}


def test_rows_wait_while_erpnext_or_their_flow_is_switched_off(on, book, customer, settings):
    settings.ERP_ENABLED = False
    assert relay() == {"skipped": "ERP_ENABLED is off"}
    settings.ERP_ENABLED, settings.ERP_SYNC_PAYMENTS = True, False
    pay_offline(ordered((book, 1), user=customer))
    settings.ERP_SYNC_PAYMENTS = True
    order = pay_offline(ordered((book, 1), user=customer))
    settings.ERP_SYNC_PAYMENTS = False  # rolled back: its rows wait, and hold their order's later ones
    relay()
    assert (
        row("payment.received").state == "pending" and row("invoice.issued", aggregate_id=order.number).state == "sent"
    )
    settings.ERP_SYNC_PAYMENTS = True
    relay()
    assert row("payment.received").state == "sent"
    on.enabled = False
    on.save()
    assert relay() == {"skipped": "no enabled ERPNext account"}
