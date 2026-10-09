"""The compliance cockpit (plan 5.15, research-rbac-security.md 4.4 and 4.6, research-lms-crm-cms.md 0): every clock
the Indian rules start, as rows with the record behind each (a data request's 48 hours and its month or 90 days, a
complaint's 48 hours and month and an NCH complaint's 30 days, a breach's 6 and 72 hours, the parents' confirmations
awaited, the yearly dark-pattern self-audit), the consents by the privacy notice's version they were given under, and
the legal calendar's next dates. Read-only: numbers and codes, never a person's details."""

from datetime import date, timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.utils import timezone

from accounts.audiences import adult_born_by
from examleaf.retention import midnight

from .config import site_setting
from .models import DarkPatternAudit, DataRequest, InboxItem, Incident
from .privacy import add_month, day

LIMIT = 20  # rows of a kind, the most urgent first; the counts are of every one
COMPLAINT_ACK, NCH_DAYS = timedelta(hours=48), 30  # E-Commerce Rules r.4(4); the National Consumer Helpline
FIRST_CERTIFICATE_YEAR = 2027  # the E-Commerce Rules as amended: the self-audit's certificate from 1 January 2027
LEGAL_DATES = [
    (
        date(2027, 1, 1),
        "The E-Commerce Rules' amendments in force",
        "A copy of the complaint as recorded, the 30-day prior price, the dark-pattern self-audit and its certificate, "
        "membership of the National Consumer Helpline.",
    ),
    (
        date(2027, 5, 13),
        "The DPDP Rules in force",
        "Rights answered within 90 days, a year of logs and processing records, a parent's verifiable consent with "
        "the age check, the breach notices.",
    ),
]


def clock(kind, label, rule, started, due, target, now, done_at=None, account=None):
    """One row: the clock, the rule that starts it, and the record behind it (and the account it is about, if any:
    its number only)."""
    target_type, target_id, target_label = target
    return {
        "kind": kind,
        "label": label,
        "rule": rule,
        "started_at": started,
        "due_at": due,
        "overdue": bool(due and done_at is None and due < now),
        "target_type": target_type,
        "target_id": str(target_id),
        "target_label": target_label,
        "account": account,
    }


def request_clocks(now):
    rows, counts = [], {}
    waiting = DataRequest.objects.exclude(status=DataRequest.Status.CLOSED)
    unacknowledged = waiting.filter(acknowledged_at=None)
    counts["data_request_ack"] = {
        "open": unacknowledged.count(),
        "overdue": unacknowledged.filter(ack_due_at__lt=now).count(),
    }
    counts["data_request_answer"] = {"open": waiting.count(), "overdue": waiting.filter(due_at__lt=now).count()}
    for request in unacknowledged.order_by("ack_due_at", "pk")[:LIMIT]:
        target = ("staff.datarequest", request.pk, f"DR-{request.pk}")
        rows.append(clock("data_request_ack", f"Acknowledge DR-{request.pk} ({request.get_kind_display()})",
                          "48 hours (the E-Commerce Rules)", request.received_at, request.ack_due_at, target, now,
                          account=request.user_id))  # fmt: skip
    for request in waiting.order_by("due_at", "pk")[:LIMIT]:
        rule = "a month (the SPDI and E-Commerce Rules); 90 days for the DPDP rights from 13 May 2027"
        target = ("staff.datarequest", request.pk, f"DR-{request.pk}")
        rows.append(clock("data_request_answer", f"Answer DR-{request.pk} ({request.get_kind_display()})", rule,
                          request.received_at, request.due_at, target, now, account=request.user_id))  # fmt: skip
    return rows, counts


def incident_clocks(now):
    rows, counts = [], {}
    open_incidents = Incident.objects.filter(closed_at=None)
    cert_in = open_incidents.filter(cert_in_reported_at=None)
    board = open_incidents.filter(board_report_at=None)
    six, seventy_two = timedelta(hours=Incident.CERT_IN_HOURS), timedelta(hours=Incident.BOARD_HOURS)
    counts["incident_cert_in"] = {"open": cert_in.count(), "overdue": cert_in.filter(detected_at__lt=now - six).count()}
    counts["incident_board"] = {
        "open": board.count(),
        "overdue": board.filter(detected_at__lt=now - seventy_two).count(),
    }
    for incident in cert_in.order_by("detected_at", "pk")[:LIMIT]:
        target = ("staff.incident", incident.pk, f"Incident {incident.pk}")
        rows.append(clock("incident_cert_in", f"Report incident {incident.pk} to CERT-In", "6 hours (CERT-In)",
                          incident.detected_at, incident.cert_in_due, target, now))  # fmt: skip
    for incident in board.order_by("detected_at", "pk")[:LIMIT]:
        target = ("staff.incident", incident.pk, f"Incident {incident.pk}")
        rows.append(clock("incident_board", f"The Board's report on incident {incident.pk}", "72 hours (DPDP r.7(2))",
                          incident.detected_at, incident.board_due, target, now))  # fmt: skip
    return rows, counts


def ticket_clocks(now):
    """The complaints' clocks from the support app's tickets (its own app, installed or not: read lazily). Returns
    (rows, counts, the state: {"installed", "error"})."""
    try:
        Ticket = apps.get_model("support", "Ticket")
    except LookupError:
        return [], {}, {"installed": False, "error": ""}
    names = {field.name for field in Ticket._meta.get_fields()}
    needed = {"number", "source", "status", "received_at", "acknowledged_at", "resolved_at"}
    if missing := sorted(needed - names):
        error = f"The support app's tickets have no {', '.join(missing)}: their clocks are not shown here."
        return [], {}, {"installed": True, "error": error}
    open_tickets = Ticket.objects.filter(resolved_at=None).exclude(status__in=["resolved", "closed", "spam"])
    rows, counts = [], {}
    clocks_of = [
        ("complaint_ack", open_tickets.filter(acknowledged_at=None), lambda at: at + COMPLAINT_ACK,
         "Acknowledge complaint {number}", "48 hours (the E-Commerce Rules)"),
        ("complaint_redress", open_tickets, add_month, "Redress complaint {number}", "a month (the E-Commerce Rules)"),
        ("complaint_nch", open_tickets.filter(source="nch"), lambda at: at + timedelta(days=NCH_DAYS),
         "Answer NCH complaint {number}", "30 days (the National Consumer Helpline)"),
    ]  # fmt: skip
    for kind, tickets, due_of, label, rule in clocks_of:
        received = list(tickets.order_by("received_at", "pk").values_list("number", "received_at")[:5000])
        counts[kind] = {"open": len(received), "overdue": sum(due_of(at) < now for _, at in received)}
        for number, at in received[:LIMIT]:
            target = ("support.ticket", number, number)
            rows.append(clock(kind, label.format(number=number), rule, at, due_of(at), target, now))
    return rows, counts, {"installed": True, "error": ""}


def parent_clocks(now):
    """The parents' confirmations awaited: children whose parent has not confirmed their consent (when consent is
    verified by a link), and children's deletions that wait for their parent."""
    from accounts.models import ConsentRecord, DeletionRequest

    rows, counts = [], {}
    children = get_user_model().objects.filter(is_active=True, date_of_birth__gt=adult_born_by())
    if site_setting("PARENTAL_CONSENT_MODE") == "verified":
        verified = ConsentRecord.objects.filter(event=ConsentRecord.Event.GIVEN, verified_at__isnull=False)
        waiting = children.exclude(pk__in=verified.values("user"))
        counts["parent_consent"] = {"open": waiting.count(), "overdue": 0}
        for user in waiting.order_by("created", "pk").only("pk", "created")[:LIMIT]:
            target = ("accounts.user", user.pk, f"Account #{user.pk}")
            rows.append(clock("parent_consent", f"A parent's consent awaited: account #{user.pk}",
                              "until then the account reads, and saves nothing", user.created, None, target, now,
                              account=user.pk))  # fmt: skip
    deletions = DeletionRequest.objects.filter(
        status=DeletionRequest.Status.PENDING, parent_confirmed_at=None, user__in=children
    )
    counts["deletion_parent"] = {"open": deletions.count(), "overdue": deletions.filter(due_at__lt=now).count()}
    for deletion in deletions.order_by("due_at", "pk")[:LIMIT]:
        target = ("accounts.deletionrequest", deletion.pk, f"Deletion {deletion.pk}")
        rows.append(clock("deletion_parent", f"A child's deletion waits for the parent: account #{deletion.user_id}",
                          "erased once the parent or guardian confirms", deletion.requested_at, deletion.due_at,
                          target, now, account=deletion.user_id))  # fmt: skip
    return rows, counts


def audit_year(today=None):
    """The year whose dark-pattern certificate is due next: this year's, or from 1 December the coming year's (the
    first: 2027)."""
    today = today or timezone.localdate()
    return max(today.year + (today.month == 12), FIRST_CERTIFICATE_YEAR)


def dark_pattern_state(today=None):
    today = today or timezone.localdate()
    year = audit_year(today)
    audit = DarkPatternAudit.objects.filter(year=year).first()
    shown = certificate(today)
    return {
        "year": year,
        "due": date(year, 1, 1),
        "audit": audit.pk if audit else None,
        "state": "completed" if audit and audit.completed_at else "draft" if audit else "missing",
        "completed_at": audit.completed_at if audit else None,
        "effective_from": audit.effective_from if audit else None,
        "certificate_year": shown.year if shown else None,
    }


def certificate(today=None):
    """The certificate the website shows: the newest completed self-audit's in force (its effective_from passed)."""
    today = today or timezone.localdate()
    audits = DarkPatternAudit.objects.exclude(completed_at=None).filter(effective_from__lte=today)
    return audits.order_by("-effective_from", "-year").first()


def dark_pattern_clock(now):
    state = dark_pattern_state(timezone.localdate(now))
    due, done = midnight(state["due"]), state["completed_at"]
    target = ("staff.darkpatternaudit", state["audit"] or state["year"], f"Self-audit {state['year']}")
    row = clock("dark_pattern_audit", f"The dark-pattern self-audit and certificate for {state['year']}",
                "once a year, the certificate shown from 1 January (the E-Commerce Rules)", None, due, target, now,
                done_at=done)  # fmt: skip
    return ([] if done else [row]), {"dark_pattern_audit": {"open": 0 if done else 1, "overdue": int(row["overdue"])}}


def consents_by_version():
    """The consents to the privacy notice by the version they were given under (and withdrawn), newest version
    first, with the version's number when the page's history knows it."""
    from accounts.models import ConsentRecord
    from pages.models import Page
    from pages.versions import versions

    page = Page.objects.filter(slug="privacy").first()
    numbers = {version.version: version for version in versions(page)} if page else {}
    rows = (
        ConsentRecord.objects.filter(purpose=ConsentRecord.Purpose.ACCOUNT)
        .values("notice_version")
        .annotate(
            given=Count("pk", filter=Q(event=ConsentRecord.Event.GIVEN)),
            withdrawn=Count("pk", filter=Q(event=ConsentRecord.Event.WITHDRAWN)),
            latest=Max("created"),
        )
        .order_by("-latest")
    )
    return [
        {
            "version": row["notice_version"],
            "number": numbers[row["notice_version"]].number if row["notice_version"] in numbers else None,
            "in_force": bool(numbers.get(row["notice_version"]) and numbers[row["notice_version"]].in_force),
            "given": row["given"],
            "withdrawn": row["withdrawn"],
        }
        for row in rows
    ]


def last_restore_drill():
    """The latest restore drill the panel recorded (the system module's staff.RestoreDrill, when it is there)."""
    try:
        model = apps.get_model("staff", "RestoreDrill")
    except LookupError:
        return None
    fields = {field.name: field for field in model._meta.get_fields() if hasattr(field, "get_internal_type")}
    for name in ["date", "drilled_on", "performed_on", "held_on", "done_at", "created"]:
        if name in fields and fields[name].get_internal_type() in ("DateField", "DateTimeField"):
            latest = model.objects.aggregate(latest=Max(name))["latest"]
            return timezone.localdate(latest) if hasattr(latest, "tzinfo") and latest.tzinfo else latest
    return None


def calendar(today=None):
    """The legal calendar's next dates: the fixed ones (1 January and 13 May 2027), the dark-pattern reminder and its
    due date, the quarterly access review and the quarterly restore drill."""
    today = today or timezone.localdate()
    items = [
        {"date": when, "title": title, "detail": detail, "state": "upcoming" if when > today else "in_force"}
        for when, title, detail in LEGAL_DATES
        if when > today - timedelta(days=60)
    ]
    year = audit_year(today)
    reminder = date(year - 1, 12, 1)
    state = dark_pattern_state(today)["state"]
    if reminder > today:
        detail = "The inbox reminds those who keep the compliance duties."
        items.append({"date": reminder, "title": f"Start the dark-pattern self-audit for {year}", "detail": detail,
                      "state": "upcoming"})  # fmt: skip
    items.append(
        {
            "date": date(year, 1, 1),
            "title": f"The dark-pattern certificate for {year} on the website",
            "detail": "The 13 patterns answered, the certificate completed and in force.",
            "state": "done" if state == "completed" else "upcoming" if date(year, 1, 1) > today else "overdue",
        }
    )
    next_quarter = ((today.month - 1) // 3 + 1) % 4  # 0 to 3: January, April, July, October
    quarter = date(today.year + (next_quarter == 0), next_quarter * 3 + 1, 1)
    items.append({"date": quarter, "title": "The quarterly access review",
                  "detail": "Who holds which role and scope: People, Access review.", "state": "upcoming"})  # fmt: skip
    drill = last_restore_drill()
    due = drill + timedelta(days=91) if drill else today
    items.append(
        {
            "date": due,
            "title": "The quarterly restore drill",
            "detail": f"The last one recorded: {day(drill)}." if drill else "None recorded in the panel yet.",
            "state": "upcoming" if drill and due > today else "overdue",
        }
    )
    return sorted(items, key=lambda item: item["date"])


def cockpit(now=None):
    """Everything the cockpit draws (GET privacy/cockpit/)."""
    now = now or timezone.now()
    rows, counts = [], {}
    for part in (request_clocks, incident_clocks, parent_clocks, dark_pattern_clock):
        part_rows, part_counts = part(now)
        rows += part_rows
        counts |= part_counts
    ticket_rows, ticket_counts, support = ticket_clocks(now)
    rows += ticket_rows
    counts |= ticket_counts
    far = now + timedelta(days=36500)
    rows.sort(key=lambda row: (not row["overdue"], row["due_at"] or far, row["kind"], row["target_id"]))
    return {
        "now": now,
        "clocks": rows,
        "counts": counts,
        "support": support,
        "consents": consents_by_version(),
        "dark_pattern": dark_pattern_state(timezone.localdate(now)),
        "calendar": calendar(timezone.localdate(now)),
        "inbox": InboxItem.objects.filter(
            done_at=None, kind__in=[InboxItem.Kind.PROCESSOR_TASK, InboxItem.Kind.COMPLIANCE]
        ).count(),
    }
