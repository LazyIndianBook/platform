"""The grievance register (plan 5.14): a staff job (staff.export_grievances: ADMIN, OWNER, AUDITOR) whose CSV lists
the complaints of a period with their deadlines and the days taken, no personal data beyond the number and category,
never spam nor a test order's; above the starter's export_rows it waits for an approver; the break-glass command gives
the same rows."""

import csv
import io
from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

from accounts import roles
from shop.factories import ProductFactory, make_order
from staff.models import ChangeRequest, Job

from .conftest import STAFF, make_staff, make_ticket, signed_in

pytestmark = pytest.mark.django_db
JOBS = STAFF + "jobs/"


def rows_of(job):
    with default_storage.open(job.result_file) as file:
        return list(csv.reader(io.StringIO(file.read().decode())))


def test_the_register_lists_the_periods_complaints_without_personal_data(commit, settings):
    staff = make_staff(roles.SUPPORT)
    with commit():
        answered = make_ticket(category="order", nch_docket="NCH-1", source="nch", channel="nch")
        make_ticket(subject="Spam", spam=True)
        old = make_ticket(received_at=timezone.now() - timedelta(days=40), category="grievance")
    services_close(answered, staff)
    admin = signed_in(make_staff(roles.ADMIN))
    today = timezone.localdate().isoformat()
    with commit():
        started = admin.post(JOBS, {"kind": "grievance_export", "params": {"from": today, "until": today}})
    assert started.status_code == 202, started.content
    job = Job.objects.get(pk=started.json()["id"])
    assert job.state == "done" and job.result == {"rows": 1}
    header, *rows = rows_of(job)
    assert header[:4] == ["number", "category", "source", "nch_docket"] and len(rows) == 1
    row = dict(zip(header, rows[0], strict=True))
    assert (row["number"], row["category"], row["nch_docket"], row["resolved_in_time"]) == (
        answered.number,
        "order",
        "NCH-1",
        "yes",
    )
    assert row["days_to_resolve"] == "0" and float(row["hours_to_acknowledge"]) < 1
    text = default_storage.open(job.result_file).read().decode()
    assert "rahul" not in text.lower() and "Where is my parcel" not in text  # the number and category only
    assert "grievance-register" in job.result_file and old.number not in text


def services_close(ticket, staff):
    from shop.factories import ProductFactory as Product
    from support import services

    order = make_order((Product(), 1), email="rahul@example.com")
    services.set_status(ticket, "closed", by=staff, resolution="Refunded.", order=order.number)


def test_a_test_orders_complaint_is_never_in_the_register(commit, settings):
    with commit():
        make_ticket(order=make_order((ProductFactory(), 1)), category="order")  # made with test keys
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # the site now runs live: that order is a test order
    with commit():
        signed_in(make_staff(roles.OWNER)).post(JOBS, {"kind": "grievance_export", "params": {}})
    header, *rows = rows_of(Job.objects.get())
    assert rows == []


def test_only_its_permission_starts_it_and_above_the_limit_it_waits_for_an_approver(commit, monkeypatch):
    with commit():
        make_ticket()
        make_ticket()
    assert signed_in(make_staff(roles.SUPPORT)).post(JOBS, {"kind": "grievance_export"}).status_code == 403
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.AUDITOR], "export_rows", 1)
    auditor = make_staff(roles.AUDITOR)
    stale = signed_in(auditor, reauth=False).post(JOBS, {"kind": "grievance_export"})
    assert stale.json()["code"] == "reauthentication_required"  # high: a re-authentication first
    with commit():
        waiting = signed_in(auditor).post(JOBS, {"kind": "grievance_export", "params": {}})
    job = Job.objects.get(pk=waiting.json()["id"])
    assert job.state == "queued" and job.change_request is not None
    change = ChangeRequest.objects.get(pk=job.change_request_id)
    assert (
        change.status == "pending" and change.action == "job.run" and "2 rows are above the limit of 1" in change.rule
    )
    refused = signed_in(auditor).post(
        JOBS, {"kind": "grievance_export", "params": {"from": "2027-02-01", "until": "2027-01-01"}}
    )
    assert refused.status_code == 400 and "until" in refused.json()["params"]


def test_the_command_writes_the_same_register(commit):
    with commit():
        ticket = make_ticket(category="payment")
    out = io.StringIO()
    call_command("grievance_register", "--from", timezone.localdate().isoformat(), stdout=out)
    header, row = list(csv.reader(io.StringIO(out.getvalue())))
    assert header[0] == "number" and row[0] == ticket.number and row[1] == "payment"
