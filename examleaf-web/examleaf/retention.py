"""The retention schedule (plan 5.15 and 7.9; research-rbac-security.md 3.4 and 4.9): for each kind of record, the
least time the law keeps it (and the day that minimum changes), what this site keeps, and what the clean-up does then.
One table in code, read by the erasure's dry run and DeletionRequest.complete (staff.privacy), by the nightly clean-up
(ops.tasks.trim_expired and purge_expired: the rows with a `model`) and by the staff API's retention page
(GET /api/v1/staff/privacy/retention/). A change here changes what the clean-up deletes: test_retention holds every
period at or above its minimum."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

DPDP_RULES = date(2027, 5, 13)  # DPDP Rules rr.3 and 5 to 16 in force: a year of logs and of processing records
BOOKS_YEARS = 8  # Companies Act s.128(5): the books of the 8 financial years before the current one
GST_MONTHS = 72  # CGST Act s.36: 72 months from the due date of the year's annual return (31 December after it)


@dataclass(frozen=True)
class Minimum:
    since: date | None  # from when the law asks this (None: already)
    days: int | None  # None: by a rule in words (financial years; while relied on)
    text: str


@dataclass(frozen=True)
class Rule:
    key: str
    records: str  # what the records are, in words
    minimums: tuple  # (Minimum, …), oldest first: the law's least time over time
    source: str
    keep: str  # what this site keeps, in words
    keep_days: int | None = None  # rows of `model` older than this are deleted (ops.tasks.purge_expired)
    model: str = ""  # "app_label.ModelName" the clean-up acts on
    date_field: str = ""
    trim_days: int | None = None  # past this age `trim`'s fields are blanked (ops.tasks.trim_expired)
    trim: dict = field(default_factory=dict)
    enforced_by: str = "ops.tasks: the nightly trim and purge"


NONE = (Minimum(None, None, "none"),)
LOGS = (Minimum(None, 180, "180 days"), Minimum(DPDP_RULES, 365, "one year"))

SCHEDULE = (
    Rule(
        "books",
        "Books of account: invoices, credit notes, and the orders and payments behind them",
        (
            Minimum(
                None,
                None,
                "8 financial years after the year's, or 72 months after the due date of the year's annual return, "
                "whichever is later",
            ),
        ),
        "Companies Act 2013 s.128(5); CGST Act 2017 s.36",
        "Until then; then the customer's details leave the order (its number and totals stay) and the documents' "
        "PDFs are deleted. A legal hold keeps an order as it is.",
        enforced_by="ops.tasks.purge_expired, from the books' date (books_until)",
    ),
    Rule(
        "security_logs",
        "Security logs: every request's line (route, status, time, account number), staff sign-ins, the web "
        "server's access log",
        LOGS,
        "CERT-In Directions of 28 April 2022, (iv); DPDP Rules r.6(1)(e) from 13 May 2027",
        "Docker's logs on the server (50 MB × 10 files a service) and their copy off the server",
        enforced_by="the server's log rotation and the copy off the server (DEPLOYMENT.md section 10)",
    ),
    Rule(
        "processing_records",
        "Records of each processing: an order's, a payment's and a parcel's events, and the audit log's events "
        "about a person",
        (Minimum(None, None, "none before the DPDP Rules"), Minimum(DPDP_RULES, 365, "one year from the processing")),
        "DPDP Rules r.8(3) from 13 May 2027",
        "With the order and the parcel, as long as the books; the audit log two years. An erasure keeps them with "
        "the account's number only.",
        enforced_by="the books' and the audit log's own periods",
    ),
    Rule(
        "consents",
        "Consent records and their withdrawals",
        (Minimum(None, None, "while processing relies on them, and 3 years after (the limitation period)"),),
        "DPDP Act 2023 s.6(10); Limitation Act 1963, art. 113",
        "Kept; an erasure drops the address hash",
        enforced_by="never deleted by the site",
    ),
    Rule(
        "staff_audit",
        "The staff audit log (money events apart)",
        (Minimum(None, 365, "one year"),),
        "DPDP Rules r.6(1)(e); money events: Companies Act 2013 s.128(5)",
        "Two years (STAFF_AUDIT_RETENTION_DAYS), money events 8 financial years (STAFF_AUDIT_MONEY_RETENTION_FY)",
        enforced_by="manage.py purge_audit, monthly (staff/README.md)",
    ),
    Rule(
        "backups",
        "Database backups",
        (Minimum(None, None, "none: kept short, so that erased data does not linger"),),
        "DPDP Act 2023 s.8(7)",
        "30 days (BACKUP_KEEP_DAYS and the bucket's lifecycle rule); an erased account is erased again after a "
        "restore (manage.py reapply_erasures)",
        enforced_by="scripts/backup.sh and the bucket's lifecycle rule",
    ),
    Rule(
        "sms_log",
        "The SMS log: kind, status, time, the number's keyed hash and last four digits, MSG91's request id",
        LOGS,
        "CERT-In Directions of 28 April 2022, (iv); DPDP Rules r.8(3) from 13 May 2027",
        "A year; the last four digits blanked after 90 days (the log keeps no message text). An erasure keeps the "
        "rows without the account.",
        keep_days=365,
        model="ops.SmsLog",
        date_field="created",
        trim_days=90,
        trim={"phone_last4": ""},
    ),
    Rule(
        "webhook_events",
        "Razorpay's webhook records: their id and digest, against a replay",
        (Minimum(None, None, "none: the payment's own record is a book of account"),),
        "The replay window (shop.payments.WEBHOOK_MAX_AGE)",
        "7 days",
        keep_days=7,
        model="shop.WebhookEvent",
        date_field="received_at",
    ),
    Rule(
        "celery_results",
        "Background tasks' results",
        NONE,
        "Celery's own (CELERY_RESULT_EXPIRES)",
        "7 days",
        keep_days=7,
        model="django_celery_results.TaskResult",
        date_field="date_done",
    ),
    Rule(
        "devices",
        "The app's phones for the daily reminder (their Firebase installation ids)",
        NONE,
        "DPDP Act 2023 s.8(7): erased once the purpose is served",
        "Deleted after 90 days without a word from the phone",
        keep_days=90,
        model="learn.Device",
        date_field="last_seen",
    ),
    Rule(
        "integration_calls",
        "Calls to the couriers and to ERPNext (redacted), their inbound events and the dead letters settled",
        NONE,
        "INTEGRATIONS_RETENTION_DAYS",
        "90 days",
        enforced_by="integrations.tasks.purge_old_records, nightly",
    ),
    Rule(
        "spam",
        "Messages marked as spam: support tickets, mistake reports",
        NONE,
        "Kept out of every report",
        "30 days",
        enforced_by="the support and content apps' nightly tasks",
    ),
    Rule(
        "payment_payloads",
        "Razorpay's last webhook body kept on a payment",
        NONE,
        "Payment.PAYLOAD_DAYS",
        "180 days, then blanked (the payment stays, a book of account)",
        enforced_by="shop.tasks.clean_up, nightly",
    ),
    Rule(
        "parent_links",
        "The consent links sent to a student's parent: when, by email or SMS, and by whom (no contact is kept)",
        (Minimum(None, None, "none before the DPDP Rules"), Minimum(DPDP_RULES, 365, "one year from the processing")),
        "DPDP Rules r.8(3) from 13 May 2027",
        "A year; an erasure keeps them with the account's number only",
        keep_days=365,
        model="accounts.ParentLinkSend",
        date_field="sent_at",
    ),
)
RULES = {rule.key: rule for rule in SCHEDULE}


def rule(key):
    return RULES[key]


def minimum(key, on=None):
    """The law's least time for these records on that day (India's date): the newest Minimum in force."""
    on = on or timezone.localdate()
    found = RULES[key].minimums[0]
    for each in RULES[key].minimums:
        if each.since is None or each.since <= on:
            found = each
    return found


def next_minimum(key, on=None):
    """The next change of the minimum after that day, or None."""
    on = on or timezone.localdate()
    return next((each for each in RULES[key].minimums if each.since and each.since > on), None)


def midnight(day):
    return datetime.combine(day, time.min, tzinfo=timezone.get_current_timezone())


def cutoff(key, days=None, now=None):
    """The moment before which a rule's rows go (its keep_days, or the days given), at India's midnight: a row is
    kept whole days."""
    now = now or timezone.now()
    days = RULES[key].keep_days if days is None else days
    return midnight(timezone.localdate(now) - timedelta(days=days))


def kept_until(key, at, days=None):
    """The last day a record made `at` is kept under a rule's keep_days (or the days given)."""
    days = RULES[key].keep_days if days is None else days
    return timezone.localdate(at) + timedelta(days=days)


def fy_start_year(financial_year):
    """2026 for "2026-27" (and the test series' "T2026-27")."""
    return int(financial_year.lstrip("T").split("-")[0])


def books_until(financial_year):
    """The last day the books of a financial year ("2026-27") are kept: 8 financial years after it (Companies Act
    s.128(5)), or 72 months after the due date of its annual return (31 December after the year: CGST Act s.36),
    whichever is later. 2026-27 → 31 March 2035."""
    start = fy_start_year(financial_year)
    companies_act = date(start + 1 + BOOKS_YEARS, 3, 31)
    gst = date(start + 1 + GST_MONTHS // 12, 12, 31)  # the annual return's due date (31 December) + 72 months
    return max(companies_act, gst)


def financial_year_of(day):
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def books_cutoff(today=None):
    """The first day of the oldest financial year whose books are still kept: documents and orders dated before it
    are past their books' period (ops.tasks.purge_expired)."""
    today = today or timezone.localdate()
    start = today.year if today.month >= 4 else today.year - 1
    while books_until(f"{start - 1}-00") >= today:  # the year before is still kept: step back
        start -= 1
    return date(start, 4, 1)


def audit_kept_until(event_ts, money=False):
    """The last day an audit event is kept (staff.audit's retention): STAFF_AUDIT_RETENTION_DAYS after it, or for a
    money event the end of the 8th financial year after its own."""
    day = timezone.localdate(event_ts)
    if money:
        start = day.year if day.month >= 4 else day.year - 1
        return date(start + 1 + settings.STAFF_AUDIT_MONEY_RETENTION_FY, 3, 31)
    return day + timedelta(days=settings.STAFF_AUDIT_RETENTION_DAYS)


def table(today=None):
    """The schedule as the staff API answers it: each rule with its minimum today, the next change, what is kept."""
    today = today or timezone.localdate()
    rows = []
    for each in SCHEDULE:
        now, upcoming = minimum(each.key, today), next_minimum(each.key, today)
        rows.append(
            {
                "key": each.key,
                "records": each.records,
                "minimum": now.text,
                "minimum_days": now.days,
                "source": each.source,
                "changes_on": upcoming.since if upcoming else None,
                "next_minimum": upcoming.text if upcoming else None,
                "keep": each.keep,
                "keep_days": each.keep_days,
                "trim_days": each.trim_days,
                "enforced_by": each.enforced_by,
            }
        )
    return rows
