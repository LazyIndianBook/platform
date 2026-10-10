"""Book codes for staff (plan 5.11 and 5.16; learn/README.md "Book codes"; the staff API in learn/staff_api.py): a
print run's batch made by a staff job (Job.Kind.CODE_BATCH) that keeps only the codes' digests and writes the codes
once, into the printer's file, its starter's alone to download for PRINTER_FILE_HOURS (then deleted: staff.jobs'
files' purge, hourly for these: learn.tasks); a batch marked dispatched (a code redeemed before is a leak: insights'
fraud rules) or voided (its unused codes refuse to open anything), a code voided alone, a typed or scanned code
looked up by its digest, and the codes report: printed, sold, activated and revoked by batch, by district with the
small cells hidden. No code is ever kept, logged or answered in the clear but in the printer's file."""

import csv
import io
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, TruncWeek
from django.utils import timezone
from rest_framework import serializers

from staff import audit
from staff.backends import scoped
from staff.models import Job

from .models import CODE_ALPHABET, CODE_LENGTH, BookCode, CodeBatch, Entitlement, clean_code, code_digest
from .services import make_codes

PRINTER_FILE_HOURS = 24  # the printer's file: its starter's to download this long after the job, then deleted
MAX_CODES = 100_000  # at a time, as make_book_codes
MIN_CELL = 10  # the codes report's districts: a cell under it is "fewer than 10" (plan 5.16)
REPORT_BATCHES = 200  # the newest print runs in the report
CODE_SIGNALS = [  # insights' fraud rules about book codes (FraudSignal.Kind)
    "codes_failed_account",
    "codes_failed_ip",
    "codes_failed_device",
    "codes_failed_spike",
    "codes_per_account",
    "accounts_per_code",
    "codes_undispatched",
]


def refused(message, field="non_field_errors"):
    return serializers.ValidationError({field: [message]})


def code_text(code):
    """A typed or scanned code, cleaned and checked: its 12 characters, or a ValidationError."""
    cleaned = clean_code(code)
    if len(cleaned) != CODE_LENGTH or set(cleaned) - set(CODE_ALPHABET):
        raise refused("A book code has 12 letters and digits, like 7KQM-3XPA-9TRW (no 0, O, 1 or I).", "code")
    return cleaned


def target(batch):
    return ("learn.codebatch", batch.pk, f"Code batch {batch.label}")


# ---- A batch: made by its job, dispatched, voided ----


def state(batch):
    """generating (its job queued or running), failed (its job ended without codes), ready, dispatched or void."""
    if batch.voided_at:
        return "void"
    if batch.generated_at is None:
        running = batch.job is not None and batch.job.state in (Job.State.QUEUED, Job.State.RUNNING)
        return "generating" if running else "failed"
    return "dispatched" if batch.dispatched_at else "ready"


def file_until(batch):
    """Until when the printer's file can be downloaded (by the job's starter), or None: gone, or never made."""
    job = batch.job
    if job is None or not job.result_file or job.finished_at is None:
        return None
    until = job.finished_at + timedelta(hours=PRINTER_FILE_HOURS)
    return until if until > timezone.now() else None


def start(*, label, subject, count, product, note, user, request=None):
    """A new batch, and the job that makes its codes (202: the job; the batch shows "generating" until it is done).
    `subject` None: codes that open every subject (a set of four books)."""
    from staff import jobs

    if not 1 <= count <= MAX_CODES:
        raise refused(f"From 1 to {MAX_CODES:,} codes at a time.", "count")
    taken = refused("A print run has this label already: give the new one its own (PHY-2027-2).", "label")
    with transaction.atomic():
        if CodeBatch.objects.filter(label__iexact=label).exists() or BookCode.objects.filter(batch=label).exists():
            raise taken
        try:
            with transaction.atomic():
                batch = CodeBatch.objects.create(
                    label=label, subject=subject, product=product, printed=count, note=note, generated_by=user
                )
        except IntegrityError:  # the same label asked for at the same moment
            raise taken from None
        job = jobs.start(
            Job.Kind.CODE_BATCH, {"batch": batch.pk, "label": label, "count": count}, user=user, request=request
        )
        batch.job = job
        batch.save(update_fields=["job"])
        details = {"count": count, "subject": subject.code if subject else "all", "job": job.pk}
        audit.record("course.batch_requested", request=request, target=target(batch), details=details)
    return batch


def job_params(params):
    """POST jobs/ with kind code_batch: a batch whose codes were never made (its first job failed), made again."""
    pk = params.get("batch") if isinstance(params, dict) else None
    batch = CodeBatch.objects.select_related("job").filter(pk=pk).first() if isinstance(pk, int) else None
    if batch is None:
        raise serializers.ValidationError({"params": {"batch": ["A batch made from course/codes/batches/."]}})
    if state(batch) != "failed":
        raise serializers.ValidationError({"params": {"batch": [f"It is {state(batch)}: nothing to make again."]}})
    return {"batch": batch.pk, "label": batch.label, "count": batch.printed}


def run_job(job, progress):
    """The job (staff.jobs RUNNERS): the batch's codes made and their digests kept, the codes written once into the
    printer's file (CSV: code, batch, subject), all in one transaction (a failure or a cancel leaves no code); the
    owners told. Returns its result: no code, only the counts."""
    with transaction.atomic():
        batch = (
            CodeBatch.objects.select_for_update().select_related("subject", "generated_by").get(pk=job.params["batch"])
        )
        if batch.generated_at is not None or batch.voided_at is not None:
            raise refused("Its codes were made already, or it was voided.")
        job.total = batch.printed
        codes = make_codes(batch.subject, batch.printed, batch.label, tick=progress.row)
        subject = batch.subject.code if batch.subject else "ALL"
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(["code", "batch", "subject"])
        writer.writerows([code, batch.label, subject] for code in codes)
        name = f"staff/jobs/{job.pk}/{batch.label}-book-codes.csv"
        job.result_file = default_storage.save(name, ContentFile(text.getvalue().encode()))
        batch.generated_at, batch.job = timezone.now(), job
        batch.save(update_fields=["generated_at", "job"])
        by = job.started_by
        audit.record("course.codes_made", actor=by, target=target(batch), details={"count": len(codes), "job": job.pk})
        audit.alert(
            f"Book codes made: batch {batch.label}",
            f"{len(codes):,} book codes ({subject}) were made for the print run {batch.label} by staff "
            f"#{getattr(by, 'pk', None)}. The printer's file is theirs to download for {PRINTER_FILE_HOURS} hours, "
            "then it is deleted.",
        )
    return {"batch": batch.label, "codes": len(codes)}


def dispatched(batch, at, *, by, request=None):
    """The books of the print run left (at `at`, now by default): a code redeemed before it is a leak."""
    now = timezone.now()
    with transaction.atomic():
        batch = CodeBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.voided_at:
            raise refused("It was voided.")
        if batch.generated_at is None:
            raise refused("Its codes are not made yet.")
        if batch.dispatched_at:
            raise refused(f"Marked dispatched already, on {timezone.localtime(batch.dispatched_at):%d %b %Y}.")
        at = at or now
        if at > now:
            raise refused("Not in the future: the day the books left.", "at")
        if at < batch.generated_at:
            raise refused("Not before its codes were made.", "at")
        batch.dispatched_at = at
        batch.save(update_fields=["dispatched_at"])
        audit.record("course.batch_dispatched", request=request, actor=by, target=target(batch), details={"at": at})
    return batch


def void_batch(batch, reason, *, by, request=None):
    """Every unused code of the batch voided (a leaked or lost print run): a redemption of one is refused from now;
    the codes redeemed already keep what they opened. The printer's file, if still there, goes. Returns (batch,
    codes voided)."""
    if not str(reason or "").strip():
        raise refused("Say why.", "reason")
    with transaction.atomic():
        batch = CodeBatch.objects.select_for_update().select_related("job").get(pk=batch.pk)
        if batch.voided_at:
            raise refused("It was voided already.")
        if batch.generated_at is None:
            raise refused("Its codes are not made yet: nothing to void.")
        now = timezone.now()
        voided = BookCode.objects.filter(batch=batch.label, redeemed_at__isnull=True, voided_at__isnull=True).update(
            voided_at=now
        )
        batch.voided_at, batch.void_reason = now, str(reason).strip()[:300]
        batch.save(update_fields=["voided_at", "void_reason"])
        job = batch.job
        if job is not None and job.result_file:
            name = job.result_file
            Job.objects.filter(pk=job.pk).update(result_file="")
            transaction.on_commit(lambda: default_storage.delete(name), robust=True)
        audit.record("course.batch_voided", request=request, actor=by, target=target(batch), reason=reason,
                     details={"voided": voided})  # fmt: skip
        audit.alert(
            f"Book codes voided: batch {batch.label}",
            f"{voided:,} unused codes of the print run {batch.label} were voided by staff #{by.pk}. Reason: {reason}",
        )
    return batch, voided


def void_code(code, reason, *, by, request=None):
    """One unused code voided (a leaked one): redeeming it is refused from now."""
    cleaned = code_text(code)
    if not str(reason or "").strip():
        raise refused("Say why.", "reason")
    with transaction.atomic():
        found = scoped(BookCode.objects.all(), by, "staff.void_book_codes").filter(digest=code_digest(cleaned))
        book_code = found.select_for_update().first()
        if book_code is None:
            raise refused("No such code: check it against the one printed in the book.", "code")
        if book_code.voided_at:
            raise refused("It is void already.", "code")
        if book_code.redeemed_at:
            raise refused("It was redeemed already: revoke the access it opened instead (the learner's page).", "code")
        book_code.voided_at = timezone.now()
        book_code.save(update_fields=["voided_at"])
        audit.record("course.code_voided", request=request, actor=by, target=book_code, reason=reason,
                     details={"batch": book_code.batch, "code_hash": code_hash(cleaned)})  # fmt: skip
        audit.alert(
            f"A book code voided (batch {book_code.batch})",
            f"Book code #{book_code.pk} of the print run {book_code.batch} was voided by staff #{by.pk}. "
            f"Reason: {reason}",
        )
    return book_code


def code_hash(cleaned):
    """The keyed hash insights keeps of a code tried (RedemptionAttempt.code_hash): a lookup matches its tries."""
    from insights.jobs import digest

    return digest("code", cleaned)


# ---- The lookup: a typed or scanned code, in one line ----


def lookup(code, reader, request=None):
    """unused, redeemed (when, and by which account: a link, the address masked), void, or unknown; by the code's
    digest, never kept. Audited (`course.code_lookup` with the code's keyed hash); a redeemer shown is a
    `sensitive_read` of their account (a child's marked so)."""
    from staff.privacy import mask_email

    cleaned = code_text(code)
    found = scoped(BookCode.objects.select_related("subject", "redeemed_by"), reader, "learn.view_bookcode")
    book_code = found.filter(digest=code_digest(cleaned)).first()
    answer = {"state": "unknown", "batch": None, "subject": None, "redeemed_at": None, "redeemed_by": None,
              "voided_at": None, "batch_state": None}  # fmt: skip
    if book_code is None:
        answer["line"] = "No such code: check it against the one printed in the book (a code has no 0, O, 1 or I)."
    else:
        batch = CodeBatch.objects.select_related("job").filter(label=book_code.batch).first()
        subject = book_code.subject.name if book_code.subject_id else "every subject"
        answer |= {"batch": book_code.batch, "subject": subject, "batch_state": state(batch) if batch else None}
        if book_code.voided_at:
            why = f" ({batch.void_reason})" if batch and batch.voided_at and batch.void_reason else ""
            answer |= {"state": "void", "voided_at": book_code.voided_at}
            answer["line"] = (
                f"Void since {timezone.localtime(book_code.voided_at):%d %b %Y}{why}: batch {book_code.batch} "
                f"({subject}). It opens nothing."
            )
        elif book_code.redeemed_at:
            user = book_code.redeemed_by
            on = f"{timezone.localtime(book_code.redeemed_at):%d %b %Y}"
            answer |= {"state": "redeemed", "redeemed_at": book_code.redeemed_at}
            if user is not None:
                answer["redeemed_by"] = {"id": user.pk, "email": mask_email(user.email), "is_minor": user.is_minor}
                answer["line"] = f"Redeemed on {on} by account #{user.pk}: batch {book_code.batch} ({subject})."
                audit.record("sensitive_read", request=request, target=user,
                             details={"what": "book_code", "child": user.is_minor})  # fmt: skip
            else:
                answer["line"] = f"Redeemed on {on} by an account since erased: batch {book_code.batch} ({subject})."
        else:
            answer |= {"state": "unused"}
            waiting = " Its batch is not marked dispatched yet." if batch and not batch.dispatched_at else ""
            answer["line"] = f"Not redeemed yet: batch {book_code.batch} ({subject}).{waiting}"
    audit.record("course.code_lookup", request=request, target=book_code,
                 details={"state": answer["state"], "code_hash": code_hash(cleaned)})  # fmt: skip
    return answer


# ---- What a batch's page and the list show ----


def with_counts(batches):
    """Each batch with its codes made, redeemed and void counted (a subquery each: no query per row)."""
    codes = BookCode.objects.filter(batch=OuterRef("label")).order_by().values("batch")

    def counted(condition):
        rows = codes.filter(condition).annotate(n=Count("pk")).values("n")[:1]
        return Coalesce(Subquery(rows), 0)

    return batches.annotate(
        codes=counted(Q()),
        redeemed=counted(Q(redeemed_at__isnull=False)),
        void=counted(Q(voided_at__isnull=False)),
    )


def redeemed_by_week(batch):
    """[{week: its Monday (India), redeemed: n}] of the batch's codes, oldest first."""
    rows = (
        BookCode.objects.filter(batch=batch.label, redeemed_at__isnull=False)
        .annotate(week=TruncWeek("redeemed_at"))
        .values("week")
        .annotate(n=Count("pk"))
        .order_by("week")
    )
    return [{"week": timezone.localdate(row["week"]), "redeemed": row["n"]} for row in rows]


def signals_for(batch, limit=50):
    """The fraud signals that name the batch (insights: its details' batch or batches), newest first.
    ponytail: read from the newest 500 signals of the code rules since the batch was made, as their details are JSON
    (no portable contains on SQLite); a batch field on FraudSignal if they grow."""
    from insights.models import FraudSignal

    rows = FraudSignal.objects.filter(kind__in=CODE_SIGNALS, created__gte=batch.created).order_by("-created")[:500]
    found = []
    for signal in rows:
        details = signal.details or {}
        if details.get("batch") == batch.label or batch.label in (details.get("batches") or []):
            found.append(signal)
    return found[:limit]


# ---- The codes report (plan 5.16): printed, sold, activated, revoked by batch, by district ----


def sold_copies(batches, today=None):
    """{batch id: copies of its book sold on the storefront}: lines of its product (and of bundles holding it) in the
    orders that count (paid or placed, not undone; test orders kept out on a live site) from its codes' day until the
    next batch of the same book. ponytail: a print run's sales are the book's in its window; ERPNext's B2B sales are
    not here (the school and distributor copies), until the sync brings them."""
    from insights.jobs import counted_orders
    from shop.models import BundleItem, OrderItem

    by_product = defaultdict(list)
    for batch in batches:
        if batch.product_id:
            by_product[batch.product_id].append(batch)
    if not by_product:
        return {}
    bundles = defaultdict(dict)  # bundle id → {book id: copies in one}
    for bundle, book, quantity in BundleItem.objects.filter(product__in=by_product).values_list(
        "bundle_id", "product_id", "quantity"
    ):
        bundles[bundle][book] = quantity
    starts = [batch.generated_at or batch.created for rows in by_product.values() for batch in rows]
    items = OrderItem.objects.filter(
        order__in=counted_orders(), order__placed_at__gte=min(starts), product__in=[*by_product, *bundles]
    ).values_list("product_id", "quantity", "order__placed_at")
    copies = defaultdict(list)  # book id → [(placed at, copies)]
    for product, quantity, placed_at in items:
        if product in by_product:
            copies[product].append((placed_at, quantity))
        for book, each in bundles.get(product, {}).items():
            copies[book].append((placed_at, quantity * each))
    sold = {}
    for product, rows in by_product.items():
        rows = sorted(rows, key=lambda batch: batch.generated_at or batch.created)
        for index, batch in enumerate(rows):
            start = batch.generated_at or batch.created
            end = (rows[index + 1].generated_at or rows[index + 1].created) if index + 1 < len(rows) else None
            sold[batch.pk] = sum(n for at, n in copies[product] if at >= start and (end is None or at < end))
    return sold


def districts(redeemed):
    """{batch label: Counter(district: codes)} for codes redeemed (batch, subject, account, when): the redeemer's last
    order of the code's subject before it, by its PIN code (insights.jobs.codes, as its nightly job counts them)."""
    from insights.jobs import UNKNOWN, district, districts_of
    from insights.jobs.codes import redeemers_orders

    orders = redeemers_orders({user for _, _, user, _ in redeemed if user})
    known = districts_of(address for rows in orders.values() for *_, address in rows)
    counts = defaultdict(Counter)
    for batch, subject, user, redeemed_at in redeemed:
        bought = [(placed_at, address) for placed_at, ordered, address in orders.get(user, [])
                  if placed_at <= redeemed_at and (subject is None or ordered == subject)]  # fmt: skip
        counts[batch][district(max(bought, key=lambda order: order[0])[1], known) if bought else UNKNOWN] += 1
    return counts


def district_cells(counts):
    """A batch's districts as cells: each of MIN_CELL redemptions or more by name; the others together as "other
    districts", hidden (null) while fewer than MIN_CELL."""
    cells, other = [], 0
    for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        if count >= MIN_CELL:
            cells.append({"district": name, "activated": count, "hidden": False})
        else:
            other += count
    if other:
        hidden = other < MIN_CELL
        cells.append({"district": "other districts", "activated": None if hidden else other, "hidden": hidden})
    return cells


def report(reader):
    """The codes report for `reader` (their scope of batches), the newest REPORT_BATCHES print runs: per batch the
    codes printed, the copies of its book sold, the codes activated (redeemed), revoked (the access they opened, taken
    back by staff), void, the activation rate (activated ÷ printed) and the districts. A handful of queries."""
    batches = list(
        with_counts(
            scoped(CodeBatch.objects.select_related("subject", "product"), reader, "learn.view_codebatch")
        ).order_by("-created", "-pk")[:REPORT_BATCHES]
    )
    labels = [batch.label for batch in batches]
    redeemed = list(
        BookCode.objects.filter(batch__in=labels, redeemed_at__isnull=False).values_list(
            "batch", "subject", "redeemed_by", "redeemed_at"
        )
    )
    places = districts(redeemed)
    revoked = Counter()
    refs = Entitlement.objects.filter(source=Entitlement.Source.BOOK_CODE, revoked_at__isnull=False)
    ids = [
        int(ref.split("#", 1)[1]) for ref in refs.values_list("reference", flat=True) if ref.split("#")[-1].isdigit()
    ]
    for start in range(0, len(ids), 500):  # the revoked ones are few: their codes' batches, 500 at a time
        for batch in BookCode.objects.filter(pk__in=ids[start : start + 500], batch__in=labels).values_list(
            "batch", flat=True
        ):
            revoked[batch] += 1
    sold = sold_copies(batches)
    rows = []
    for batch in batches:
        printed = batch.codes or batch.printed
        rows.append(
            {
                "batch": batch,
                "printed": printed,
                "sold": sold.get(batch.pk) if batch.product_id else None,
                "activated": batch.redeemed,
                "revoked": revoked[batch.label],
                "void": batch.void,
                "activation_rate": round(batch.redeemed / printed, 4) if printed else None,
                "districts": district_cells(places.get(batch.label, {})),
            }
        )
    return rows


def totals(rows):
    printed = sum(row["printed"] for row in rows)
    activated = sum(row["activated"] for row in rows)
    return {
        "printed": printed,
        "sold": sum(row["sold"] or 0 for row in rows),
        "activated": activated,
        "revoked": sum(row["revoked"] for row in rows),
        "void": sum(row["void"] for row in rows),
        "activation_rate": round(activated / printed, 4) if printed else None,
    }
