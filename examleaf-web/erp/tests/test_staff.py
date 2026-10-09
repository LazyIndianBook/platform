"""The ERPNext sync in the staff app: its items in the inbox (a dead letter until replayed or discarded, a
reconciliation's differences until the last is resolved), its audit events, the initial load as a staff job, and the
switches as the panel's feature flags."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts import roles
from erp import reconcile, tasks
from erp.fake import FAKE
from erp.models import ErpOutbox
from staff import jobs
from staff.config import changed
from staff.models import AuditEvent, FeatureFlag, InboxItem, Job
from staff.tests.conftest import STAFF, make_staff, signed_in

from .helpers import ordered, pay_offline, relay, row, rows

pytestmark = pytest.mark.django_db
CONFLICT = {"message": {"ok": False, "error": {"code": "conflict", "message": "Taken.", "field": "invoice_number"}}}


def dead_invoice(book, customer, django_capture_on_commit_callbacks):
    order = pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    with django_capture_on_commit_callbacks(execute=True):  # dead_letter_created comes after the commit
        relay()
    return order, row("invoice.issued")


def test_a_dead_letter_waits_in_the_inbox_until_it_is_replayed(on, book, customer, django_capture_on_commit_callbacks):
    order, dead = dead_invoice(book, customer, django_capture_on_commit_callbacks)
    item = InboxItem.objects.get(kind="sync_failed", done_at=None)
    assert (item.target_type, item.target_id, item.permission) == ("erp.erpoutbox", str(dead.pk), "erp.replay_sync")
    assert item.title == f"ERPNext refused invoice:{order.invoice.number} (invoice.issued): replay or discard it"
    assert "conflict" in item.data["error"]
    admin = signed_in(make_staff(roles.ADMIN))
    assert admin.get(STAFF + "inbox/").json()["results"][0]["id"] == item.pk  # the replayers see it
    assert not signed_in(make_staff(roles.SALES)).get(STAFF + "inbox/").json()["results"]  # others do not
    dead.replay()
    item.refresh_from_db()
    assert item.done_at is not None


def test_a_discarded_dead_letter_is_done_in_the_inbox_and_audited(
    on, book, customer, django_capture_on_commit_callbacks
):
    _order, dead = dead_invoice(book, customer, django_capture_on_commit_callbacks)
    staff = make_staff(roles.ADMIN)
    assert dead.discard("Made by hand in ERPNext.", by=staff)
    assert not InboxItem.objects.filter(kind="sync_failed", done_at=None).exists()
    event = AuditEvent.objects.get(action="erp.discard")
    assert (event.actor_id, event.reason, event.target_type) == (staff.pk, "Made by hand in ERPNext.", "erp.erpoutbox")


def test_a_shipping_dead_letter_is_not_the_erp_app_s(on):
    from integrations.services import dead_letter

    dead_letter("shipping.tasks.book_shipment", "t-1", RuntimeError("no"), [1], {})
    assert not InboxItem.objects.filter(kind="sync_failed").exists()


def test_a_reconciliation_s_differences_wait_until_the_last_is_resolved(on, book, customer):
    pay_offline(ordered((book, 1), user=customer))  # never relayed: ERPNext has nothing of the day
    run = reconcile.run(timezone.localdate())
    assert run.differences_count > 1
    [item] = InboxItem.objects.filter(kind="reconciliation", done_at=None)
    assert item.permission == "erp.resolve_difference" and f"{run.differences_count} difference(s)" in item.title
    first, *others = run.differences.all()
    first.resolve("Checked: the relay was off.")
    item.refresh_from_db()
    assert item.done_at is None
    for difference in others:
        difference.resolve("Checked.")
    item.refresh_from_db()
    assert item.done_at is not None
    assert AuditEvent.objects.filter(action="erp.resolve").count() == run.differences_count


def test_a_quiet_night_files_nothing(on):
    assert reconcile.run(timezone.localdate()).differences_count == 0
    assert not InboxItem.objects.exists()


def test_the_initial_load_as_a_staff_job(book, customer, settings, django_capture_on_commit_callbacks):
    order = pay_offline(ordered((book, 1), user=customer))  # before the sync was switched on
    for name in ["ERP_SYNC_CATALOGUE", "ERP_SYNC_INVOICES", "ERP_SYNC_PAYMENTS"]:
        setattr(settings, name, True)
    assert not ErpOutbox.objects.exists()
    body = {"kind": "erp_initial_load", "params": {"invoices_from": timezone.localdate().isoformat()}}
    sales = signed_in(make_staff(roles.SALES))
    assert sales.post(STAFF + "jobs/", {**body, "dry_run": True}, format="json").status_code == 403
    owner = make_staff(roles.OWNER)
    with django_capture_on_commit_callbacks(execute=True):  # the job's task runs at the commit (eagerly here)
        dry = signed_in(owner).post(STAFF + "jobs/", {**body, "dry_run": True}, format="json")
    assert dry.status_code == 202, dry.content
    job = Job.objects.get(pk=dry.json()["id"])
    assert job.state == "done" and job.done == 2 and not ErpOutbox.objects.exists()
    assert job.result["written"] == {"invoice.issued": 1, "item.upserted": 1, "payment.received": 1}
    with django_capture_on_commit_callbacks(execute=True):
        written = signed_in(owner).post(STAFF + "jobs/", body, format="json")
    assert Job.objects.get(pk=written.json()["id"]).state == "done"
    assert [r.event for r in rows()] == ["item.upserted", "invoice.issued", "payment.received"]
    assert rows()[1].aggregate_id == order.number
    events = AuditEvent.objects.filter(action="erp.initial_load").order_by("id")
    assert [e.details["dry_run"] for e in events] == [True, False] and events[1].actor_id == owner.pk
    bad = signed_in(owner).post(STAFF + "jobs/", {"kind": "erp_initial_load", "params": {"invoices_from": "soon"}})
    assert bad.status_code == 400
    assert jobs.permission("erp_initial_load", {}) == "erp.run_initial_load"


def flag(key, value):
    """A feature flag set in the panel (its PUT does the same: a row, then the switches read again)."""
    FeatureFlag.objects.create(key=key, value=value, effective_from=timezone.now() - timedelta(seconds=1))
    changed(FeatureFlag)


def test_the_switches_follow_the_panel_s_feature_flags(on, book, customer, settings):
    flag("ERP_SYNC_INVOICES", False)
    pay_offline(ordered((book, 1), user=customer))
    assert not rows(event="invoice.issued")  # the panel switched the flow off, whatever the environment says
    settings.ERP_ENABLED = False
    flag("ERP_ENABLED", True)
    assert tasks.relay() != {"skipped": "ERP_ENABLED is off"}
    flag("ERP_ENABLED", None)  # back to the environment's
    assert tasks.relay() == {"skipped": "ERP_ENABLED is off"}
