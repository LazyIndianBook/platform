"""Learner analytics, aggregate only: the quiz's item analysis worked out by hand, chapter accuracy, cohorts."""

import math
from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from api.tests import sign_in, student
from insights.jobs import learning
from insights.models import ChapterStat, CohortStat, ItemStat
from learn.models import Chapter, Entitlement, Learner, QuizAttempt, QuizItem, Revision

from .helpers import at_noon, learners

pytestmark = pytest.mark.django_db
approx = pytest.approx


def item(chapter, kind="true_false"):
    """A true-or-false item (true), or a multiple-choice one of four options (the first right)."""
    options, key = (["(i) a", "(ii) b", "(iii) c", "(iv) d"], "1") if kind == "mcq" else ([], "true")
    return QuizItem.objects.create(chapter=chapter, kind=kind, text=f"Item {kind}", options=options, answer=key)


def answer(quiz_item, people, right, chosen=lambda i: None, when=None):
    """One attempt at the item by each of `people`; `right` and `chosen` are functions of the person's number."""
    when = when or timezone.now() - timedelta(hours=1)
    QuizAttempt.objects.bulk_create(
        QuizAttempt(user=person, item=quiz_item, correct=right(i), chosen=chosen(i), created=when)
        for i, person in enumerate(people)
    )


@pytest.fixture
def chapter(physics):
    return Chapter.objects.create(subject=physics, number=1, title="Electric Charges and Fields")


def test_the_item_analysis_of_a_chapter_worked_out_by_hand(chapter):
    """40 learners; A right for 0-23 (p = 0.6), B for 0-19, C for 0-27 and 36-39. A's rest score (B and C): 1 for 0-19,
    0.5 for 20-27 and 36-39, 0 for 28-35."""
    people = learners(40)
    a, b, c = item(chapter, "mcq"), item(chapter), item(chapter)
    answer(a, people, lambda i: i < 24)
    answer(b, people, lambda i: i < 20)
    answer(c, people, lambda i: i < 28 or i >= 36)
    QuizAttempt.objects.create(user=people[30], item=a, correct=True)  # a second try: only the first counts
    learning.item_analysis()
    stat = ItemStat.objects.get(item=a)
    m1, m0 = (20 * 1 + 4 * 0.5) / 24, (8 * 0.5 + 8 * 0) / 16  # mean rest score of those right, of those wrong
    sd = math.sqrt((20 * 1**2 + 12 * 0.5**2) / 40 - (26 / 40) ** 2)  # of all 40 rest scores (mean 0.65)
    assert (stat.n, stat.p, stat.flags) == (40, 0.6, [])
    assert stat.discrimination == approx((m1 - m0) / sd * math.sqrt(0.6 * 0.4)) == approx(0.8363, abs=1e-4)
    chapter_stat = ChapterStat.objects.get(chapter=chapter)
    shares = 20 * 1 + 4 * 2 / 3 + 4 * 1 / 3 + 8 * 0 + 4 * 1 / 3  # each learner's share right of A, B and C
    assert (chapter_stat.n_learners, chapter_stat.mean_accuracy) == (40, approx(shares / 40))


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_the_quiz_keeps_the_option_chosen_for_multiple_choice_only(chapter):
    Revision.objects.create(chapter=chapter, title="Revise", status="published")
    mcq, true_false = item(chapter, "mcq"), item(chapter)
    api = APIClient()
    Entitlement.objects.create(user=sign_in(api, student()))  # every subject
    assert api.post(f"/api/v1/learn/quiz/{mcq.pk}/attempt/", {"answer": " 2 "}).json()["correct"] is False
    assert api.post(f"/api/v1/learn/quiz/{true_false.pk}/attempt/", {"answer": "true"}).json()["correct"] is True
    assert list(QuizAttempt.objects.order_by("pk").values_list("chosen", "correct")) == [("2", False), (None, True)]


def test_items_are_flagged_with_the_timss_thresholds(physics):
    """G marks the strong learners (0-19). D's key says option 1, which the strong ones did not choose: a negative
    discrimination, and a distractor chosen by the strong (option 2) with a positive point-biserial."""
    chapter = Chapter.objects.create(subject=physics, number=2, title="Electrostatic Potential")
    people = learners(40)
    d, easy, hard, rare, g = item(chapter, "mcq"), item(chapter), item(chapter, "mcq"), item(chapter), item(chapter)
    answer(g, people, lambda i: i < 20)
    answer(easy, people, lambda i: i != 39)  # p = 0.975
    answer(hard, people, lambda i: i < 8)  # p = 0.2, multiple choice
    answer(rare, people, lambda i: i < 8)  # p = 0.2, true or false: not "too hard" (half guess it right)
    answer(d, people, lambda i: i >= 20, chosen=lambda i: "2" if i < 20 else "1")
    learning.item_analysis()
    flags = {stat.item_id: stat.flags for stat in ItemStat.objects.all()}
    assert flags[d.pk] == ["low_discrimination", "distractor_2"]  # options 3 and 4, chosen by nobody: no flag
    assert "too_easy" in flags[easy.pk] and "too_hard" in flags[hard.pk] and "too_hard" not in flags[rare.pk]
    assert ItemStat.objects.get(item=d).discrimination < -0.5


def test_an_item_is_analysed_once_30_learners_answered_it(chapter):
    few, other = item(chapter, "mcq"), item(chapter)
    people = learners(29)
    answer(few, people, lambda i: i < 3)
    answer(other, people, lambda i: True)
    learning.item_analysis()
    stat = ItemStat.objects.get(item=few)
    assert (stat.n, stat.p, stat.discrimination, stat.flags) == (29, None, None, [])  # n shown, nothing else
    learning.item_analysis()  # again the same day: today's rows replaced
    assert ItemStat.objects.filter(item=few).count() == 1


def test_chapter_accuracy_has_a_trend_and_hides_groups_under_5(physics, chapter):
    people = learners(10)
    first, second = item(chapter), item(chapter)
    answer(first, people, lambda i: i < 6)  # this week: 6 of 10
    answer(second, people, lambda i: i < 8, when=timezone.now() - timedelta(weeks=6))  # six weeks ago: 8 of 10
    small = Chapter.objects.create(subject=physics, number=3, title="Current Electricity")
    answer(item(small), people[:4], lambda i: True)
    learning.item_analysis()
    stat = ChapterStat.objects.get(chapter=chapter)
    assert (stat.mean_accuracy, stat.trend) == (approx(0.7), approx(0.6 - 0.8))
    stat = ChapterStat.objects.get(chapter=small)
    assert (stat.n_learners, stat.mean_accuracy, stat.trend) == (4, None, None)


def test_cohorts_count_weekly_activity_and_hide_groups_under_5(physics):
    """Six learners opened the course with a book code on 1 September, three by a purchase. Their quiz answers, by
    day after the 1st: b0 1, 8, 15, 22; b1 2; b2 3, 16; b3 and b5 none (b5's exam on the 21st); b4 9."""
    start = date(2026, 9, 1)
    coded, bought = learners(6), learners(3, start=6)
    quiz = item(Chapter.objects.create(subject=physics, number=4, title="Magnetism"))
    for person, source in [*((p, "book_code") for p in coded), *((p, "purchase") for p in bought)]:
        opened = Entitlement.objects.create(user=person, source=source)
        Entitlement.objects.filter(pk=opened.pk).update(created=at_noon(start))
    Learner.objects.create(user=coded[5], exam_date=start + timedelta(days=20))
    for person, days in zip(coded, [[1, 8, 15, 22], [2], [3, 16], [], [9], []], strict=True):
        for day in days:
            QuizAttempt.objects.create(user=person, item=quiz, correct=True, created=at_noon(start + timedelta(day)))
    learning.cohorts(today=start + timedelta(days=30))
    rows = {(row.source, row.week_index): row for row in CohortStat.objects.all()}
    assert set(rows) == {(source, week) for source in ("book_code", "purchase") for week in range(4)}
    assert [(rows["book_code", w].n, rows["book_code", w].active_share) for w in range(4)] == [
        (6, 3 / 6), (6, 2 / 6), (5, 2 / 5), (5, 1 / 5),  # b5's exam was in the third week: no longer counted
    ]  # fmt: skip
    assert [rows["book_code", w].churned_share for w in range(4)] == [None, 2 / 6, 2 / 5, 3 / 5]  # quiet 14 days
    assert {(row.n, row.active_share, row.churned_share) for (s, _), row in rows.items() if s == "purchase"} == {
        (3, None, None)
    }  # three learners: their size only
    assert all(row.cohort_month == start for row in rows.values())
