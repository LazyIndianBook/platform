"""The commands: each runs on an empty database; the initial load counts first and writes once, in order; replay,
reconcile, pull and status."""

import copy
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from erp.fake import FAKE
from erp.models import ErpOutbox
from integrations.models import IntegrationAccount
from shop.factories import ProductFactory
from shop.models import BundleItem, Product
from staff.models import AuditEvent

from .helpers import ordered, pay_offline, relay, rows, ship_by_hand, stock_in

pytestmark = pytest.mark.django_db


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "args", "says"),
    [
        ("erp_status", [], "ERP_ENABLED off"),
        ("erp_replay", ["--dead"], "Replayed 0 row(s)"),
        ("erp_initial_load", [], "Dry run, nothing written; would write: nothing."),
        ("erp_reconcile", [], "Nothing reconciled"),
        ("erp_pull", [], "Nothing read: ERP_ENABLED is off."),
    ],
)
def test_each_command_runs_on_an_empty_database(name, args, says):
    assert says in run(name, *args)


def test_replay_needs_a_row_or_dead():
    with pytest.raises(CommandError):
        run("erp_replay")
    with pytest.raises(CommandError):
        run("erp_replay", "41")


def test_the_initial_load_counts_first_then_writes_once_in_order(book, customer, settings):
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, title="Physics and Chemistry")
    BundleItem.objects.create(bundle=bundle, product=book)
    order = ship_by_hand(pay_offline(ordered((book, 1), user=customer)))  # all before the sync was switched on
    assert not ErpOutbox.objects.exists()
    for name in ["ERP_SYNC_CATALOGUE", "ERP_SYNC_INVOICES", "ERP_SYNC_PAYMENTS", "ERP_SYNC_DELIVERIES"]:
        setattr(settings, name, True)
    since = timezone.localdate().isoformat()
    said = run("erp_initial_load", "--invoices-from", since)
    assert said.startswith(
        "Dry run, nothing written; would write: 1 bundle.upserted, 1 invoice.issued, 2 item.upserted, "
        "1 parcel.dispatched, 1 payment.received."
    )
    assert "Flows off, not loaded: ERP_SYNC_SETTLEMENTS." in said and not ErpOutbox.objects.exists()
    said = run("erp_initial_load", "--apply", "--invoices-from", since)
    assert said.startswith("Wrote: 1 bundle.upserted") and "ERP_ENABLED is off: the rows wait" in said
    events = [r.event for r in rows()]
    assert events == [
        "item.upserted",
        "item.upserted",
        "bundle.upserted",  # after every item: its components exist by then
        "invoice.issued",
        "payment.received",
        "parcel.dispatched",
    ]
    assert [r.sequence for r in rows(aggregate_id=order.number)] == [1, 2, 3]
    assert run("erp_initial_load", "--apply", "--invoices-from", since).startswith("Wrote: nothing.")


def test_status_replay_reconcile_and_pull_when_on(on, book, customer):
    pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body={"message": {"ok": False, "error": {"code": "conflict"}}})
    relay()
    stock_in(book, 20)  # what the platform held before the order
    status = run("erp_status")
    assert "ERP_ENABLED on (mode fake)" in status and "dead 1" in status and "held by a dead row: 1" in status
    assert "Account: ERPNext (test), erp-sync@, circuit closed" in status
    dead = ErpOutbox.objects.get(state="dead")
    assert run("erp_replay", str(dead.pk)) == f"Replayed 1 row(s): {dead.pk}.\n"
    assert "is pending" in run("erp_replay", str(dead.pk))
    relay()
    said = run("erp_reconcile", "--date", timezone.localdate().isoformat())
    assert said.startswith(f"Reconciliation of {timezone.localdate()}") and "0 difference(s)" in said
    FAKE.add_b2b("Quotation", party_name="St. Mary's School")
    assert "Quotation: 1 row(s)" in run("erp_pull")
    assert "Quotation: 1 row(s)" in run("erp_pull", "--doctype", "Quotation", "--restart")
    assert "Last reconciliation" in run("erp_status")


def test_the_status_tells_the_time_in_india(on, book):
    # the shadow run (SHADOW-RUN.md): a row written at 02:03 in Guwahati was "waiting since 20:33" the day before
    relay()
    sent = ErpOutbox.objects.get()
    ErpOutbox.objects.filter(pk=sent.pk).update(state="pending")
    said = run("erp_status")
    assert f"Oldest row waiting: {timezone.localtime(sent.created):%Y-%m-%d %H:%M}" in said
    assert f"last success {timezone.localtime(IntegrationAccount.objects.get().last_success_at):%Y-%m-%d %H:%M}" in said


def test_erpnext_restored_from_a_backup_gets_what_was_sent_since(on, book, customer):
    kept = pay_offline(ordered((book, 1), user=customer))
    relay()
    backup = copy.deepcopy(vars(FAKE))  # ERPNext's backup, taken here
    since = timezone.now()
    lost = pay_offline(ordered((book, 2), user=customer))
    relay()
    vars(FAKE).update(copy.deepcopy(backup))  # restored: the second order's documents are gone
    assert ("Sales Invoice", lost.invoice.number) not in FAKE.docs
    said = run("erp_replay", "--sent-since", since.isoformat())
    assert said == f"Sent again: 2 row(s) sent since {timezone.localtime(since):%Y-%m-%d %H:%M}.\n"
    relay()
    assert ("Sales Invoice", lost.invoice.number) in FAKE.docs and all(r.state == "sent" for r in rows())
    assert ("Sales Invoice", kept.invoice.number) in FAKE.docs
    assert AuditEvent.objects.get(action="erp.resend").details == {"sent_since": since.isoformat(), "rows": 2}
    with pytest.raises(CommandError):
        run("erp_replay", "--dead", "--sent-since", "2026-10-01")
