"""The student's learning dashboard (GET /api/v1/me/learning/): what is open, progress per subject and chapter, the
clip to continue with, the revise-again counts, the plan's next days and the streak. Read from the rows the course
keeps already (Progress, QuizAttempt, CardReview, Learner); no table of its own."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Least, TruncDate
from django.utils import timezone

from . import plan
from .models import CardReview, Chapter, Clip, Learner, Progress, QuizAttempt, Revision
from .services import entitled_subjects, is_free_clip

PLAN_DAYS = 3
NO_EXAM_DATE = "Save the date of your exam to see what to watch each day."
EXAM_PASSED = "The exam date you saved has passed: save the next one."
NOTHING_TO_PLAN = "Nothing to plan: the clips open to you are watched, or none is ready yet."


def percent(part, whole):
    return round(100 * part / whole) if whole else None


def activity(seconds, watched, total, answers, right, last):
    return {
        "clips_watched": watched,
        "clips_total": total,
        "minutes_watched": round(seconds / 60),
        "quiz_answers": answers,
        "quiz_accuracy": percent(right, answers),
        "last_activity": max(filter(None, last), default=None),
    }


def subjects(user, entitled):
    """Per subject open to the user or touched by them, its published chapters with clips watched (of the processed
    ones), minutes watched (at most each clip's length), quiz answers and the share right, and the latest activity."""
    # a clip or a quiz item in the course's bin (the panel's; Phase B) is not counted: joins filter it themselves
    watched = Progress.objects.filter(user=user, clip__processing=Clip.Processing.READY, clip__deleted_at__isnull=True)
    progress = {
        row["clip__revision__chapter"]: row
        for row in watched.values("clip__revision__chapter").annotate(
            done=Count("pk", filter=Q(completed=True)),
            seconds=Sum(Least("seconds_watched", "clip__duration")),
            last=Max("updated"),
        )
    }
    quiz = {
        row["item__chapter"]: row
        for row in QuizAttempt.objects.filter(user=user, item__deleted_at__isnull=True)
        .values("item__chapter")
        .annotate(answers=Count("pk"), right=Count("pk", filter=Q(correct=True)), last=Max("created"))
    }
    ready = Q(revision__clips__processing=Clip.Processing.READY, revision__clips__deleted_at__isnull=True)
    chapters = (
        Chapter.objects.filter(revision__status=Revision.Status.PUBLISHED)
        .annotate(total=Count("revision__clips", filter=ready))
        .select_related("subject")
        .order_by("subject", "number")
    )
    by_subject = {}
    for chapter in chapters:
        if not (chapter.subject_id in entitled or chapter.pk in progress or chapter.pk in quiz):
            continue
        p, q = progress.get(chapter.pk, {}), quiz.get(chapter.pk, {})
        row = (p.get("seconds") or 0, p.get("done", 0), chapter.total, q.get("answers", 0), q.get("right", 0))
        by_subject.setdefault(chapter.subject, []).append((chapter, row, (p.get("last"), q.get("last"))))
    result = []
    for subject, rows in by_subject.items():
        sums = [sum(row[i] for _, row, _ in rows) for i in range(5)]
        lasts = [moment for _, _, pair in rows for moment in pair]
        chapter_rows = [
            {"id": chapter.pk, "number": chapter.number, "title": chapter.title, **activity(*row, last)}
            for chapter, row, last in rows
        ]
        result.append(
            {"id": subject.pk, "code": subject.code, "name": subject.name, "entitled": subject.pk in entitled,
             **activity(*sums, lasts), "chapters": chapter_rows}
        )  # fmt: skip
    return result


def next_clip(user, entitled):
    """The next unwatched, processed clip of the revision the student watched last (of the one before, when that one
    is done), with its revision and chapter; None before any clip was watched."""
    progress = {row.clip_id: row for row in Progress.objects.filter(user=user)}
    recent = (
        Progress.objects.filter(user=user, clip__revision__status=Revision.Status.PUBLISHED)
        .order_by("-updated")
        .values_list("clip__revision", flat=True)
    )
    for revision in dict.fromkeys(recent):  # each revision once, the latest first
        clips = list(Clip.objects.filter(revision=revision).select_related("revision__chapter__subject"))
        for clip in clips:
            if clip.processing == Clip.Processing.READY and not getattr(progress.get(clip.pk), "completed", False):
                clip.free = is_free_clip(clip, first=clips[0].pk)
                clip.locked = not (clip.free or clip.revision.chapter.subject_id in entitled)
                clip.seconds_watched = getattr(progress.get(clip.pk), "seconds_watched", 0)
                return {"clip": clip, "revision": clip.revision, "chapter": clip.revision.chapter}
    return None


def revise_again_counts(user, now=None):
    """The quiz items and flash cards answered wrong (learn/revise-again/): due today (or before), and due later."""
    now = now or timezone.now()
    pending = plan.revise_again(user, now=now + timedelta(days=plan.INTERVALS[-1]))  # each one due within a week
    today = timezone.localdate(now)
    days = [timezone.localdate(row["due"]) for rows in pending.values() for row in rows]
    return {"due_today": sum(day <= today for day in days), "later": sum(day > today for day in days)}


def next_days(user, today=None):
    """The pass plan's first PLAN_DAYS days for the exam date and minutes saved (learn/settings/), or a hint why
    there are none."""
    today = today or timezone.localdate()
    saved = Learner.objects.filter(user=user).first() or Learner()
    answer = {"exam_date": saved.exam_date, "days_left": None, "minutes_per_day": saved.minutes_per_day, "days": []}
    if not saved.exam_date or saved.exam_date <= today:
        return {**answer, "hint": EXAM_PASSED if saved.exam_date else NO_EXAM_DATE}
    made = plan.build(user, plan.default_subjects(user), saved.exam_date, saved.minutes_per_day, today=today)
    days = made["days"][:PLAN_DAYS]
    return {**answer, "days_left": made["days_left"], "days": days, "hint": "" if days else NOTHING_TO_PLAN}


def streak(user, today=None):
    """Consecutive days with a clip watched, a quiz answer or a card review, up to today (or up to yesterday while
    today has none yet). ponytail: a Progress row keeps only its latest update, so a clip watched on two days counts
    on the later one; a log of watching would be a table of its own."""
    days = set()
    for rows, moment in [
        (Progress.objects.filter(user=user), "updated"),
        (QuizAttempt.objects.filter(user=user), "created"),
        (CardReview.objects.filter(user=user), "created"),
    ]:
        days.update(rows.order_by().annotate(day=TruncDate(moment)).values_list("day", flat=True).distinct())
    today = today or timezone.localdate()
    day, count = (today if today in days else today - timedelta(days=1)), 0
    while day in days:
        count, day = count + 1, day - timedelta(days=1)
    return {"days": count, "today": today in days, "last_day": max(days, default=None)}


def learning(user):
    """Everything the dashboard shows, for LearningSerializer."""
    entitled, today = entitled_subjects(user), timezone.localdate()
    return {
        "entitlements": user.entitlements.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=today)
        ).select_related("subject"),
        "subjects": subjects(user, entitled),
        "continue_watching": next_clip(user, entitled),
        "revise_again": revise_again_counts(user),
        "plan": next_days(user, today),
        "streak": streak(user, today),
        "consent_pending": user.consent_pending,
        "has_app_links": bool(settings.APP_LINK_ANDROID or settings.APP_LINK_IOS),
    }
