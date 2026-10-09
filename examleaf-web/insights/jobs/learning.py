"""Learner analytics, aggregate only (research-b2b-predictive.md 4.6 and 4.7): the quiz's item analysis, chapter
accuracy and cohorts. Every number is about a group: no row names a learner and groups under 5 show their size alone.
They fix items, pick webinar topics and find errata; they never feed marketing, prices or offers (DPDP Act s. 9(3))."""

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models.functions import TruncDate
from django.utils import timezone

from learn.models import CardReview, Entitlement, Learner, Progress, QuizAttempt, QuizItem

from .. import stats
from ..models import ChapterStat, CohortStat, ItemStat
from . import HIDDEN_BELOW, KEEP, WEEKS, save_stats

MIN_ANSWERS = 30  # learners before an item is analysed (an own rule of thumb, research 4.7)
LOW_DISCRIMINATION, TOO_EASY, TOO_HARD = 0.10, 0.95, 0.25  # TIMSS's thresholds; "too hard" for multiple choice only


def first_answers():
    """{chapter id: {learner: {item id: (right 0/1, option chosen, when)}}} from each learner's first attempt at each
    item. ponytail: held in memory, fine to about a million answers; go chapter by chapter beyond."""
    first = {}
    rows = QuizAttempt.objects.order_by("created", "pk").values_list(
        "user_id", "item_id", "correct", "chosen", "created"
    )
    for learner, item, right, chosen, created in rows.iterator(chunk_size=5000):
        first.setdefault((learner, item), (int(right), chosen, created))
    chapters = dict(QuizItem.objects.filter(pk__in={item for _, item in first}).values_list("pk", "chapter_id"))
    grouped = defaultdict(lambda: defaultdict(dict))
    for (learner, item), answer in first.items():
        grouped[chapters[item]][learner][item] = answer
    return grouped


def analysed(item, learners, now, today):
    """The item's ItemStat: p, and the corrected item-total point-biserial (the answer against the learner's share right
    on the chapter's other items), with TIMSS's flags, once MIN_ANSWERS learners answered it; a distractor with a
    positive point-biserial (often a wrong key) is flagged from the option chosen, where it was recorded."""
    answered, pairs, chosen = [], [], []
    for answers in learners.values():
        if item.pk not in answers:
            continue
        right, option, _ = answers[item.pk]
        answered.append(right)
        others = [answer[0] for other, answer in answers.items() if other != item.pk]
        if others:
            rest = sum(others) / len(others)
            pairs.append((right, rest))
            if option is not None:
                chosen.append((option, rest))
    stat = ItemStat(item=item, n=len(answered), computed_at=now, run_date=today)
    if stat.n < MIN_ANSWERS:
        return stat
    stat.p = sum(answered) / stat.n
    if len(pairs) >= MIN_ANSWERS:
        stat.discrimination = stats.point_biserial([right for right, _ in pairs], [rest for _, rest in pairs])
    if stat.discrimination is not None and stat.discrimination < LOW_DISCRIMINATION:
        stat.flags.append("low_discrimination")
    if stat.p > TOO_EASY:
        stat.flags.append("too_easy")
    if item.kind == QuizItem.Kind.MCQ and stat.p < TOO_HARD:
        stat.flags.append("too_hard")
    if item.kind == QuizItem.Kind.MCQ and len(chosen) >= MIN_ANSWERS:
        for option in (str(number) for number in range(1, len(item.options) + 1)):
            picked = [int(answer.strip() == option) for answer, _ in chosen]
            score = stats.point_biserial(picked, [rest for _, rest in chosen])
            if option != item.answer and score is not None and score > 0:
                stat.flags.append(f"distractor_{option}")
    return stat


def accuracy_between(learners, start, end):
    """The share right of the first attempts made from `start` to the day before `end`; None under 5 learners."""
    answers = [
        (learner, answer[0])
        for learner, items in learners.items()
        for answer in items.values()
        if start <= timezone.localdate(answer[2]) < end
    ]
    if len({learner for learner, _ in answers}) < HIDDEN_BELOW:
        return None
    return sum(right for _, right in answers) / len(answers)


@transaction.atomic
def item_analysis(today=None):
    """Each answered quiz item's ItemStat (today's replace any earlier ones of the day) and each chapter's ChapterStat:
    the mean of its learners' shares right, and the last four weeks' accuracy less the four weeks before."""
    now = timezone.now()
    today = today or timezone.localdate(now)
    items, chapters = [], []
    grouped = first_answers()
    quiz = QuizItem.objects.in_bulk({item for learners in grouped.values() for a in learners.values() for item in a})
    for chapter, learners in grouped.items():
        answered = {item for answers in learners.values() for item in answers}
        items += [analysed(quiz[item], learners, now, today) for item in sorted(answered)]
        shares = [sum(answer[0] for answer in answers.values()) / len(answers) for answers in learners.values()]
        stat = ChapterStat(chapter_id=chapter, n_learners=len(shares), computed_at=now)
        if len(shares) >= HIDDEN_BELOW:
            stat.mean_accuracy = sum(shares) / len(shares)
            recent = accuracy_between(learners, today - timedelta(weeks=4), today + timedelta(days=1))
            before = accuracy_between(learners, today - timedelta(weeks=8), today - timedelta(weeks=4))
            stat.trend = recent - before if recent is not None and before is not None else None
        chapters.append(stat)
    ItemStat.objects.filter(run_date=today).delete()
    ItemStat.objects.bulk_create(items)
    ItemStat.objects.filter(run_date__lt=today - KEEP).delete()
    return len(items) + save_stats(ChapterStat, chapters, now)


@transaction.atomic
def cohorts(today=None):
    """Each cohort's (the month its learners' course first opened, and how: book code, purchase, grant) share active in
    each week since, while their exam is ahead (Learner.exam_date where they gave one), and the share gone quiet: no
    quiz answer, card or clip for 14 days. Activity is a day with any of them."""
    now = timezone.now()
    today = today or timezone.localdate(now)
    starts, opened = {}, Entitlement.objects.order_by("created", "pk")
    for learner, source, created in opened.values_list("user", "source", "created"):
        starts.setdefault(learner, (timezone.localdate(created), source))
    exams = dict(Learner.objects.filter(exam_date__isnull=False).values_list("user", "exam_date"))
    days = defaultdict(set)
    for model, field in ((QuizAttempt, "created"), (CardReview, "created"), (Progress, "updated")):
        for learner, day in model.objects.annotate(day=TruncDate(field)).values_list("user", "day").distinct():
            days[learner].add(day)
    counts = defaultdict(lambda: [0, 0, 0])  # (month, source, week): learners, active, quiet
    for learner, (start, source) in starts.items():
        exam, active = exams.get(learner), days[learner]
        for week in range(WEEKS):
            end = start + timedelta(weeks=week + 1)
            if end > today or (exam is not None and exam < end):
                break
            cell = counts[start.replace(day=1), source, week]
            cell[0] += 1
            cell[1] += any(end - timedelta(weeks=1) <= day < end for day in active)
            cell[2] += week > 0 and not any(end - timedelta(days=14) <= day < end for day in active)
    rows = []
    for (month, source, week), (n, active, quiet) in counts.items():
        shown = n >= HIDDEN_BELOW
        cell = {"cohort_month": month, "source": source, "week_index": week, "n": n, "computed_at": now}
        rows.append(
            CohortStat(
                **cell, active_share=active / n if shown else None, churned_share=quiet / n if shown and week else None
            )
        )
    return save_stats(CohortStat, rows, now)
