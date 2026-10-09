"""The log inventory (research-rbac-security 7, ASVS 16.1.1): what is logged, where, how long and who may read it, as
the system page's Logs and time section shows it beside the retention the law asks for now (CERT-In's 180 days, rolling;
the DPDP Rules' year from STAFF_DPDP_RULES_FROM). A table in code: a new log is a new row here, in the same commit."""

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

CERT_IN_DAYS, DPDP_DAYS = 180, 365


@dataclass(frozen=True)
class Log:
    key: str
    what: str
    where: str
    kept: str
    readers: str
    days: object = None  # how many days it is kept (a callable reading the settings), None: not set by this code
    forever: bool = False  # never deleted by this code


INVENTORY = [
    Log(
        "audit",
        "Staff actions and refusals, staff log-ins, failed log-ins and lock-outs, reveals of personal data",
        "PostgreSQL (the append-only, hash-chained audit log), copied each day to the backups bucket (audit/)",
        "2 years; money events 8 financial years (STAFF_AUDIT_RETENTION_DAYS, STAFF_AUDIT_MONEY_RETENTION_FY)",
        "OWNER and AUDITOR, each read logged",
        lambda: settings.STAFF_AUDIT_RETENTION_DAYS,
    ),
    Log(
        "requests",
        "Every request to the backend: its route, status, time and account id (one JSON line each)",
        "The containers' standard output: the host's log driver (Docker) or the cluster's log store",
        'As the host keeps them: set it to at least the retention below (RUNBOOK.md "Reading the logs")',
        "Whoever runs the servers",
    ),
    Log(
        "proxy",
        "Caddy's access log: client addresses, paths, statuses",
        "Caddy's log on the server",
        "As Caddy's log roll keeps it",
        "Whoever runs the servers",
    ),
    Log(
        "integration_calls",
        "Calls to the providers (Shiprocket, ERPNext, the connection tests), redacted",
        "PostgreSQL (the integrations' call log)",
        "INTEGRATIONS_RETENTION_DAYS (90 by default)",
        "OWNER, ADMIN and AUDITOR (the connections page)",
        lambda: settings.INTEGRATIONS_RETENTION_DAYS,
    ),
    Log(
        "inbound_events",
        "Webhooks received from the providers, kept raw, deduplicated",
        "PostgreSQL (the integrations' inbound events)",
        "INTEGRATIONS_RETENTION_DAYS (90 by default)",
        "OWNER, ADMIN and AUDITOR (the connections page)",
        lambda: settings.INTEGRATIONS_RETENTION_DAYS,
    ),
    Log(
        "sms",
        "SMS asked for: kind, status, the number's last four digits, the delivery report",
        "PostgreSQL (the SMS log)",
        "90 days (ops.sms); a year from 13 May 2027 (the plan, 7.11)",
        "SUPPORT, ADMIN, OWNER and AUDITOR",
        lambda: 90,
    ),
    Log(
        "failed_logins",
        "Failed log-ins of every account (django-axes), for its lock-outs",
        "PostgreSQL",
        "Until the nightly reset at 03:30; staff accounts' failed log-ins stay in the audit log",
        "Superusers (the Django admin)",
        lambda: 1,
    ),
    Log(
        "task_results",
        "Background tasks' results and failures (Celery)",
        "PostgreSQL",
        "7 days (CELERY_RESULT_EXPIRES)",
        "ADMIN, OWNER and AUDITOR (the system page), superusers",
        lambda: settings.CELERY_RESULT_EXPIRES.days,
    ),
    Log(
        "sessions",
        "Signed-in devices: address, browser, last seen (allauth.usersessions)",
        "PostgreSQL",
        "Until the session ends (8 hours for staff, two weeks for the website)",
        "The person themselves; OWNER for staff",
    ),
    Log(
        "errors",
        "Errors with their stack traces, personal data scrubbed",
        "The error tracker (Sentry or GlitchTip: SENTRY_DSN)",
        "As the tracker's project keeps them",
        "Whoever the tracker lets in",
    ),
    Log(
        "admin_log",
        "Changes made in the Django admin",
        "PostgreSQL (the admin's log entries)",
        "Kept",
        "Superusers",
        forever=True,
    ),
    Log(
        "backups",
        "Database dumps, encrypted with age when BACKUP_AGE_RECIPIENT is set",
        "The backups bucket (BACKUP_BUCKET) and the server's backups/ folder",
        "BACKUP_KEEP_DAYS (30 by default)",
        "Whoever holds the bucket's keys and the age key",
        lambda: settings.BACKUP_KEEP_DAYS,
    ),
]


def required_days(today=None):
    """The retention the law asks for logs today: CERT-In's 180 days, rolling; a year once the DPDP Rules apply."""
    today = today or timezone.localdate()
    return DPDP_DAYS if today >= settings.STAFF_DPDP_RULES_FROM else CERT_IN_DAYS


def inventory(today=None):
    """Each log with how long it is kept and whether that meets the retention required now (None: set elsewhere)."""
    needed = required_days(today)
    rows = []
    for log in INVENTORY:
        days = log.days() if callable(log.days) else None
        meets = True if log.forever else None if days is None else days >= needed
        rows.append(
            {
                "key": log.key,
                "what": log.what,
                "where": log.where,
                "kept": log.kept,
                "readers": log.readers,
                "days": days,
                "meets_retention": meets,
            }
        )
    return rows
