"""Drafts and their review (plan 5.10: author → checker → publish). An edit of a question or a solution in the panel
writes its draft (the changed fields, `draft`), never the live text the site shows: the record is then "changed since
publish". The editor submits it; a second person (REVIEWER, staff.publish_paper, within their subjects) approves or
asks for changes, and publishes: the draft becomes the live text, the text it replaced kept on the review for a
rollback (and in the history). The checker is never the draft's last editor, nor who submitted it (403 `own_edit`);
an edit after a submission cancels the review, so what was approved is what goes live. Each step is an audit event
(content.*) and the inbox follows: a review waits for the reviewers of its subject; changes asked for wait for the
editor who submitted. Books and papers have no draft: their edits apply at once (the paper's publishing needs
staff.publish_paper), and a version from their history is restored as it was."""

import difflib
import json

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions, serializers

from staff import audit
from staff.models import InboxItem
from staff.signals import close_items, open_item

from . import latex
from .models import Book, Paper, Question, ReviewTask

State = Question.State
TEXTS = ("body_md", "text_md", "table_md", "marks_text", "group_label", "part_label")  # checked by content.latex
# what a version of a book or a paper restores (a paper's code is in its printed QR code, and publishing it is
# staff.publish_paper's: neither comes back with a version)
LINE_OPS = ["equal", "delete", "insert"]  # a diff line: the same in both, gone, new
VERSION_TYPES = [("+", "made"), ("~", "changed"), ("-", "deleted")]  # simple-history's history_type
RESTORED = {
    Book: ["title", "subject", "edition", "slug", "cover", "isbn", "format", "published_on"],
    Paper: ["title", "tier", "number", "full_marks", "pass_marks", "time_text", "header_json"],
}


class OwnEdit(exceptions.PermissionDenied):
    default_detail = "You edited or submitted this draft: another reviewer checks and publishes it."
    default_code = "own_edit"


def refused(message):
    return serializers.ValidationError({"non_field_errors": [message]})


def paper_of(obj):
    return obj.paper if isinstance(obj, Question) else obj.question.paper


def label_of(obj):
    """The record by its codes, never a person: "PHY-E01 2(c), solution"."""
    question = obj if isinstance(obj, Question) else obj.question
    kind = "question" if isinstance(obj, Question) else "solution"
    return f"{question.paper.code} {question.label}, {kind}"


def target(obj):
    """The audit log's target: the record by its codes."""
    return obj._meta.label_lower, obj.pk, label_of(obj)


def subject_code(obj):
    return paper_of(obj).book.subject.code


def locked(obj):
    """The record again, locked to the end of the transaction (two people saving one draft wait for each other)."""
    return type(obj).objects.select_for_update().select_related(*related(obj)).get(pk=obj.pk)


def related(obj):
    return ["paper__book__subject"] if isinstance(obj, Question) else ["question__paper__book__subject"]


def check_texts(changes):
    """The drafted texts through the structural check (content.latex): 400 with each field's problems."""
    found = {}
    for field, value in changes.items():
        texts = value if field == "options_json" else [value] if field in TEXTS else []
        problems = [problem for text in texts if isinstance(text, str) for problem in latex.problems(text)]
        if problems:
            found[field] = problems
    if found:
        raise serializers.ValidationError(found)


def open_tasks(obj):
    kind = ContentType.objects.get_for_model(obj)
    return ReviewTask.objects.filter(ReviewTask.OPEN, target_type=kind, target_id=obj.pk)


def cancel_open(obj, user, why):
    for task in open_tasks(obj).select_for_update():
        task.state = ReviewTask.State.CANCELLED
        task.comments = [*task.comments, comment(user, why)]
        task.save(update_fields=["state", "comments", "modified"])
        close_items(task, InboxItem.Kind.REVIEW)


def comment(user, text, field=""):
    return {"author": getattr(user, "pk", None), "text": text, "at": timezone.now().isoformat(), "field": field}


def changed_fields(obj, values):
    return {field: value for field, value in values.items() if getattr(obj, field) != value}


def version_of(obj):
    return obj.history.order_by("-history_id").values_list("history_id", flat=True).first()


@transaction.atomic
def save_draft(obj, changes, user, request=None, action="content.draft_saved", details=None):
    """`changes` ({field: value}, fields of obj.DRAFTED) into the draft; a field back at its live value leaves the
    draft. A changed draft cancels the review it waited in. Answers the record."""
    obj = locked(obj)
    check_texts(changes)
    draft = {**obj.draft, **changes}
    draft = {field: value for field, value in draft.items() if getattr(obj, field) != value}
    if draft == obj.draft:
        return obj
    if obj.state == State.IN_REVIEW:
        cancel_open(obj, user, "The draft changed after it was submitted: submit it again.")
    obj.draft = draft
    obj.state = State.DRAFT if draft else State.PUBLISHED
    obj.draft_by = user if draft else None
    obj._change_reason = "draft saved" if draft else "draft cleared"
    obj.save(update_fields=["draft", "state", "draft_by"])
    audit.record(
        action,
        request=request,
        target=target(obj),
        details={"fields": sorted(set(changes) | set(draft)), "version": version_of(obj), **(details or {})},
    )
    return obj


@transaction.atomic
def discard_draft(obj, user, request=None):
    obj = locked(obj)
    if not obj.draft:
        raise refused("There is no draft: the live text is the latest.")
    cancel_open(obj, user, "The draft was discarded.")
    obj.draft, obj.state, obj.draft_by = {}, State.PUBLISHED, None
    obj._change_reason = "draft discarded"
    obj.save(update_fields=["draft", "state", "draft_by"])
    audit.record("content.draft_discarded", request=request, target=target(obj))
    return obj


@transaction.atomic
def submit(obj, user, request=None, assignee=None):
    """The draft to a second person: a review task, the record in review, an inbox item for the subject's
    reviewers (or the one named)."""
    obj = locked(obj)
    if obj.state == State.IN_REVIEW:
        raise refused("It waits for review already.")
    if not obj.draft:
        raise refused("Nothing to submit: there is no change since the last publish.")
    check_texts(obj.draft)
    if assignee is not None and (assignee.pk == user.pk or not assignee.has_perm("staff.publish_paper", obj)):
        raise serializers.ValidationError({"assignee": ["A reviewer of this subject other than yourself."]})
    paper = paper_of(obj)
    kind = ContentType.objects.get_for_model(obj)
    earlier = ReviewTask.objects.filter(target_type=kind, target_id=obj.pk).values_list("pk", flat=True)
    InboxItem.objects.filter(
        target_type="content.reviewtask", target_id__in=[str(pk) for pk in earlier], done_at=None
    ).update(done_at=timezone.now())  # changes asked for earlier: answered by this submission
    task = ReviewTask.objects.create(
        target_type=kind,
        target_id=obj.pk,
        subject=paper.book.subject,
        paper=paper,
        label=label_of(obj),
        draft=obj.draft,
        submitted_by=user,
        edited_by=obj.draft_by,
        assignee=assignee,
    )
    obj.state = State.IN_REVIEW
    obj._change_reason = "submitted for review"
    obj.save(update_fields=["state"])
    open_item(InboxItem.Kind.REVIEW, task, f"Review: {task.label}", "staff.publish_paper", subject=subject_code(obj))
    if assignee is not None:
        InboxItem.objects.filter(target_type="content.reviewtask", target_id=str(task.pk), done_at=None).update(
            assignee=assignee
        )
    audit.record("content.submitted", request=request, target=target(obj), details={"review": task.pk})
    return task


def check_not_own(task, user):
    if user.pk in (task.submitted_by_id, task.edited_by_id):
        raise OwnEdit()


def locked_task(task):
    return ReviewTask.objects.select_for_update().get(pk=task.pk)


def target_of(task):
    """The reviewed record, locked; refused when it is gone (deleted in the admin)."""
    obj = task.target
    if obj is None:
        raise refused("Its question or solution is gone.")
    return locked(obj)


@transaction.atomic
def approve(task, user, request=None, text=""):
    task = locked_task(task)
    check_not_own(task, user)
    if task.state != ReviewTask.State.IN_PROGRESS:
        raise refused(f"It is {task.get_state_display()}: only a review in progress is approved.")
    task.state, task.stage = ReviewTask.State.APPROVED, ReviewTask.Stage.PUBLISH
    task.approved_by, task.approved_at = user, timezone.now()
    if text:
        task.comments = [*task.comments, comment(user, text)]
    task.save()
    InboxItem.objects.filter(target_type="content.reviewtask", target_id=str(task.pk), done_at=None).update(
        title=f"Publish: {task.label}"[:200]
    )
    audit.record("content.review_approved", request=request, target=task, details={"label": task.label})
    return task


@transaction.atomic
def needs_changes(task, user, text, request=None, field=""):
    """Back to the editor with what to change: the draft stays, out of review; the submitter's inbox has it."""
    task = locked_task(task)
    check_not_own(task, user)
    if not task.is_open:
        raise refused(f"It is {task.get_state_display()}: nothing to send back.")
    obj = target_of(task)
    task.state, task.stage = ReviewTask.State.NEEDS_CHANGES, ReviewTask.Stage.CHECK
    task.comments = [*task.comments, comment(user, text, field)]
    task.save()
    if obj.state == State.IN_REVIEW:
        obj.state = State.DRAFT
        obj._change_reason = "changes asked for"
        obj.save(update_fields=["state"])
    close_items(task, InboxItem.Kind.REVIEW)
    if task.submitted_by_id:
        InboxItem.objects.create(
            kind=InboxItem.Kind.REVIEW,
            title=f"Changes asked: {task.label}"[:200],
            target_type="content.reviewtask",
            target_id=str(task.pk),
            permission=f"content.change_{obj._meta.model_name}",
            assignee_id=task.submitted_by_id,
            data={"subject": subject_code(obj)},
        )
    audit.record("content.review_needs_changes", request=request, target=task, details={"field": field})
    return task


@transaction.atomic
def publish(task, user, request=None, text=""):
    """The reviewed draft becomes the live text (approved on the way, if it was not yet); the text it replaced stays
    on the review (`previous`) for a rollback, and in the history."""
    task = locked_task(task)
    check_not_own(task, user)
    if not task.is_open:
        raise refused(f"It is {task.get_state_display()}{' and published' if task.published_at else ''}.")
    obj = target_of(task)
    if obj.draft != task.draft:
        raise refused("The draft changed after it was submitted: it needs a new review.")
    now = timezone.now()
    task.previous = {field: getattr(obj, field) for field in task.draft}
    for field, value in task.draft.items():
        setattr(obj, field, value)
    obj.draft, obj.state, obj.draft_by = {}, State.PUBLISHED, None
    obj.published_at, obj.published_by = now, user
    obj._change_reason = f"published (review #{task.pk})"
    obj.save()
    if task.state == ReviewTask.State.IN_PROGRESS:
        task.approved_by, task.approved_at = user, now
    task.state, task.stage = ReviewTask.State.APPROVED, ReviewTask.Stage.PUBLISH
    task.published_by, task.published_at = user, now
    if text:
        task.comments = [*task.comments, comment(user, text)]
    task.save()
    close_items(task, InboxItem.Kind.REVIEW)
    audit.record(
        "content.published",
        request=request,
        target=target(obj),
        details={"review": task.pk, "fields": sorted(task.draft), "version": version_of(obj)},
    )
    return task


def last_publish(obj):
    kind = ContentType.objects.get_for_model(obj)
    return (
        ReviewTask.objects.select_for_update()
        .filter(target_type=kind, target_id=obj.pk, published_at__isnull=False, rolled_back_at=None)
        .order_by("-published_at", "-pk")
        .first()
    )


@transaction.atomic
def rollback(obj, user, request=None):
    """The last publish undone: the live text before it back, the text it published back in the draft (unless a
    newer draft is being written). Refused when the live text changed since that publish (an import, a later one)."""
    obj = locked(obj)
    task = last_publish(obj)
    if task is None:
        raise refused("Nothing to roll back: no publish from the panel is live.")
    if any(getattr(obj, field) != value for field, value in task.draft.items()):
        raise refused("The live text changed since that publish: restore a version from the history instead.")
    for field, value in task.previous.items():
        setattr(obj, field, value)
    if not obj.draft:
        obj.draft = changed_fields(obj, task.draft)
        obj.draft_by = task.edited_by
    obj.state = State.DRAFT if obj.draft else State.PUBLISHED
    obj._change_reason = f"rolled back (review #{task.pk})"
    obj.save()
    task.rolled_back_by, task.rolled_back_at = user, timezone.now()
    task.save(update_fields=["rolled_back_by", "rolled_back_at", "modified"])
    audit.record(
        "content.rolled_back",
        request=request,
        target=target(obj),
        details={"review": task.pk, "fields": sorted(task.previous), "version": version_of(obj)},
    )
    return obj


@transaction.atomic
def restore(obj, history_id, user, request=None):
    """A version from the history: a question's or a solution's text into the draft (to be reviewed); a book's or a
    paper's fields at once (RESTORED)."""
    version = obj.history.filter(history_id=history_id).first()
    if version is None:
        raise exceptions.NotFound("No such version of this record.")
    details = {"restored": history_id}
    if hasattr(obj, "DRAFTED"):
        values = {field: getattr(version, field) for field in obj.DRAFTED}
        before = locked(obj)
        after = save_draft(before, values, user, request, "content.version_restored", details)
        if after.draft == before.draft:
            raise refused("That version is the text as it is now.")
        return after
    obj = type(obj).objects.select_for_update().get(pk=obj.pk)
    changes = {}
    for field in RESTORED[type(obj)]:
        name = obj._meta.get_field(field).attname  # subject_id for the subject
        if getattr(obj, name) != getattr(version, name):
            changes[field] = [getattr(obj, name), getattr(version, name)]
            setattr(obj, name, getattr(version, name))
    if not changes:
        raise refused("That version is the record as it is now.")
    try:
        obj.full_clean()
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.message_dict) from error
    obj._change_reason = f"restored version {history_id}"
    obj.save()
    audit.record("content.version_restored", request=request, target=obj, changes=changes, details=details)
    return obj


# ---- What the panel reads: the diff of a draft or a version, line by line ----


def as_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return json.dumps(value, ensure_ascii=False) if value is not None else ""


def diff_lines(before, after):
    """[{op: equal|delete|insert, text}] of two values, line by line (difflib)."""
    old, new = as_text(before).split("\n"), as_text(after).split("\n")
    lines = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op == "equal":
            lines += [{"op": "equal", "text": text} for text in old[i1:i2]]
            continue
        lines += [{"op": "delete", "text": text} for text in old[i1:i2]]
        lines += [{"op": "insert", "text": text} for text in new[j1:j2]]
    return lines


def change(field, before, after):
    before, after = audit.plain(before), audit.plain(after)  # times and decimals as text, as JSON has them
    return {"field": field, "before": before, "after": after, "lines": diff_lines(before, after)}


def draft_changes(obj, draft):
    """The draft against the live text, field by field."""
    return [change(field, getattr(obj, field), value) for field, value in draft.items()]


def version_changes(new, old):
    """What a version changed from the one before it (simple-history's diff_against); a draft's fields one by one."""
    if old is None:
        return []
    found = []
    for item in new.diff_against(old).changes:
        if item.field == "draft":
            before, after = item.old or {}, item.new or {}
            for key in sorted(set(before) | set(after)):
                if before.get(key) != after.get(key):
                    found.append(change(f"draft.{key}", before.get(key, ""), after.get(key, "")))
        else:
            found.append(change(item.field, item.old, item.new))
    return found
