"""What ERPNext tells the platform (erp/README.md, "The flows"). A webhook is a doorbell only (Frappe tries
each one three times, then gives up): POST /api/hooks/erp-events/ checks its signature, keeps it and answers at once;
a task reads again what it rings about and applies it. The pull every 15 minutes reads what changed since each
doctype's cursor, the net under lost doorbells.

- Stock (a Stock Ledger Entry, which rings once per movement; a Purchase Receipt, a Stock Reconciliation;
  ERP_PULL_STOCK): ERPNext's stock of our items in ERP_WAREHOUSE, read with get_stock (the sync user may not read the
  stock documents themselves), one read for a burst of doorbells, kept as ErpStockSnapshot; with
  ERP_STOCK_PROJECTION the copies for sale follow it (project). Off (shadow mode), the snapshots are only compared,
  nightly (reconcile.py).
- B2B documents (Sales Invoice, Quotation, Customer of a B2B group; ERP_PULL_B2B): read again over REST and kept as
  a read-only copy, ErpMirror.
- Any other doctype: logged and ignored."""

import base64
import hashlib
import hmac
import logging
from collections import Counter

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from integrations.client import IntegrationError
from integrations.models import IntegrationAccount
from integrations.services import receive_event
from shop.models import Order, Product

from . import contract
from .client import client
from .models import ErpCursor, ErpMirror, ErpOutbox, ErpStockSnapshot
from .producers import switch

logger = logging.getLogger(__name__)
PAGE = 100  # rows per page of the pull
STOCK_DEBOUNCE = 30  # seconds: the stock doorbells of a burst of movements make one read


def signed(account, body, signature):
    """Whether `signature` is the base64 HMAC-SHA256 of the raw body with the account's webhook secret (its current
    one, or for 24 hours after a rotation the previous one). Constant time; no secret set: never (deny by default)."""
    given = signature.strip().encode()
    matches = False
    for secret in account.webhook_secrets():
        expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest())
        matches |= hmac.compare_digest(given, expected)
    return bool(given) and matches


class ErpEventsView(APIView):
    """POST /api/hooks/erp-events/: ERPNext's webhooks ({doctype, name, modified, examleaf_ref, event}). A missing or
    wrong signature, no enabled account, or ERP_ENABLED off: 403 (kept as a rejected event, without its body).
    Otherwise the raw body is kept (InboundEvent, once per SHA-256: a repeat is a duplicate), answered 200 at once and
    read again by a task. Throttled per client address."""

    authentication_classes = []  # the signature is the authentication
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "erp_events"

    @extend_schema(exclude=True)  # ERPNext's, not the API's
    def post(self, request, *args, **kwargs):
        body, signature = request.body, request.headers.get(contract.SIGNATURE_HEADER, "")
        account = IntegrationAccount.enabled_for("erpnext") if switch("ERP_ENABLED") else None
        if account is None or not signed(account, body, signature):
            receive_event("erpnext", body, request.headers, rejected=True)
            return Response({"detail": "Unknown or missing signature."}, status=status.HTTP_403_FORBIDDEN)
        receive_event("erpnext", body, request.headers, account=account)
        return Response({"detail": "Received."})


def ring(event):
    """A stored doorbell (tasks.process_inbound_event): "" once applied (or its stock read queued), else why nothing
    was done."""
    doctype, name = contract.doorbell(event.body)
    if doctype in contract.STOCK_DOCTYPES:
        if not switch("ERP_PULL_STOCK"):
            return "ignored: ERP_PULL_STOCK is off"
        return stock_soon()
    return apply(doctype, name)


def apply(doctype, name, erp=None):
    """Read a B2B document of ERPNext's again and keep it: "" once done, else why nothing was done."""
    if doctype not in contract.B2B_DOCTYPES:
        logger.info("ERPNext's doorbell for %s %s ignored: not a doctype the platform reads", doctype, name)
        return f"ignored: {doctype or 'no doctype'} is not read"
    if not switch("ERP_PULL_B2B"):
        return "ignored: ERP_PULL_B2B is off"
    erp = erp or client()
    if erp is None:
        return "ignored: no enabled ERPNext account"
    return mirror_doc(erp, doctype, name)


# Stock


def stock_soon():
    """One stock read for a burst of doorbells: queued STOCK_DEBOUNCE seconds ahead, unless one is queued already
    (a cache key; without the cache, a read each time)."""
    from .tasks import refresh_stock

    try:
        first = cache.add("erp:stock-refresh", 1, timeout=STOCK_DEBOUNCE)
    except Exception:  # the cache is down: read anyway
        first = True
    if not first:
        return "a stock read is queued already"
    refresh_stock.apply_async(countdown=STOCK_DEBOUNCE)
    return ""


def stocked_products():
    """The products ERPNext keeps stock of (a bundle's are its books'; a course has none)."""
    return Product.objects.filter(kind__in=contract.STOCK_KINDS)


def read_stock(erp):
    """ERPNext's stock in ERP_WAREHOUSE, of our items: {item code: (actual, projected, reserved, batches)}. An item it
    holds no stock of (no Bin) is not in it."""
    answer = erp.call("get_stock", {"warehouse": settings.ERP_WAREHOUSE, "by_batch": True})
    return {code: rest for code, *rest in contract.stock_rows(answer)}


def refresh_stock(erp):
    """ERPNext's stock of our printed items, kept as snapshots (one get_stock for all of them: an item ERPNext holds
    none of has 0), and projected when ERP_STOCK_PROJECTION is on. Returns the snapshots."""
    products = list(stocked_products())
    codes = contract.item_codes(products)
    held, now, snapshots = read_stock(erp), timezone.now(), []
    zero = (contract.number(0), contract.number(0), contract.number(0), [])
    for product in products:
        actual, projected, reserved, batches = held.get(codes[product.pk], zero)
        snapshot, _ = ErpStockSnapshot.objects.update_or_create(
            item_code=codes[product.pk],
            warehouse=settings.ERP_WAREHOUSE,
            defaults={
                "product": product,
                "actual": actual,
                "projected": projected,
                "reserved": reserved,
                "batches": batches,
                "as_of": now,
            },
        )
        snapshots.append(snapshot)
        if switch("ERP_STOCK_PROJECTION"):
            project(product.pk, actual - reserved)
    return snapshots


def reserved_not_shipped(product_ids=None):
    """{product id: copies} taken from the platform's stock (paid, or placed with cash on delivery) that ERPNext still
    counts in its warehouse: not shipped yet, or shipped with the parcel's delivery note not yet in ERPNext (one
    order's copies per parcel waiting: a re-shipment counts again). Bundles count their books."""
    waiting = Order.objects.filter(
        stock_reserved=True, status__in=[Order.Status.PENDING, Order.Status.PAID, Order.Status.PACKED]
    )
    numbers = Counter(waiting.values_list("number", flat=True))
    unsent = ErpOutbox.objects.filter(event="parcel.dispatched", state__in=ErpOutbox.OPEN)
    numbers.update(unsent.values_list("aggregate_id", flat=True))
    copies = Counter()
    for order in Order.objects.filter(number__in=numbers).prefetch_related("items__product"):
        for entry in order.items.all():
            for pk, count in entry.product.stock_lines(entry.quantity).items():
                copies[pk] += count * numbers[order.number]
    if product_ids is None:
        return copies
    return Counter({pk: copies[pk] for pk in product_ids})


def project(product_id, free):
    """ERP_STOCK_PROJECTION: the product's copies for sale become ERPNext's free copies (`free`: its own, less what
    its B2B orders hold) less those reserved here and not shipped, never below 0 (so never more than ERPNext can
    give). Under a lock on the product, as checkout's reserve_stock: a payment at that moment counts on one side or
    the other, never on both or neither. Returns the copies for sale."""
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        stock = max(0, int(free) - reserved_not_shipped([product_id])[product_id])
        if stock != product.stock:
            Product.objects.filter(pk=product_id).update(stock=stock)  # no post_save: no item upsert for it
            logger.info("erp: %s's copies for sale %s → %s (ERPNext free: %s)", product, product.stock, stock, free)
    return stock


# B2B documents


def mirror_doc(erp, doctype, name):
    """A B2B document read again and kept (its mirror deleted when ERPNext no longer has it): "" or why not."""
    document = erp.get_doc(doctype, name)
    if not document:
        ErpMirror.objects.filter(doctype=doctype, name=name).delete()
        return "gone: its mirror deleted"
    if not contract.is_b2b(doctype, document):
        return "ignored: not a B2B document"
    ref, state, data, modified = contract.mirror(doctype, document)
    ErpMirror.objects.update_or_create(
        doctype=doctype,
        name=name,
        defaults={
            "examleaf_ref": ref,
            "status": state,
            "data": data,
            "modified": modified,
            "fetched_at": timezone.now(),
        },
    )
    return ""


# The pull


def pulled_doctypes():
    stock = contract.STOCK_PULLED if switch("ERP_PULL_STOCK") else []
    return [*stock, *(contract.B2B_DOCTYPES if switch("ERP_PULL_B2B") else [])]


def pull(doctypes=None):
    """Per doctype read (ERP_PULL_STOCK, ERP_PULL_B2B), the rows changed since its cursor, page by page while ERPNext
    has more: a B2B page's documents mirrored and the cursor moved to the page's `next`; stock's pages read to their
    end, then the stock read once and the cursor moved. A doctype ERPNext could not be asked about keeps its cursor
    (its error on it) for the next run. Returns {doctype: rows read, or the error}."""
    erp = client()
    if erp is None:
        return {"skipped": "no enabled ERPNext account"}
    read = {}
    for doctype in doctypes or pulled_doctypes():
        cursor, _ = ErpCursor.objects.get_or_create(doctype=doctype)
        position, count = (cursor.modified_after or contract.START, cursor.last_name), 0
        try:
            while True:
                after = {"modified_after": position[0], **({"after_name": position[1]} if position[1] else {})}
                answer = erp.call("get_changes_since", {"doctype": doctype, **after, "limit": PAGE})
                rows, more, following = contract.changes(answer)
                if not rows or following <= position:  # nothing new (or a page that does not move on)
                    break
                if doctype not in contract.STOCK_DOCTYPES:
                    for row in rows:
                        mirror_doc(erp, doctype, row["name"])
                    _move(cursor, following, len(rows))
                position, count = following, count + len(rows)
                if not more:
                    break
            if doctype in contract.STOCK_DOCTYPES and count:
                refresh_stock(erp)
                _move(cursor, position, count)
            cursor.last_error = ""
            read[doctype] = count
        except IntegrationError as error:
            cursor.last_error = str(error)[:500]
            read[doctype] = f"error: {cursor.last_error}"
            logger.warning("erp: the pull of %s stopped: %s", doctype, error)
        cursor.last_run_at = timezone.now()
        cursor.save(update_fields=["last_error", "last_run_at"])
    return read


def _move(cursor, position, rows):
    cursor.modified_after, cursor.last_name = position
    cursor.rows_read += rows
    cursor.save(update_fields=["modified_after", "last_name", "rows_read"])
