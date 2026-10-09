"""The Catalogue module's jobs (shop/catalogue_jobs.py): a school's single-use codes and their file, the product import
as a dry run then its apply for the same file, the export of the list's filters with formula cells escaped; each above
its starter's limit through an approver first."""

import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts import roles
from shop import catalogue_jobs
from shop.factories import CouponFactory, ProductFactory
from shop.models import CouponCode, Product
from staff.models import AuditEvent, ChangeRequest, Job
from staff.tests.conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
JOBS = STAFF + "jobs/"


def started(client, capture, kind, params, dry_run=False):
    with capture(execute=True):
        response = client.post(JOBS, {"kind": kind, "params": params, "dry_run": dry_run}, format="json")
    return response


def rows_of(job):
    with default_storage.open(job.result_file) as file:
        return list(csv.reader(io.StringIO(file.read().decode("utf-8-sig"))))


# ---- coupon_codes ----


def test_a_schools_codes_are_made_by_a_job_and_given_as_a_file(django_capture_on_commit_callbacks):
    marketing = signed_in(make_staff(roles.MARKETING))
    CouponFactory(code="PLAIN")
    CouponFactory(code="CCHS", single_use=True, value=Decimal("15"))
    refused = marketing.post(JOBS, {"kind": "coupon_codes", "params": {"coupon": "plain", "count": 0}}, format="json")
    problems = refused.json()["params"]
    assert refused.status_code == 400 and set(problems) == {"coupon", "count", "prefix", "note"}
    assert "single-use" in problems["coupon"][0]
    params = {"coupon": "cchs", "count": 30, "prefix": "cchs", "note": "=Cotton Collegiate"}
    response = started(marketing, django_capture_on_commit_callbacks, "coupon_codes", params)
    assert response.status_code == 202, response.content
    job = Job.objects.get(pk=response.json()["id"])
    assert (job.state, job.done, job.result) == ("done", 30, {"codes": 30, "coupon": "CCHS"})
    header, *rows = rows_of(job)
    assert header == ["code", "school", "offer", "minimum order", "valid from", "valid until", "use"]
    assert len(rows) == 30 and {row[0] for row in rows} == set(CouponCode.objects.values_list("code", flat=True))
    assert rows[0][1] == "'=Cotton Collegiate" and rows[0][2] == "15% off"  # a formula never reaches a spreadsheet
    assert all(row[0].startswith("CCHS-") for row in rows) and job.result_file.endswith(".csv")
    made = AuditEvent.objects.get(action="coupon.codes_made")
    assert made.details == {"job": job.pk, "count": 30}
    above = started(marketing, django_capture_on_commit_callbacks, "coupon_codes", {**params, "count": 101}).json()
    assert above["state"] == "queued" and above["change_request_id"]  # MARKETING: 100 rows, then an approver
    assert CouponCode.objects.count() == 30


# ---- product_import ----


def upload(client, capture, text):
    with capture(execute=True):
        response = client.post(
            STAFF + "catalogue/import/",
            {"file": SimpleUploadedFile("products.csv", text.encode(), content_type="text/csv")},
            format="multipart",
        )
    assert response.status_code == 202, response.content
    return Job.objects.get(pk=response.json()["id"])


def exported_csv(client, capture, **filters):
    response = started(client, capture, "product_export", {"filters": filters})
    assert response.status_code == 202, response.content
    return rows_of(Job.objects.get(pk=response.json()["id"]))


def as_text(rows):
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue()


def test_an_import_runs_dry_then_applies_the_same_file_through_the_panels_rules(django_capture_on_commit_callbacks):
    capture = django_capture_on_commit_callbacks
    admin = make_staff(roles.ADMIN)  # the import is ADMIN's (plan 5.5); 50% off at most without an approver
    client = signed_in(admin)
    physics = ProductFactory(slug="physics", title="Physics", weight_grams=300, packaging="flyer", stock=7)
    ProductFactory(slug="chemistry", title="Chemistry", weight_grams=300, packaging="flyer")
    ProductFactory(slug="maths", title="Maths", weight_grams=300, packaging="flyer", mrp=Decimal("400.00"))
    header, *rows = exported_csv(client, capture)  # the admin's format, round-tripped
    column = {name: index for index, name in enumerate(header)}
    by_slug = {row[column["slug"]]: row for row in rows}
    by_slug["physics"][column["title"]] = "Physics 2027"
    by_slug["physics"][column["weight_grams"]] = "320"
    by_slug["physics"][column["stock"]] = "999"  # never imported: sales go on meanwhile
    by_slug["maths"][column["price"]] = "100.00"  # 75% off: waits for FINANCE
    new = dict.fromkeys(header, "")
    new.update(slug="biology", title="Biology", kind="sample-papers", is_active="0", mrp="300.00", price="270.00")
    new.update(weight_grams="250", packaging="flyer", hsn_code="4901")
    wrong = {**new, "slug": "bad-isbn", "isbn": "9780306406158"}
    rows = [*by_slug.values(), [new[name] for name in header], [wrong[name] for name in header]]
    dry = upload(client, capture, as_text([header, *rows]))
    counts = {"created": 1, "updated": 2, "unchanged": 1, "errors": 1, "prices_waiting": 1}
    assert dry.state == "done" and dry.dry_run and dry.result["counts"] == counts, (dry.result, dry.errors)
    assert dry.errors[0]["label"] == "bad-isbn" and "ISBN" in dry.errors[0]["message"]
    ways = {row["slug"]: row["price"] for row in dry.result["rows"]}
    assert ways == {"physics": None, "maths": "waits", "biology": "at once"}
    assert not Product.objects.filter(slug="biology").exists()
    assert Product.objects.get(slug="physics").title == "Physics"  # a dry run changes nothing
    applied = started(client, capture, "product_import", {"file": dry.params["file"], "dry_run_job": dry.pk})
    job = Job.objects.get(pk=applied.json()["id"])
    assert job.state == "done" and job.result["counts"] == counts, (job.result, job.errors)
    physics.refresh_from_db()
    assert (physics.title, physics.weight_grams, physics.stock) == ("Physics 2027", 320, 7)
    assert physics.history.first().history_change_reason == f"Product import (job #{job.pk})"
    biology = Product.objects.get(slug="biology")
    assert (biology.price.amount, biology.is_active, biology.hsn_id) == (Decimal("270.00"), False, "4901")
    waiting = ChangeRequest.objects.get(action="product.price", status="pending")
    assert waiting.target_label.startswith("maths") or "Maths" in waiting.target_label
    assert Product.objects.get(slug="maths").price.amount == Decimal("299.00")  # until FINANCE approves
    assert not default_storage.exists(catalogue_jobs.upload_name(dry.params["file"]))  # applied: the file goes
    params = {"file": dry.params["file"], "dry_run_job": dry.pk}
    again = client.post(JOBS, {"kind": "product_import", "params": params}, format="json")
    assert again.status_code == 400  # its file has gone with its apply


def test_an_apply_needs_its_own_finished_dry_run_of_the_same_bytes_within_a_day(django_capture_on_commit_callbacks):
    capture = django_capture_on_commit_callbacks
    client = signed_in(make_staff(roles.ADMIN))
    ProductFactory(slug="physics", title="Physics", weight_grams=300, packaging="flyer")
    text = "slug,title\nphysics,Physics 2027\n"
    dry, other = upload(client, capture, text), upload(client, capture, text)
    token = dry.params["file"]

    def apply(file, dry_run_job):
        job = started(client, capture, "product_import", {"file": file, "dry_run_job": dry_run_job}).json()
        return Job.objects.get(pk=job["id"])

    wrong_file = apply(other.params["file"], dry.pk)
    assert wrong_file.state == "failed" and "its own file" in wrong_file.errors[0]["message"]
    default_storage.delete(catalogue_jobs.upload_name(token))
    default_storage.save(catalogue_jobs.upload_name(token), ContentFile(b"slug,title\nphysics,Physics 2030\n"))
    changed = apply(token, dry.pk)
    assert changed.state == "failed" and "changed since its dry run" in changed.errors[0]["message"]
    Job.objects.filter(pk=other.pk).update(finished_at=timezone.now() - timedelta(hours=25))
    late = apply(other.params["file"], other.pk)
    assert late.state == "failed" and "more than 24 hours" in late.errors[0]["message"]
    someone = signed_in(make_staff(roles.OWNER))
    theirs = started(someone, capture, "product_import", {"file": other.params["file"], "dry_run_job": other.pk})
    assert Job.objects.get(pk=theirs.json()["id"]).errors[0]["message"].startswith("No such dry run of yours")
    assert Product.objects.get(slug="physics").title == "Physics"
    no_slug = {"file": SimpleUploadedFile("x.csv", b"title\nx\n")}
    assert client.post(STAFF + "catalogue/import/", no_slug, format="multipart").status_code == 400
    sales = signed_in(make_staff(roles.SALES))
    file = {"file": SimpleUploadedFile("x.csv", text.encode())}
    assert sales.post(STAFF + "catalogue/import/", file, format="multipart").status_code == 403  # ADMIN's


# ---- product_export ----


def test_the_export_takes_the_lists_filters_escapes_formulas_and_waits_above_the_limit(
    monkeypatch, django_capture_on_commit_callbacks
):
    capture = django_capture_on_commit_callbacks
    client = signed_in(make_staff(roles.ADMIN))
    ProductFactory(slug="formula", title='=HYPERLINK("http://example.com")', weight_grams=300, packaging="flyer")
    ProductFactory(slug="set", kind=Product.Kind.BUNDLE)
    header, *rows = exported_csv(client, capture)
    titles = {row[header.index("slug")]: row[header.index("title")] for row in rows}
    assert titles["formula"].startswith("'=HYPERLINK") and set(titles) == {"formula", "set"}
    assert header == catalogue_jobs.COLUMNS  # the import reads what the export writes
    header, *rows = exported_csv(client, capture, kind="bundle")
    assert [row[0] for row in rows] == ["set"]
    unknown = client.post(JOBS, {"kind": "product_export", "params": {"filters": {"owner": "x"}}}, format="json")
    assert unknown.status_code == 400 and "owner" in unknown.json()["params"]["filters"]
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.ADMIN], "export_rows", 1)
    waiting = started(client, capture, "product_export", {"filters": {}}).json()
    assert waiting["state"] == "queued" and waiting["change_request_id"]
    assert ChangeRequest.objects.get(pk=waiting["change_request_id"]).action == "job.run"
    exported = AuditEvent.objects.filter(action="catalogue.exported")
    assert exported.count() == 2 and exported.first().details["rows"] in (1, 2)
