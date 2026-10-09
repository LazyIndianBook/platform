"""The staff app's tasks (celery beat, settings.CELERY_BEAT_SCHEDULE): the audit chain verified nightly and copied off
the server daily, expired roles, scopes and change requests taken away (and old job files deleted), failed refunds
filed in the inbox; and on demand, a background job from the panel (staff.jobs) and an access request's data emailed
to the account's own address."""

import json
import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from django.core.mail import EmailMessage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from examleaf.celery import LONG_TASK, single_run

from . import approvals, audit
from .models import InboxItem, RoleGrant, StaffScope

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
    """Nightly: roles given until a time (just-in-time elevation), and scopes, past it are taken away; so are
    change requests whose time is over."""
    from .services import revoke_role

    now = timezone.now()
    grants = RoleGrant.objects.filter(expires_at__lte=now).select_related("user")
    for grant in grants:
        revoke_role(grant.user, grant.role, by=None, reason="Its time was over.")
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
    from django.conf import settings

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
