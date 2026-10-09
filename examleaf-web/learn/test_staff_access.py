"""The Course module's access side (learn/staff_api.py, learn.course): entitlements granted, extended and revoked with
a reason (and refused where they would not make sense), the student's progress kept across a revoke and a new grant,
the bulk versions as jobs with a dry run, a search by email as a lookup event with its hash, the learner's page logged
as a sensitive read (a child's a summary without times), a phone signed out, and no endpoint that lists or ranks
learners."""

from datetime import date, timedelta

import pytest
from django.urls import URLPattern, URLResolver
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.factories import UserFactory
from api.tests import sign_in, student
from content.models import Subject
from staff.audit import mask
from staff.models import Job

from . import staff_api
from .conftest import COURSE, STAFF, events, make_staff, signed_in
from .models import BookCode, CardReview, Clip, Device, Entitlement, FlashCard, Progress, QuizAttempt, QuizItem
from .services import make_codes, redeem

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def grant(client, user, subject="PHY", **body):
    return client.post(f"{COURSE}entitlements/", {"user": user.pk, "subject": subject, "reason": "A school's pupil",
                                                   **body}, format="json")  # fmt: skip


def test_access_is_granted_extended_and_revoked_with_a_reason(support, physics):
    pupil = student()
    client = signed_in(support)
    until = timezone.localdate() + timedelta(days=30)
    made = grant(client, pupil, valid_until=str(until), reference="SR-2026-000103")
    assert made.status_code == 201
    entitlement = Entitlement.objects.get(pk=made.json()["id"])
    assert (entitlement.source, entitlement.note, entitlement.reference) == (
        "grant",
        "A school's pupil",
        "SR-2026-000103",
    )
    assert made.json()["state"] == "active" and made.json()["user"]["email"].startswith(pupil.email[:2] + "•••")
    assert grant(client, pupil).json() == {
        "subject": [f"It is open already, until {until:%d %b %Y} (entitlement #{entitlement.pk}): extend that one "
                    "instead."]
    }  # fmt: skip
    assert grant(client, make_staff(roles.SALES)).json() == {
        "user": ["A member of staff has every subject open already."]
    }
    assert "valid_until" in grant(client, student(), valid_until="2020-01-01").json()
    assert grant(client, pupil, subject="XYZ").json() == {"subject": ["No subject XYZ: PHY, CHE, MAT, BIO or ALL."]}
    url = f"{COURSE}entitlements/{entitlement.pk}/"
    extended = client.post(url + "extend/", {"days": 10, "reason": "The exam moved"}, format="json").json()
    assert extended["valid_until"] == str(until + timedelta(days=10))
    assert client.post(url + "extend/", {"days": 400, "reason": "x"}, format="json").status_code == 400
    revoked = client.post(url + "revoke/", {"reason": "Granted by mistake"}, format="json").json()
    assert revoked["state"] == "revoked" and revoked["valid_until"] == str(timezone.localdate() - timedelta(days=1))
    assert client.post(url + "revoke/", {"reason": "again"}, format="json").json() == {
        "non_field_errors": ["It was revoked already."]
    }
    assert client.post(url + "extend/", {"days": 5, "reason": "x"}, format="json").json() == {
        "non_field_errors": ["It was revoked: grant access again instead."]
    }
    history = client.get(url).json()["history"]
    assert [version["type"] for version in history] == ["~", "~", "+"]
    assert {e.action for e in events(target_type="learn.entitlement")} == {
        "course.entitlement_granted", "course.entitlement_extended", "course.entitlement_revoked",
    }  # fmt: skip
    # a member narrowed to a subject grants that subject only, never all at once
    narrow = make_staff(roles.SUPPORT)
    from staff.models import StaffScope

    StaffScope.objects.create(user=narrow, kind="subject", value="CHE")
    assert grant(signed_in(narrow), student(), subject="ALL").json() == {"subject": ["Not one of your subjects (CHE)."]}


def test_the_students_progress_stays_across_a_revoke_and_a_new_grant(support, physics):
    api = APIClient()
    pupil = sign_in(api, student())
    code = make_codes(physics, 1, "PHY-2027-1")[0]
    entitlement = redeem(pupil, code)
    clip = Clip.objects.filter(revision__chapter__number=1).first()
    api.post(f"/api/v1/learn/clips/{clip.pk}/progress/", {"seconds_watched": 120, "completed": True}, format="json")
    api.post(f"/api/v1/learn/quiz/{QuizItem.objects.first().pk}/attempt/", {"answer": "true"}, format="json")
    before = api.get("/api/v1/me/learning/").json()["subjects"][0]
    assert (before["clips_watched"], before["quiz_answers"], before["entitled"]) == (1, 1, True)
    client = signed_in(support)
    client.post(f"{COURSE}entitlements/{entitlement.pk}/revoke/", {"reason": "A refunded book"}, format="json")
    ended = api.get("/api/v1/me/learning/").json()["subjects"][0]
    assert (ended["clips_watched"], ended["quiz_answers"], ended["entitled"]) == (1, 1, False)
    assert api.get(f"/api/v1/learn/clips/{Clip.objects.filter(revision__chapter__number=1)[1].pk}/").status_code == 403
    assert grant(client, pupil).status_code == 201  # access again: where it stopped
    again = api.get("/api/v1/me/learning/").json()["subjects"][0]
    assert again == before
    assert Progress.objects.filter(user=pupil).count() == 1 and QuizAttempt.objects.filter(user=pupil).count() == 1


def test_access_in_bulk_is_a_job_with_a_dry_run_first(support, physics, django_capture_on_commit_callbacks):
    pupils = [student() for _ in range(3)]
    open_one = Entitlement.objects.create(user=pupils[0], subject=physics, valid_until=timezone.localdate())
    client = signed_in(support)
    body = {"kind": "bulk_action", "dry_run": True, "params": {"action": "entitlement.grant",
            "targets": [pupil.pk for pupil in pupils], "payload": {"subject": "PHY", "valid_until": None},
            "reason": "Cotton Collegiate's pupils"}}  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True):
        started = client.post(f"{STAFF}jobs/", body, format="json").json()
    job = Job.objects.get(pk=started["id"])
    assert job.result["outcomes"] == {"valid": 2, "refused": 1} and job.errors[0]["id"] == pupils[0].pk
    assert Entitlement.objects.count() == 1  # the dry run made nothing
    body["dry_run"] = False
    with django_capture_on_commit_callbacks(execute=True):
        started = client.post(f"{STAFF}jobs/", body, format="json").json()
    job = Job.objects.get(pk=started["id"])
    assert job.result["outcomes"] == {"executed": 2, "refused": 1}
    assert set(Entitlement.objects.filter(source="grant", valid_until=None).values_list("user", flat=True)) == {
        pupils[1].pk, pupils[2].pk,
    }  # fmt: skip
    extend = {"kind": "bulk_action", "dry_run": False, "params": {"action": "entitlement.extend",
              "targets": [open_one.pk], "payload": {"days": 30}, "reason": "The exam moved"}}  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"{STAFF}jobs/", extend, format="json")
    open_one.refresh_from_db()
    assert open_one.valid_until == timezone.localdate() + timedelta(days=30)
    revoke = {"kind": "bulk_action", "dry_run": False, "params": {"action": "entitlement.revoke",
              "targets": [open_one.pk], "payload": {}, "reason": "A refunded order"}}  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"{STAFF}jobs/", revoke, format="json")
    assert Entitlement.objects.get(pk=open_one.pk).revoked_at is not None


def test_a_search_by_email_is_a_lookup_event_with_its_hash_and_lists_filter(support, physics):
    pupil = student(email="riya.das@example.com")
    Entitlement.objects.create(user=pupil, subject=physics, source="book_code")
    Entitlement.objects.create(user=student(), subject=None, revoked_at=timezone.now(),
                               valid_until=date(2026, 1, 1))  # fmt: skip
    client = signed_in(support)
    rows = client.get(f"{COURSE}entitlements/?q=Riya.Das@example.com").json()["results"]
    assert [row["user"]["id"] for row in rows] == [pupil.pk]
    event = events("customer.lookup").get()
    assert event.details["query"] == mask("riya.das@example.com", "contact") and event.details["found"] == 1
    assert "riya" not in str(event.details)
    assert [row["state"] for row in client.get(f"{COURSE}entitlements/?state=revoked").json()["results"]] == ["revoked"]
    assert [row["subject"] for row in client.get(f"{COURSE}entitlements/?subject=ALL").json()["results"]] == [None]
    assert len(client.get(f"{COURSE}entitlements/?source=book_code&state=active").json()["results"]) == 1


def learner_url(user):
    return f"{COURSE}learners/{user.pk}/"


def test_the_learner_page_is_logged_and_a_childs_is_a_summary_without_times(support, physics):
    adult = student(date_of_birth=date(2000, 1, 1))
    child = student(date_of_birth=timezone.localdate().replace(year=timezone.localdate().year - 16))
    for pupil in (adult, child):
        Entitlement.objects.create(user=pupil, subject=physics, valid_until=timezone.localdate() + timedelta(days=9))
        Progress.objects.create(user=pupil, clip=Clip.objects.first(), seconds_watched=120, completed=True)
        CardReview.objects.create(user=pupil, card=FlashCard.objects.first(), known=True)
        Device.objects.create(user=pupil, token=f"fid-{pupil.pk}", platform="android")
    code = make_codes(physics, 1, "PHY-2027-1")[0]
    redeem(adult, code)
    client = signed_in(support)
    page = client.get(learner_url(adult)).json()
    assert page["logged"] is True and page["summary_only"] is False
    assert page["summary"]["clips_watched"] == 1 and page["summary"]["last_active"] is not None
    assert page["devices"][0]["last_seen"] is not None and page["codes"][0]["batch"] == "PHY-2027-1"
    chapter = next(row for row in page["chapters"] if row["number"] == 1)
    assert (chapter["clips_watched"], chapter["clips_total"], chapter["card_reviews"]) == (1, 3, 1)
    assert page["tickets"] == [] and page["user"]["email"].endswith("@example.com")
    read = events("sensitive_read").get(target_id=str(adult.pk))
    assert read.details == {"what": "learner", "child": False}
    page = client.get(learner_url(child)).json()
    assert page["summary_only"] is True and page["user"]["is_minor"] is True
    assert page["summary"]["last_active"] is None and page["summary"]["last_active_week"] is not None
    assert all(device["last_seen"] is None and device["added"] is None for device in page["devices"])
    assert events("sensitive_read").get(target_id=str(child.pk)).details["child"] is True
    unknown = student()  # no date of birth: a summary too
    assert client.get(learner_url(unknown)).json()["summary_only"] is True
    assert client.get(learner_url(make_staff(roles.SUPPORT))).status_code == 404  # staff are not learners
    assert signed_in(make_staff(roles.CONTENT_EDITOR)).get(learner_url(adult)).status_code == 403


def test_a_phone_is_signed_out_of_the_account(support):
    pupil = student()
    device = Device.objects.create(user=pupil, token="fid-1", platform="ios")
    other = Device.objects.create(user=UserFactory(), token="fid-2", platform="ios")
    client = signed_in(support)
    url = f"{COURSE}learners/{pupil.pk}/devices/"
    assert client.post(f"{url}{other.pk}/sign-out/").status_code == 404  # another account's
    assert client.post(f"{url}{device.pk}/sign-out/").status_code == 204
    assert not Device.objects.filter(pk=device.pk).exists() and Device.objects.filter(pk=other.pk).exists()
    assert events("course.device_signed_out").get().details == {"device": device.pk, "platform": "ios"}


SCORES = ("score", "risk", "attention", "rank", "progress", "accuracy", "active", "streak")


def walk(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


def test_no_endpoint_lists_learners_or_orders_them_by_a_score():
    """Plan 5.11 and 10.1 (DPDP Act s.9(3)): no per-student "needs attention" list. No path of the module lists
    accounts; the one list of rows naming accounts (entitlements) is ordered by date only, and takes no ordering."""
    paths = [path for path, _ in walk(staff_api.urlpatterns)]
    assert [path for path in paths if path.startswith("learners")] == [
        "learners/<int:user>/",
        "learners/<int:user>/devices/<int:device>/sign-out/",
    ]  # one learner at a time, never a list
    for path, callback in walk(staff_api.urlpatterns):
        cls = getattr(callback, "cls", None)
        ordering = getattr(getattr(cls, "pagination_class", None), "ordering", ()) or ()
        ordering = [ordering] if isinstance(ordering, str) else list(ordering)
        assert not any(word in field for field in ordering for word in SCORES), (path, ordering)
        assert not getattr(cls, "ordering_fields", None), path  # no ?ordering= anywhere
    assert staff_api.EntitlementViewSet.pagination_class.ordering == ("-created", "-pk")


def test_the_entitlement_and_learner_reads_take_a_fixed_number_of_queries(support, physics):
    client = signed_in(support)
    pupil = student(date_of_birth=date(2000, 1, 1))
    Entitlement.objects.create(user=pupil, subject=physics)

    def count(path):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.get(path)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(path).status_code == 200
        return len(captured)

    one = {path: count(path) for path in [f"{COURSE}entitlements/", learner_url(pupil)]}
    for _ in range(3):
        Entitlement.objects.create(user=student(), subject=Subject.objects.get(code="PHY"))
        Entitlement.objects.create(user=pupil, subject=None, revoked_at=timezone.now(), valid_until=date(2026, 1, 1))
        Device.objects.create(user=pupil, token=f"fid-{Device.objects.count()}", platform="android")
        BookCode.objects.create(digest=f"{BookCode.objects.count():064d}", batch="PHY-1", redeemed_by=pupil,
                                redeemed_at=timezone.now())  # fmt: skip
    for path, before in one.items():
        assert count(path) == before, path
