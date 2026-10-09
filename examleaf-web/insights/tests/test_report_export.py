"""Exports of the reports as staff jobs (insights/exports.py): the filters of the page, the cap with an approver above
it, formula cells escaped, a small cell never a number in a file, and no report carrying a date of birth, a contact or
a key to a person (a test over every report and every file)."""

import csv
import io
import json
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.storage import default_storage
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from insights.exports import cell, escaped
from insights.jobs import health
from insights.models import CodeActivationStat
from insights.reports import EXPORTABLE
from learn.models import BookCode, CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from shipping.models import CodRemittance
from shop.factories import ProductFactory
from shop.models import Shipment
from staff.models import AuditEvent, ChangeRequest, Job
from staff.tests.conftest import STAFF, events, make_staff, signed_in

from .helpers import at, sell

pytestmark = pytest.mark.django_db
JOBS = STAFF + "jobs/"
PERIOD = {"from": "2026-10-01", "to": "2026-10-07"}


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live
    settings.INSIGHTS_MIN_CELL = 10
    settings.INSIGHTS_MIN_CELL_CLASS = 5


@pytest.fixture(autouse=True)
def october(monkeypatch):
    original = timezone.localdate
    monkeypatch.setattr(
        timezone, "localdate", lambda value=None, tz=None: date(2026, 10, 10) if value is None else original(value, tz)
    )


def start(user, report="sales", filters=None, **body):
    return signed_in(user).post(
        JOBS, {"kind": "report_export", "params": {"report": report, "filters": filters or {}}, **body}, format="json"
    )


def run(user, report="sales", filters=None, capture=None):
    with capture(execute=True):
        response = start(user, report, filters)
    assert response.status_code == 202, response.content
    return Job.objects.get(pk=response.json()["id"])


def table(job):
    with default_storage.open(job.result_file) as file:
        return list(csv.reader(io.StringIO(file.read().decode())))


def test_a_report_is_exported_as_a_job_with_its_filters_logged(django_capture_on_commit_callbacks):
    book = ProductFactory(title="Physics Sample Papers", price=Decimal("300.00"))
    sell(book, date(2026, 10, 2), copies=2)
    finance = make_staff(roles.FINANCE)
    job = run(finance, "sales", {**PERIOD, "by": "product"}, django_capture_on_commit_callbacks)
    assert (job.state, job.done, job.total, job.result) == ("done", 1, 1, {"rows": 1})
    header, row, *rest = table(job)
    assert header == ["Group", "Period", "Orders", "Units", "Gross (₹)", "Discount (₹)", "Net (₹)"]
    assert row == ["Physics Sample Papers", "", "1", "2", "600.00", "0.00", "600.00"]
    assert rest[-1][0] == "Report" and f"by staff member #{finance.pk}" in rest[-1][2]
    assert "by=product" in rest[-1][3] and "from=2026-10-01" in rest[-1][3]  # who, when and the filter, at the end
    assert job.result_file.endswith(".csv") and "2026-10-01-to-2026-10-07" in job.result_file
    assert "Rahul" not in job.result_file  # a file name carries no person
    logged = events("report.exported").get()
    assert logged.actor_id == finance.pk and logged.details["report"] == "sales" and logged.details["rows"] == 1
    assert logged.details["filters"] == {**PERIOD, "by": "product"} and logged.details["job"] == job.pk
    assert events("job.requested").filter(target_id=str(job.pk)).exists() and events("job.done").exists()
    client = signed_in(finance)
    detail = client.get(f"{JOBS}{job.pk}/").json()
    assert detail["result_url"] and client.get(detail["result_url"]).status_code == 200  # its starter's link
    assert signed_in(make_staff(roles.OWNER)).get(f"{JOBS}{job.pk}/").json()["result_url"] is None


def test_every_report_exports(django_capture_on_commit_callbacks):
    owner = make_staff(roles.OWNER)
    for key in EXPORTABLE:
        job = run(owner, key, {}, django_capture_on_commit_callbacks)
        assert job.state == "done", (key, job.errors)
        header, *_ = table(job)
        assert header == [column["label"] for column in EXPORTABLE[key].columns], key


def test_a_dry_run_counts_the_rows_and_writes_no_file(django_capture_on_commit_callbacks):
    sell(ProductFactory(), date(2026, 10, 2))
    with django_capture_on_commit_callbacks(execute=True):
        response = start(make_staff(roles.FINANCE), "sales", PERIOD, dry_run=True)
    job = Job.objects.get(pk=response.json()["id"])
    assert (job.state, job.result, job.result_file) == ("done", {"rows": 1}, "")
    assert not events("report.exported").exists()


def test_above_the_starters_limit_an_admin_approves_it_first(monkeypatch, django_capture_on_commit_callbacks):
    book = ProductFactory()
    sell(book, date(2026, 10, 2))
    other = ProductFactory()
    sell(other, date(2026, 10, 3))
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.FINANCE], "export_rows", 1)
    finance, admin = make_staff(roles.FINANCE), make_staff(roles.ADMIN)
    job = start(finance, "sales", {**PERIOD, "by": "product"}).json()
    assert job["state"] == "queued" and job["change_request_id"]  # two rows, a limit of one
    change = ChangeRequest.objects.get(pk=job["change_request_id"])
    assert change.action == "job.run" and change.payload["params"]["report"] == "sales"
    within = start(finance, "sales", {**PERIOD, "by": "class"}).json()
    assert within["change_request_id"] is None  # one row: within the limit
    sha = {"payload_sha256": change.payload_sha256}
    assert signed_in(admin).post(f"{STAFF}change-requests/{change.pk}/approve/", sha).json()["status"] == "approved"
    with django_capture_on_commit_callbacks(execute=True):
        assert signed_in(finance).post(f"{STAFF}change-requests/{change.pk}/execute/").json()["status"] == "executed"
    assert Job.objects.get(pk=job["id"]).state == "done"


def test_text_a_spreadsheet_would_run_is_made_text_and_numbers_are_left_alone():
    for risky in ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1"]:
        assert escaped(risky) == f"'{risky}" and cell(risky) == f"'{risky}"
    assert cell("Physics") == "Physics" and cell("") == ""
    assert cell(Decimal("-50.00")) == "-50.00" and cell(-3) == -3 and cell(None) == ""  # a negative number is a number
    assert cell(date(2026, 10, 1)) == "2026-10-01"


def test_a_product_title_that_is_a_formula_is_exported_as_text(django_capture_on_commit_callbacks):
    sell(ProductFactory(title="=1+1 Sample Papers", slug="formula", price=Decimal("300.00")), date(2026, 10, 2))
    job = run(make_staff(roles.AUDITOR), "sales", {**PERIOD, "by": "product"}, django_capture_on_commit_callbacks)
    assert table(job)[1][0] == "'=1+1 Sample Papers"


def test_a_small_cell_is_words_in_a_file_never_a_number(django_capture_on_commit_callbacks, directory):
    book = ProductFactory(price=Decimal("300.00"))
    for _ in range(3):
        sell(book, date(2026, 10, 2), pin="785001")  # Jorhat: three orders
    for _ in range(12):
        sell(book, date(2026, 10, 2), pin="781001")
    job = run(
        make_staff(roles.AUDITOR), "sales-by-place", {**PERIOD, "level": "district"}, django_capture_on_commit_callbacks
    )
    rows = {row[0]: row for row in table(job)[1:3]}
    assert rows["Jorhat, Assam"][1:] == ["fewer than 10"] * 3
    assert rows["Kamrup Metro, Assam"][1:] == ["12", "12", "3600.00"]
    assert "900.00" not in "".join(map(str, table(job)))  # Jorhat's net never reaches the file


def test_who_may_export_what(django_capture_on_commit_callbacks):
    sell(ProductFactory(), date(2026, 10, 2))
    assert start(make_staff(roles.SALES), "sales", PERIOD).status_code == 403  # reads the report, not the export
    refused = start(make_staff(roles.MARKETING), "sales", PERIOD)
    assert refused.status_code == 403 and "staff.export_report" in refused.json()["detail"]
    assert start(make_staff(roles.SUPPORT), "sales", PERIOD).status_code == 403
    finance_codes = start(make_staff(roles.FINANCE), "codes", {})  # the export, but not the course's data
    assert finance_codes.status_code == 403 and "learn.view_bookcode" in finance_codes.json()["detail"]
    for role in (roles.FINANCE, roles.ADMIN, roles.OWNER, roles.AUDITOR):
        assert start(make_staff(role), "sales", PERIOD).status_code == 202, role
    assert AuditEvent.objects.filter(action="authz_fail").exists()


def test_the_export_needs_a_recent_authentication():
    finance = make_staff(roles.FINANCE)
    stale = signed_in(finance, reauth=False).post(
        JOBS, {"kind": "report_export", "params": {"report": "sales"}}, format="json"
    )
    assert stale.status_code == 403 and stale.json()["code"] == "reauthentication_required"


def test_the_params_are_checked_before_anything_is_queued():
    finance = make_staff(roles.FINANCE)
    for params, where in [
        ({"report": "everything"}, "report"),
        ({}, "report"),
        ({"report": "sales", "filters": {"colour": "red"}}, "filters"),
        ({"report": "sales", "filters": {"from": "yesterday"}}, "filters"),
        ({"report": "sales", "filters": {"from": "2024-01-01", "to": "2026-10-01"}}, "filters"),  # over 13 months
        ({"report": "sales", "filters": "by=product"}, "filters"),
        ({"report": "sales-by-place", "filters": {"level": "street"}}, "filters"),
    ]:
        response = signed_in(finance).post(JOBS, {"kind": "report_export", "params": params}, format="json")
        assert response.status_code == 400 and where in json.dumps(response.json()["params"]), params
    assert not Job.objects.exists()


# ---- No report carries a person ----

PERSON = {
    "name": "Anil Kumar Bora",
    "email": "anil.bora@example.com",
    "phone": "+919864099999",
    "parent": "Mrs Bora Parent",
    "contact": "parent.bora@example.com",
    "born": date(2010, 5, 5),
    "street": "House 77 Secret Lane",
}
KEYS = {"user", "user_id", "learner", "learner_id", "account", "email", "phone", "full_name", "date_of_birth", "dob"}
KEYS |= {"parent", "parent_name", "parent_contact", "address", "line1", "line2", "customer", "requester", "birth"}


def walk(value, found):
    if isinstance(value, dict):
        for key, inside in value.items():
            found.add(key)
            walk(inside, found)
    elif isinstance(value, list):
        for inside in value:
            walk(inside, found)
    return found


def test_no_report_and_no_file_carries_a_person(django_capture_on_commit_callbacks, physics, directory):
    """A minor who bought a book, redeemed a code, answered and watched: every report is run with the whole of them in
    the database, as is every export: not a key to an account, not a name, a contact, a date of birth or an address."""
    child = UserFactory(
        full_name=PERSON["name"],
        email=PERSON["email"],
        phone=PERSON["phone"],
        parent_name=PERSON["parent"],
        parent_contact=PERSON["contact"],
        date_of_birth=PERSON["born"],
        class_level=10,
    )
    book = ProductFactory(subject=physics, price=Decimal("300.00"))
    for _ in range(12):
        order = sell(
            book,
            date(2026, 10, 2),
            user=child,
            email=PERSON["email"],
            name=PERSON["name"],
            phone=PERSON["phone"],
            line1=PERSON["street"],
        )
        shipment = Shipment.objects.create(order=order, courier="India Post", tracking_number=f"T{order.pk}")
        CodRemittance.objects.create(
            shipment=shipment, expected_amount=300, expected_on=date(2026, 10, 1), state="overdue"
        )
    chapter = Chapter.objects.create(subject=physics, number=1, title="Charges")
    clip = Clip.objects.create(revision=Revision.objects.create(chapter=chapter, title="Revise"), title="Gauss")
    item = QuizItem.objects.create(chapter=chapter, kind="true_false", text="T", answer="true")
    card = FlashCard.objects.create(chapter=chapter, front="f", back="b")
    BookCode.objects.create(
        digest="a" * 64, batch="PHY-1", subject=physics, redeemed_by=child, redeemed_at=at(date(2026, 10, 3))
    )
    QuizAttempt.objects.create(user=child, item=item, correct=True, created=at(date(2026, 10, 6)))
    CardReview.objects.create(user=child, card=card, known=True, created=at(date(2026, 10, 6)))
    Progress.objects.create(user=child, clip=clip, completed=True)
    Progress.objects.filter(user=child).update(updated=at(date(2026, 10, 6)))
    CodeActivationStat.objects.create(batch="PHY-1", district="Kamrup Metro", redeemed=12, redeemed_7d=1)
    health.course_health(today=date(2026, 10, 14))
    owner = make_staff(roles.OWNER)
    client = signed_in(owner)
    seen, texts = set(), []
    for path in [
        "",
        "sales/",
        "sales-by-place/",
        "sales-by-place/?level=pin",
        "codes/",
        "course-health/",
        "course-health/?grain=day",
        "cod/",
        "settlements/",
    ]:
        response = client.get(
            STAFF + "reports/" + path, {"from": PERIOD["from"], "to": PERIOD["to"]} if "?" not in path else {}
        )
        assert response.status_code == 200, (path, response.content)
        walk(response.json(), seen)
        texts.append(response.content.decode())
    home = client.get(STAFF + "home/")
    walk(home.json(), seen)
    texts.append(home.content.decode())
    for key in EXPORTABLE:
        job = run(owner, key, {}, django_capture_on_commit_callbacks)
        texts.append(" ".join(" ".join(row) for row in table(job)) + job.result_file)
    assert not seen & KEYS, seen & KEYS
    everything = "\n".join(texts)
    for what, value in PERSON.items():
        assert str(value) not in everything, what
