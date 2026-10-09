"""The course's actions for staff.approvals (registered in its ACTIONS, so a bulk action names them: POST jobs/
{"kind": "bulk_action", "params": {"action": …, "targets": […], "payload": {…}, "reason": …}, "dry_run": true}),
each row run through approvals.ask as a single request would be: its permission, its scope, an idempotency key per
job and row, the job itself above the starter's `bulk_rows` approved first. Their own rule never waits: a row within
the job runs at once. The rules are learn.course's.

Imported by staff/approvals.py only (at its end, where Action is defined): import it from nowhere else."""

from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import serializers

from content.models import Subject
from staff.approvals import Action, Refused
from staff.backends import scoped

from . import course
from .models import Entitlement, QuizItem


def _entitlement(maker, target, perm):
    pk = str(target).strip()
    found = scoped(Entitlement.objects.all(), maker, perm).filter(pk=pk).first() if pk.isdigit() else None
    if found is None:
        raise serializers.ValidationError({"target": ["No such entitlement (or not one you may change)."]})
    return found


def subject_of(value):
    """A subject by its code (PHY), "ALL" or empty for every subject."""
    code = str(value or "").strip().upper()
    if code in ("", "ALL"):
        return None
    subject = Subject.objects.filter(code=code).order_by("pk").first()
    if subject is None:
        raise serializers.ValidationError({"subject": [f"No subject {code}: PHY, CHE, MAT, BIO or ALL."]})
    return subject


def day_of(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise serializers.ValidationError({"valid_until": ["A day: YYYY-MM-DD, or null (no end)."]}) from None


class Course(Action):
    """A course action: never waits on its own (the job does, above `bulk_rows`); ADMIN approves large ones."""

    checker = "staff.approve_export"

    def rule(self, maker, change_request):
        return None


class GrantEntitlement(Course):
    name, label, maker = "entitlement.grant", "Open the course for an account", "learn.add_entitlement"

    def account(self, change_request):
        return int(change_request.target_id)

    def validate(self, maker, target, payload):
        pk = str(target).strip()
        account = get_user_model().objects.filter(pk=pk).first() if pk.isdigit() else None
        if account is None:
            raise serializers.ValidationError({"target": ["No such account."]})
        subject, until = subject_of(payload.get("subject")), day_of(payload.get("valid_until"))
        course.check_subject_scope(maker, self.maker, subject)
        course.check_grant(account, subject, until)
        clean = {
            "user": account.pk,
            "subject": subject.code if subject else "ALL",
            "valid_until": until.isoformat() if until else None,
            "reference": str(payload.get("reference") or "")[:40],
        }
        return ("accounts.user", account.pk, f"Account #{account.pk}"), clean, None

    def run(self, change_request, by):
        payload = change_request.payload
        account = get_user_model().objects.filter(pk=payload["user"]).first()
        if account is None:
            raise Refused("The account is gone.")
        try:
            entitlement = course.grant(
                account, subject_of(payload["subject"]), day_of(payload["valid_until"]), change_request.reason,
                by=change_request.maker, reference=payload["reference"],
            )  # fmt: skip
        except serializers.ValidationError as error:
            raise Refused(next(iter(error.detail.values()))[0]) from error
        return {"entitlement": entitlement.pk}


class ExtendEntitlement(Course):
    name, label, maker = "entitlement.extend", "Extend course access", "learn.change_entitlement"

    def account(self, change_request):
        return change_request.payload.get("user")

    def validate(self, maker, target, payload):
        entitlement = _entitlement(maker, target, self.maker)
        days = payload.get("days")
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
            raise serializers.ValidationError({"days": ["From 1 to 365 days."]})
        course.check_extend(entitlement)
        return entitlement, {"entitlement": entitlement.pk, "user": entitlement.user_id, "days": days}, None

    def run(self, change_request, by):
        entitlement = Entitlement.objects.filter(pk=change_request.payload["entitlement"]).first()
        if entitlement is None:
            raise Refused("The entitlement is gone.")
        try:
            done = course.extend(entitlement, change_request.payload["days"], change_request.reason,
                                 by=change_request.maker)  # fmt: skip
        except serializers.ValidationError as error:
            raise Refused(next(iter(error.detail.values()))[0]) from error
        return {"entitlement": done.pk, "valid_until": done.valid_until.isoformat()}


class RevokeEntitlement(Course):
    name, label, maker = "entitlement.revoke", "Revoke course access", "learn.change_entitlement"

    def account(self, change_request):
        return change_request.payload.get("user")

    def validate(self, maker, target, payload):
        entitlement = _entitlement(maker, target, self.maker)
        course.check_revoke(entitlement)
        return entitlement, {"entitlement": entitlement.pk, "user": entitlement.user_id}, None

    def run(self, change_request, by):
        entitlement = Entitlement.objects.filter(pk=change_request.payload["entitlement"]).first()
        if entitlement is None:
            raise Refused("The entitlement is gone.")
        try:
            done = course.revoke(entitlement, change_request.reason, by=change_request.maker)
        except serializers.ValidationError as error:
            raise Refused(next(iter(error.detail.values()))[0]) from error
        return {"entitlement": done.pk}


class ItemMetadata(Course):
    """The quiz bank's bulk edit: each item's topic, marks, difficulty, Bloom level and tags."""

    name, label, maker = "item_metadata", "Change quiz items' metadata", "learn.change_quizitem"

    def validate(self, maker, target, payload):
        pk = str(target).strip()
        items = scoped(QuizItem.objects.all(), maker, self.maker)
        item = items.filter(pk=pk).first() if pk.isdigit() else None
        if item is None:
            raise serializers.ValidationError({"target": ["No such quiz item (or not one of your subjects')."]})
        return item, {"item": item.pk, **course.clean_metadata(payload)}, None

    def run(self, change_request, by):
        payload = dict(change_request.payload)
        item = QuizItem.objects.filter(pk=payload.pop("item")).first()
        if item is None:
            raise Refused("The quiz item is gone (or in the bin).")
        changed = course.set_metadata(item, payload, actor=change_request.maker)
        return {"item": item.pk, "changed": sorted(changed)}


COURSE_ACTIONS = [GrantEntitlement(), ExtendEntitlement(), RevokeEntitlement(), ItemMetadata()]
