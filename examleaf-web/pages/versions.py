"""The legal pages' versions (plan 5.15, research-lms-crm-cms.md 2.8): each publish of a page is a numbered version
with the day it is in force from and a line on what changed, and consent rows keep the privacy notice's version they
were given under (accounts.ConsentRecord.notice_version). The versions are read from the page's history: a run of its
history rows with one `version` is one version (its last row's text: a correction within a version changes no
number); a version published for a later day waits in `Page.scheduled` until publish_due (pages.tasks, every night
just after midnight, India's date) puts it in force. The diff of a version is against the one before it."""

import difflib
from dataclasses import dataclass
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers

from .models import Page


@dataclass
class Version:
    number: int
    version: str  # the label consent records keep
    title: str
    body_md: str
    summary: str
    effective_from: date
    published_at: datetime | None
    published_by: int | None
    in_force: bool = False
    upcoming: bool = False


def versions(page):
    """Every version of the page, oldest first: those it has had (its history), then the scheduled one."""
    runs = []
    rows = page.history.order_by("history_date", "history_id").values(
        "version", "title", "body_md", "summary", "effective_from", "history_date", "history_user_id"
    )
    for row in rows.iterator():
        if runs and runs[-1].version == row["version"]:  # a correction within the version: its text, no new number
            last = runs[-1]
            last.title, last.body_md, last.summary = row["title"], row["body_md"], row["summary"]
            last.effective_from = row["effective_from"] or last.effective_from
            continue
        runs.append(
            Version(
                number=len(runs) + 1,
                version=row["version"],
                title=row["title"],
                body_md=row["body_md"],
                summary=row["summary"],
                effective_from=row["effective_from"] or timezone.localdate(row["history_date"]),
                published_at=row["history_date"],
                published_by=row["history_user_id"],
            )
        )
    if not runs:  # a page without history (made outside the migrations): the row is its one version
        runs.append(Version(1, page.version, page.title, page.body_md, page.summary, page.effective_from, None, None))
    runs[-1].in_force = True
    if page.scheduled:
        upcoming = page.scheduled
        runs.append(
            Version(
                number=len(runs) + 1,
                version=upcoming["version"],
                title=upcoming["title"],
                body_md=upcoming["body_md"],
                summary=upcoming["summary"],
                effective_from=parse_date(upcoming["effective_from"]),
                published_at=parse_datetime(upcoming["published_at"]),
                published_by=upcoming.get("published_by"),
                upcoming=True,
            )
        )
    return runs


def in_force_number(page):
    """The number of the version in force (the page's row), as the website shows it: "Version N"."""
    return next(version.number for version in versions(page) if version.in_force)


def find(page, number):
    """One version by its number, or None."""
    return next((version for version in versions(page) if version.number == number), None)


def diff(page, number):
    """A version against the one before it: the unified diff of their Markdown as lines, each with its kind (`hunk`,
    `added`, `removed`, `context`), and whether the title changed. None when there is no such version."""
    all_versions = versions(page)
    if not 1 <= number <= len(all_versions):
        return None
    current = all_versions[number - 1]
    previous = all_versions[number - 2] if number > 1 else None
    before = previous.body_md.splitlines() if previous else []
    lines = []
    for line in difflib.unified_diff(before, current.body_md.splitlines(), lineterm="", n=2):
        if line.startswith(("---", "+++")):
            continue
        kind = {"@": "hunk", "+": "added", "-": "removed"}.get(line[:1], "context")
        lines.append({"kind": kind, "text": line[1:] if kind != "hunk" else line})
    return {
        "number": current.number,
        "version": current.version,
        "previous": previous.number if previous else None,
        "effective_from": current.effective_from,
        "summary": current.summary,
        "title": current.title,
        "title_changed": bool(previous and previous.title != current.title),
        "added": sum(line["kind"] == "added" for line in lines),
        "removed": sum(line["kind"] == "removed" for line in lines),
        "lines": lines,
    }


def next_label(page):
    """The label of the next version: its number, made unique against the labels the page has had."""
    known = versions(page)
    labels, number = {version.version for version in known}, len(known) + 1
    while str(number) in labels:
        number += 1
    return str(number)


def publish(page, *, markdown, title, summary, effective_from, by, request=None):
    """A new version of the page: in force today (at once), or from a later day (kept as `scheduled`, replacing one
    scheduled before). Refused (ValidationError) for a day before today or a text and title the same as the version
    in force. Audited: `policy.published` or `policy.scheduled`. Returns the page."""
    from staff import audit  # (staff imports this app's models)

    today = timezone.localdate()
    if effective_from < today:
        raise serializers.ValidationError({"effective_from": ["Today or a later day: a version is never backdated."]})
    title = (title or page.title).strip()
    if markdown.strip() == page.body_md.strip() and title == page.title:
        raise serializers.ValidationError({"markdown": ["This is the text in force: nothing to publish."]})
    with transaction.atomic():
        page = Page.objects.select_for_update().get(pk=page.pk)
        replaced = page.scheduled["version"] if page.scheduled else None
        label = replaced or next_label(page)  # a replacement of the scheduled version takes its number
        if effective_from == today:
            page.title, page.body_md, page.version, page.summary = title, markdown, label, summary
            page.effective_from, page.scheduled = today, None
            page._change_reason = f"version {label} published"
            page.save()
            action = "policy.published"
        else:
            page.scheduled = {
                "version": label,
                "title": title,
                "body_md": markdown,
                "summary": summary,
                "effective_from": effective_from.isoformat(),
                "published_at": timezone.now().isoformat(),
                "published_by": getattr(by, "pk", None),
            }
            Page.objects.filter(pk=page.pk).update(scheduled=page.scheduled)  # no history row: not a version yet
            action = "policy.scheduled"
        audit.record(
            action,
            request=request,
            actor=by,
            target=("pages.page", page.pk, page.slug),
            details={"version": label, "effective_from": effective_from, "replaced": replaced},
        )
    return page


def cancel_scheduled(page, *, by, reason, request=None):
    """The version waiting for its day withdrawn before it: ValidationError when none waits."""
    from staff import audit

    with transaction.atomic():
        page = Page.objects.select_for_update().get(pk=page.pk)
        if not page.scheduled:
            raise serializers.ValidationError({"non_field_errors": ["No version waits for its day."]})
        label = page.scheduled["version"]
        page.scheduled = None
        Page.objects.filter(pk=page.pk).update(scheduled=None)
        audit.record(
            "policy.schedule_cancelled",
            request=request,
            actor=by,
            target=("pages.page", page.pk, page.slug),
            reason=reason,
            details={"version": label},
        )
    return page


def publish_due(today=None):
    """Every version whose day has come put in force (the nightly task; a second run finds none waiting). Returns
    the slugs made new."""
    from staff import audit

    today = today or timezone.localdate()
    done = []
    for pk in Page.objects.filter(scheduled__isnull=False).values_list("pk", flat=True):
        with transaction.atomic():
            page = Page.objects.select_for_update().get(pk=pk)
            upcoming = page.scheduled
            if not upcoming or parse_date(upcoming["effective_from"]) > today:
                continue
            page.title, page.body_md, page.version = upcoming["title"], upcoming["body_md"], upcoming["version"]
            page.summary, page.effective_from = upcoming["summary"], parse_date(upcoming["effective_from"])
            page.scheduled = None
            page._change_reason = f"version {page.version} in force"
            page.save()
            audit.record(
                "policy.in_force",
                actor_type=audit.ActorType.SYSTEM,
                target=("pages.page", page.pk, page.slug),
                details={"version": page.version, "effective_from": page.effective_from},
            )
            done.append(page.slug)
    return done
