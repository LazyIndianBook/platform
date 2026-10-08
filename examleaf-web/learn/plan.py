"""The pass plan (GET /api/v1/learn/plan/): the clips to watch day by day until the exam, most valuable chapters first,
and the minimum to pass; and what to revise again (spaced repetition)."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q
from django.utils import timezone

from content.models import Paper

from .models import CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from .services import entitled_subjects, is_free_chapter

# ponytail: aim at chapters worth 1.5 times the pass marks, as nobody scores every mark of a chapter they revised
PASS_MARGIN = Decimal("1.5")
QUICK_KINDS = [Clip.Kind.PYQ, Clip.Kind.FORMULA, Clip.Kind.SHORTCUT, Clip.Kind.TRICK]  # marks fastest
INTERVALS = [1, 3, 7]  # days until a wrong answer comes back, then after each right one


def weakness(user, chapters):
    """{chapter id: share of the student's quiz answers in it that were wrong}."""
    rows = (
        QuizAttempt.objects.filter(user=user, item__chapter__in=chapters)
        .values("item__chapter")
        .annotate(total=Count("pk"), wrong=Count("pk", filter=Q(correct=False)))
    )
    return {row["item__chapter"]: Decimal(row["wrong"]) / row["total"] for row in rows}


def priority(chapter, weak):
    """Board marks x previous-year questions (at least 1) x (1 + the share of wrong quiz answers in it)."""
    return chapter.weight * max(chapter.frequency, 1) * (1 + weak.get(chapter.pk, 0))


def build(user, subjects, exam_date, minutes_per_day, today=None):
    """Greedy: chapters by priority, their unwatched clips in order, packed into days of `minutes_per_day` (a clip
    longer than that gets a day of its own) from today until the day before the exam."""
    today = today or timezone.localdate()
    days_left = (exam_date - today).days
    chapters = list(
        Chapter.objects.filter(subject__in=subjects, revision__status=Revision.Status.PUBLISHED).select_related(
            "subject", "revision"
        )
    )
    clips = defaultdict(list)
    for clip in Clip.objects.filter(revision__chapter__in=chapters, processing=Clip.Processing.READY):
        clips[clip.revision.chapter_id].append(clip)
    watched = set(Progress.objects.filter(user=user, completed=True).values_list("clip_id", flat=True))
    weak = weakness(user, chapters)
    ranked = sorted(chapters, key=lambda c: (-priority(c, weak), c.subject_id, c.number))

    days, seconds, budget, left_out = [], 0, minutes_per_day * 60, []
    for chapter in ranked:
        for clip in (clip for clip in clips[chapter.pk] if clip.pk not in watched):
            if not days or (seconds and seconds + clip.duration > budget):
                if len(days) == days_left:
                    left_out.append(chapter)
                    break
                days.append({"date": today + timedelta(days=len(days)), "clips": []})
                seconds = 0
            days[-1]["clips"].append(clip)
            seconds += clip.duration
    return {
        "exam_date": exam_date,
        "days_left": days_left,
        "minutes_per_day": minutes_per_day,
        "days": days,
        "not_scheduled": left_out,
        "minimum_to_pass": minimum_to_pass(ranked, clips),
    }


def minimum_to_pass(chapters, clips):
    """Per subject, the chapters that give the most Board marks per minute of revision, until they are worth the pass
    marks (of the subject's papers) times PASS_MARGIN; in each, its clips of the quickest kinds."""
    passes = dict(
        Paper.objects.filter(book__subject__in={c.subject_id for c in chapters})
        .values_list("book__subject")
        .annotate(Max("pass_marks"))
    )
    by_subject = defaultdict(list)
    for chapter in chapters:
        minutes = max(sum(clip.duration for clip in clips[chapter.pk]) / 60, 1)
        by_subject[chapter.subject].append((chapter.weight / Decimal(minutes), minutes, chapter))
    result = []
    for subject, rows in by_subject.items():
        pass_marks = passes.get(subject.pk) or round(sum(row[2].weight for row in rows) * Decimal("0.3"))  # 30%
        target, total, picked = pass_marks * PASS_MARGIN, Decimal(0), []
        for per_minute, minutes, chapter in sorted(rows, key=lambda row: -row[0]):
            if total >= target:
                break
            total += chapter.weight
            quick = [clip for clip in clips[chapter.pk] if clip.kind in QUICK_KINDS]
            picked.append(
                {"chapter": chapter, "minutes": round(minutes), "marks_per_minute": per_minute, "clips": quick}
            )
        result.append({"subject": subject, "pass_marks": pass_marks, "marks": total, "chapters": picked})
    return result


def due(answers, now):
    """When an item answered wrong comes back: INTERVALS days after the last answer, the step being the number of right
    answers since the last wrong one; None when never wrong, or right at every step since."""
    step, last = None, None
    for created, right in answers:
        step = (step + 1 if step is not None else None) if right else 0
        last = created
    return None if step is None or step >= len(INTERVALS) else last + timedelta(days=INTERVALS[step])


def revise_again(user, now=None):
    """Quiz items and flash cards the student got wrong whose day has come, the longest waiting first; only of
    published revisions the student may still open, as the quiz and the cards themselves (I5): not after the year of
    access, nor once a revision is back in draft."""
    now, entitled = now or timezone.now(), entitled_subjects(user)
    lists = {}
    for name, model, rows in [
        ("quiz_items", QuizItem, QuizAttempt.objects.filter(user=user).values_list("item", "created", "correct")),
        ("flash_cards", FlashCard, CardReview.objects.filter(user=user).values_list("card", "created", "known")),
    ]:
        answers = defaultdict(list)
        for pk, created, right in rows.order_by("created", "pk"):
            answers[pk].append((created, right))
        when = {pk: at for pk, history in answers.items() if (at := due(history, now)) and at <= now}
        published = model.objects.filter(pk__in=when, chapter__revision__status=Revision.Status.PUBLISHED)
        items = [
            item
            for item in published.select_related("chapter")
            if item.chapter.subject_id in entitled or model is FlashCard and is_free_chapter(item.chapter)
        ]
        lists[name] = sorted(({"item": item, "due": when[item.pk]} for item in items), key=lambda row: row["due"])
    return lists
