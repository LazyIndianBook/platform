"""Background jobs (plan 3.6): started with the kind's own permission (the single action's), run by Celery with their
progress and each failed row's error, approved first above the starter's limit, cancelled by their starter, their file
behind a link signed for 5 minutes; every step in the audit log."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from accounts import roles
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Order, Refund
from staff import audit, jobs
from staff.models import ChangeRequest, Job
from staff.tasks import expire_access

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
JOBS = STAFF + "jobs/"


def paid_order(price):
    order = make_order((ProductFactory(price=Decimal(price), mrp=Decimal(price) + 100), 1))
    shop.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def refunds(*targets, **params):
    return {"kind": "bulk_action", "params": {"action": "order.refund", "targets": list(targets), "payload": {},
                                              "reason": "The courier lost the batch", **params}}  # fmt: skip


def test_a_large_audit_export_runs_as_a_job_and_its_file_is_linked_for_its_starter_only(
    monkeypatch, django_capture_on_commit_callbacks
):
    for n in range(4):
        audit.record("user.unlocked", reason=f"#{n}")
    monkeypatch.setattr("staff.api.INLINE_EXPORT_ROWS", 2)
    auditor = make_staff(roles.AUDITOR)
    client = signed_in(auditor)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(STAFF + "audit/export/", {"filters": {"action": "user.unlocked"}}, format="json")
    assert response.status_code == 202 and response.json()["state"] == "queued"
    job = client.get(f"{JOBS}{response.json()['id']}/").json()
    assert (job["kind"], job["state"], job["done"], job["total"]) == ("audit_export", "done", 4, 4)
    assert job["errors"] == [] and job["result"] == {"rows": 4} and job["started_by"] == auditor.pk
    download = client.get(job["result_url"])
    assert download.status_code == 200 and download["Cache-Control"] == "no-store"
    rows = [json.loads(line) for line in b"".join(download.streaming_content).decode().splitlines()]
    assert [row["reason"] for row in rows] == ["#0", "#1", "#2", "#3"]
    assert all(audit.chain_hash(row["prev_hash"], row) == row["hash"] for row in rows)  # each line verifies alone
    owner = signed_in(make_staff(roles.OWNER))
    assert owner.get(f"{JOBS}{job['id']}/").json()["result_url"] is None  # everyone's jobs, nobody else's files
    assert owner.get(job["result_url"]).status_code == 404
    assert client.get(f"{JOBS}{job['id']}/result/?token=forged").json()["code"] == "link_expired"
    monkeypatch.setattr(jobs, "LINK_SECONDS", -1)
    assert client.get(job["result_url"]).status_code == 403  # 5 minutes on
    trail = [event.action for event in events(target_type="staff.job")]
    assert trail == ["job.requested", "job.started", "job.done", "job.result_downloaded"]
    assert events("audit.exported").get().details["job"] == job["id"]


def test_an_export_above_the_limit_waits_for_admin_then_runs(monkeypatch, django_capture_on_commit_callbacks):
    for n in range(3):
        audit.record("user.unlocked", reason=f"#{n}")
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.AUDITOR], "export_rows", 2)
    auditor, admin = make_staff(roles.AUDITOR), make_staff(roles.ADMIN)
    job = signed_in(auditor).post(JOBS, {"kind": "audit_export", "params": {"filters": {}}}, format="json").json()
    assert job["state"] == "queued" and job["change_request_id"]
    url = f"{STAFF}change-requests/{job['change_request_id']}/"
    change = signed_in(auditor).get(url).json()
    assert change["action"] == "job.run" and change["checker"] == "staff.approve_export"
    assert change["payload"]["params"] == {"filters": {}}  # what ADMIN reads: the filters, the rows
    assert change["payload"]["total"] == Job.objects.get(pk=job["id"]).total >= 3
    sha = {"payload_sha256": change["payload_sha256"]}
    assert signed_in(make_staff(roles.FINANCE)).post(url + "approve/", sha).status_code == 403  # ADMIN's to approve
    assert signed_in(admin).post(url + "approve/", sha).json()["status"] == "approved"
    with django_capture_on_commit_callbacks(execute=True):
        assert signed_in(auditor).post(url + "execute/").json()["status"] == "executed"
    assert Job.objects.get(pk=job["id"]).state == "done"


def test_a_bulk_refund_runs_each_order_as_its_own_request(rzp, django_capture_on_commit_callbacks):
    sales = make_staff(roles.SALES)  # refunds up to ₹2,000 at once
    small, other, big = paid_order("299.00"), paid_order("499.00"), paid_order("2500.00")
    body = refunds(small.number, other.number, big.number, "EL-NOPE")
    with django_capture_on_commit_callbacks(execute=True):
        response = signed_in(sales).post(JOBS, body, format="json")
    assert response.status_code == 202, response.content
    job = Job.objects.get(pk=response.json()["id"])
    assert (job.state, job.done, job.total) == ("done", 4, 4)
    assert job.result["outcomes"] == {"executed": 2, "pending": 1, "refused": 1}
    [waiting] = job.result["waiting"]
    assert ChangeRequest.objects.get(pk=waiting).target_label == big.number  # above SALES' limit: FINANCE approves
    assert job.errors == [{"id": "EL-NOPE", "label": "EL-NOPE", "message": "No such order (or not one you may see)."}]
    assert set(Refund.objects.values_list("order", flat=True)) == {small.pk, other.pk}
    requested = events("order.refund.requested")
    assert requested.count() == 3 and {event.actor_id for event in requested} == {sales.pk}  # the maker, not the site
    again = refunds(small.number)  # a job of its own: a new request, refused since refunded already
    with django_capture_on_commit_callbacks(execute=True):
        twice = signed_in(sales).post(JOBS, again, format="json").json()
    assert Job.objects.get(pk=twice["id"]).result["outcomes"] == {"refused": 1}


def test_a_dry_run_checks_every_row_and_changes_nothing(rzp, django_capture_on_commit_callbacks):
    sales, order = make_staff(roles.SALES), paid_order("2500.00")
    with django_capture_on_commit_callbacks(execute=True):
        response = signed_in(sales).post(JOBS, {**refunds(order.number, "EL-NOPE"), "dry_run": True}, format="json")
    job = Job.objects.get(pk=response.json()["id"])
    assert job.state == "done" and job.dry_run and job.result["outcomes"] == {"valid": 1, "refused": 1}
    assert not Refund.objects.exists() and not ChangeRequest.objects.exists()


def test_a_job_needs_its_own_permission_and_a_bulk_action_above_the_row_limit_waits(rzp, monkeypatch):
    first, second = paid_order("299.00"), paid_order("299.00")
    denied = signed_in(make_staff(roles.MARKETING)).post(JOBS, refunds(first.number), format="json")
    assert denied.status_code == 403 and denied.json()["code"] == "permission_denied"
    assert "staff.refund_order" in denied.json()["detail"]
    support = make_staff(roles.SUPPORT)
    bad = signed_in(support).post(JOBS, refunds(first.number, action="staff.grant_role"), format="json")
    assert bad.status_code == 400 and "action" in bad.json()["params"]  # bulk: the change-requests/ actions only
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.SUPPORT], "bulk_rows", 1)
    waiting = signed_in(support).post(JOBS, refunds(first.number, second.number), format="json").json()
    assert waiting["state"] == "queued" and waiting["change_request_id"]
    url = f"{JOBS}{waiting['id']}/cancel/"
    assert signed_in(make_staff(roles.OWNER)).post(url).status_code == 404  # its starter's to cancel
    cancelled = signed_in(support).post(url).json()
    assert cancelled["state"] == "cancelled" and cancelled["cancel_requested"]
    assert ChangeRequest.objects.get(pk=waiting["change_request_id"]).status == "rejected"  # the approval withdrawn
    assert signed_in(support).post(url).status_code == 400  # finished
    assert not Refund.objects.exists()


def test_each_person_lists_their_jobs_and_operators_everyone_s():
    sales, support, admin = make_staff(roles.SALES), make_staff(roles.SUPPORT), make_staff(roles.ADMIN)
    mine = Job.objects.create(kind="audit_export", params={"filters": {}}, started_by=sales)
    Job.objects.create(kind="audit_export", params={"filters": {}}, started_by=support)
    assert [row["id"] for row in signed_in(sales).get(JOBS).json()["results"]] == [mine.pk]
    assert len(signed_in(admin).get(JOBS).json()["results"]) == 2
    assert signed_in(admin).get(JOBS, {"mine": "true"}).json()["results"] == []
    assert signed_in(sales).get(JOBS, {"state": "done"}).json()["results"] == []


def test_a_running_job_stops_at_its_next_row_and_one_whose_starter_lost_the_permission_fails(monkeypatch):
    sales = make_staff(roles.SALES)
    params = {"action": "order.refund", "targets": ["A", "B", "C"], "payload": {}, "reason": "r"}
    job = Job.objects.create(kind="bulk_action", params=params, dry_run=True, total=3, started_by=sales)
    Job.objects.filter(pk=job.pk).update(cancel_requested=True)  # (cancelled while it runs)
    clock = iter(range(0, 10_000, 5))
    monkeypatch.setattr(jobs, "monotonic", lambda: next(clock))  # a second between rows: a save and a check each
    assert jobs.run(job.pk) == "cancelled" and Job.objects.get(pk=job.pk).done == 1
    assert events("job.stopped", target_id=str(job.pk)).exists()
    assert jobs.run(job.pk) is None  # once
    marketing = make_staff(roles.MARKETING)
    lost = Job.objects.create(kind="bulk_action", params=params, total=3, started_by=marketing)
    assert jobs.run(lost.pk) == "failed"
    assert "no longer holds staff.refund_order" in Job.objects.get(pk=lost.pk).errors[0]["message"]


def test_result_files_go_after_a_week():
    sales = make_staff(roles.SALES)
    name = default_storage.save("staff/jobs/test/old.jsonl", ContentFile(b"{}\n"))
    finished = timezone.now() - timedelta(days=jobs.KEEP_FILES_DAYS + 1)
    old = Job.objects.create(
        kind="audit_export", started_by=sales, state="done", finished_at=finished, result_file=name
    )
    assert expire_access()["job_files"] == 1
    assert Job.objects.get(pk=old.pk).result_file == "" and not default_storage.exists(name)
