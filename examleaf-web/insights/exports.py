"""The reports as files (plan 5.0 and 5.16): any report as a staff job (`report_export`, `POST /api/v1/staff/jobs/`
with `{"report": "sales", "filters": {"from": "2026-10-01", "to": "2026-10-31", "by": "subject"}}`), the filters the
page had, a CSV in the private storage that its starter alone is linked to for 5 minutes at a time and that is kept a
week (staff.jobs). `staff.export_report` (high: FINANCE, ADMIN, the owners, AUDITOR) is the job's own permission, and
the starter needs the report's own too (its data's `view_`); above the starter's `export_rows` an approver (ADMIN)
passes it first.

What a file holds is what the page showed, from the same function (reports.py): the cells hidden under the minimum say
"fewer than k" in a file, never a number; a cell of text that a spreadsheet would read as a formula is written as text
(a leading = + - @ tab or return gets an apostrophe: CSV injection, OWASP); there is no date of birth, no contact and no
account in any report to leave out, and a test holds every report to it. Each export is an audit event with its filters
and its row count (`report.exported`); a file ends with who made it and when (the member of staff's number)."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import exceptions, serializers

from staff import audit

from . import cells
from .reports import EXPORTABLE, parse

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def escaped(value):
    """A cell of text a spreadsheet would run as a formula is made text (an apostrophe first); numbers are the
    system's own and pass as they are."""
    return f"'{value}" if isinstance(value, str) and value.startswith(FORMULA_STARTS) else value


def text(value):
    """A cell as the file writes it: no None, dates as ISO days, money and shares as their decimals."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if isinstance(value, Decimal) else value


def clean_params(params):
    """A job's params, checked (staff.serializers.JobStartSerializer): the report, and its filters, each one of its own
    and valid; an unknown or invalid one is refused, so that an export never widens because of a typo."""
    params = params if isinstance(params, dict) else {}
    report = EXPORTABLE.get(params.get("report"))
    if report is None:
        raise serializers.ValidationError({"params": {"report": [f"One of {', '.join(EXPORTABLE)}."]}})
    filters = params.get("filters", {})
    if not isinstance(filters, dict):
        raise serializers.ValidationError({"params": {"filters": ["The report's filters, as an object."]}})
    if unknown := sorted(set(filters) - set(report.params)):
        wrong = {name: ["Not a filter of this report."] for name in unknown}
        raise serializers.ValidationError({"params": {"filters": wrong}})
    clean = {name: str(value).strip() for name, value in filters.items() if value not in (None, "")}
    try:
        parse(clean, report.params)
    except serializers.ValidationError as error:
        raise serializers.ValidationError({"params": {"filters": error.detail}}) from None
    return {"report": report.key, "filters": clean}


def answer(user, params):
    """The report's answer for the person: they hold the permissions that open it (else 403, naming one)."""
    report = EXPORTABLE[params["report"]]
    if missing := next((perm for perm in report.required() if not user.has_perm(perm)), None):
        raise exceptions.PermissionDenied(f"You need the permission {missing} to export the {report.label} report.")
    try:
        return report, report.run(user, params["filters"])
    except serializers.ValidationError as error:
        raise serializers.ValidationError({"params": {"filters": error.detail}}) from None


def size(user, params):
    """The rows a job will write (its total, against its starter's `export_rows`)."""
    return len(answer(user, params)[1]["rows"])


def cell(value):
    """One cell as the file writes it: text a spreadsheet could run as a formula is made text; numbers, money, shares
    and dates are the system's own and pass as they are (a negative amount stays a number)."""
    return escaped(value) if isinstance(value, str) else text(value)


def line(report, row):
    """A row's cells in the report's columns' order: a hidden row says "fewer than k" in its numbers."""
    hidden = row.get("hidden")
    return [
        cell(cells.words(row) if hidden and each["key"] in report.measures else row.get(each["key"]))
        for each in report.columns
    ]


def export(job, progress):
    """The staff job's runner (staff.jobs.RUNNERS): the file in the private storage, linked to its starter by the job's
    result_url; a dry run counts the rows."""
    report, made = answer(job.started_by, job.params)
    table = made["rows"]
    job.total = len(table)
    if job.dry_run:
        return {"rows": job.total}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([each["label"] for each in report.columns])
    for row in table:
        writer.writerow(line(report, row))
        progress.row()
    now = timezone.localtime()
    filters = ", ".join(f"{name}={value}" for name, value in sorted(job.params["filters"].items())) or "none"
    writer.writerow([])
    writer.writerow(
        [
            "Report",
            report.label,
            f"made {now:%Y-%m-%d %H:%M} by staff member #{job.started_by_id}",
            f"filters: {filters}",
        ]
    )
    period = made.get("period")
    span = f"{period['start']}-to-{period['end']}-" if period else ""
    name = f"staff/jobs/{job.pk}/report-{report.key}-{span}made-{now:%Y%m%d}.csv"
    job.result_file = default_storage.save(name, ContentFile(out.getvalue().encode("utf-8")))
    audit.record(
        "report.exported",
        actor=job.started_by,
        change_request=job.change_request_id,
        details={"report": report.key, "filters": job.params["filters"], "rows": job.done, "job": job.pk},
    )
    return {"rows": job.done}
