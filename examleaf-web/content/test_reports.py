"""Reported mistakes (plan 5.10, research-lms-crm-cms.md 2.4): the public "Report a mistake" (Turnstile checked as the
contact form checks it, 5 an hour and 20 a day per address, a honeypot, spam kept apart and purged after 30 days), the
triage (its states, the inbox, the reporter told once), the errata, and the item analysis's flags joining the queue
once."""

from datetime import timedelta

import httpx
import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import forms, roles
from accounts.factories import UserFactory
from accounts.models import TeacherProfile
from insights.models import ItemStat
from learn.models import Chapter, QuizItem
from staff.models import InboxItem

from . import reports
from .conftest import CONTENT, events, make_paper, make_staff, narrowed, signed_in
from .models import ErrorReport, Solution
from .tasks import flag_items, purge_spam

pytestmark = pytest.mark.django_db
REPORT = {"kind": "solution", "paper": "phy-e01", "question": "2(c)", "step": 2, "category": "wrong_answer"}


@pytest.fixture(autouse=True)
def fresh_limits():
    cache.clear()  # the limits per address are counted in the cache


def send(client=None, **fields):
    return (client or APIClient()).post("/api/v1/reports/", {**REPORT, **fields}, format="json")


def test_a_reader_reports_a_step_and_the_triage_of_its_subject_has_it():
    make_paper()
    answer = send(printing="PHY-2027-1", note="0.5 A, not 5 A.", email="reader@example.com")
    assert answer.status_code == 201, answer.content
    report = ErrorReport.objects.get(pk=answer.json()["reference"])
    assert (
        report.target == Solution.objects.get() and report.question.label == "2(c)" and report.paper.code == "PHY-E01"
    )
    assert (report.step, report.printing, report.state, report.spam, report.reporter) == (
        2,
        "PHY-2027-1",
        "reported",
        False,
        None,
    )
    item = InboxItem.objects.get(kind=InboxItem.Kind.ERROR_REPORT)
    assert item.title == f"Reported mistake #{report.pk}: PHY-E01 2(c), step 2" and "reader" not in item.title
    assert (item.permission, item.data["subject"]) == ("staff.triage_report", "PHY")
    event = events("content.report_received").get()
    assert event.actor_type == "anonymous" and "reader@example.com" not in str(event.details)
    # a verified teacher's report is marked; a signed-in reader is its reporter
    teacher = UserFactory()
    TeacherProfile.objects.create(user=teacher, school_name="Cotton Collegiate", verified=True)
    api = APIClient()
    api.force_authenticate(teacher)
    marked = ErrorReport.objects.get(pk=send(api, category="typo").json()["reference"])
    assert marked.teacher_verified and marked.reporter == teacher


def test_what_cannot_be_reported_is_refused_in_words():
    make_paper()
    assert send(question="9(z)").json() == {"question": ["No such question on that paper."]}
    assert "category" in send(category="item_analysis").json()  # the item analysis's own
    assert "printing" in send(printing="PHY 2027/1").json()
    assert send(kind="quiz_item").json() == {"quiz_item": ["No such quiz item."]}


def test_turnstile_is_checked_as_the_contact_form_checks_it(settings, monkeypatch):
    make_paper()
    settings.TURNSTILE, settings.TURNSTILE_SITE_KEY, settings.TURNSTILE_SECRET_KEY = True, "0x4-site", "0x4-secret"
    answers = [{"success": False, "error-codes": ["invalid-input-response"]}, {"success": True}]
    monkeypatch.setattr(forms.httpx, "post", lambda url, data, timeout: httpx.Response(200, json=answers.pop(0)))
    assert send(turnstile="forged").status_code == 400 and not ErrorReport.objects.exists()
    assert send(turnstile="token").status_code == 201


def test_five_an_hour_and_twenty_a_day_per_address(monkeypatch):
    make_paper()
    for _ in range(5):
        assert send().status_code == 201
    assert send().status_code == 429  # the sixth in the hour
    monkeypatch.setattr("api.reports.LIMITS", [("report", 50, 3600), ("report-day", 20, 86400)])
    cache.clear()  # a day of reports spread over several hours
    sent = [send().status_code for _ in range(21)]
    assert sent[:20] == [201] * 20 and sent[20] == 429


def test_the_honeypot_is_thanked_and_dropped_and_spam_is_kept_apart_then_purged():
    make_paper()
    assert send(website="https://cheap.example").status_code == 201 and not ErrorReport.objects.exists()
    spam = ErrorReport.objects.get(pk=send(note="Best prices at www.cheap.example").json()["reference"])
    assert spam.spam and spam.spam_reason == "a link in the note"
    assert not InboxItem.objects.filter(kind=InboxItem.Kind.ERROR_REPORT).exists()  # out of the queue
    owner = make_staff(roles.OWNER)
    assert signed_in(owner).get(f"{CONTENT}reports/").json()["results"] == []
    assert reports.spam_reason("aaaaaaaaaaaaaaaa") and reports.spam_reason("!!!! ???? 1234 5678 ....")
    assert reports.spam_reason("The sign in step 2 is wrong: it should be minus.") == ""
    ErrorReport.objects.filter(pk=spam.pk).update(created=timezone.now() - timedelta(days=31))
    kept = ErrorReport.objects.get(pk=send(note="Spam <a href=x>").json()["reference"])
    assert purge_spam() == 1 and list(ErrorReport.objects.all()) == [kept]


def test_the_triage_moves_a_report_through_its_states_and_tells_the_reporter_once(
    mailoutbox, django_capture_on_commit_callbacks
):
    make_paper()
    reference = send(email="reader@example.com").json()["reference"]
    editor = narrowed(roles.CONTENT_EDITOR, "PHY")
    client = signed_in(editor)
    url = f"{CONTENT}reports/{reference}/"
    listed = client.get(f"{CONTENT}reports/").json()["results"][0]
    assert listed["email"] == "re•••@example.com" and listed["can_tell"] is False
    assert client.post(url + "fix-in-printing/", {}, format="json").status_code == 400  # not from reported
    assert client.post(url + "confirm/", {}, format="json").json()["state"] == "confirmed"
    assert client.post(url + "fix-in-printing/", {"fixed_in": "x y"}, format="json").json() == {
        "fixed_in": ["The printing that carries the fix: PHY-2027-2."]
    }
    assert client.post(url + "fix-online/", {}, format="json").json()["state"] == "fixed_online"
    assert not InboxItem.objects.filter(kind=InboxItem.Kind.ERROR_REPORT, done_at=None).exists()
    fixed = client.post(url + "fix-in-printing/", {"fixed_in": "PHY-2027-2"}, format="json").json()
    assert (fixed["state"], fixed["fixed_in"], fixed["can_tell"]) == ("fixed_in_printing", "PHY-2027-2", True)
    with django_capture_on_commit_callbacks(execute=True):
        told = client.post(url + "tell/", {}, format="json")
    assert told.status_code == 200 and told.json()["reporter_told_at"] and told.json()["email"] == ""
    assert mailoutbox[-1].to == ["reader@example.com"] and "PHY-E01 2(c), step 2" in mailoutbox[-1].body
    assert "PHY-2027-2" in mailoutbox[-1].body and "/s/PHY-E01/#q-2-c" in mailoutbox[-1].body
    assert client.post(url + "tell/", {}, format="json").status_code == 400  # once
    trail = [event.action for event in events(target_type="content.errorreport")]
    assert trail == ["content.report_received", "content.report_confirm", "content.report_fix_online",
                     "content.report_fix_in_printing", "content.reporter_told"]  # fmt: skip
    assert "reader@example.com" not in str([event.details for event in events(target_type="content.errorreport")])


def test_a_rejection_says_why_drops_the_address_and_can_be_reopened():
    make_paper()
    reference = send(email="reader@example.com").json()["reference"]
    client = signed_in(narrowed(roles.REVIEWER, "PHY"))
    url = f"{CONTENT}reports/{reference}/"
    assert client.post(url + "reject/", {}, format="json").json() == {"staff_note": ["Say why it is not a mistake."]}
    rejected = client.post(url + "reject/", {"staff_note": "The marking scheme allows both."}, format="json").json()
    assert (rejected["state"], rejected["email"]) == ("rejected", "")
    assert client.get(f"{CONTENT}reports/").json()["results"] == []  # the queue: the open ones
    assert client.get(f"{CONTENT}reports/?state=rejected").json()["results"][0]["id"] == reference
    assert client.post(url + "reopen/", {}, format="json").json()["state"] == "reported"
    assert InboxItem.objects.filter(kind=InboxItem.Kind.ERROR_REPORT, done_at=None).count() == 1
    support = signed_in(make_staff(roles.SUPPORT))
    assert support.get(url).status_code == 200 and support.post(url + "confirm/", {}).status_code == 403


def test_a_subject_narrows_the_queue_and_another_subjects_report_is_not_found():
    make_paper()
    make_paper("CHE")
    physics = send().json()["reference"]
    chemistry = send(paper="CHE-E01").json()["reference"]
    client = signed_in(narrowed(roles.CONTENT_EDITOR, "PHY"))
    assert [row["id"] for row in client.get(f"{CONTENT}reports/").json()["results"]] == [physics]
    assert client.get(f"{CONTENT}reports/{chemistry}/").status_code == 404
    assert client.post(f"{CONTENT}reports/{chemistry}/confirm/", {}).status_code == 404


def test_the_errata_list_what_staff_publish(settings):
    paper = make_paper()
    reference = send(printing="PHY-2027-1").json()["reference"]
    send(question="2(c)", step=1)  # still only reported: no erratum
    client = signed_in(make_staff(roles.OWNER))
    client.post(f"{CONTENT}reports/{reference}/fix-online/", {}, format="json")
    assert APIClient().get("/api/v1/errata/?book=physics-2027").json()["results"] == []  # not public yet
    client.patch(f"{CONTENT}reports/{reference}/", {"public": True}, format="json")
    public = APIClient().get(f"/api/v1/errata/?book={paper.book.slug}")
    assert sorted(public["Cache-Control"].split(", ")) == ["max-age=300", "public"]
    row = public.json()["results"][0]
    assert (row["paper"], row["question"], row["step"], row["printing"], row["state"]) == (
        "PHY-E01",
        "2(c)",
        2,
        "PHY-2027-1",
        "fixed_online",
    )
    assert APIClient().get("/api/v1/errata/").status_code == 400
    staff = client.get(f"{CONTENT}errata/?book={paper.book.pk}").json()["results"]
    assert [row["id"] for row in staff] == [reference]


def test_the_item_analysis_flags_join_the_queue_once():
    paper = make_paper()
    chapter = Chapter.objects.create(subject=paper.book.subject, number=3, title="Current Electricity")
    item = QuizItem.objects.create(chapter=chapter, kind="mcq", text="Which?", options=["(i) a", "(ii) b"], answer="1")
    fine = QuizItem.objects.create(chapter=chapter, kind="mcq", text="And?", options=["(i) a", "(ii) b"], answer="2")
    ItemStat.objects.create(item=item, n=40, p=0.97, discrimination=0.05, flags=["too_easy", "low_discrimination"])
    ItemStat.objects.create(item=fine, n=40, p=0.6, discrimination=0.4, flags=[])
    assert flag_items() == 1 and flag_items() == 0  # one report per flagged item, not twice
    report = ErrorReport.objects.get()
    assert (report.category, report.target, report.subject.code, report.state) == (
        "item_analysis",
        item,
        "PHY",
        "reported",
    )
    assert "97% right" in report.note and "too_easy" in report.note
    assert (
        InboxItem.objects.get(kind=InboxItem.Kind.ERROR_REPORT).title
        == f"Reported mistake #{report.pk}: quiz item #{item.pk}"
    )
    client = signed_in(make_staff(roles.OWNER))
    client.post(f"{CONTENT}reports/{report.pk}/reject/", {"staff_note": "Easy on purpose."}, format="json")
    assert flag_items() == 0  # closed lately: not again for a while
    ErrorReport.objects.filter(pk=report.pk).update(modified=timezone.now() - timedelta(days=31))
    assert flag_items() == 1
