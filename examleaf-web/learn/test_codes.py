"""Book codes for staff (learn.codes, learn/staff_api.py): a print run's batch made by a job that keeps only the codes'
digests and writes the codes once into the printer's file, its starter's alone and gone after 24 hours (the owners
told); a batch dispatched once, and voided with its unused codes refused at redemption; one code voided; the lookup's
one line, its audit and its throttle; the codes report with its small districts hidden; the batches made from the
codes' labels when the migration ran; the batch pages read with a fixed number of queries."""

import csv
import io
from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from api.tests import sign_in, student
from insights.models import FraudSignal
from shop.factories import ADDRESS, ProductFactory
from shop.models import Order, OrderItem, PinCode
from staff import jobs
from staff.models import Job
from staff.tasks import expire_access

from . import codes
from .conftest import COURSE, events, make_staff, signed_in
from .models import BookCode, CodeBatch, Entitlement, code_digest
from .services import make_codes
from .tasks import purge_code_files

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
BATCHES = f"{COURSE}codes/batches/"


def make_batch(client, physics, label="PHY-2027-1", count=5, callbacks=None):
    book = ProductFactory(subject=physics)
    body = {"label": label, "subject": "PHY", "count": count, "product": book.slug, "note": "Printed by Saraighat"}
    with callbacks(execute=True):
        response = client.post(BATCHES, body, format="json")
    assert response.status_code == 202, response.content
    return CodeBatch.objects.get(label=label), response.json()


def printed(client, batch):
    """The codes of the printer's file, through the job's link (its starter's)."""
    job = client.get(f"{BATCHES}{batch.label}/").json()["generation"]
    download = client.get(job["result_url"])
    assert download.status_code == 200
    content = b"".join(download.streaming_content).decode()
    return [row["code"] for row in csv.DictReader(io.StringIO(content))]


def test_a_batch_keeps_digests_only_and_its_file_is_its_makers_for_24_hours(
    physics, django_capture_on_commit_callbacks, settings
):
    settings.STAFF_ALERT_EMAILS = ["owner@example.com"]
    sales = make_staff(roles.SALES)
    client = signed_in(sales)
    batch, answer = make_batch(client, physics, callbacks=django_capture_on_commit_callbacks)
    assert answer["batch"]["state"] == "generating" and answer["job"]["kind"] == "code_batch"
    batch.refresh_from_db()
    assert batch.generated_at is not None and batch.generated_by == sales and batch.printed == 5
    page = client.get(f"{BATCHES}{batch.label}/").json()
    assert page["state"] == "ready" and page["codes"] == 5 and page["file_until"] is not None
    assert page["generation"]["result"] == {"batch": "PHY-2027-1", "codes": 5}  # counts, never a code
    plain = printed(client, batch)
    assert len(plain) == 5 and len(set(plain)) == 5
    kept = list(BookCode.objects.filter(batch="PHY-2027-1").values_list("digest", flat=True))
    assert sorted(kept) == sorted(code_digest(code) for code in plain)
    stored = " ".join(str(value) for row in BookCode.objects.values() for value in row.values())
    assert not any(code.replace("-", "") in stored or code in stored for code in plain)  # digests only
    assert not any(code in str(event.details) for event in events() for code in plain)
    assert "Book codes made: batch PHY-2027-1" in mail.outbox[-1].subject  # the owners told
    # the file: its starter's alone
    job = Job.objects.get(kind="code_batch")
    owner = signed_in(make_staff(roles.OWNER))
    assert owner.get(f"{BATCHES}{batch.label}/").json()["generation"]["result_url"] is None
    link = client.get(f"{BATCHES}{batch.label}/").json()["generation"]["result_url"]
    assert owner.get(link).status_code == 404
    # gone after 24 hours: no link, the old one refused, the file deleted by the hourly purge
    Job.objects.filter(pk=job.pk).update(finished_at=timezone.now() - timedelta(hours=24, minutes=1))
    page = client.get(f"{BATCHES}{batch.label}/").json()
    assert page["file_until"] is None and page["generation"]["result_url"] is None
    assert client.get(link).json()["code"] == "link_expired"
    name = Job.objects.get(pk=job.pk).result_file
    from django.core.files.storage import default_storage

    assert default_storage.exists(name)
    assert purge_code_files() == 1 and not default_storage.exists(name)
    assert Job.objects.get(pk=job.pk).result_file == ""
    # a week's files are another kind's: the nightly purge leaves an export of a day alone
    export = Job.objects.create(kind="audit_export", params={}, result_file="staff/jobs/x/audit.jsonl",
                                finished_at=timezone.now() - timedelta(days=2))  # fmt: skip
    expire_access()
    assert Job.objects.get(pk=export.pk).result_file


def test_a_batch_whose_codes_were_not_made_is_made_again_once(physics):
    client = signed_in(make_staff(roles.SALES))
    book = ProductFactory(subject=physics)
    body = {"label": "PHY-2027-5", "subject": "PHY", "count": 3, "product": book.slug}
    assert client.post(BATCHES, body, format="json").status_code == 202  # its job is queued (never run here)
    batch = CodeBatch.objects.get(label="PHY-2027-5")
    Job.objects.filter(pk=batch.job_id).update(state=Job.State.FAILED, finished_at=timezone.now())
    assert client.get(f"{BATCHES}PHY-2027-5/").json()["state"] == "failed"
    again = {"kind": "code_batch", "params": {"batch": batch.pk}}
    started = client.post("/api/v1/staff/jobs/", again, format="json")
    assert started.status_code == 202, started.content
    assert client.get(f"{BATCHES}PHY-2027-5/").json()["state"] == "generating"  # it follows the new job
    refused = client.post("/api/v1/staff/jobs/", again, format="json")
    assert refused.json() == {"params": {"batch": ["It is generating: nothing to make again."]}}
    assert client.post("/api/v1/staff/jobs/", {**again, "dry_run": True}, format="json").status_code == 400
    jobs.run(started.json()["id"])
    page = client.get(f"{BATCHES}PHY-2027-5/").json()
    assert page["state"] == "ready" and page["codes"] == 3 and page["generation"]["id"] == started.json()["id"]


def test_the_label_is_the_print_runs_own(physics, django_capture_on_commit_callbacks):
    client = signed_in(make_staff(roles.SALES))
    make_batch(client, physics, callbacks=django_capture_on_commit_callbacks)
    book = ProductFactory(subject=physics)
    again = client.post(
        BATCHES, {"label": "phy-2027-1", "subject": "PHY", "count": 2, "product": book.slug}, format="json"
    )
    assert again.json() == {"label": ["A print run has this label already: give the new one its own (PHY-2027-2)."]}
    bad = client.post(BATCHES, {"label": "PHY 2027", "subject": "PHY", "count": 2, "product": book.slug}, format="json")
    assert "label" in bad.json()
    digital = ProductFactory(kind="digital", subject=physics)
    body = {"label": "PHY-2027-9", "subject": "PHY", "count": 2, "product": digital.slug}
    assert client.post(BATCHES, body, format="json").json() == {"product": ["A book (printed) the codes go into."]}
    assert client.post(BATCHES, {**body, "count": 0, "product": book.slug}, format="json").status_code == 400
    assert signed_in(make_staff(roles.SUPPORT)).post(BATCHES, {**body, "product": book.slug}).status_code == 403


def test_a_void_batch_refuses_its_unused_codes_and_keeps_the_redeemed(physics):
    plain = make_codes(physics, 3, "PHY-2027-2")
    batch = CodeBatch.objects.create(label="PHY-2027-2", subject=physics, printed=3, generated_at=timezone.now())
    api = APIClient()
    first = sign_in(api, student())
    redeem = api.post("/api/v1/learn/redeem/", {"code": plain[0]}, format="json")
    assert redeem.status_code == 200
    admin = signed_in(make_staff(roles.ADMIN))
    assert admin.post(f"{BATCHES}{batch.label}/void/", {}, format="json").json() == {
        "reason": ["This field is required."]
    }
    voided = admin.post(f"{BATCHES}{batch.label}/void/", {"reason": "The printer's proofs leaked"}, format="json")
    assert voided.json()["voided"] == 2 and voided.json()["batch"]["state"] == "void"
    sign_in(api, student())
    refused = api.post("/api/v1/learn/redeem/", {"code": plain[1]}, format="json")
    assert refused.status_code == 400 and refused.json()["code"][0].startswith("This code can no longer be used")
    assert Entitlement.objects.filter(user=first).exists()  # the redeemed code keeps what it opened
    sign_in(api, first)
    assert api.post("/api/v1/learn/redeem/", {"code": plain[0]}, format="json").status_code == 200  # the same again
    assert admin.post(f"{BATCHES}{batch.label}/void/", {"reason": "again"}, format="json").json() == {
        "non_field_errors": ["It was voided already."]
    }
    assert events("course.batch_voided").get().details == {"voided": 2}
    assert (
        signed_in(make_staff(roles.SUPPORT)).post(f"{BATCHES}{batch.label}/void/", {"reason": "x"}).status_code == 403
    )


def test_one_code_is_voided_and_a_redeemed_one_is_refused(physics):
    plain = make_codes(physics, 2, "PHY-2027-3")
    redeem_user = student()
    from .services import redeem

    redeem(redeem_user, plain[0])
    owner = signed_in(make_staff(roles.OWNER))
    url = f"{COURSE}codes/void/"
    assert owner.post(url, {"code": plain[0], "reason": "Leaked"}, format="json").json() == {
        "code": ["It was redeemed already: revoke the access it opened instead (the learner's page)."]
    }
    done = owner.post(url, {"code": plain[1].lower().replace("-", " "), "reason": "A photo online"}, format="json")
    assert done.status_code == 200 and done.json()["batch"] == "PHY-2027-3"
    assert owner.post(url, {"code": plain[1], "reason": "x"}, format="json").json() == {"code": ["It is void already."]}
    assert owner.post(url, {"code": "ABCD", "reason": "x"}, format="json").status_code == 400
    event = events("course.code_voided").get()
    assert plain[1] not in str(event.details) and event.reason == "A photo online"


def test_the_lookup_answers_in_one_line_audits_and_is_throttled(physics, monkeypatch, support):
    plain = make_codes(physics, 3, "PHY-2027-4")
    CodeBatch.objects.create(label="PHY-2027-4", subject=physics, printed=3, generated_at=timezone.now())
    child = student(date_of_birth=timezone.localdate().replace(year=timezone.localdate().year - 15))
    from .services import redeem

    redeem(child, plain[0])
    BookCode.objects.filter(digest=code_digest(plain[1])).update(voided_at=timezone.now())
    client = signed_in(support)

    def lookup(code):
        return client.post(f"{COURSE}codes/lookup/", {"code": code}, format="json").json()

    redeemed = lookup(plain[0].lower())
    assert redeemed["state"] == "redeemed" and redeemed["redeemed_by"]["id"] == child.pk
    assert redeemed["redeemed_by"]["email"].startswith(child.email[:2] + "•••") and redeemed["redeemed_by"]["is_minor"]
    assert redeemed["line"].startswith("Redeemed on ") and f"account #{child.pk}" in redeemed["line"]
    assert lookup(plain[1])["state"] == "void" and lookup(plain[1])["line"].startswith("Void since")
    unused = lookup(plain[2])
    assert unused["state"] == "unused" and unused["line"].endswith("Its batch is not marked dispatched yet.")
    assert lookup("7KQM-3XPA-9TRW")["state"] == "unknown"
    assert lookup("O0O0")["code"][0].startswith("A book code has 12")
    assert events("sensitive_read").get().details == {"what": "book_code", "child": True}
    lookups = events("course.code_lookup")
    assert [event.details["state"] for event in lookups] == ["redeemed", "void", "void", "unused", "unknown"]
    assert not any(code in str(event.details) for event in lookups for code in plain)
    cache.clear()
    from rest_framework.throttling import SimpleRateThrottle

    # the rates' own dict, put back after the test (rebinding it to a copy left 2 an hour for every later test)
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "staff_code_lookup", "2/hour")
    statuses = [client.post(f"{COURSE}codes/lookup/", {"code": plain[2]}, format="json").status_code
                for _ in range(3)]  # fmt: skip
    assert statuses == [200, 200, 429]


def test_a_batch_is_dispatched_once_and_never_before_its_codes(physics):
    batch = CodeBatch.objects.create(label="PHY-2027-5", subject=physics, printed=1)
    client = signed_in(make_staff(roles.SALES))
    url = f"{BATCHES}{batch.label}/dispatched/"
    assert client.post(url, {}, format="json").json() == {"non_field_errors": ["Its codes are not made yet."]}
    CodeBatch.objects.filter(pk=batch.pk).update(generated_at=timezone.now() - timedelta(days=3))
    future = (timezone.now() + timedelta(days=1)).isoformat()
    assert "at" in client.post(url, {"at": future}, format="json").json()
    two_days = timezone.now() - timedelta(days=2)
    answer = client.post(url, {"at": two_days.isoformat()}, format="json").json()
    assert answer["state"] == "dispatched"
    assert client.post(url, {}, format="json").json()["non_field_errors"][0].startswith("Marked dispatched already")


def sale(book, district_pin, user, copies=1):
    order = Order.objects.create(
        user=user, email=user.email, shipping_address={**ADDRESS, "pin": district_pin}, subtotal=100, total=100,
        status="paid", payment_method="razorpay", placed_at=timezone.now() - timedelta(days=1), livemode=True,
    )  # fmt: skip
    OrderItem.objects.create(order=order, product=book, title="b", hsn_code="4901", gst_rate=0, mrp=book.mrp,
                             unit_price=book.price, quantity=copies)  # fmt: skip


def test_the_codes_report_hides_districts_under_10(physics, settings):
    settings.RAZORPAY_KEY_ID = "rzp_live_x"
    book = ProductFactory(subject=physics, kind="sample-papers")
    PinCode.objects.create(pin="781001", districts=["Kamrup Metro"], states=["AS"])
    PinCode.objects.create(pin="788001", districts=["Cachar"], states=["AS"])
    plain = make_codes(physics, 20, "PHY-2027-6")
    batch = CodeBatch.objects.create(label="PHY-2027-6", subject=physics, product=book, printed=20,
                                     generated_at=timezone.now() - timedelta(days=5),
                                     created=timezone.now() - timedelta(days=5))  # fmt: skip
    from .services import redeem

    learners = [student() for _ in range(14)]
    for index, user in enumerate(learners):
        sale(book, "781001" if index < 11 else "788001", user)
        redeem(user, plain[index])
    revoked = Entitlement.objects.filter(user=learners[0]).get()
    Entitlement.objects.filter(pk=revoked.pk).update(revoked_at=timezone.now())
    BookCode.objects.filter(digest=code_digest(plain[19])).update(voided_at=timezone.now())
    client = signed_in(make_staff(roles.SUPPORT))
    report = client.get(f"{COURSE}codes/report/").json()
    row = report["rows"][0]
    assert row["batch"]["label"] == "PHY-2027-6"
    assert (row["printed"], row["sold"], row["activated"], row["revoked"], row["void"]) == (20, 14, 14, 1, 1)
    assert row["activation_rate"] == 0.7 and report["min_cell"] == 10
    assert row["districts"] == [
        {"district": "Kamrup Metro", "activated": 11, "hidden": False},
        {"district": "other districts", "activated": None, "hidden": True},  # Cachar's 3: fewer than 10
    ]
    assert report["totals"]["activated"] == 14 and "sold" in report["definitions"]
    assert batch.pk  # (the batch the report reads)


def test_the_migration_made_a_batch_of_each_label_counted_as_dispatched(physics):
    make_codes(physics, 3, "PHY-OLD-1")
    make_codes(None, 2, "ALL-OLD-1")
    migration = import_module("learn.migrations.0003_phase_b_course")
    migration.batches_from_codes(apps, None)
    old = CodeBatch.objects.get(label="PHY-OLD-1")
    assert (old.printed, old.subject, old.dispatched_at is not None) == (3, physics, True)
    assert CodeBatch.objects.get(label="ALL-OLD-1").subject is None
    migration.batches_from_codes(apps, None)  # run again: nothing twice
    assert CodeBatch.objects.count() == 2


def test_the_shells_codes_are_a_print_run_of_the_panel_too(physics, tmp_path):
    from django.core.management import call_command

    out = tmp_path / "codes.csv"
    call_command("make_book_codes", "ALL", "3", batch="ALL-2027-1", out=str(out), stderr=io.StringIO())
    batch = CodeBatch.objects.get(label="ALL-2027-1")
    assert (batch.printed, batch.subject, batch.generated_at is not None, batch.dispatched_at) == (3, None, True, None)
    assert len(out.read_text().splitlines()) == 4


def test_the_batch_pages_read_with_a_fixed_number_of_queries(physics):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = signed_in(make_staff(roles.OWNER))

    def count(path):
        client.get(path)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(path).status_code == 200
        return len(captured)

    def batch(label):
        make_codes(physics, 2, label)
        return CodeBatch.objects.create(label=label, subject=physics, product=ProductFactory(subject=physics),
                                        printed=2, generated_at=timezone.now())  # fmt: skip

    batch("PHY-Q-1")
    paths = [BATCHES, f"{BATCHES}PHY-Q-1/", f"{COURSE}codes/report/"]
    one = {path: count(path) for path in paths}
    for number in (2, 3, 4):
        batch(f"PHY-Q-{number}")
    FraudSignal.objects.create(kind="codes_undispatched", subject="b" * 64, count=1, window_start=timezone.now(),
                               window_end=timezone.now(), details={"batch": "PHY-Q-1"})  # fmt: skip
    for path in paths:
        assert count(path) == one[path], path
    assert jobs.KEEP_FILES[Job.Kind.CODE_BATCH] == timedelta(hours=codes.PRINTER_FILE_HOURS)
