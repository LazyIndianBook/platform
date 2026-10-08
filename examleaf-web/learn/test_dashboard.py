"""The learning dashboard (GET /api/v1/me/learning/): a student with an open subject and some watching and answers, a
student with nothing yet, and one whose parent has not confirmed (who may read it)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from api.tests import sign_in, student

from .models import CardReview, Clip, Entitlement, FlashCard, Learner, Progress, QuizAttempt, QuizItem
from .tests import make_course

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
URL = "/api/v1/me/learning/"


@pytest.fixture
def api(settings):
    settings.APP_LINK_ANDROID = settings.APP_LINK_IOS = ""  # whatever the developer's .env says
    return APIClient()


def watch(user, title, seconds, completed, when):
    progress = Progress.objects.create(user=user, clip=Clip.objects.get(title=title), seconds_watched=seconds)
    Progress.objects.filter(pk=progress.pk).update(completed=completed, updated=when)  # update(): not auto_now


def test_an_entitled_student_sees_progress_where_to_continue_what_to_revise_the_next_days_and_the_streak(api):
    subject = make_course(chapters=2, clips=3, seconds=600)  # ten minutes a clip
    user = sign_in(api, student())
    now, today = timezone.now(), timezone.localdate()
    Entitlement.objects.create(user=user, subject=subject, valid_until=today + timedelta(days=365))
    Entitlement.objects.create(user=user, subject=subject, valid_until=today - timedelta(days=1))  # ended
    watch(user, "Clip 2.1", 600, True, now - timedelta(days=3))
    watch(user, "Clip 1.1", 900, True, now)  # more than its length is counted as its length
    watch(user, "Clip 1.2", 60, False, now)
    one, two = QuizItem.objects.order_by("chapter__number")
    QuizAttempt.objects.create(user=user, item=one, correct=False, created=now - timedelta(days=1))  # due today
    QuizAttempt.objects.create(user=user, item=two, correct=True, created=now - timedelta(days=2))
    CardReview.objects.create(user=user, card=FlashCard.objects.get(front="Front 2"), known=False)  # due tomorrow
    Learner.objects.create(user=user, exam_date=today + timedelta(days=30), minutes_per_day=10)
    other = student()  # another student's rows stay theirs
    watch(other, "Clip 2.2", 600, True, now)
    QuizAttempt.objects.create(user=other, item=two, correct=False)

    response = api.get(URL)
    data = response.json()
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    assert [(e["subject_name"], e["source"]) for e in data["entitlements"]] == [("Physics", "grant")]
    [physics] = data["subjects"]
    assert (physics["name"], physics["entitled"], physics["clips_watched"], physics["clips_total"]) == (
        "Physics", True, 2, 6
    )  # fmt: skip
    assert (physics["minutes_watched"], physics["quiz_answers"], physics["quiz_accuracy"]) == (21, 2, 50)
    assert [
        (c["number"], c["clips_watched"], c["clips_total"], c["minutes_watched"], c["quiz_answers"], c["quiz_accuracy"])
        for c in physics["chapters"]
    ] == [(1, 1, 3, 11, 1, 0), (2, 1, 3, 10, 1, 100)]
    assert physics["last_activity"] == physics["chapters"][0]["last_activity"] is not None
    nxt = data["continue_watching"]
    assert (nxt["clip"]["title"], nxt["clip"]["free"], nxt["clip"]["locked"], nxt["clip"]["seconds_watched"]) == (
        "Clip 1.2", False, False, 60
    )  # fmt: skip
    assert (nxt["revision"]["title"], nxt["chapter"]["number"], nxt["chapter"]["subject_name"]) == (
        "Revise 1", 1, "Physics"
    )  # fmt: skip
    assert data["revise_again"] == {"due_today": 1, "later": 1}
    plan = data["plan"]
    assert (plan["days_left"], plan["minutes_per_day"], plan["hint"]) == (30, 10, "")
    assert [[clip["title"] for clip in day["clips"]] for day in plan["days"]] == [
        ["Clip 1.2"],
        ["Clip 1.3"],
        ["Clip 2.2"],
    ]
    # of four days to watch: the first three
    assert data["streak"] == {"days": 4, "today": True, "last_day": today.isoformat()}  # today and the 3 before
    assert (data["consent_pending"], data["has_app_links"]) == (False, False)

    Progress.objects.filter(user=user).update(completed=True)  # chapter 1 done: on to the revision watched before
    watch(user, "Clip 1.3", 600, True, now)
    assert api.get(URL).json()["continue_watching"]["clip"]["title"] == "Clip 2.2"


def test_a_student_with_nothing_yet_gets_the_empty_states(api):
    make_course(chapters=1, clips=2)
    assert api.get(URL).status_code == 401
    sign_in(api, student())
    data = api.get(URL).json()
    assert data == {
        "entitlements": [],
        "subjects": [],
        "continue_watching": None,
        "revise_again": {"due_today": 0, "later": 0},
        "plan": {"exam_date": None, "days_left": None, "minutes_per_day": 30, "days": [],
                 "hint": "Save the date of your exam to see what to watch each day."},
        "streak": {"days": 0, "today": False, "last_day": None},
        "consent_pending": False,
        "has_app_links": False,
    }  # fmt: skip


def test_a_free_clip_watched_shows_its_subject_and_a_locked_next_clip_says_so(api):
    make_course(chapters=1, clips=2)
    user = sign_in(api, student())
    watch(user, "Clip 1.1", 120, True, timezone.now() - timedelta(days=2))  # the free first clip, two days ago
    data = api.get(URL).json()
    assert [(s["name"], s["entitled"], s["clips_watched"]) for s in data["subjects"]] == [("Physics", False, 1)]
    assert (data["continue_watching"]["clip"]["title"], data["continue_watching"]["clip"]["locked"]) == (
        "Clip 1.2", True
    )  # fmt: skip
    assert data["streak"]["days"] == 0  # two days ago: the run has ended
    Learner.objects.create(user=user, exam_date=timezone.localdate())
    assert api.get(URL).json()["plan"]["hint"] == "The exam date you saved has passed: save the next one."


def test_a_student_waiting_for_a_parents_consent_can_read_it(api, settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    settings.APP_LINK_ANDROID = "https://play.google.com/store/apps/details?id=in.examleaf"
    make_course(chapters=1, clips=1)
    sign_in(api, student(date_of_birth=timezone.localdate() - timedelta(days=16 * 366)))
    response = api.get(URL)
    assert response.status_code == 200
    assert (response.json()["consent_pending"], response.json()["has_app_links"]) == (True, True)
