"""Reported mistakes (plan 5.10, research-lms-crm-cms.md 2.4): what a reader sends with "Report a mistake" (the public
POST /api/v1/reports/, api/reports.py) and what the quiz's item analysis flags (flag_items, nightly) land in one
triage queue: reported → confirmed or rejected → fixed online → fixed in printing N. A report that looks like spam
(`spam_reason`) is kept out of the queue and goes after SPAM_DAYS (purge_spam, nightly); the others open an inbox item
for the triage of their subject. The reporter's email address, when left, serves to tell them of the fix and is then
cleared (on rejection too). The public errata list what staff mark `public`. Every step is an audit event."""

import re
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers

from ops.tasks import queue_text_email
from staff import audit
from staff.models import InboxItem
from staff.signals import close_items, open_item

from .models import ErrorReport, Question, Solution

State = ErrorReport.State
TARGETS = ["solution", "question", "quiz_item", "clip"]  # what a reader reports on (POST /api/v1/reports/ `kind`)
READER_CATEGORIES = [(value, label) for value, label in ErrorReport.Category.choices if value != "item_analysis"]
SPAM_DAYS = 30
FLAG_PAUSE_DAYS = 30  # an item's flag closed (fixed or rejected) is not reported again within these days
PRINTING = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,39}\Z")  # a print run's label: PHY-2027-1
LINK = re.compile(r"https?://|www\.|\[url", re.I)
MARKUP = re.compile(r"<\s*/?\s*[a-z!]", re.I)
REPEATED = re.compile(r"(.)\1{9,}", re.S)
# what each step does: the states it starts from, the state it leaves the report in
TRANSITIONS = {
    "confirm": ([State.REPORTED], State.CONFIRMED),
    "reject": ([State.REPORTED, State.CONFIRMED], State.REJECTED),
    "fix-online": ([State.REPORTED, State.CONFIRMED], State.FIXED_ONLINE),
    "fix-in-printing": ([State.CONFIRMED, State.FIXED_ONLINE], State.FIXED_IN_PRINTING),
    "reopen": ([State.REJECTED], State.REPORTED),
}


def spam_reason(note):
    """Why a note reads as spam, or "": a link, markup, one character over and over, or no word at all."""
    # ponytail: four plain rules (Turnstile, the limits and the honeypot stop most bots first); a scoring filter
    # once real spam slips past them
    if LINK.search(note):
        return "a link in the note"
    if MARKUP.search(note):
        return "markup in the note"
    if REPEATED.search(note):
        return "one character repeated"
    if len(note) > 20 and not any(char.isalpha() for char in note):
        return "no words in the note"
    return ""


def where(report):
    """Where the mistake is, by codes and labels (an inbox title names no one): "PHY-E01 2(c), step 3"."""
    if report.question_id:
        text = f"{report.paper.code if report.paper_id else ''} {report.question.label}".strip()
    elif report.target_type.model == "quizitem":
        text = f"quiz item #{report.target_id}"
    elif report.target_type.model == "clip":
        text = f"clip #{report.target_id}"
    else:
        text = f"{report.target_type.model} #{report.target_id}"
    return f"{text}, step {report.step}" if report.step else text


def kind_of(report):
    return {"quizitem": "quiz_item"}.get(report.target_type.model, report.target_type.model)


def file(report):
    """Its inbox item, for whoever triages its subject."""
    if report.spam:
        return
    open_item(
        InboxItem.Kind.ERROR_REPORT,
        report,
        f"Reported mistake #{report.pk}: {where(report)}",
        "staff.triage_report",
        subject=report.subject.code if report.subject_id else None,
    )


def teacher(user):
    profile = getattr(user, "teacher_profile", None) if user is not None else None
    return bool(profile and profile.verified)


@transaction.atomic
def receive(*, target, subject, paper=None, question=None, step=None, printing="", category, note="", email="",
            reporter=None, request=None):  # fmt: skip
    """A reader's report, stored (spam set apart by the rules), filed in the inbox, audited."""
    reason = spam_reason(note)
    report = ErrorReport.objects.create(
        target_type=ContentType.objects.get_for_model(target),
        target_id=target.pk,
        subject=subject,
        paper=paper,
        question=question,
        step=step,
        printing=printing,
        category=category,
        note=note,
        email=email,
        reporter=reporter,
        teacher_verified=teacher(reporter),
        spam=bool(reason),
        spam_reason=reason,
    )
    file(report)
    audit.record(
        "content.report_received",
        request=request,
        actor=reporter,
        actor_type=None if reporter else audit.ActorType.ANONYMOUS,
        target=report,
        details={"category": category, "where": where(report), "spam": report.spam},
    )
    return report


def locked(report):
    # of=("self",): the report's row alone; PostgreSQL refuses FOR UPDATE on the nullable side of an outer join
    return (
        ErrorReport.objects.select_for_update(of=("self",))
        .select_related("paper", "question", "subject")
        .get(pk=report.pk)
    )


@transaction.atomic
def transition(report, verb, user, request=None, staff_note=None, fixed_in=""):
    """One step of the triage (TRANSITIONS); a rejection says why, a fix in printing names the printing."""
    report = locked(report)
    sources, state = TRANSITIONS[verb]
    if report.state not in sources:
        raise serializers.ValidationError(
            {"non_field_errors": [f"It is {report.get_state_display()}: this step does not follow from there."]}
        )
    if staff_note is not None:
        report.staff_note = staff_note.strip()
    if verb == "reject" and not report.staff_note:
        raise serializers.ValidationError({"staff_note": ["Say why it is not a mistake."]})
    if verb == "fix-in-printing":
        if not PRINTING.fullmatch(fixed_in or ""):
            raise serializers.ValidationError({"fixed_in": ["The printing that carries the fix: PHY-2027-2."]})
        report.fixed_in = fixed_in
    now = timezone.now()
    if state in (State.CONFIRMED, State.REJECTED):
        report.resolved_at = now
    if state == State.FIXED_ONLINE:
        report.fixed_at = now
    if state in ErrorReport.FIXED:
        report.resolved_at = report.resolved_at or now
    if state == State.REJECTED:
        report.email = ""  # nothing will be fixed to tell them about
    if state == State.REPORTED:
        report.resolved_at = None
    report.state, report.handled_by = state, user
    report.save()
    if state in ErrorReport.OPEN:
        file(report)
    else:
        close_items(report, InboxItem.Kind.ERROR_REPORT)
    audit.record(
        f"content.report_{verb.replace('-', '_')}",
        request=request,
        target=report,
        details={"state": state, "fixed_in": report.fixed_in},
    )
    return report


def page_of(report):
    """Where a reader finds the fix: the solutions page at the question, or the course."""
    if report.paper_id:
        anchor = re.sub(r"[^a-z0-9]+", "-", report.question.label.lower()).strip("-") if report.question_id else ""
        return f"{settings.SITE_URL}/s/{report.paper.code}/" + (f"#q-{anchor}" if anchor else "")
    return f"{settings.SITE_URL}/revision/"


@transaction.atomic
def tell(report, user, request=None):
    """The reporter is emailed that the fix is published (once, if they left an address); the address goes then."""
    report = locked(report)
    if report.state not in ErrorReport.FIXED:
        raise serializers.ValidationError({"non_field_errors": ["Tell the reporter once it is fixed."]})
    if report.reporter_told_at:
        raise serializers.ValidationError({"non_field_errors": ["The reporter was told already."]})
    if not report.email:
        raise serializers.ValidationError({"non_field_errors": ["No email address was left with this report."]})
    email = report.email
    body = render_to_string(
        "content/email/report_fixed.txt",
        {"where": where(report), "url": page_of(report), "fixed_in": report.fixed_in, "site_url": settings.SITE_URL},
    )
    transaction.on_commit(lambda: queue_text_email(email, "The mistake you reported is fixed", body), robust=True)
    report.reporter_told_at, report.email = timezone.now(), ""
    report.save(update_fields=["reporter_told_at", "email", "modified"])
    audit.record("content.reporter_told", request=request, target=report, details={"where": where(report)})
    return report


def errata(reports):
    """What the errata list: confirmed and fixed mistakes, not spam, in paper and question order."""
    return (
        reports.filter(spam=False, state__in=[State.CONFIRMED, *ErrorReport.FIXED])
        .select_related("paper", "question", "subject")
        .order_by("paper__code", "question__order", "step", "pk")
    )


def purge_spam(now=None):
    """Nightly: the reports set apart as spam, after SPAM_DAYS."""
    cutoff = (now or timezone.now()) - timedelta(days=SPAM_DAYS)
    count, _ = ErrorReport.objects.filter(spam=True, created__lt=cutoff).delete()
    return count


def flag_items():
    """Nightly, after the item analysis: one report per quiz item its latest run flags, in the same queue, unless one
    is open for the item or one was closed in the last FLAG_PAUSE_DAYS (run twice, it makes none the second time)."""
    from insights.models import ItemStat
    from learn.models import QuizItem

    latest = ItemStat.objects.aggregate(day=Max("run_date"))["day"]
    if latest is None:
        return 0
    kind = ContentType.objects.get_for_model(QuizItem)
    since = timezone.now() - timedelta(days=FLAG_PAUSE_DAYS)
    reported = set(
        ErrorReport.objects.filter(target_type=kind, category=ErrorReport.Category.ITEM_ANALYSIS)
        .filter(Q(state__in=ErrorReport.OPEN) | Q(modified__gte=since))
        .values_list("target_id", flat=True)
    )
    made = 0
    stats = ItemStat.objects.filter(run_date=latest, item__deleted_at__isnull=True)  # not an item in the course's bin
    for stat in stats.select_related("item__chapter__subject").order_by("pk"):
        if not stat.flags or stat.item_id in reported:
            continue
        p = f"{stat.p:.0%}" if stat.p is not None else "N/A"
        discrimination = f"{stat.discrimination:.2f}" if stat.discrimination is not None else "N/A"
        note = f"Item analysis of {stat.n} learners: {p} right, discrimination {discrimination}; flags: " + ", ".join(
            stat.flags
        )
        try:
            with transaction.atomic():
                report = ErrorReport.objects.create(
                    target_type=kind,
                    target_id=stat.item_id,
                    subject=stat.item.chapter.subject,
                    category=ErrorReport.Category.ITEM_ANALYSIS,
                    note=note,
                )
                file(report)
                audit.record("content.item_flagged", actor_type=audit.ActorType.SYSTEM, target=report,
                             details={"item": stat.item_id, "flags": stat.flags})  # fmt: skip
        except IntegrityError:  # another run made it meanwhile (one open flag per item)
            continue
        made += 1
    return made


def linked(report):
    """The content a report is about, as the triage reads it: the question and its solution (live, and whether a
    draft waits), or the quiz item's text, or the clip's title."""
    model = report.target_type.model
    found = {"question_id": None, "solution_id": None, "paper_id": report.paper_id}
    if report.question_id:
        question = Question.objects.select_related("paper").filter(pk=report.question_id).first()
        solution = Solution.objects.filter(question_id=report.question_id).first()
        found |= {
            "question_id": report.question_id,
            "question_text": question.text_md if question else "",
            "solution_id": solution.pk if solution else None,
            "solution_text": solution.body_md if solution else "",
            "solution_state": solution.state if solution else None,
        }
    elif model in ("quizitem", "clip"):
        target = report.target
        found |= {"title": (getattr(target, "text", None) or getattr(target, "title", "")) if target else ""}
    return found
