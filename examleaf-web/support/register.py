"""The grievance register (plan 5.14, research lms 4.9 and gst 7): a dated CSV of the complaints received in a period,
when each was acknowledged and resolved, against which deadline, the days taken and the NCH docket, for an audit or an
NCH query. No personal data: the ticket's number and category are all it says of a complaint. A staff job
(`grievance_export`: staff.export_grievances, capped by `export_rows` with an approver above it, staff.jobs) or, as the
break-glass way, `manage.py grievance_register`. Spam and tickets about a test order are never in it."""

import csv
import io
from datetime import datetime, time, timedelta

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from shop.models import live_mode
from staff import audit

from .models import Ticket

COLUMNS = [
    *["number", "category", "source", "nch_docket", "received_at", "acknowledge_by", "acknowledged_at"],
    *["hours_to_acknowledge", "acknowledged_in_time", "first_response_at", "resolve_by", "resolved_at"],
    *["days_to_resolve", "resolved_in_time", "closed_at", "status", "reopened"],
]


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def tickets(params):
    """The register's tickets: received in the period (India's days, both included; none given: from the first, to
    today), oldest first."""
    rows = Ticket.objects.exclude(status=Ticket.Status.SPAM)
    if live_mode():
        rows = rows.exclude(order__livemode=False)
    if since := params.get("from"):
        rows = rows.filter(received_at__gte=day_start(datetime.fromisoformat(since).date()))
    if until := params.get("until"):
        rows = rows.filter(received_at__lt=day_start(datetime.fromisoformat(until).date() + timedelta(days=1)))
    return rows.order_by("received_at", "pk")


def local(moment):
    return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M") if moment else ""


def in_time(done, due):
    return "" if done is None else ("yes" if done <= due else "no")


def row(ticket):
    """One complaint: India's times, the hours to its acknowledgement, the calendar days to its resolution (India's
    dates), and whether each came before its deadline (the earliest that applied)."""
    acknowledged, resolved = ticket.acknowledged_at, ticket.resolved_at
    hours = f"{(acknowledged - ticket.received_at).total_seconds() / 3600:.1f}" if acknowledged else ""
    days = (timezone.localdate(resolved) - timezone.localdate(ticket.received_at)).days if resolved else ""
    return [
        ticket.number,
        ticket.category or "not sorted",
        ticket.source,
        ticket.nch_docket,
        local(ticket.received_at),
        local(ticket.ack_due_at),
        local(acknowledged),
        hours,
        in_time(acknowledged, ticket.ack_due_at),
        local(ticket.first_response_at),
        local(ticket.due_at),
        local(resolved),
        days,
        in_time(resolved, ticket.due_at),
        local(ticket.closed_at),
        ticket.status,
        ticket.reopened_count,
    ]


def write(rows, out, progress=None):
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for ticket in rows.iterator(chunk_size=500):
        writer.writerow(row(ticket))
        if progress is not None:
            progress.row()


def export(job, progress):
    """The staff job's runner (staff.jobs.RUNNERS): the file in the private storage, linked to its starter by the job's
    result_url (5 minutes at a time, kept a week); a dry run counts the rows."""
    rows = tickets(job.params)
    job.total = rows.count()
    if job.dry_run:
        return {"rows": job.total}
    out = io.StringIO()
    write(rows, out, progress)
    since, until = job.params.get("from") or "start", job.params.get("until") or timezone.localdate().isoformat()
    name = f"staff/jobs/{job.pk}/grievance-register-{since}-to-{until}-made-{timezone.localdate():%Y%m%d}.csv"
    job.result_file = default_storage.save(name, ContentFile(out.getvalue().encode("utf-8")))
    audit.record(
        "support.register_exported",
        actor=job.started_by,
        change_request=job.change_request_id,
        details={"rows": job.done, "from": job.params.get("from"), "until": job.params.get("until"), "job": job.pk},
    )
    return {"rows": job.done}
