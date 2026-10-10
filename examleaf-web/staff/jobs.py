"""Background work started from the panel (plan 3.6). `start()` stores a Job once the starter holds the kind's own
permission (the single action's), and queues it; above the starter's limit (`export_rows`, `bulk_rows`) it first waits
for an approver (a ChangeRequest "job.run"). The Celery task `staff.tasks.run_job` calls `run()`: the kind's runner,
with a Progress that counts the rows, keeps each failed row's error, saves both at most once a second and stops at the
next row once the job is cancelled. Kinds: `audit_export` (the audit log as JSON lines, a file in the private storage,
linked for 5 minutes), `bulk_action` (an approvals action on many targets, each through `approvals.ask` as a
single request would go: its permission, its scope, its limit and approval) and `erp_initial_load` (the ERPNext
sync's first load: erp.producers). Every step is an audit event."""

import hashlib
import json
import logging
import tempfile
from collections import Counter
from datetime import timedelta
from time import monotonic

from django.core import signing
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from rest_framework import exceptions, serializers

from shop import catalogue_jobs, order_jobs

from . import approvals, audit
from .backends import scoped
from .models import AuditEvent, ChangeRequest, Job

logger = logging.getLogger(__name__)
SIGNER = signing.TimestampSigner(salt="staff.job.result")
LINK_SECONDS = 300  # a result's link, as the private storage's own are (settings.STORAGES "default")
KEEP_FILES_DAYS = 7  # then the nightly task deletes the result file
# Phase B: course. A kind's file kept less than a week: the printer's file of book codes (learn.codes) 24 hours, its
# link refused after that, and the file deleted by the hourly purge (learn.tasks.purge_code_files)
KEEP_FILES = {Job.Kind.CODE_BATCH: timedelta(hours=24)}


def file_expired(job, now=None):
    """Whether a job's file is past the time its kind keeps it (its link refused, the file to delete)."""
    keep = KEEP_FILES.get(job.kind, timedelta(days=KEEP_FILES_DAYS))
    return job.finished_at is not None and job.finished_at + keep <= (now or timezone.now())


LIMITS = {
    Job.Kind.AUDIT_EXPORT: "export_rows",
    Job.Kind.BULK_ACTION: "bulk_rows",
    Job.Kind.ERP_INITIAL_LOAD: "bulk_rows",
    Job.Kind.GSTR1_EXPORT: "export_rows",
    **order_jobs.LIMITS,  # the Orders module's (shop/order_jobs.py)
    Job.Kind.GRIEVANCE_EXPORT: "export_rows",
    Job.Kind.REPORT_EXPORT: "export_rows",  # the Reports (insights/exports.py)
    **catalogue_jobs.LIMITS,  # the Catalogue module's (shop/catalogue_jobs.py)
}


class Cancelled(Exception):
    pass


def bulk_actions():
    """The approvals actions a bulk action may name: those asked for through change-requests/, and the customers'
    account actions (user.suspend …), which are named by bulk actions only."""
    return sorted(name for name, action in approvals.ACTIONS.items() if action.generic or action.bulk)


def children_in(kind, params):
    """How many of a bulk action's targets are children's accounts (Action.children): such a job waits for an approver
    whatever its size (a child's data is never changed in bulk by one person alone)."""
    if kind == Job.Kind.BULK_ACTION and isinstance(params, dict) and params.get("action") in approvals.ACTIONS:
        return approvals.ACTIONS[params["action"]].children(params.get("targets") or [])
    return 0


def permission(kind, params):
    """The permission a job needs, the single action's: the audit log's export, or a bulk action's own action's. None
    when the kind or the action does not exist."""
    if kind == Job.Kind.AUDIT_EXPORT:
        return "staff.export_auditlog"
    if kind == Job.Kind.BULK_ACTION and isinstance(params, dict) and params.get("action") in bulk_actions():
        return approvals.ACTIONS[params["action"]].maker
    if kind == Job.Kind.ERP_INITIAL_LOAD:
        return "erp.run_initial_load"
    if kind == Job.Kind.GSTR1_EXPORT:
        return "staff.run_gstr1"
    if kind == Job.Kind.CONTENT_IMPORT:
        return "staff.import_content"
    if kind == Job.Kind.GRIEVANCE_EXPORT:
        return "staff.export_grievances"
    if kind == Job.Kind.SETTLEMENT_FETCH:
        return "staff.reconcile_settlements"
    if kind == Job.Kind.REPORT_EXPORT:
        return "staff.export_report"
    if kind == Job.Kind.CODE_BATCH:
        return "staff.make_book_codes"
    return order_jobs.PERMISSIONS.get(kind) or catalogue_jobs.PERMISSIONS.get(kind)


def audit_events(user, filters):
    from .api import audit_filter  # the list's own filters

    return audit_filter(filters, scoped(AuditEvent.objects.all(), user, "staff.view_auditlog")).order_by("id")


def _event(job, verb, request=None, **kwargs):
    details = {
        "kind": job.kind,
        "done": job.done,
        "total": job.total,
        "failed": len(job.errors),
        "dry_run": job.dry_run,
    }
    if job.kind == Job.Kind.BULK_ACTION and isinstance(job.params, dict):  # the batch's own event names its action
        details["action"] = str(job.params.get("action", ""))[:60]
    return audit.record(f"job.{verb}", request=request, actor=job.started_by, target=job, details=details, **kwargs)


def start(kind, params, *, user, dry_run=False, request=None):
    """Store a job and queue it; above the starter's limit (never for a dry run) it waits for an approver first
    (staff.approve_export: ADMIN, the owners). A job whose rows ask for an approvals action as its starter (a
    cancellation refunds the orders paid online) needs that action's step-up now, as asking for it once would. Returns
    the job."""
    if not dry_run and (asked := order_jobs.ASKS.get(kind)):
        approvals.step_up(request, asked)
    if kind == Job.Kind.AUDIT_EXPORT:
        total = audit_events(user, params["filters"]).count()
    elif kind == Job.Kind.ERP_INITIAL_LOAD:
        from erp.producers import initial_load_size

        total = initial_load_size(params["invoices_from"])
    elif kind == Job.Kind.GSTR1_EXPORT:
        from shop.gstr1 import document_count, period_of

        total = document_count(*period_of(params["month"], params.get("months", 1)))
    elif kind in order_jobs.PERMISSIONS:
        total = order_jobs.size(kind, user, params)
    elif kind == Job.Kind.CONTENT_IMPORT:
        total = 0  # the source's papers, counted as it runs; no approver: its own dry run comes first
    elif kind == Job.Kind.GRIEVANCE_EXPORT:
        from support.register import tickets

        total = tickets(params).count()
    elif kind == Job.Kind.SETTLEMENT_FETCH:
        total = 0  # the day's settlement lines, counted as Razorpay gives them; no approver: it reads and matches
    elif kind == Job.Kind.REPORT_EXPORT:
        from insights.exports import size

        total = size(user, params)  # the report as its starter reads it: their permissions, their scope
    elif kind in catalogue_jobs.PERMISSIONS:
        total = catalogue_jobs.size(kind, user, params)
    elif kind == Job.Kind.CODE_BATCH:
        total = params["count"]  # no approver: the owners are told once the codes are made (learn.codes)
    else:
        total = len(params["targets"])
    with transaction.atomic():
        job = Job.objects.create(kind=kind, params=params, dry_run=dry_run, total=total, started_by=user)
        if kind == Job.Kind.CODE_BATCH:  # the batch's state follows its newest job (a failed one made again)
            from learn.models import CodeBatch

            CodeBatch.objects.filter(pk=params["batch"]).update(job=job)
        _event(job, "requested", request)
        limit = approvals.limit_of(user, LIMITS[kind]) if kind in LIMITS else None
        if dry_run or not (approvals.over(total, limit, "{amount} {limit}") or children_in(kind, params)):
            enqueue(job)
            return job
        reason = f"{job.get_kind_display().capitalize()} of {total:,} rows (job #{job.pk})"
        change_request, _ = approvals.ask("job.run", maker=user, target=job, payload={}, reason=reason, request=request)
        job.change_request = change_request
        job.save(update_fields=["change_request"])
    return job


def enqueue(job):
    from .tasks import run_job

    transaction.on_commit(lambda: run_job.delay(job.pk), robust=True)  # a broker down: the job stays queued


def cancel(job, *, user, request=None):
    """Its starter stops it: a queued job at once (and its approval withdrawn), a running one at its next row."""
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job.pk)
        if job.started_by_id != user.pk:
            raise exceptions.PermissionDenied("Only who started a job cancels it.")
        if job.state in Job.FINISHED:
            raise serializers.ValidationError({"non_field_errors": ["The job has finished."]})
        job.cancel_requested = True
        if job.state == Job.State.QUEUED:
            job.state, job.finished_at = Job.State.CANCELLED, timezone.now()
        job.save(update_fields=["cancel_requested", "state", "finished_at"])
        _event(job, "cancelled", request)
        waiting = job.change_request
        if waiting is not None and waiting.status == ChangeRequest.Status.PENDING:
            approvals.reject(waiting, user=user, comment="The job was cancelled.", request=request)
    return job


def result_url(job, request):
    """The result file's link for the job's starter, signed for 5 minutes; None for anyone else, without a file, or
    once its kind's time to keep it is over (KEEP_FILES)."""
    if not job.result_file or request is None or job.started_by_id != request.user.pk or file_expired(job):
        return None
    token = SIGNER.sign_object({"job": job.pk, "user": request.user.pk})
    path = reverse("staff:job-result", kwargs={"version": "v1", "pk": job.pk})
    return request.build_absolute_uri(f"{path}?token={token}")


def check_link(job, user, token):
    """Whether `token` is a link to this job's file made for `user` less than 5 minutes ago (and the file's time not
    over)."""
    try:
        return SIGNER.unsign_object(token, max_age=LINK_SECONDS) == {"job": job.pk, "user": user.pk} and not (
            file_expired(job)
        )
    except signing.BadSignature:  # forged or expired
        return False


class Progress:
    """A running job's count and its rows' errors, saved at most once a second; at a save it stops (Cancelled) once
    the job is cancelled."""

    def __init__(self, job):
        self.job, self.saved = job, monotonic()

    def error(self, target, label, message):
        if len(self.job.errors) < Job.MAX_ERRORS:
            self.job.errors.append({"id": target, "label": str(label)[:200], "message": str(message)[:500]})
        self.job.result["failed"] = self.job.result.get("failed", 0) + 1

    def row(self):
        self.job.done += 1
        if monotonic() - self.saved >= 1:
            self.save()
            if Job.objects.filter(pk=self.job.pk, cancel_requested=True).exists():
                raise Cancelled

    def save(self):
        self.saved = monotonic()
        job = self.job
        Job.objects.filter(pk=job.pk).update(done=job.done, total=job.total, errors=job.errors)


def message(error):
    """A DRF error's messages as one line."""
    detail = getattr(error, "detail", error)
    if isinstance(detail, dict):
        return "; ".join(message(value) for value in detail.values())
    if isinstance(detail, list):
        return " ".join(message(item) for item in detail)
    return str(detail)


def export_audit(job, progress):
    events = audit_events(job.started_by, job.params["filters"])
    job.total = events.count()  # as it is now
    if job.dry_run:
        return {"rows": job.total}
    with tempfile.TemporaryFile() as file:
        for event in events.iterator():
            file.write((json.dumps(audit.export_row(event), sort_keys=True, ensure_ascii=False) + "\n").encode())
            progress.row()
        file.seek(0)
        job.result_file = default_storage.save(
            f"staff/jobs/{job.pk}/audit-{timezone.localdate():%Y%m%d}.jsonl", File(file)
        )
    audit.record(
        "audit.exported",
        actor=job.started_by,
        change_request=job.change_request_id,
        details={"filters": job.params["filters"], "rows": job.done, "heads": audit.heads(), "job": job.pk},
    )
    return {"rows": job.done}


def bulk_action(job, progress):
    """Each target as its own request (`approvals.ask`, an idempotency key per job and target: a task run twice does
    nothing twice): run at once within the limits, waiting for an approver above them, or refused with its reason.
    The result also counts the children's accounts among the targets (`minors`), and a dry run says whether the real
    run will wait for an approver (`approval`: the rule's words, or null)."""
    params, maker = job.params, job.started_by
    action = approvals.ACTIONS[params["action"]]
    outcomes, waiting = Counter(), []
    for target in params["targets"]:
        try:
            if job.dry_run:
                action.validate(maker, target, params["payload"])
                outcomes["valid"] += 1
            else:
                key = f"job-{job.pk}-" + hashlib.sha256(str(target).encode()).hexdigest()[:20]
                change_request, _ = approvals.ask(
                    params["action"], maker=maker, target=target, payload=params["payload"], reason=params["reason"],
                    idempotency_key=key,
                )  # fmt: skip
                outcomes[change_request.status] += 1
                if change_request.status == ChangeRequest.Status.PENDING:
                    waiting.append(change_request.pk)
                elif change_request.status == ChangeRequest.Status.FAILED:
                    progress.error(target, change_request.target_label, change_request.result.get("error", ""))
        except (serializers.ValidationError, exceptions.PermissionDenied) as error:
            outcomes["refused"] += 1
            progress.error(target, target, message(error))
        progress.row()
    result = {"outcomes": dict(outcomes), "waiting": waiting}
    if minors := action.children(params["targets"]):
        result["minors"] = minors
    if job.dry_run:
        result["approval"] = approvals.bulk_rule(maker, len(params["targets"]), minors)
    return result


def erp_initial_load(job, progress):
    """The ERPNext sync's initial load (erp.producers.initial_load_job): each product and invoice a row."""
    from erp.producers import initial_load_job

    return initial_load_job(job, progress)


def gstr1_export(job, progress):
    """A period's GSTR-1 files, zipped (shop.gstr1.export_job)."""
    from shop.gstr1 import export_job

    return export_job(job, progress)


def content_import(job, progress):
    """An import from the books repository, a dry run or its apply (content.imports.run_job)."""
    from content.imports import run_job

    return run_job(job, progress)


def grievance_export(job, progress):
    """The grievance register as CSV (support.register.export)."""
    from support.register import export

    return export(job, progress)


def settlement_fetch(job, progress):
    """A day's Razorpay settlements fetched, matched and posted (shop.settlements.fetch_job)."""
    from shop.settlements import fetch_job

    return fetch_job(job, progress)


def report_export(job, progress):
    """A report as CSV (insights.exports.export)."""
    from insights.exports import export

    return export(job, progress)


def code_batch(job, progress):
    """A print run's book codes: their digests kept, the codes once into the printer's file (learn.codes.run_job)."""
    from learn.codes import run_job

    return run_job(job, progress)


RUNNERS = {
    Job.Kind.AUDIT_EXPORT: export_audit,
    Job.Kind.BULK_ACTION: bulk_action,
    Job.Kind.ERP_INITIAL_LOAD: erp_initial_load,
    Job.Kind.GSTR1_EXPORT: gstr1_export,
    **order_jobs.RUNNERS,
    Job.Kind.CONTENT_IMPORT: content_import,
    Job.Kind.GRIEVANCE_EXPORT: grievance_export,
    Job.Kind.SETTLEMENT_FETCH: settlement_fetch,
    Job.Kind.REPORT_EXPORT: report_export,
    **catalogue_jobs.RUNNERS,
    Job.Kind.CODE_BATCH: code_batch,
}


def run(job_id):
    """Run a queued job once (a task delivered twice finds it running); returns its final state, or None."""
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id, state=Job.State.QUEUED).first()
        if job is None:  # cancelled before it started, or started already
            return None
        job.state, job.started_at = Job.State.RUNNING, timezone.now()
        job.save(update_fields=["state", "started_at"])
        _event(job, "started")
    progress = Progress(job)
    try:
        perm = permission(job.kind, job.params)
        starter = job.started_by
        if starter is None or not starter.is_active or perm is None or not starter.has_perm(perm):
            raise exceptions.PermissionDenied(f"Its starter no longer holds {perm}.")
        job.result = {**job.result, **RUNNERS[job.kind](job, progress)}
        state = Job.State.DONE
    except Cancelled:
        state = Job.State.CANCELLED
    except Exception as error:  # kept on the job, and Sentry has it
        logger.exception("Job #%s failed", job.pk)
        progress.error(None, "", message(error))
        state = Job.State.FAILED
    job.state, job.finished_at = state, timezone.now()
    job.result = audit.plain(job.result)
    job.save(update_fields=["state", "finished_at", "done", "total", "errors", "result", "result_file"])
    verb = {Job.State.DONE: "done", Job.State.FAILED: "failed", Job.State.CANCELLED: "stopped"}[state]
    _event(job, verb, outcome=audit.Outcome.SUCCESS if state == Job.State.DONE else audit.Outcome.FAILED)
    return state


def delete_old_files(kinds=None):
    """The result files of jobs finished more than a week ago, or their kind's time (KEEP_FILES) (nightly:
    staff.tasks.expire_access; `kinds` only, hourly: learn.tasks.purge_code_files)."""
    now = timezone.now()
    older = Q(finished_at__lt=now - timedelta(days=KEEP_FILES_DAYS))
    for kind, keep in KEEP_FILES.items():
        older |= Q(kind=kind, finished_at__lt=now - keep)
    old = Job.objects.filter(older).exclude(result_file="")
    if kinds is not None:
        old = old.filter(kind__in=kinds)
    for job in old:
        default_storage.delete(job.result_file)
    return old.update(result_file="")
