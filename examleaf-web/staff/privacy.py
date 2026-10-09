"""Data protection duties as code (research section 4): the clocks of a data request; the erasure's dry run (what
DeletionRequest.complete erases, what stays, why and until when, and what stops it) and the holds the erasure obeys
(legal holds, the books, a year of processing logs, the intermediary rule, a child's parent); after an erasure or a
withdrawn consent, the tasks for the processors that keep the data; the answer's text with the contact block; the
erasure ledger's keyed hash; and the masks staff see by default."""

import calendar
from datetime import date, timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from examleaf import retention
from pages.models import PLACEHOLDER

from .config import SETTINGS, site_setting
from .models import AuditEvent, DataRequest, InboxItem, ProcessorRecord

Kind = DataRequest.Kind


def add_month(when):
    """The same day a month later (the last day of a shorter month)."""
    year, month = (when.year + 1, 1) if when.month == 12 else (when.year, when.month + 1)
    return when.replace(year=year, month=month, day=min(when.day, calendar.monthrange(year, month)[1]))


def clocks(kind, received_at):
    """(acknowledge by, answer by) for a request received then. Acknowledged within STAFF_DATA_REQUEST_ACK_HOURS (48:
    the E-Commerce Rules); answered within one month (the SPDI Rules and the E-Commerce Rules) until the DPDP Rules'
    rights take effect (STAFF_DPDP_RULES_FROM, 13 May 2027), then within STAFF_DPDP_RESPONSE_DAYS (90, r.14(3)). A
    grievance or complaint keeps the E-Commerce Rules' month after that too: the strictest clock that applies."""
    ack = received_at + timedelta(hours=settings.STAFF_DATA_REQUEST_ACK_HOURS)
    month = add_month(received_at)
    if timezone.localdate(received_at) < settings.STAFF_DPDP_RULES_FROM:
        return ack, month
    due = received_at + timedelta(days=settings.STAFF_DPDP_RESPONSE_DAYS)
    return ack, min(due, month) if kind in (Kind.GRIEVANCE, Kind.COMPLAINT) else due


def mask_email(email):
    name, _, domain = (email or "").partition("@")
    return f"{name[:2]}•••@{domain}" if domain else ""


def mask_phone(phone):
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    return f"••••••{digits[-4:]}" if len(digits) >= 4 else ""


def mask_contact(contact):
    """An email address or a phone number, masked as the panel shows them."""
    return mask_email(contact) if "@" in (contact or "") else mask_phone(contact)


def mask_ip(ip):
    """203.0.113.x; an IPv6 address to its first four groups."""
    if not ip:
        return ""
    if ":" in ip:
        return ":".join(ip.split(":")[:4]) + ":…"
    return ".".join(ip.split(".")[:3]) + ".x"


def financial_year_end(day):
    return day.replace(year=day.year + (day.month >= 4), month=3, day=31)


def day(value):
    """A date in words, as the answers and the dry run write them: 31 March 2035."""
    return f"{value.day} {value:%B %Y}"


def plural(count, one, many):
    return f"{count:,} {one if count == 1 else many}"


# The settings the answers quote (the panel's Disclosures: staff/config.py)


def disclosure(key):
    """A disclosure setting in effect (the panel's, else settings.py's); "" while empty or still a [placeholder]."""
    value = str(site_setting(key) or "").strip()
    return "" if PLACEHOLDER.search(value) else value


def grievance_officer():
    """The Grievance Officer as the answers name them: name, designation, contact (DATA_PROTECTION_OFFICER until the
    disclosures name one); "" while none is set."""
    parts = [disclosure(key) for key in ("DISCLOSURE_GRIEVANCE_OFFICER", "DISCLOSURE_GRIEVANCE_DESIGNATION")]
    parts.append(disclosure("DISCLOSURE_GRIEVANCE_CONTACT"))
    officer = ", ".join(part for part in parts if part)
    return officer or disclosure("DATA_PROTECTION_OFFICER")


def contact_block(draft=False):
    """The contact block of every answer about personal data (DPDP Rules r.9; E-Commerce Rules r.4(4)): who answers
    questions about the processing, the Grievance Officer, the legal name and address. A part not set yet is left out
    of what goes to a person; in a draft for staff it says where to set it."""
    missing = "[not set yet: Legal and privacy, Disclosures]" if draft else ""
    lines = []
    if contact := disclosure("DATA_PROTECTION_OFFICER") or missing:
        lines.append(f"Questions about your personal data: {contact}")
    if officer := grievance_officer() or missing:
        lines.append(f"Grievance Officer: {officer}")
    name_and_address = ", ".join(
        part for part in (disclosure("DISCLOSURE_LEGAL_NAME"), disclosure("DISCLOSURE_REGISTERED_ADDRESS")) if part
    )
    if name_and_address or missing:
        lines.append(name_and_address or missing)
    return "\n".join(lines)


def intermediary_rules():
    """Whether the IT Rules' duties of an intermediary apply (SUPPORT_INTERMEDIARY_RULES, the support app's: off while
    counsel's answer is pending): the panel's setting once it is one, else settings.py's, else off."""
    if "SUPPORT_INTERMEDIARY_RULES" in SETTINGS:
        return bool(site_setting("SUPPORT_INTERMEDIARY_RULES"))
    return bool(getattr(settings, "SUPPORT_INTERMEDIARY_RULES", False))


def recipients():
    """Who else processes the personal data (DPDP s.11(1)(b), research 4.2): the processor register's in use, with
    their purpose, the kinds of data and where."""
    rows = ProcessorRecord.objects.filter(active=True).order_by("name")
    return [
        {"name": row.name, "purpose": row.purpose, "data_categories": row.data_categories, "country": row.country}
        for row in rows
    ]


# Legal holds (accounts.LegalHold): their targets, and what they keep

# What a hold may name besides a person: `app_label.model` → how the API finds it (its number, else its id)
HOLD_TARGETS = {
    "shop.order": "number",
    "shop.invoice": "number",
    "shop.creditnote": "number",
    "shop.payment": None,
    "shop.refund": None,
    "staff.datarequest": None,
}


def find_hold_target(label, value):
    """(content type, the object) a hold may name, by its number or id; None when there is no such record."""
    from django.apps import apps

    model = apps.get_model(label)
    number = HOLD_TARGETS[label]
    value = str(value or "").strip()
    query = Q(**{number: value}) if number else Q(pk__in=[])
    if value.isdigit():
        query |= Q(pk=int(value))
    found = model._default_manager.filter(query).first() if value else None
    return (ContentType.objects.get_for_model(model), found) if found else None


def hold_labels(holds):
    """{hold id: what it keeps, by number or code}: one query per kind of record, whatever the number of holds."""
    labels, wanted = {}, {}
    for hold in holds:
        if hold.user_id:
            labels[hold.pk] = f"Account #{hold.user_id}"
        else:
            wanted.setdefault(hold.target_type_id, []).append(hold)
    for type_id, group in wanted.items():
        model = ContentType.objects.get_for_id(type_id).model_class()
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        ids = [int(hold.target_id) for hold in group if hold.target_id.isdigit()]
        found = model._default_manager.in_bulk(ids)
        for hold in group:
            row = found.get(int(hold.target_id)) if hold.target_id.isdigit() else None
            if row is None:
                labels[hold.pk] = f"{model._meta.verbose_name.capitalize()} #{hold.target_id} (gone)"
            elif label == "staff.datarequest":
                labels[hold.pk] = f"Data request DR-{row.pk}"
            elif HOLD_TARGETS.get(label):
                labels[hold.pk] = f"{model._meta.verbose_name.capitalize()} {getattr(row, HOLD_TARGETS[label])}"
            else:
                labels[hold.pk] = f"{model._meta.verbose_name.capitalize()} #{row.pk}"
    return labels


def held_order_ids(today=None):
    """The orders a legal hold keeps as they are (the retention's clean-up leaves them): held themselves, through one
    of their documents, payments or refunds, or through their customer."""
    from accounts.models import LegalHold
    from shop.models import CreditNote, Invoice, Order, Payment, Refund

    ids, users, by_type = set(), [], {}
    for hold in LegalHold.objects.active(today).only("user_id", "target_type_id", "target_id"):
        if hold.user_id:
            users.append(hold.user_id)
        elif hold.target_id.isdigit():
            by_type.setdefault(hold.target_type_id, []).append(int(hold.target_id))
    if users:
        ids |= set(Order.objects.filter(user__in=users).values_list("pk", flat=True))
    to_order = {Order: "pk", Invoice: "order_id", CreditNote: "invoice__order_id", Payment: "order_id"}
    to_order[Refund] = "order_id"
    for type_id, pks in by_type.items():
        model = ContentType.objects.get_for_id(type_id).model_class()
        if model in to_order:
            ids |= set(model.objects.filter(pk__in=pks).values_list(to_order[model], flat=True))
    return ids


def user_holds(user):
    """The active legal holds on the person, and on the records of theirs that a hold may name."""
    from accounts.models import LegalHold
    from shop.models import CreditNote, Invoice, Order, Payment, Refund

    owned = {
        Order: Order.objects.filter(user=user),
        Invoice: Invoice.objects.filter(order__user=user),
        CreditNote: CreditNote.objects.filter(invoice__order__user=user),
        Payment: Payment.objects.filter(order__user=user),
        Refund: Refund.objects.filter(order__user=user),
        DataRequest: DataRequest.objects.filter(user=user),
    }
    query = Q(user=user)
    for model, rows in owned.items():
        ids = [str(pk) for pk in rows.values_list("pk", flat=True)]
        if ids:
            query |= Q(target_type=ContentType.objects.get_for_model(model), target_id__in=ids)
    return list(LegalHold.objects.active().filter(query).order_by("pk"))


# The erasure: its holds and its dry run


def parent_confirmed(user, deletion=None, data_request=None):
    """Whether a student under 18's parent or guardian confirmed the erasure: through their link (the deletion
    request's parent_confirmed_at), or as staff recorded it on the data request (details: parent_confirmed)."""
    deletion = deletion or user.pending_deletion
    if deletion is not None and deletion.parent_confirmed_at:
        return True
    details = data_request.details if data_request is not None else {}
    return bool(details.get("parent_confirmed") or details.get("parent_confirmed_at"))


def erasure_holds(user, deletion=None, data_request=None):
    """What holds an erasure back now, in words (each a `blocks` line of the dry run too; DeletionRequest.complete
    waits for them): a legal hold on the person, a student under 18 whose parent or guardian has not confirmed."""
    from accounts.models import LegalHold

    reasons = []
    for hold in LegalHold.objects.active().filter(user=user).order_by("pk"):
        until = f"until {day(hold.until)}" if hold.until else "until it is released"
        reasons.append(f"A legal hold ({hold.get_reason_display()}, hold {hold.pk}) keeps the account {until}.")
    if user.is_minor and not parent_confirmed(user, deletion, data_request):
        reasons.append(
            "A student under 18: the parent or guardian confirms the erasure first (through the link sent to them, "
            "or staff record their confirmation with the evidence)."
        )
    return reasons


def _keep(kind, part, what, count, why, until):
    when = f"kept until {day(until)}" if until else "kept"
    return {
        "kind": kind,
        "part": part,
        "what": what,
        "count": count,
        "why": why,
        "until": until,
        "line": f"{when}: {what}, {why}",
    }


def books_lines(user):
    """The books of account a person's erasure keeps, a line per financial year: its invoices, credit notes and the
    orders behind them, until examleaf.retention.books_until; and the orders without an invoice (the test series
    left out: not books)."""
    from shop.models import CreditNote, Invoice, Order

    years = {}
    invoices = Invoice.objects.filter(order__user=user).exclude(financial_year__startswith="T")
    for year, count in invoices.values_list("financial_year").annotate(n=Count("pk")).order_by():
        years.setdefault(year, {"invoices": 0, "notes": 0})["invoices"] = count
    notes = CreditNote.objects.filter(invoice__order__user=user).exclude(financial_year__startswith="T")
    for year, count in notes.values_list("financial_year").annotate(n=Count("pk")).order_by():
        years.setdefault(year, {"invoices": 0, "notes": 0})["notes"] = count
    lines = []
    why = "for GST and the Companies Act (8 financial years, or 72 months after the year's annual return)"
    for year in sorted(years):
        invoices_n, notes_n = years[year]["invoices"], years[year]["notes"]
        documents = [plural(invoices_n, "invoice", "invoices")] if invoices_n else []
        documents += [plural(notes_n, "credit note", "credit notes")] if notes_n else []
        behind = "the order behind it" if invoices_n + notes_n == 1 else "the orders behind them"
        what = f"{' and '.join(documents)} of {year} with {behind}"
        lines.append(_keep("books", f"books:{year}", what, invoices_n + notes_n, why, retention.books_until(year)))
    loose = Order.objects.filter(user=user, livemode=True, invoice=None)
    if latest := loose.aggregate(latest=Max("created"))["latest"]:
        count = loose.count()
        year = retention.financial_year_of(timezone.localdate(latest))
        what = plural(count, "order", "orders") + " without an invoice (unpaid or cancelled)"
        why_loose = "with the books; an order never paid loses the customer's details 30 days after its cancellation"
        lines.append(_keep("books", "orders", what, count, why_loose, retention.books_until(year)))
    if tests := Order.objects.filter(user=user, livemode=False).count():  # apart: the T series is not the books
        what = plural(tests, "order", "orders") + " made in test mode"
        lines.append(_keep("test", "test_orders", what, tests, "as they are: not books of account", None))
    return lines


def processing_log_lines(user):
    """The year of processing logs a person's erasure keeps (DPDP Rules r.8(3); CERT-In's logs): the audit log's
    events about the account (by its number only), and the SMS log's rows (without the account, after it)."""
    lines = []
    events = AuditEvent.objects.filter(Q(target_type="accounts.user", target_id=str(user.pk)) | Q(actor_id=user.pk))
    chains = events.values("chain").annotate(n=Count("pk"), latest=Max("ts")).order_by("chain")
    for chain in chains:
        money = chain["chain"] == AuditEvent.Chain.MONEY
        until = retention.audit_kept_until(chain["latest"], money=money)
        what = plural(chain["n"], "event", "events") + (" of money" if money else "") + " in the staff audit log"
        why = "naming the account by its number only (the audit log: " + (
            "8 financial years for money)" if money else "two years)"
        )
        lines.append(_keep("processing_logs", f"audit:{chain['chain']}", what, chain["n"], why, until))
    sms = user.sms_messages.aggregate(n=Count("pk"), latest=Max("created"))
    if sms["n"]:
        until = retention.kept_until("sms_log", sms["latest"])
        what = plural(sms["n"], "row", "rows") + " of the SMS log, without the account or the number's last digits"
        why = "processing logs (CERT-In's 180 days now, a year from 13 May 2027)"
        lines.append(_keep("processing_logs", "sms", what, sms["n"], why, until))
    return lines


def hold_lines(user):
    """The legal holds on the person or on records of theirs: a line each, kept until its end or its release."""
    holds = user_holds(user)
    labels = hold_labels(holds)
    lines = []
    for hold in holds:
        what = "the account" if hold.user_id else labels[hold.pk]
        why = f"under a legal hold ({hold.get_reason_display()}){'' if hold.until else ', until released'}"
        lines.append(_keep("legal_hold", f"hold:{hold.pk}", what, 1, why, hold.until))
    return lines


def erasure_report(user, data_request=None):
    """The dry run of an erasure (research 4.5): what DeletionRequest.complete would erase now, with counts; what
    stays, why and until when (`line`: "kept until 31 March 2035: 3 invoices of 2026-27 with the orders behind them,
    for GST and the Companies Act"): the books, a year of processing logs, the legal holds, the intermediary rule's
    180 days when on, the consents; and what stops it now (`blocks`). Nothing is changed."""
    from allauth.account.models import EmailAddress
    from axes.models import AccessAttempt

    from accounts.models import ConsentRecord, Nominee, TeacherProfile
    from shop.models import Order, QuoteRequest, Refund, StockAlert

    erase = [
        ("profile", "name, email address, phones, date of birth, district, parent's details", 1),
        ("email_addresses", "email addresses", EmailAddress.objects.filter(user=user).count()),
        ("authenticators", "passkeys and authenticator apps", user.authenticator_set.count()),
        ("google_accounts", "Google accounts connected", user.socialaccount_set.count()),
        ("sessions", "signed-in devices", user.usersession_set.count()),
        ("teacher_profile", "teacher access request", TeacherProfile.objects.filter(user=user).count()),
        ("nominee", "the nominee recorded", Nominee.objects.filter(user=user).count()),
        ("attempt_notes", "notes on saved marks", user.attempts.exclude(notes="").count()),
        ("answer_sheets", "answer sheets and their photos", user.answer_sheets.count()),
        ("addresses", "saved addresses", user.addresses.count()),
        ("reviews", "reviews", user.reviews.count()),
        (
            "stock_alerts",
            "'email me when it is back' requests",
            StockAlert.objects.filter(email__iexact=user.email).count(),
        ),
        (
            "failed_logins",
            "failed log-ins",
            AccessAttempt.objects.filter(username__in=[user.email, user.login_phone or user.email]).count(),
        ),
        ("roles", "roles and permissions", user.groups.count()),
    ]
    today = timezone.localdate()
    keep = [*books_lines(user), *processing_log_lines(user), *hold_lines(user)]
    if intermediary_rules():
        keep.append(
            _keep(
                "intermediary",
                "registration",
                "the details given to register (name, email address, numbers, date of birth, the parent's details)",
                1,
                "the IT Rules' r.3(1)(h): 180 days after the account closes",
                today + timedelta(days=180),
            )
        )
    consents = ConsentRecord.objects.filter(user=user).count()
    if consents:
        keep.append(
            _keep(
                "consent",
                "consents",
                plural(consents, "consent record", "consent records") + ", without the address hash",
                consents,
                "proof of the notice and the consent (DPDP s.6(10); the limitation period of 3 years)",
                date(today.year + 3, today.month, min(today.day, 28)),
            )
        )
    if attempts := user.attempts.count():
        keep.append(
            _keep(
                "statistics",
                "attempts",
                plural(attempts, "saved mark", "saved marks"),
                attempts,
                "as anonymous statistics: no personal data left",
                None,
            )  # fmt: skip
        )
    if quotes := QuoteRequest.objects.filter(email__iexact=user.email).count():
        keep.append(
            _keep(
                "by_hand",
                "quote_requests",
                plural(quotes, "quotation request", "quotation requests"),
                quotes,
                "made with the address: not erased by the purge, delete them by hand (RUNBOOK.md)",
                None,
            )  # fmt: skip
        )
    blocks = []
    if user.is_staff or user.is_superuser:
        blocks.append("A member of staff: offboard them first (people/<id>/offboard/).")
    if user.email.endswith("@deleted.invalid"):
        blocks.append("The account is erased already.")
    on_the_way = [Order.Status.PAID, Order.Status.PACKED, Order.Status.SHIPPED]
    if Order.objects.filter(user=user, status__in=on_the_way).exists():
        blocks.append("An order is on its way: wait until it is delivered, cancelled or refunded.")
    if Refund.objects.filter(order__user=user, status=Refund.Status.PENDING).exists():
        blocks.append("A refund is under way: wait until it is done.")
    if data_request is not None and not data_request.identity_verified:
        blocks.append("The requester's identity is not verified yet.")
    blocks += erasure_holds(user, data_request=data_request)
    told = list(ProcessorRecord.objects.filter(active=True, holds_personal_data=True).values_list("name", flat=True))
    notes = [f"Once it is done, the inbox asks to tell: {', '.join(told)}."] if told else []
    return {
        "erase": [{"part": part, "what": what, "count": count} for part, what, count in erase],
        "keep": keep,
        "blocks": blocks,
        "can_erase": not blocks,
        "notes": notes,
    }


# After an erasure, or a withdrawn consent: the processors' tasks, the ledger


def ledger_hash(email, secret=None):
    """The erasure ledger's keyed hash of an email address (DeletionRequest.subject_hash): enough to know the account
    again after a restore, not to read the address back."""
    return salted_hmac("accounts.DeletionRequest.subject", (email or "").strip().lower(), secret=secret,
                       algorithm="sha256").hexdigest()  # fmt: skip


def ledger_matches(email, digest):
    """Whether an address is the one a ledger line hashed, with SECRET_KEY or one of its fallbacks (a key rotated
    since)."""
    secrets = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return any(constant_time_compare(ledger_hash(email, secret), digest) for secret in secrets)


def processor_tasks(deletion, data_request=None):
    """One inbox item per processor in use whose record says it keeps personal data (research 4.5, s.8(7)(b)): what to
    ask them (their `erasure_action`), with the erasure's number, for those who keep the compliance duties (OWNER,
    ADMIN). Titles name the account by its number only."""
    reference = f"DR-{data_request.pk}" if data_request is not None else f"deletion {deletion.pk}"
    for processor in ProcessorRecord.objects.filter(active=True, holds_personal_data=True).order_by("name"):
        action = processor.erasure_action or f"ask {processor.name} to erase what they keep of it"
        InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.PROCESSOR_TASK,
            target_type="staff.processorrecord",
            target_id=f"{processor.pk}:erasure:{deletion.pk}"[:64],
            done_at=None,
            defaults={
                "title": f"Erasure of account #{deletion.user_id} ({reference}): {action} ({processor.name})"[:200],
                "permission": "staff.manage_compliance",
                "data": {
                    "processor": processor.pk,
                    "deletion_request": deletion.pk,
                    "account": deletion.user_id,
                    "data_request": getattr(data_request, "pk", None),
                },  # fmt: skip
            },
        )


def after_erasure(deletion, data_request=None):
    """Once an erasure is committed: the processors' tasks, and the ledger's line copied off the server."""
    from accounts.tasks import copy_erasure_ledger

    processor_tasks(deletion, data_request)
    copy_erasure_ledger.delay(deletion.pk)


def cease_tasks(consent):
    """A marketing consent withdrawn: one inbox item per processor in use that holds marketing data, to make it stop
    (s.6(6)), for those who keep the compliance duties."""
    channel = consent.get_channel_display() if consent.channel else "every channel"
    for processor in ProcessorRecord.objects.filter(active=True, holds_marketing_data=True).order_by("name"):
        InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.PROCESSOR_TASK,
            target_type="staff.processorrecord",
            target_id=f"{processor.pk}:cease:{consent.pk}"[:64],
            done_at=None,
            defaults={
                "title": f"Marketing consent withdrawn by account #{consent.user_id} ({channel}): tell "
                f"{processor.name} to stop"[:200],
                "permission": "staff.manage_compliance",
                "data": {"processor": processor.pk, "consent": consent.pk, "account": consent.user_id},
            },
        )


# The answers


RESPONSES = {
    Kind.ACCESS: "We attach a copy of the personal data we keep about the account, with the processors who handle it "
    "for us.",
    Kind.CORRECTION: "We have corrected the details as you asked.",
    Kind.ERASURE: "We have erased the account's personal data. What the law makes us keep, and until when, is below.",
    Kind.NOMINATION: "We have recorded the person you nominated to act for you in case of your death or incapacity.",
    Kind.GRIEVANCE: "We have looked into your grievance; what we found and did is below.",
    Kind.COMPLAINT: "We have looked into your complaint; what we found and did is below.",
}


def recipients_text():
    lines = [f"- {row['name']}: {row['purpose']} ({row['data_categories']}; {row['country']})" for row in recipients()]
    return "\n".join(lines) or "- nobody else"


def response_text(data_request):
    """The answer's subject and text for staff to complete and send, with the contact block (DPDP r.9): an access
    request's names who else processes the data (the processor register, s.11(1)(b)); an erasure's says what stays
    and until when (the dry run's lines)."""
    received = timezone.localtime(data_request.received_at)
    parts = [
        "Hello,",
        f"We received your request ({data_request.get_kind_display()}) on {received:%d %B %Y}, reference "
        f"DR-{data_request.pk}.",
        RESPONSES[data_request.kind],
    ]
    if data_request.kind == Kind.ACCESS:
        parts.append(f"Who processes it for us:\n{recipients_text()}")
    if data_request.kind == Kind.ERASURE and data_request.user is not None:
        kept = [row["line"] for row in erasure_report(data_request.user, data_request)["keep"]]
        parts.append("What we keep:\n" + ("\n".join(f"- {line[0].upper()}{line[1:]}" for line in kept) or "- nothing"))
    parts.append("[What we did]")
    officer = grievance_officer() or "[not set yet: Legal and privacy, Disclosures]"
    parts.append(
        f"If you are not satisfied with this answer, write to our Grievance Officer: {officer}. Under the Digital "
        "Personal Data Protection Act, 2023 you may also complain to the Data Protection Board of India once you "
        "have used this process."
    )
    parts.append(contact_block(draft=True))
    return {"subject": f"Your request DR-{data_request.pk} to ExamLeaf", "body": "\n\n".join(parts)}


def erasure_confirmation(user, data_request=None):
    """The email that tells a person their account is erased (research 4.5; DPDP r.9): what stays and until when,
    and the contact block. Made before the erasure (its dry run reads the account), sent after it."""
    kept = [row["line"] for row in erasure_report(user, data_request)["keep"]]
    body = ["Your ExamLeaf account and the personal details in it have been deleted, as you asked."]
    if kept:
        body.append("What the law makes us keep:\n" + "\n".join(f"- {line[0].upper()}{line[1:]}" for line in kept))
    if block := contact_block():
        body.append(block)
    return "Your account has been deleted", "\n\n".join(body)
