"""The staff app's tasks (celery beat, settings.CELERY_BEAT_SCHEDULE): the audit chain verified nightly and copied off
the server daily, expired roles, scopes and change requests taken away (and old job files deleted), failed refunds
filed in the inbox; and on demand, a background job from the panel (staff.jobs) and an access request's data emailed
to the account's own address."""

import json
import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime as parse_iso

from examleaf.celery import LONG_TASK, single_run

from . import approvals, audit
from .models import AuditEvent, InboxItem, RoleGrant, StaffScope

logger = logging.getLogger(__name__)


@shared_task(**LONG_TASK)  # the whole log read, or a week of it
@single_run(LONG_TASK["time_limit"])
def verify_audit_chain():
    """Nightly: recompute both chains; a break alerts the owners and files an inbox item (research 3.3)."""
    problems = audit.verify()
    action = "audit.chain_broken" if problems else "audit.verified"
    details = {"problems": problems[:20], "count": len(problems), "heads": audit.heads()}
    with transaction.atomic():
        audit.record(
            action,
            actor_type=audit.ActorType.SYSTEM,
            outcome=audit.Outcome.FAILED if problems else audit.Outcome.SUCCESS,
            details=details,
        )
        if problems:
            day = timezone.localdate().isoformat()
            InboxItem.objects.get_or_create(
                kind=InboxItem.Kind.INCIDENT,
                target_type="audit.chain",
                target_id=day,
                done_at=None,
                defaults={
                    "title": "The audit log's chain is broken",
                    "permission": "staff.view_auditlog",
                    "data": {"problems": problems[:20]},
                },
            )
            audit.alert("The audit log's chain is broken", "\n".join(problems[:20]))
    return len(problems)


@shared_task(**LONG_TASK)  # the whole log read, or a week of it
@single_run(LONG_TASK["time_limit"])
def export_audit_log(days=7):
    """Daily: each of the last `days` UTC days not yet in the backups' bucket, as JSON lines with the chains' heads
    (audit.export_day). A failure alerts the owners."""
    today = datetime.now(UTC).date()
    written = []
    try:
        for back in range(days, 0, -1):
            if name := audit.export_day(today - timedelta(days=back)):
                written.append(name)
    except Exception as error:
        logger.exception("The audit log's export failed")
        audit.alert("The audit log's export failed", f"{type(error).__name__}: {error}")
        raise
    return written


@shared_task
def expire_access():
    """Nightly: roles given until a time (just-in-time elevation), and scopes, past it are taken away (audited: the
    role change's event, by the system), each person's ended roles noted in the owners' inbox; so are change requests
    whose time is over."""
    from .services import revoke_role

    now = timezone.now()
    grants = list(RoleGrant.objects.filter(expires_at__lte=now).select_related("user"))
    ended = {}
    for grant in grants:
        revoke_role(grant.user, grant.role, by=None, reason="Its time was over.")
        ended.setdefault(grant.user, []).append(grant.role)
    for user, names in ended.items():  # a note per person ("staff.person": the console opens their page)
        title = f"Temporary role ended: {', '.join(sorted(names))} of user #{user.pk}"
        InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.ROLE_EXPIRED,
            target_type="staff.person",
            target_id=str(user.pk),
            done_at=None,
            defaults={"title": title[:200], "permission": "staff.assign_role", "data": {"roles": sorted(names)}},
        )
    scopes = list(StaffScope.objects.filter(expires_at__lte=now).select_related("user"))
    for scope in scopes:
        with transaction.atomic():
            details = {"scope": {"kind": scope.kind, "value": scope.value}, "added": False, "expired": True}
            scope.delete()
            audit.record("authz_change", actor_type=audit.ActorType.SYSTEM, target=scope.user, details=details)
    from .jobs import delete_old_files

    return {
        "roles": len(grants),
        "scopes": len(scopes),
        "change_requests": approvals.expire_due(),
        "job_files": delete_old_files(),
    }


@shared_task(**LONG_TASK)  # past the soft limit the job ends failed, with the reason, not running forever
def run_job(job_id):
    """A job started from the panel (staff.jobs.run): its rows, its progress, its file."""
    from .jobs import run

    return run(job_id)


@shared_task
def expire_change_requests():
    """Hourly: the change requests whose time is over expire (an approval works once, and not forever)."""
    return approvals.expire_due()


@shared_task
def watch():
    """Hourly: refunds Razorpay refused in the last 30 days get an inbox item each (shop.services.refund_failed writes
    them without a signal)."""
    from shop.models import Refund

    since = timezone.now() - timedelta(days=30)
    filed = 0
    for refund in Refund.objects.filter(status=Refund.Status.FAILED, modified__gte=since).select_related("order"):
        _, created = InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.FAILED_JOB,
            target_type="shop.refund",
            target_id=str(refund.pk),
            defaults={
                "title": f"Refund #{refund.pk} of {refund.order.number} failed",
                "permission": "staff.refund_order",
                "data": {"error": refund.error[:200]},
            },
        )
        filed += created
    waiting = InboxItem.objects.filter(target_type="shop.refund", done_at=None)
    ids = [int(pk) for pk in waiting.values_list("target_id", flat=True)]
    processed = Refund.objects.filter(pk__in=ids, status=Refund.Status.PROCESSED).values_list("pk", flat=True)
    waiting.filter(target_id__in=[str(pk) for pk in processed]).update(done_at=timezone.now())  # refunded since
    return filed


@shared_task(acks_late=False)  # run again after a lost worker, it would email the data a second time
def email_data_export(data_request_id):
    """An access request's answer (research 4.2, s.11): everything kept about the account, as Download my data's JSON
    file, attached to an email to the account's own address only, with who processes it for ExamLeaf (the processor
    register). Staff never see the file."""
    from accounts.views import export_user_data

    from .models import DataRequest, ProcessorRecord

    data_request = DataRequest.objects.select_related("user").get(pk=data_request_id)
    user = data_request.user
    data = json.dumps(export_user_data(user), cls=DjangoJSONEncoder, indent=2)
    processors = "\n".join(
        f"- {row.name}: {row.purpose} ({row.data_categories}; {row.country})"
        for row in ProcessorRecord.objects.filter(active=True)
    )
    message = EmailMessage(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Your data, as you asked (DR-{data_request.pk})",
        f"Attached is everything ExamLeaf keeps about your account, as you asked on "
        f"{timezone.localtime(data_request.received_at):%d %B %Y}.\n\n"
        f"Who processes it for us:\n{processors or '- nobody else'}\n\nQuestions about it: "
        f"{settings.DATA_PROTECTION_OFFICER}",
        to=[user.email],
    )
    message.attach(f"examleaf-data-{timezone.localdate():%Y%m%d}.json", data, "application/json")
    message.send()


# Phase B: the system's watches (staff/system_api.py) and the audit log's weekly skim

SKIM_ACTIONS = {"authz_fail", "authn_login_lock", "authn_login_fail", "audit.chain_broken", "scripts.changed"}
SKIM_PREFIXES = ("break_glass.", "user.impersonation", "user.offboarded", "connection.")


def _watch_item(kind, target_id, *, open_it, title, data=None, alert=None):
    """An inbox item without a record behind it (the bucket, the report): opened once while `open_it` holds (the owners
    alerted then, if `alert`), done once it no longer does. Returns whether one was opened now."""
    items = InboxItem.objects.filter(kind=kind, target_type="system", target_id=target_id, done_at=None)
    if not open_it:
        items.update(done_at=timezone.now())
        return False
    with transaction.atomic():
        _, created = InboxItem.objects.get_or_create(
            kind=kind,
            target_type="system",
            target_id=target_id,
            done_at=None,
            defaults={"title": title[:200], "permission": "staff.view_system", "data": data or {}},
        )
        if created and alert:
            audit.alert(title, alert)
    return created


@shared_task
@single_run(300)
def check_backups():
    """Hourly: the backups bucket read again (system_api.backup_summary); no recent backup in a source that has them
    (BACKUP_STALE_HOURS), or a bucket that cannot be read, opens an inbox item and alerts the owners once; a recent one
    closes it (research 3.6: no backup for more than 26 hours)."""
    from .system_api import backup_summary

    summary = backup_summary(refresh=True)
    if not summary["configured"]:
        return None
    hours = settings.BACKUP_STALE_HOURS
    title = "The backups bucket cannot be read" if summary["unreadable"] else f"No backup for {hours} hours"
    stale = [row["key"] for row in summary["sources"] if row["stale"]]
    opened = _watch_item(
        InboxItem.Kind.BACKUP_STALE,
        "backups",
        open_it=summary["stale"],
        title=title,
        data={"sources": stale},
        alert='See the console\'s System page, Backups: which source stopped and since when (RUNBOOK.md "Backups").',
    )
    return {"stale": summary["stale"], "opened": opened}


@shared_task(**LONG_TASK)  # every script of two pages fetched, each within its own timeout
@single_run(LONG_TASK["time_limit"])
def check_scripts():
    """Daily: the checkout's and the console's sign-in page's scripts inventoried and compared with the day before
    (system_api.check_scripts: a change opens an inbox item for ADMIN and alerts the owners, once)."""
    from .system_api import check_scripts as inventory

    return {
        str(page): {"ok": run["ok"], "added": run["added"], "removed": run["removed"]}
        for page, run in inventory().items()
    }


@shared_task
@single_run(300)
def check_dependency_report():
    """Weekly (Mondays): an inbox item while CI's dependency report is older than 8 days or missing (system_api
    .dependency_report), closed once a fresh one is loaded."""
    from .system_api import dependency_report

    report = dependency_report()
    if report["available"]:
        title = f"The dependency report is {report['age_days']} days old: load the latest CI run's"
    else:
        title = "No dependency report is loaded (manage.py load_dependency_report)"
    _watch_item(InboxItem.Kind.DEPENDENCIES_STALE, "dependencies", open_it=report["stale"], title=title)
    return {"stale": report["stale"]}


@shared_task(**LONG_TASK)  # a week of the audit log, grouped
@single_run(LONG_TASK["time_limit"])
def weekly_audit_skim(now=None):
    """Mondays at 08:30 (India): the owners' email of the last 7 days' high-risk events, counted by action (research
    3.5, AU-6): every event of a high or critical permission, the refusals, lock-outs, break-glass sessions,
    impersonations, offboardings and the connections' changes. Counts only, never a person. Once a week: a second run
    in the same week sends nothing (an `audit.skim_sent` event marks it)."""
    from django.db.models import Count

    from ops.tasks import queue_text_email

    from . import catalogue

    now = parse_iso(now) if isinstance(now, str) else now or timezone.now()
    year, week, _ = timezone.localdate(now).isocalendar()
    key = f"{year}-W{week:02d}"
    if AuditEvent.objects.filter(action="audit.skim_sent", details__week=key).exists():
        return None
    start = now - timedelta(days=7)
    counts = {}
    events = AuditEvent.objects.filter(ts__gte=start, ts__lt=now).values_list("action", "permission")
    for action, permission, n in events.annotate(n=Count("pk")).order_by():
        entry = catalogue.entry(permission) if permission else None
        if (entry and entry.reauth) or action in SKIM_ACTIONS or action.startswith(SKIM_PREFIXES):
            counts[action] = counts.get(action, 0) + n
    rows = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    span = f"{timezone.localtime(start):%d %b} to {timezone.localtime(now):%d %b %Y}"
    lines = "\n".join(f"- {action}: {n}" for action, n in rows) or "- No high-risk event this week."
    body = (
        f"The audit log's high-risk events, {span}, by action:\n\n{lines}\n\nRead them in the console's audit trail "
        "(each read is itself logged); refusals: authz_fail; break-glass sessions: break_glass=true."
    )
    for address in audit.owners_emails():
        queue_text_email(address, f"The week's high-risk events ({span})", body)
    with transaction.atomic():
        details = {"week": key, "events": sum(counts.values()), "actions": len(counts)}
        audit.record("audit.skim_sent", actor_type=audit.ActorType.SYSTEM, details=details)
    return counts
