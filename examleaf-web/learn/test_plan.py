"""The pass plan (priorities, day packing, the minimum to pass) and spaced repetition (1, 3, 7 days)."""

from datetime import date, datetime, timedelta

import pytest

from accounts.factories import UserFactory

from .models import CardReview, Chapter, Clip, Entitlement, FlashCard, Progress, QuizAttempt, QuizItem
from .plan import build, revise_again
from .tests import make_course

pytestmark = pytest.mark.django_db
TODAY = date(2027, 1, 10)


def titles(plan):
    return [[clip.title for clip in day["clips"]] for day in plan["days"]]


def test_chapters_by_marks_and_frequency_packed_into_days():
    subject = make_course(chapters=2, clips=3, seconds=120)
    Chapter.objects.filter(number=2).update(weight=9, frequency=2)  # 18 against chapter 1's 7 x 1
    user = UserFactory()
    Progress.objects.create(user=user, clip=Clip.objects.get(title="Clip 2.2"), completed=True)
    plan = build(user, [subject], TODAY + timedelta(days=30), minutes_per_day=4, today=TODAY)
    assert titles(plan) == [["Clip 2.1", "Clip 2.3"], ["Clip 1.1", "Clip 1.2"], ["Clip 1.3"]]
    assert plan["days"][1]["date"] == TODAY + timedelta(days=1) and plan["days_left"] == 30

    short = build(user, [subject], TODAY + timedelta(days=2), minutes_per_day=4, today=TODAY)
    assert titles(short) == [["Clip 2.1", "Clip 2.3"], ["Clip 1.1", "Clip 1.2"]]
    assert [chapter.number for chapter in short["not_scheduled"]] == [1]


def test_weak_chapters_come_first_and_a_long_clip_gets_its_own_day():
    subject = make_course(chapters=2, clips=1, seconds=600)
    user = UserFactory()
    QuizAttempt.objects.create(user=user, item=QuizItem.objects.get(chapter__number=2), correct=False)
    plan = build(user, [subject], TODAY + timedelta(days=9), minutes_per_day=5, today=TODAY)
    assert titles(plan) == [["Clip 2.1"], ["Clip 1.1"]]


def test_the_minimum_to_pass_takes_the_most_marks_per_minute_first():
    subject = make_course(chapters=3, clips=2, seconds=120)  # each chapter 4 minutes; the paper's pass marks: 21
    Chapter.objects.filter(number=1).update(weight=6)
    Chapter.objects.filter(number=2).update(weight=20)
    Chapter.objects.filter(number=3).update(weight=12)
    Clip.objects.filter(title="Clip 2.2").update(kind="formula")
    [minimum] = build(UserFactory(), [subject], TODAY + timedelta(days=30), 30, today=TODAY)["minimum_to_pass"]
    assert (minimum["pass_marks"], minimum["marks"]) == (21, 32)  # 21 x 1.5 = 31.5: two chapters are enough
    assert [(row["chapter"].number, row["marks_per_minute"]) for row in minimum["chapters"]] == [(2, 5), (3, 3)]
    assert [clip.title for clip in minimum["chapters"][0]["clips"]] == ["Clip 2.2"]


def test_wrong_answers_come_back_after_1_3_and_7_days():
    make_course(chapters=1)
    user, item, card = UserFactory(), QuizItem.objects.get(), FlashCard.objects.get()
    Entitlement.objects.create(user=user)  # the quiz is for those who may open the course (I5)
    start = datetime(2027, 1, 1, 9, 0).astimezone()

    def listed(at):
        due = revise_again(user, now=at)
        return [row["item"] for row in due["quiz_items"]], [row["item"] for row in due["flash_cards"]]

    QuizAttempt.objects.create(user=user, item=item, correct=True, created=start)  # right first time: never listed
    assert listed(start + timedelta(days=30)) == ([], [])
    QuizAttempt.objects.create(user=user, item=item, correct=False, created=start)
    CardReview.objects.create(user=user, card=card, known=False, created=start)
    assert listed(start + timedelta(hours=23)) == ([], []) and listed(start + timedelta(days=1)) == ([item], [card])
    for days, wait in [(1, 3), (4, 7)]:
        QuizAttempt.objects.create(user=user, item=item, correct=True, created=start + timedelta(days=days))
        assert listed(start + timedelta(days=days + wait) - timedelta(minutes=1))[0] == []
        assert listed(start + timedelta(days=days + wait))[0] == [item]
    QuizAttempt.objects.create(user=user, item=item, correct=True, created=start + timedelta(days=11))
    assert listed(start + timedelta(days=60))[0] == []
