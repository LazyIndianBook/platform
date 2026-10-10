"""The rules of the panel's Course module (plan 5.11; learn/README.md "The Course module"; its staff API is
learn/staff_api.py): a parent's clips, cards or quiz items kept in a dense order, moved without dragging; a revision's
review and its publish, now or at a set time (learn.tasks.publish_due); the 30-day bin and its purge (learn.tasks
.purge_bin: a clip's video and HLS files go only then); a quiz item flagged into the content triage; the quiz bank's
metadata; entitlements granted, extended and revoked, the student's progress kept whatever becomes of them. Every
change is an audit event written in the caller's transaction (staff.audit); who may do it is the views' to check."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions, serializers

from staff import audit
from staff.models import InboxItem
from staff.signals import close_items, open_item

from .models import Chapter, Clip, Entitlement, FlashCard, QuizItem, Revision

BIN_DAYS = 30  # a clip, card or quiz item in the bin: restored within, purged after (with a clip's files)
KINDS = {"clips": Clip, "cards": FlashCard, "items": QuizItem}  # the {kind} of the staff API's paths
ROW_KINDS = list(KINDS)
SIBLINGS = {Clip: "revision", FlashCard: "chapter", QuizItem: "chapter"}  # whose children they are, in order
NOUNS = {Clip: "clip", FlashCard: "flash card", QuizItem: "quiz item"}
MOVES = ["first", "last", "before", "after"]
COMPLETION_RULE = (
    "A clip counts as completed once the app reports it watched to its end (the student's own player sends "
    "completed); once completed it stays completed, whatever is watched again."
)
Status = Revision.Status


def refused(message, field="non_field_errors"):
    return serializers.ValidationError({field: [message]})


class OwnEdit(exceptions.PermissionDenied):
    """Separation of duties (plan 4.1): whoever submitted a revision never approves or publishes it."""

    default_detail = "You submitted this revision: another reviewer approves and publishes it."
    default_code = "own_edit"


def subject_code(obj):
    """The subject's code of a revision, clip, card or quiz item (an inbox item is narrowed by it)."""
    chapter = obj.chapter if hasattr(obj, "chapter_id") else obj.revision.chapter
    return chapter.subject.code


# ---- Order: a parent's live rows numbered 1, 2, 3 …, moved without dragging ----


def parent_model(model):
    return Revision if model is Clip else Chapter


def parent_of(obj):
    return getattr(obj, f"{SIBLINGS[type(obj)]}_id")


def live_siblings(model, parent_id):
    """A parent's rows outside the bin, in their order."""
    return model.objects.filter(**{f"{SIBLINGS[model]}_id": parent_id}).order_by("order", "pk")


def lock_parent(model, parent_id):
    """One change to a parent's order at a time (two moves at once would number its rows twice)."""
    parent_model(model).objects.select_for_update().filter(pk=parent_id).first()


def renumber(model, rows):
    """Number `rows` (a parent's live rows in their new order) 1, 2, 3 …: a dense order; the changed ones saved."""
    changed = []
    for number, row in enumerate(rows, 1):
        if row.order != number:
            row.order = number
            changed.append(row)
    model.all_objects.bulk_update(changed, ["order"])


def move(obj, to, target=None, request=None):
    """The row first, last, or before or after a sibling (`target`, its id), its siblings renumbered in one
    transaction: the keyboard's path for every drag (WCAG 2.5.7)."""
    model = type(obj)
    noun, parent = NOUNS[model], parent_of(obj)
    if to not in MOVES:
        raise refused(f"One of {', '.join(MOVES)}.", "to")
    with transaction.atomic():
        lock_parent(model, parent)
        rows = list(live_siblings(model, parent).select_for_update())
        here = next((row for row in rows if row.pk == obj.pk), None)
        if here is None:
            raise refused(f"This {noun} is in the bin: restore it first.")
        rest = [row for row in rows if row.pk != here.pk]
        if to in ("before", "after"):
            if target is None or str(target) == str(here.pk):
                raise refused(f"Another {noun} of the same {SIBLINGS[model]} to move it {to}.", "target")
            index = next((i for i, row in enumerate(rest) if str(row.pk) == str(target)), None)
            if index is None:
                raise refused(f"Not a {noun} of the same {SIBLINGS[model]} (or it is in the bin).", "target")
            index += to == "after"
        else:
            index = 0 if to == "first" else len(rest)
        rest.insert(index, here)
        before = here.order
        renumber(model, rest)
        details = {"to": to, "target": int(target) if str(target or "").isdigit() else None}
        audit.record("course.moved", request=request, target=here, changes={"order": [before, here.order]},
                     details=details)  # fmt: skip
    return here


# ---- A revision's review and publish ----


def locked_revision(revision):
    return Revision.objects.select_for_update(of=("self",)).select_related("chapter__subject").get(pk=revision.pk)


def ready_clips(revision):
    return Clip.objects.filter(revision=revision, processing=Clip.Processing.READY).exists()


def revision_title(revision):
    return f"revision #{revision.pk} ({revision.chapter.subject.code} chapter {revision.chapter.number})"


def check_reviewer(revision, user):
    if revision.submitted_by_id is not None and revision.submitted_by_id == user.pk:
        raise OwnEdit()


def save_revision(revision, *fields):
    revision.save(update_fields=[*fields, "modified"])


def submit(revision, user, request=None):
    """A draft to review: the subject's reviewers find it in their inbox."""
    with transaction.atomic():
        revision = locked_revision(revision)
        if revision.status != Status.DRAFT:
            raise refused(f"It is {revision.get_status_display()}: only a draft is submitted for review.")
        revision.status, revision.submitted_by, revision.submitted_at = Status.REVIEW, user, timezone.now()
        revision.reviewer, revision.publish_at = None, None
        save_revision(revision, "status", "submitted_by", "submitted_at", "reviewer", "publish_at")
        close_items(revision, InboxItem.Kind.REVIEW)  # "changes asked" for the submitter: done
        title = f"Course review: {revision_title(revision)}"
        open_item(InboxItem.Kind.REVIEW, revision, title, "staff.publish_course", subject=subject_code(revision))
        audit.record("course.revision_submitted", request=request, target=revision)
    return revision


def approve(revision, user, comment="", request=None):
    """A reviewer's approval (never its submitter's): then published now or at a time."""
    with transaction.atomic():
        revision = locked_revision(revision)
        if revision.status != Status.REVIEW:
            raise refused(f"It is {revision.get_status_display()}: only a revision in review is approved.")
        check_reviewer(revision, user)
        revision.status, revision.reviewer = Status.APPROVED, user
        save_revision(revision, "status", "reviewer")
        close_items(revision, InboxItem.Kind.REVIEW)
        audit.record("course.revision_approved", request=request, target=revision, reason=comment[:500])
    return revision


def needs_changes(revision, user, comment, request=None):
    """Back to draft with what to change; its submitter finds it in their inbox."""
    if not str(comment or "").strip():
        raise refused("Say what to change.", "comment")
    with transaction.atomic():
        revision = locked_revision(revision)
        if revision.status != Status.REVIEW:
            raise refused(f"It is {revision.get_status_display()}: only a revision in review is sent back.")
        revision.status, revision.reviewer, revision.publish_at = Status.DRAFT, None, None
        save_revision(revision, "status", "reviewer", "publish_at")
        close_items(revision, InboxItem.Kind.REVIEW)
        if revision.submitted_by_id:
            InboxItem.objects.create(
                kind=InboxItem.Kind.REVIEW,
                title=f"Changes asked: {revision_title(revision)}"[:200],
                target_type=revision._meta.label_lower,
                target_id=str(revision.pk),
                permission="learn.change_revision",
                assignee_id=revision.submitted_by_id,
                data={"subject": subject_code(revision)},
            )
        audit.record("course.revision_needs_changes", request=request, target=revision, reason=comment[:500])
    return revision


def publish(revision, user, at=None, request=None):
    """In review (approved on the way) or approved: published now, which needs a clip ready to watch; or at `at`, a
    time to come, by the task (learn.tasks.publish_due). Never by its submitter."""
    now = timezone.now()
    if at is not None and at <= now:
        raise refused("A time to come, or none to publish it now.", "publish_at")
    if at is not None and at > now + timedelta(days=366):
        raise refused("Within a year.", "publish_at")
    with transaction.atomic():
        revision = locked_revision(revision)
        if revision.status == Status.PUBLISHED:
            raise refused("It is published already.")
        if revision.status == Status.DRAFT:
            raise refused("It is a draft: submit it for review first.")
        check_reviewer(revision, user)
        if revision.status == Status.REVIEW:
            revision.reviewer = user  # approved on the way, by whoever publishes it
        if at is None and not ready_clips(revision):
            raise refused("None of its clips is ready yet: it would publish nothing to watch.")
        revision.status, revision.publish_at = (Status.APPROVED, at) if at else (Status.PUBLISHED, None)
        save_revision(revision, "status", "reviewer", "publish_at")
        close_items(revision)
        action = "course.revision_scheduled" if at else "course.revision_published"
        audit.record(action, request=request, target=revision, details={"publish_at": at})
    return revision


def unpublish(revision, user, request=None):
    """Back to draft, from review, approval (its scheduled publish cancelled) or published: the app hides it again;
    the students keep their progress."""
    with transaction.atomic():
        revision = locked_revision(revision)
        if revision.status == Status.DRAFT:
            raise refused("It is a draft already.")
        was = revision.status
        revision.status, revision.reviewer, revision.publish_at = Status.DRAFT, None, None
        save_revision(revision, "status", "reviewer", "publish_at")
        close_items(revision)
        audit.record("course.revision_unpublished", request=request, target=revision, details={"was": was})
    return revision


def publish_due(now=None):
    """Every 5 minutes (learn.tasks): the approved revisions whose time has come, published once each; one without a
    ready clip waits, with an inbox item, until a clip is ready or it is sent back to draft. Returns how many."""
    now = now or timezone.now()
    published = 0
    for pk in Revision.objects.filter(status=Status.APPROVED, publish_at__lte=now).values_list("pk", flat=True):
        with transaction.atomic():
            revision = (
                Revision.objects.select_for_update()
                .select_related("chapter__subject")
                .filter(pk=pk, status=Status.APPROVED, publish_at__lte=now)
                .first()
            )
            if revision is None:  # published or sent back meanwhile
                continue
            if not ready_clips(revision):
                title = f"Scheduled publish waits: {revision_title(revision)} has no clip ready"
                open_item(InboxItem.Kind.FAILED_JOB, revision, title, "staff.publish_course",
                          subject=subject_code(revision))  # fmt: skip
                continue
            due = revision.publish_at
            revision.status, revision.publish_at = Status.PUBLISHED, None
            save_revision(revision, "status", "publish_at")
            close_items(revision)
            details = {"scheduled_for": due, "approved_by": revision.reviewer_id}
            audit.record("course.revision_published", actor_type=audit.ActorType.SYSTEM, target=revision,
                         details=details)  # fmt: skip
            published += 1
    return published


# ---- The bin ----


def bin_until(obj):
    return obj.deleted_at + timedelta(days=BIN_DAYS) if obj.deleted_at else None


def save_row(obj, *fields):
    obj.save(update_fields=[*fields, *(["modified"] if isinstance(obj, Clip) else [])])


def delete(obj, request=None):
    """Into the bin for BIN_DAYS (a clip keeps its video and HLS files): out of the app's sight at once, its siblings
    renumbered."""
    model = type(obj)
    parent = parent_of(obj)
    with transaction.atomic():
        lock_parent(model, parent)
        obj = model.objects.select_for_update().filter(pk=obj.pk).first()
        if obj is None:
            raise refused(f"This {NOUNS[model]} is in the bin already.")
        obj.deleted_at = timezone.now()
        save_row(obj, "deleted_at")
        renumber(model, list(live_siblings(model, parent)))
        if model is Clip:
            close_items(obj, InboxItem.Kind.FAILED_JOB)  # a failed clip binned: nothing left to retry
        audit.record("course.deleted", request=request, target=obj, details={"bin_until": bin_until(obj)})
    return obj


def restore(obj, request=None):
    """Out of the bin within BIN_DAYS, back at the place it had among its siblings."""
    model = type(obj)
    parent = parent_of(obj)
    with transaction.atomic():
        lock_parent(model, parent)
        obj = model.all_objects.select_for_update().get(pk=obj.pk)
        if obj.deleted_at is None:
            raise refused(f"This {NOUNS[model]} is not in the bin.")
        if timezone.now() >= bin_until(obj):
            raise refused(f"It was in the bin more than {BIN_DAYS} days: it goes with the next purge.")
        rows = list(live_siblings(model, parent).select_for_update())
        rows.insert(max(0, min(obj.order - 1, len(rows))), obj)
        obj.deleted_at = None
        save_row(obj, "deleted_at")
        renumber(model, rows)
        audit.record("course.restored", request=request, target=obj)
    return obj


def purge(now=None):
    """Nightly (learn.tasks.purge_bin): the rows in the bin more than BIN_DAYS deleted for good, and with a clip its
    video and HLS files (learn.signals.delete_clip_files, once the deletion is saved). Returns {kind: rows}."""
    cutoff = (now or timezone.now()) - timedelta(days=BIN_DAYS)
    gone = {}
    for name, model in KINDS.items():
        with transaction.atomic():
            _, per_model = model.all_objects.filter(deleted_at__lt=cutoff).delete()
            gone[name] = per_model.get(model._meta.label, 0)
    if any(gone.values()):
        audit.record("course.purged", actor_type=audit.ActorType.SYSTEM, details={"deleted": gone})
    return gone


# ---- The quiz bank ----

METADATA = ["topic", "marks", "difficulty", "bloom"]
TAGS_AT_ONCE, TAG_LENGTH = 20, 100


def clean_tags(value, field):
    if not isinstance(value, list) or len(value) > TAGS_AT_ONCE:
        raise refused(f"A list of at most {TAGS_AT_ONCE} tags.", field)
    tags = [" ".join(str(tag).split()) for tag in value]
    if any(not tag or len(tag) > TAG_LENGTH for tag in tags):
        raise refused(f"Each tag a word or a few, {TAG_LENGTH} characters at most.", field)
    return sorted(set(tags))


def clean_metadata(payload):
    """The bank's bulk edit (the `item_metadata` action): topic, marks, difficulty, Bloom level, tags to add and to
    take off; at least one. Raises ValidationError field by field."""
    payload = payload if isinstance(payload, dict) else {}
    clean = {}
    if "topic" in payload:
        topic = " ".join(str(payload["topic"] or "").split())
        if len(topic) > 120:
            raise refused("At most 120 characters.", "topic")
        clean["topic"] = topic
    if "marks" in payload:
        marks = payload["marks"]
        if not isinstance(marks, int) or isinstance(marks, bool) or not 1 <= marks <= 10:
            raise refused("A whole number from 1 to 10.", "marks")
        clean["marks"] = marks
    for name, choices in (("difficulty", QuizItem.Difficulty), ("bloom", QuizItem.Bloom)):
        if name in payload:
            value = str(payload[name] or "")
            if value and value not in choices.values:
                raise refused(f"One of {', '.join(choices.values)}, or empty (not set).", name)
            clean[name] = value
    for name in ("tags_add", "tags_remove"):
        if name in payload:
            clean[name] = clean_tags(payload[name], name)
    if not clean:
        raise refused("Say what to change: topic, marks, difficulty, bloom, tags_add or tags_remove.")
    return clean


def set_metadata(item, changes, request=None, actor=None):
    """The bank's metadata of one item changed (a history row, an audit event); returns what changed."""
    with transaction.atomic():
        item = QuizItem.objects.select_for_update().get(pk=item.pk)
        changed = {name: [getattr(item, name), value] for name, value in changes.items()
                   if name in METADATA and getattr(item, name) != value}  # fmt: skip
        for name, (_, value) in changed.items():
            setattr(item, name, value)
        if changed:
            item._change_reason = "the quiz bank"
            item.save(update_fields=list(changed))
        before = sorted(item.tags.names())
        if changes.get("tags_add"):
            item.tags.add(*changes["tags_add"])
        if changes.get("tags_remove"):
            item.tags.remove(*changes["tags_remove"])
        after = sorted(item.tags.names())
        if after != before:
            changed["tags"] = [before, after]
        if changed:
            audit.record("course.item_changed", request=request, actor=actor, target=item, changes=changed)
    return changed


def flag_item(item, note="", request=None):
    """ "Needs checking": a report of category item_analysis in the content triage (content.reports: its inbox item
    for the subject's triage), once while one is open. Returns (the report, made now)."""
    from content import reports
    from content.models import ErrorReport
    from insights.models import ItemStat

    kind = ContentType.objects.get_for_model(QuizItem)
    flags = ErrorReport.objects.filter(
        target_type=kind, target_id=item.pk, category=ErrorReport.Category.ITEM_ANALYSIS, state__in=ErrorReport.OPEN
    )
    if found := flags.first():
        return found, False
    stat = ItemStat.objects.filter(item=item).order_by("-run_date").first()
    lines = [" ".join(str(note or "").split())[:2000] or "Flagged from the quiz bank as needing checking."]
    if stat is not None and stat.p is not None:
        discrimination = f"{stat.discrimination:.2f}" if stat.discrimination is not None else "N/A"
        lines.append(f"Item analysis of {stat.n} learners: {stat.p:.0%} right, discrimination {discrimination}.")
    try:
        with transaction.atomic():
            report = ErrorReport.objects.create(
                target_type=kind,
                target_id=item.pk,
                subject=item.chapter.subject,
                category=ErrorReport.Category.ITEM_ANALYSIS,
                note=" ".join(lines),
            )
            reports.file(report)
            audit.record("course.item_flagged", request=request, target=item, details={"report": report.pk})
    except IntegrityError:  # flagged at the same moment by someone else: one open flag per item
        return flags.get(), False
    return report, True


# ---- Entitlements: granted, extended, revoked (the student's progress stays whatever happens to them) ----

GRANT_DAYS = 366 * 2  # a grant's last day at most two years ahead (or no end)


def is_active(entitlement, today=None):
    today = today or timezone.localdate()
    return entitlement.revoked_at is None and (entitlement.valid_until is None or entitlement.valid_until >= today)


def active_q(today=None):
    today = today or timezone.localdate()
    return Q(revoked_at__isnull=True) & (Q(valid_until__isnull=True) | Q(valid_until__gte=today))


def check_subject_scope(maker, perm, subject):
    """A member of staff narrowed to some subjects (StaffScope) grants those only, never every subject at once."""
    from staff.backends import SUBJECT, scope_values

    values = None if getattr(maker, "is_superuser", False) else scope_values(maker, perm, SUBJECT)
    if values is not None and (subject is None or subject.code not in values):
        raise refused(f"Not one of your subjects ({', '.join(sorted(values))}).", "subject")


def check_grant(account, subject, valid_until, today=None):
    """Why this grant is refused (a ValidationError), else nothing: a closed or staff account, a day gone or too far,
    access already open to the subject (an active entitlement to extend instead)."""
    today = today or timezone.localdate()
    if not account.is_active:
        raise refused("This account is closed: there is nobody to open the course for.", "user")
    if account.is_staff:
        raise refused("A member of staff has every subject open already.", "user")
    if valid_until is not None and valid_until < today:
        raise refused("A day from today on, or none (no end).", "valid_until")
    if valid_until is not None and valid_until > today + timedelta(days=GRANT_DAYS):
        raise refused("Within two years, or none (no end).", "valid_until")
    covering = Entitlement.objects.filter(active_q(today), user=account).filter(
        Q(subject__isnull=True) | Q(subject=subject) if subject else Q(subject__isnull=True)
    )
    if open_one := covering.first():
        until = f"until {open_one.valid_until:%d %b %Y}" if open_one.valid_until else "with no end"
        raise refused(f"It is open already, {until} (entitlement #{open_one.pk}): extend that one instead.", "subject")


def grant(account, subject, valid_until, reason, *, by, reference="", request=None):
    """Access opened by staff, with why (kept on it as its note)."""
    if not str(reason or "").strip():
        raise refused("Say why.", "reason")
    with transaction.atomic():
        get_user_model().objects.select_for_update().filter(pk=account.pk).first()  # one grant per account at a time
        check_grant(account, subject, valid_until)
        entitlement = Entitlement(
            user=account,
            subject=subject,
            source=Entitlement.Source.GRANT,
            reference=str(reference or "")[:40],
            valid_until=valid_until,
            note=str(reason).strip()[:200],
        )
        entitlement._change_reason = "granted in the panel"
        entitlement.save()
        details = {"user": account.pk, "subject": subject.code if subject else "all", "valid_until": valid_until}
        audit.record("course.entitlement_granted", request=request, actor=by, target=entitlement,
                     reason=reason, details=details)  # fmt: skip
    return entitlement


def check_extend(entitlement):
    if entitlement.revoked_at is not None:
        raise refused("It was revoked: grant access again instead.")
    if entitlement.valid_until is None:
        raise refused("It has no end date: nothing to extend.")


def extend(entitlement, days, reason, *, by, request=None):
    """`days` more, from its end (from today if it has ended), with why."""
    if not str(reason or "").strip():
        raise refused("Say why.", "reason")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        raise refused("From 1 to 365 days.", "days")
    with transaction.atomic():
        entitlement = Entitlement.objects.select_for_update().get(pk=entitlement.pk)
        check_extend(entitlement)
        before = entitlement.valid_until
        entitlement.valid_until = max(before, timezone.localdate()) + timedelta(days=days)
        entitlement.note = str(reason).strip()[:200]
        entitlement._change_reason = f"extended by {days} days in the panel"
        entitlement.save(update_fields=["valid_until", "note", "modified"])
        audit.record("course.entitlement_extended", request=request, actor=by, target=entitlement, reason=reason,
                     changes={"valid_until": [before, entitlement.valid_until]}, details={"days": days})  # fmt: skip
    return entitlement


def check_revoke(entitlement, today=None):
    if entitlement.revoked_at is not None:
        raise refused("It was revoked already.")
    if not is_active(entitlement, today):
        raise refused(f"It ended on {entitlement.valid_until:%d %b %Y}: nothing to revoke.")


def revoke(entitlement, reason, *, by, request=None):
    """Access ended now, with why: its last day becomes yesterday (the app reads it as ended); the student's
    progress, answers and cards stay, so access given again picks up where it stopped."""
    if not str(reason or "").strip():
        raise refused("Say why.", "reason")
    with transaction.atomic():
        entitlement = Entitlement.objects.select_for_update().get(pk=entitlement.pk)
        today = timezone.localdate()
        check_revoke(entitlement, today)
        before = entitlement.valid_until
        entitlement.valid_until, entitlement.revoked_at = today - timedelta(days=1), timezone.now()
        entitlement.note = str(reason).strip()[:200]
        entitlement._change_reason = "revoked in the panel"
        entitlement.save(update_fields=["valid_until", "revoked_at", "note", "modified"])
        audit.record("course.entitlement_revoked", request=request, actor=by, target=entitlement, reason=reason,
                     changes={"valid_until": [before, entitlement.valid_until]})  # fmt: skip
    return entitlement
