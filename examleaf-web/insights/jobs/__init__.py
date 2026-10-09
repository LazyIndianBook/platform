"""What the jobs share: a run's record, keyed hashes, districts from PIN codes, the orders that count as sales, a
season's weeks and the copies sold in them. Each job is a function over the database's rows that writes its own rows
in one transaction; insights/tasks.py runs them at night and `manage.py insights_run` by hand."""

import logging
import math
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from shop.models import OrderItem, PinCode, Product, StockAlert

from ..metrics import live_orders as counted_orders  # noqa: F401  (the one place that says which orders count)
from ..models import ExamSeason, ForecastRun

logger = logging.getLogger("insights")

WEEKS = 52  # a season: the 52 weeks before its exam
HIDDEN_BELOW = 5  # learners: a smaller group shows its size, never its shares
KEEP = timedelta(days=90)  # runs and stat rows older than this are deleted by the next run of their job
UNKNOWN = "unknown"  # a district: neither the directory nor the address gives one
PRINTED = [Product.Kind.SAMPLE_PAPERS, Product.Kind.SOLUTIONS]  # books with copies of their own (bundles sell these)


def digest(kind, value):
    """A keyed hash of an account id, IP address, phone number, address or code (INSIGHTS_HASH_SALT, else SECRET_KEY):
    equal values match, none can be read back."""
    secret = settings.INSIGHTS_HASH_SALT or settings.SECRET_KEY
    return salted_hmac(f"insights.{kind}", str(value), secret=secret, algorithm="sha256").hexdigest()


def districts_of(addresses):
    """{PIN code: district} for these address snapshots, from India Post's directory (a PIN on a border: the first)."""
    pins = {address.get("pin") for address in addresses}
    rows = PinCode.objects.filter(pin__in=pins).values_list("pin", "districts")
    return {pin: names[0] for pin, names in rows if names}


def district(address, known):
    """An order's district: its PIN code's in the directory (`known`), else the one typed in the address."""
    return known.get(address.get("pin")) or str(address.get("district", "")).strip() or UNKNOWN


def week_index(season, day):
    """The index of a day's week in the season, 0 (the first) to 51 (the week before the exam); None outside it."""
    days = (season.exam_start - day).days
    return WEEKS - math.ceil(days / 7) if 1 <= days <= WEEKS * 7 else None


def week_start(season, index):
    return season.exam_start - timedelta(weeks=WEEKS - index)


def seasons_around(board_id, level_id, today):
    """(The season whose exam comes next after today, the one before it, the one before that); None if not entered."""
    seasons = list(ExamSeason.objects.filter(board=board_id, class_level=level_id).order_by("exam_start"))
    ahead = next((i for i, season in enumerate(seasons) if season.exam_start > today), None)
    if ahead is None:
        return None, None, None
    return seasons[ahead], *(seasons[i] if i >= 0 else None for i in (ahead - 1, ahead - 2))


def printed_books():
    """Every printed book with a subject (its board and class give its exam), with `wanted`: on sale or with a print
    cost entered, the ones forecast and advised on."""
    books = Product.objects.filter(kind__in=PRINTED, subject__isnull=False).select_related("subject")
    wanted = set(books.filter(Q(is_active=True) | Q(print_cost__isnull=False)).values_list("pk", flat=True))
    for book in books:
        book.wanted = book.pk in wanted
        yield book


def history(season, books):
    """Copies of each of these books (ids) sold in the season's weeks: {id: (52 weekly counts, Counter of copies by
    district)}. A bundle's copies count for its books, as stock does. A request to be emailed once a book is back in
    stock counts as a copy that week: demand that the stock-out hid."""
    start, end = season.exam_start - timedelta(weeks=WEEKS), season.exam_start
    sold = defaultdict(lambda: ([0.0] * WEEKS, Counter()))
    items = OrderItem.objects.filter(
        order__in=counted_orders(), order__placed_at__date__gte=start, order__placed_at__date__lt=end
    )
    rows = list(items.values_list("product_id", "quantity", "order__placed_at", "order__shipping_address"))
    known = districts_of(address for *_, address in rows)
    # ponytail: a bundle splits into the books it holds today, not when it was sold; keep the split on OrderItem if
    # bundles change mid-season
    lines = {pk: product.stock_lines(1) for pk, product in Product.objects.in_bulk({row[0] for row in rows}).items()}
    for product_id, quantity, placed_at, address in rows:
        index, where = week_index(season, timezone.localdate(placed_at)), district(address, known)
        for book, copies in lines[product_id].items():
            if book in books:
                sold[book][0][index] += copies * quantity
                sold[book][1][where] += copies * quantity
    # ponytail: an alert is deleted once its email goes (shop.tasks.send_stock_alerts), so only requests still waiting
    # count; keep a weekly count per title if stock-outs become common
    alerts = StockAlert.objects.filter(product__in=books, created__date__gte=start, created__date__lt=end)
    for book, created in alerts.values_list("product_id", "created"):
        sold[book][0][week_index(season, timezone.localdate(created))] += 1
    return sold


def latest(kind):
    """The newest finished run of this kind, or None."""
    return ForecastRun.objects.filter(kind=kind, status=ForecastRun.Status.DONE).first()


@contextmanager
def run(kind, method, **params):
    """The ForecastRun of a job: "running" while it works, then "done", or "skipped" when the job says so (the reason
    in the notes). On an error it is "failed", the error in its notes, and the error is raised again for Celery to
    retry and Sentry to report. The job's rows are written in one transaction; runs older than KEEP go."""
    record = ForecastRun.objects.create(
        kind=kind, method=method, params=params, data_as_of=timezone.now(), code_version=settings.RELEASE
    )
    try:
        with transaction.atomic():
            yield record
    except Exception as error:
        record.status, record.notes = ForecastRun.Status.FAILED, f"{type(error).__name__}: {error}"[:2000]
        record.save(update_fields=["status", "notes"])
        raise
    if record.status == ForecastRun.Status.RUNNING:
        record.status = ForecastRun.Status.DONE
    record.save(update_fields=["status", "notes", "params"])
    ForecastRun.objects.filter(kind=kind, created__lt=timezone.now() - KEEP).delete()
    logger.info("insights %s run %s %s. %s", kind, record.pk, record.status, record.notes)


def save_stats(model, rows, now):
    """A stat job's rows (all computed at `now`), and the deletion of its rows older than KEEP. Returns how many."""
    model.objects.bulk_create(rows)
    model.objects.filter(computed_at__lt=now - KEEP).delete()
    logger.info("insights %s: %s rows", model._meta.model_name, len(rows))
    return len(rows)
