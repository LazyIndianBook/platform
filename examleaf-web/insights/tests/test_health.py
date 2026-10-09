"""Course health (insights/jobs/health.py and the report): the nightly job's counts worked out by hand over complete
days, weeks and months, learners counted once, staff and today left out; and the report's series, chapters and codes by
week, with the minimum cell hiding a small one and the average counting a hidden day as nothing."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from accounts import roles
from content.models import Subject
from insights import cells, checks
from insights.jobs import health
from insights.models import CourseHealthStat
from learn.models import BookCode, CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from staff.models import StaffScope
from staff.tests.conftest import STAFF, make_staff, signed_in

from .helpers import at, learners

pytestmark = pytest.mark.django_db
TODAY = date(2026, 10, 14)  # a Wednesday: yesterday (Tuesday the 13th) is the last day counted
Grain = CourseHealthStat.Grain


@pytest.fixture(autouse=True)
def limits(settings):
    settings.INSIGHTS_MIN_CELL = 10
    settings.INSIGHTS_MIN_CELL_CLASS = 5


@pytest.fixture
def course(physics):
    """Physics with two chapters and Chemistry with one, each with a clip, a quiz item and a flash card."""
    chemistry = Subject.objects.create(
        name="Chemistry", code="CHE", board=physics.board, class_level=physics.class_level
    )
    made = {}
    for name, subject, number in [("ch1", physics, 1), ("ch2", physics, 2), ("che1", chemistry, 1)]:
        chapter = Chapter.objects.create(subject=subject, number=number, title=f"Chapter {name}")
        revision = Revision.objects.create(chapter=chapter, title="Revise", status="published")
        made[name] = {
            "chapter": chapter,
            "clip": Clip.objects.create(revision=revision, title="Clip"),
            "item": QuizItem.objects.create(chapter=chapter, kind="true_false", text="T", answer="true"),
            "card": FlashCard.objects.create(chapter=chapter, front="f", back="b"),
        }
    made["physics"], made["chemistry"] = physics, chemistry
    return made


def answer(user, item, day, right=True):
    QuizAttempt.objects.create(user=user, item=item, correct=right, created=at(day))


def turn(user, card, day, known=True):
    CardReview.objects.create(user=user, card=card, known=known, created=at(day))


def watch(user, clip, day, done=False):
    Progress.objects.create(user=user, clip=clip, completed=done)
    Progress.objects.filter(user=user, clip=clip).update(updated=at(day))


@pytest.fixture
def activity(course):
    """Six learners answer on Tuesday 6 October (4 right); the first three turn cards the next day (one not known); the
    first two watch a clip on the 8th (one to the end); one more learner turns a physics chapter 2 card; one answers in
    Chemistry; yesterday one answers again, and in September one did. A member of staff, today and a year ago count for
    nothing."""
    people = learners(8)
    staff = make_staff(roles.CONTENT_EDITOR)
    ch1, ch2, che1 = course["ch1"], course["ch2"], course["che1"]
    for number, user in enumerate(people[:6]):
        answer(user, ch1["item"], date(2026, 10, 6), right=number < 4)
    for number, user in enumerate(people[:3]):
        turn(user, ch1["card"], date(2026, 10, 7), known=number != 2)
    watch(people[0], ch1["clip"], date(2026, 10, 8), done=True)
    watch(people[1], ch1["clip"], date(2026, 10, 8))
    turn(people[6], ch2["card"], date(2026, 10, 7))
    answer(people[7], che1["item"], date(2026, 10, 7))
    answer(people[0], ch1["item"], date(2026, 10, 13))
    answer(people[0], ch1["item"], date(2026, 9, 20))
    answer(staff, ch1["item"], date(2026, 10, 6))  # staff preview the course: not a learner
    answer(people[0], ch1["item"], TODAY)  # today is not over
    answer(people[0], ch1["item"], date(2025, 1, 15))  # long ago: in no period kept
    return people


def stat(grain, begins, **scope):
    return CourseHealthStat.objects.get(grain=grain, period_start=begins, **scope)


def test_the_windows_are_complete_periods_up_to_yesterday():
    found = health.windows(TODAY)
    assert (found[Grain.DAY][0], found[Grain.DAY][-1], len(found[Grain.DAY])) == (
        date(2026, 7, 14),
        date(2026, 10, 13),
        92,
    )
    assert (found[Grain.WEEK][-1], len(found[Grain.WEEK])) == (date(2026, 10, 5), 56)  # the week of the 5th is over
    assert (found[Grain.MONTH][-1], found[Grain.MONTH][0]) == (date(2026, 9, 1), date(2025, 8, 1))  # October is not
    assert (found[Grain.LAST_7], found[Grain.LAST_28]) == ([date(2026, 10, 7)], [date(2026, 9, 16)])
    sunday_today = health.windows(date(2026, 10, 12))  # yesterday was a Sunday: that week is over
    assert sunday_today[Grain.WEEK][-1] == date(2026, 10, 5)
    first = health.windows(date(2026, 11, 1))  # yesterday was the last day of October: October is over
    assert first[Grain.MONTH][-1] == date(2026, 10, 1) and first[Grain.WEEK][-1] == date(2026, 10, 19)
    assert health.shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1) and health.shift_month(
        date(2026, 12, 1), 2
    ) == date(2027, 2, 1)


def test_a_day_belongs_to_its_week_month_and_trailing_windows_only_when_they_are_complete():
    periods = health.Periods(TODAY)
    assert periods.of(TODAY) == [] and periods.of(date(2026, 10, 15)) == []  # not over
    assert {(grain, begins) for grain, begins in periods.of(date(2026, 10, 13))} == {
        (Grain.DAY, date(2026, 10, 13)),
        (Grain.LAST_7, date(2026, 10, 7)),
        (Grain.LAST_28, date(2026, 9, 16)),
    }
    assert (Grain.WEEK, date(2026, 10, 5)) in periods.of(date(2026, 10, 7))  # a complete week
    assert (Grain.MONTH, date(2026, 9, 1)) in periods.of(date(2026, 9, 20))
    assert periods.of(date(2025, 1, 15)) == []


def test_the_job_counts_learners_once_and_the_rest_as_sums(activity, course):
    rows = health.course_health(today=TODAY)
    assert rows == CourseHealthStat.objects.count() > 0
    one = {"chapter": course["ch1"]["chapter"]}
    first = stat(Grain.DAY, date(2026, 10, 6), **one)
    assert (first.active_learners, first.quiz_answers, first.quiz_correct, first.subject) == (
        6,
        6,
        4,
        course["physics"],
    )
    cards = stat(Grain.DAY, date(2026, 10, 7), **one)
    assert (cards.active_learners, cards.card_reviews, cards.card_lapses) == (3, 3, 1)
    clips = stat(Grain.DAY, date(2026, 10, 8), **one)
    assert (clips.active_learners, clips.clips_started, clips.clips_completed) == (2, 2, 1)
    week = stat(Grain.WEEK, date(2026, 10, 5), **one)  # the six learners, once each, whatever else they did
    assert (week.active_learners, week.quiz_answers, week.card_reviews, week.clips_started) == (6, 6, 3, 2)
    assert stat(Grain.MONTH, date(2026, 9, 1), **one).active_learners == 1
    assert not CourseHealthStat.objects.filter(grain=Grain.MONTH, period_start=date(2026, 10, 1)).exists()
    assert not CourseHealthStat.objects.filter(period_start=TODAY).exists()


def test_the_subject_and_the_whole_course_count_their_chapters_learners_once(activity, course):
    health.course_health(today=TODAY)
    physics = stat(Grain.DAY, date(2026, 10, 7), subject=course["physics"], chapter=None)
    assert (physics.active_learners, physics.card_reviews) == (4, 4)  # chapter 1's three and chapter 2's one
    everything = stat(Grain.DAY, date(2026, 10, 7), subject=None, chapter=None)
    assert (everything.active_learners, everything.card_reviews, everything.quiz_answers) == (5, 4, 1)  # + chemistry
    last7 = stat(Grain.LAST_7, date(2026, 10, 7), subject=course["physics"], chapter=None)
    assert last7.active_learners == 4  # the three, one of whom answered yesterday, and chapter 2's
    last28 = stat(Grain.LAST_28, date(2026, 9, 16), chapter=course["ch1"]["chapter"])
    assert last28.active_learners == 6 and last28.quiz_answers == 8  # the six, the 13th and the 20th of September


def test_the_job_replaces_the_night_before_and_keeps_no_learner(activity):
    health.course_health(today=TODAY)
    first = CourseHealthStat.objects.count()
    older = timezone.now() - timedelta(days=1)
    CourseHealthStat.objects.update(computed_at=older)
    health.course_health(today=TODAY)
    assert CourseHealthStat.objects.count() == first and not CourseHealthStat.objects.filter(computed_at=older).exists()
    names = {field.name for field in CourseHealthStat._meta.get_fields()}
    assert not names & {"user", "learner", "email", "phone", "name", "address", "pin", "ip"}


def test_the_job_runs_on_an_empty_database_and_with_a_chapter_nobody_touched(course):
    assert health.course_health(today=TODAY) == 0
    assert CourseHealthStat.objects.count() == 0


# ---- The report ----


def report(user, **query):
    response = signed_in(user).get(STAFF + "reports/course-health/", query)
    assert response.status_code == 200, response.content
    return response.json()


def test_the_report_before_the_job_has_run_says_so(course):
    answer = report(make_staff(roles.OWNER))
    assert (answer["computed_at"], answer["series"]) == (None, []) and answer["whole_course"] is True
    assert [chapter["active_28d"] for chapter in answer["rows"]] == []  # nothing worked out yet: no chapter rows
    assert {subject["name"] for subject in answer["subjects"]} == {
        "Physics, ASSEB, Class 12",
        "Chemistry, ASSEB, Class 12",
    }


def test_the_series_by_day_week_and_month_hides_a_day_under_the_minimum_and_counts_it_as_nothing_in_the_average(
    activity, course
):
    health.course_health(today=TODAY)
    owner = make_staff(roles.OWNER)
    days = report(owner, subject=course["physics"].pk, grain="day")
    points = {point["period_start"]: point for point in days["series"]}
    assert len(days["series"]) == 92 and days["series"][-1]["period_start"] == "2026-10-13"
    assert (points["2026-10-06"]["active_learners"], points["2026-10-06"]["hidden"]) == (6, False)
    assert points["2026-10-06"]["quiz_accuracy"] == "0.6667"  # 4 of 6 right
    seventh = points["2026-10-07"]  # four learners: under the 5 of a class's learners
    assert (seventh["hidden"], seventh["under"], seventh["active_learners"], seventh["card_reviews"]) == (
        True,
        5,
        None,
        None,
    )
    assert (
        points["2026-10-10"]["active_learners"] == 0 and points["2026-10-10"]["hidden"] is False
    )  # nobody: nothing hidden
    # the 7-day average on the 7th: the 6th's six, and the 7th's four counted as nothing (hidden), over 7 days
    assert points["2026-10-07"]["smoothed_7"] == "0.9"
    assert points["2026-10-12"]["smoothed_7"] == "0.9"  # the 8th's two are hidden too: still just the six
    assert days["minimum"] == 5 and days["definition"]
    weeks = report(owner, subject=course["physics"].pk, grain="week")["series"]
    assert len(weeks) == 56 and weeks[-1]["period_start"] == "2026-10-05" and weeks[-1]["active_learners"] == 7
    assert weeks[-1]["smoothed_7"] is None
    months = report(owner, subject=course["physics"].pk, grain="month")["series"]
    assert (
        len(months) == 14 and months[-1]["period_start"] == "2026-09-01" and months[-1]["hidden"] is True
    )  # one learner


def test_the_chapters_over_the_last_28_days_with_a_small_one_hidden(activity, course):
    health.course_health(today=TODAY)
    answer = report(make_staff(roles.OWNER), subject=course["physics"].pk)
    chapters = {row["number"]: row for row in answer["rows"]}
    first, second = chapters[1], chapters[2]
    assert (first["active_28d"], first["active_7d"], first["hidden"]) == (6, None, False)  # 7 days: three, under 5
    assert (first["clips_started"], first["clips_completed"], first["completion_rate"]) == (2, 1, "0.5000")
    assert (first["quiz_answers"], first["quiz_accuracy"], first["card_reviews"], first["card_lapses"]) == (
        8,
        "0.7500",
        3,
        1,
    )
    assert (second["hidden"], second["under"], second["active_28d"], second["card_reviews"]) == (True, 5, None, None)
    assert {row["subject"] for row in answer["rows"]} == {course["physics"].pk}
    whole = report(make_staff(roles.OWNER))
    assert whole["whole_course"] is True and {
        row["number"] for row in whole["rows"] if row["subject"] != course["physics"].pk
    } == {1}
    only = report(make_staff(roles.OWNER), chapter=course["ch1"]["chapter"].pk)
    assert only["chapter"] == course["ch1"]["chapter"].pk and only["whole_course"] is False
    assert (only["series"][-1]["period_start"], only["series"][-1]["active_learners"]) == ("2026-10-05", 6)  # its own


def test_a_person_who_looks_after_some_subjects_sees_only_theirs(activity, course):
    health.course_health(today=TODAY)
    owner = make_staff(roles.OWNER)
    StaffScope.objects.create(user=owner, kind="subject", value="CHE")
    answer = report(owner)
    assert answer["whole_course"] is False and answer["subject"] == course["chemistry"].pk
    assert [subject["name"] for subject in answer["subjects"]] == ["Chemistry, ASSEB, Class 12"]
    assert {row["subject"] for row in answer["rows"]} == {course["chemistry"].pk}
    refused = signed_in(owner).get(STAFF + "reports/course-health/", {"subject": course["physics"].pk})
    assert refused.status_code == 400 and "subject" in refused.json()
    assert (
        signed_in(owner).get(STAFF + "reports/course-health/", {"chapter": course["ch1"]["chapter"].pk}).status_code
        == 400
    )


def test_codes_redeemed_by_week_in_the_report_hide_a_week_under_the_minimum(course, activity):
    redeemer = activity[0]
    now = timezone.now()
    for number in range(6):  # six this week
        BookCode.objects.create(
            digest=f"a{number}".ljust(64, "0"),
            batch="PHY-1",
            subject=course["physics"],
            redeemed_by=redeemer,
            redeemed_at=now,
        )
    BookCode.objects.create(
        digest="z" * 64,
        batch="PHY-1",
        subject=course["physics"],
        redeemed_by=redeemer,
        redeemed_at=now - timedelta(weeks=3),
    )  # one three weeks ago
    health.course_health(today=TODAY)
    weeks = report(make_staff(roles.OWNER), subject=course["physics"].pk)["codes_by_week"]
    assert [(week["redeemed"], week["hidden"]) for week in weeks] == [(None, True), (6, False)]


def test_the_cells_helper_hides_some_but_fewer_than_k_and_not_none():
    assert cells.is_hidden(4, cells.CLASS) and cells.is_hidden(9) and not cells.is_hidden(5, cells.CLASS)
    assert not cells.is_hidden(10) and not cells.is_hidden(0) and cells.is_hidden(None)
    assert cells.apply({"a": 1}, 3, ["a"], cells.CLASS) == {"a": None, "hidden": True, "under": 5}
    assert cells.apply({"a": 1}, 7, ["a"]) == {"a": None, "hidden": True, "under": 10}
    assert cells.apply({"a": 1}, 12, ["a"]) == {"a": 1, "hidden": False, "under": None}
    assert cells.words({"under": 10}) == "fewer than 10"


def test_a_minimum_cell_below_five_stops_the_server_from_starting(settings):
    assert checks.minimum_cells(None) == []
    settings.INSIGHTS_MIN_CELL = 4
    settings.INSIGHTS_MIN_CELL_CLASS = 1
    found = checks.minimum_cells(None)
    assert [(error.id, error.msg.split(" is ")[0]) for error in found] == [
        ("insights.E001", "INSIGHTS_MIN_CELL"),
        ("insights.E001", "INSIGHTS_MIN_CELL_CLASS"),
    ]
    settings.INSIGHTS_MIN_CELL, settings.INSIGHTS_MIN_CELL_CLASS = 5, 5
    assert checks.minimum_cells(None) == []  # the floor itself is allowed
