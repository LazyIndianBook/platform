"""Course health, aggregate only (plan 5.16; research-lms-crm-cms.md 5.6): how the revision course is used, by subject
and chapter, as counts over complete days, weeks, months and the last 7 and 28 days. For each period and scope (the
whole course, a subject, a chapter): the learners with any activity (counted once each), the clips started and
completed, the quiz answers and the right ones, the flash cards turned over and the ones not known (lapses). Written
every night into `CourseHealthStat`, replacing the night before's, so that the report reads a few thousand rows
instead of every answer ever given (the distinct learners of a week or a month cannot be added up from its days).

No row names a learner and none can be traced to one: the learners of a period are counted in memory and only their
number is kept. The reports hide a cell standing on fewer than INSIGHTS_MIN_CELL_CLASS learners (insights/cells.py).
Staff accounts, which preview the course, are not learners. Today is not counted: it is not over."""

import calendar
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from content.models import Subject
from learn.models import CardReview, Chapter, Progress, QuizAttempt

from ..metrics import day_start
from ..models import CourseHealthStat

Grain = CourseHealthStat.Grain
DAYS, WEEKS, MONTHS = 92, 56, 14  # the complete periods kept of each grain
# What each source of activity gives: (model, the path to its chapter, its date, {a count's name: its aggregate}); the
# counts come in this order, and each is a measure of the stat row.
SOURCES = {
    "clips": (
        Progress,
        "clip__revision__chapter",
        "updated",
        {"started": Count("pk"), "completed": Count("pk", filter=Q(completed=True))},
        ["clips_started", "clips_completed"],
    ),
    "quiz": (
        QuizAttempt,
        "item__chapter",
        "created",
        {"answers": Count("pk"), "right": Count("pk", filter=Q(correct=True))},
        ["quiz_answers", "quiz_correct"],
    ),
    "cards": (
        CardReview,
        "card__chapter",
        "created",
        {"reviews": Count("pk"), "lapses": Count("pk", filter=Q(known=False))},
        ["card_reviews", "card_lapses"],
    ),
}
MEASURES = [name for *_, names in SOURCES.values() for name in names]


def monday(day):
    return day - timedelta(days=day.weekday())


def month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def shift_month(first, by):
    """The first day of the month `by` months after the month of `first` (before it for a negative `by`)."""
    index = first.year * 12 + first.month - 1 + by
    return first.replace(year=index // 12, month=index % 12 + 1, day=1)


def windows(today):
    """{grain: [the period starts, oldest first]} of the complete periods up to yesterday: DAYS days, WEEKS weeks
    (Monday to Sunday, the last one over), MONTHS months (the last one over), and the two trailing windows."""
    yesterday = today - timedelta(days=1)
    days = [yesterday - timedelta(days=n) for n in range(DAYS - 1, -1, -1)]
    last_sunday = yesterday if yesterday.weekday() == 6 else monday(yesterday) - timedelta(days=1)
    weeks = [monday(last_sunday) - timedelta(weeks=n) for n in range(WEEKS - 1, -1, -1)]
    this_month = yesterday.replace(day=1)
    last_month = this_month if yesterday == month_end(yesterday) else shift_month(this_month, -1)
    months = [shift_month(last_month, -n) for n in range(MONTHS - 1, -1, -1)]
    return {
        Grain.DAY: days,
        Grain.WEEK: weeks,
        Grain.MONTH: months,
        Grain.LAST_7: [yesterday - timedelta(days=6)],
        Grain.LAST_28: [yesterday - timedelta(days=27)],
    }


class Periods:
    """The periods kept (`windows`), and which of them a day belongs to."""

    TRAILING = {Grain.LAST_7: 6, Grain.LAST_28: 27}

    def __init__(self, today):
        self.found = windows(today)
        self.yesterday = today - timedelta(days=1)
        self.sets = {grain: set(starts) for grain, starts in self.found.items()}
        self.earliest = min(starts[0] for starts in self.found.values())

    def of(self, day):
        """[(grain, period start)] of the periods kept that contain this day (none after yesterday)."""
        if day > self.yesterday:
            return []
        belongs = [(Grain.DAY, day), (Grain.WEEK, monday(day)), (Grain.MONTH, day.replace(day=1))]
        belongs += [
            (grain, self.yesterday - timedelta(days=back))
            for grain, back in self.TRAILING.items()
            if (self.yesterday - day).days <= back
        ]
        return [(grain, start) for grain, start in belongs if start in self.sets[grain]]


def scopes(subject, chapter):
    """The three scopes an activity in a chapter counts in: the chapter, its subject, the whole course."""
    return [("chapter", chapter), ("subject", subject), ("all", 0)]


def reads(source, subject, start, end):
    """(the learner, the chapter and the day of each day a learner was active in a subject, once a day; and the
    counts of each chapter and day). Staff accounts are left out."""
    model, chapter, when, counts, _ = source
    within = model.objects.filter(
        **{f"{chapter}__subject": subject, f"{when}__gte": start, f"{when}__lt": end, "user__is_staff": False}
    )
    within = within.order_by().annotate(day=TruncDate(when))  # (no default ordering: it would widen the DISTINCT)
    days = within.values_list("user_id", f"{chapter}_id", "day").distinct()
    totals = within.values(f"{chapter}_id", "day").annotate(**counts).values_list(f"{chapter}_id", "day", *counts)
    return days, totals


@transaction.atomic
def course_health(today=None):
    """Rewrite the course health for every period and scope; returns the number of rows."""
    now = timezone.now()
    today = today or timezone.localdate(now)
    periods = Periods(today)
    start, end = day_start(periods.earliest), day_start(today)
    learners = defaultdict(set)  # (scope, grain, period start) → the learners (kept in memory only, never stored)
    sums = defaultdict(lambda: dict.fromkeys(MEASURES, 0))
    for subject in Subject.objects.filter(chapters__isnull=False).distinct():
        for source in SOURCES.values():
            days, totals = reads(source, subject, start, end)
            for learner, chapter, day in days.iterator(chunk_size=5000):
                for grain, begins in periods.of(day):
                    for scope in scopes(subject.pk, chapter):
                        learners[scope, grain, begins].add(learner)
            for chapter, day, *counted in totals:
                for grain, begins in periods.of(day):
                    for scope in scopes(subject.pk, chapter):
                        for measure, count in zip(source[4], counted, strict=True):
                            sums[scope, grain, begins][measure] += count
    subject_of = dict(Chapter.objects.values_list("pk", "subject_id"))
    rows = []
    for key in sorted(set(learners) | set(sums), key=lambda each: (each[0], each[1], each[2])):
        (scope, ident), grain, begins = key
        rows.append(
            CourseHealthStat(
                grain=grain,
                period_start=begins,
                subject_id=ident if scope == "subject" else subject_of[ident] if scope == "chapter" else None,
                chapter_id=ident if scope == "chapter" else None,
                active_learners=len(learners.get(key, ())),
                computed_at=now,
                computed_for=today,
                **sums[key],
            )
        )
    CourseHealthStat.objects.all().delete()
    CourseHealthStat.objects.bulk_create(rows, batch_size=1000)
    return len(rows)
