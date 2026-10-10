"""The Orders module's background jobs (staff.jobs: started with POST /api/v1/staff/jobs/, their progress, their rows'
errors, their file): mark packed, print (packing slips, labels for parcels sent by hand, or invoices, as one PDF),
cancel (250 at most), and the order export (the list's filters; shop.export_order's columns with the GST fields).
Each job's own permission (PERMISSIONS) is the single action's; above its starter's `bulk_rows` (an export: its
`export_rows`) a second person approves it first (staff.approvals "job.run"); a dry run checks every row and changes
nothing. Each order goes through the shop's own flow, in its starter's scope, and is an audit event. Nothing here is
imported by staff.jobs but these names: no import of staff.jobs or staff.api at module level (they import this)."""

import csv
import io
import tempfile

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Prefetch
from django.utils import timezone
from django_fsm import TransitionNotAllowed, can_proceed
from rest_framework import exceptions, serializers

from staff import approvals, audit
from staff.backends import scoped
from staff.models import ChangeRequest, Job

from . import invoices, services
from .models import STATES, Order, OrderItem, Shipment

Kind = Job.Kind
PERMISSIONS = {
    Kind.ORDERS_PACK: "staff.pack_order",
    Kind.ORDERS_PRINT: "staff.pack_order",
    Kind.ORDERS_CANCEL: "shop.change_order",
    Kind.ORDERS_EXPORT: "shop.export_order",
}
ASKS = {Kind.ORDERS_CANCEL: "order.refund"}  # the approvals action a kind's rows ask for: its step-up at the start
LIMITS = {**dict.fromkeys([Kind.ORDERS_PACK, Kind.ORDERS_PRINT, Kind.ORDERS_CANCEL], "bulk_rows")}
LIMITS[Kind.ORDERS_EXPORT] = "export_rows"
MAX_TARGETS = 1000
MAX_CANCEL = 250  # Shopify's cap, the plan's (5.3): a wider cancellation is a mistake waiting to happen
DOCUMENTS = {"packing_slip": "packing slips", "label": "labels for parcels sent by hand", "invoices": "invoices"}
EXPORT_FILTERS = ["status", "method", "courier", "created_from", "created_to", "shipping", "tag", "hold", "risk"]
EXPORT_FILTERS += ["livemode", "tab"]  # not q: a person's search is the list's, never an export's


def params_for(kind, params):
    """A job's params, checked (staff.serializers.JobStartSerializer). Raises ValidationError({"params": …})."""
    params = params if isinstance(params, dict) else {}
    if kind == Kind.ORDERS_EXPORT:
        filters = params.get("filters", {})
        if not isinstance(filters, dict):
            raise serializers.ValidationError({"params": {"filters": ["The list's filters, as an object."]}})
        unknown = sorted(set(filters) - set(EXPORT_FILTERS))
        if unknown:
            errors = {name: ["Not a filter of the export (a search is the list's)."] for name in unknown}
            raise serializers.ValidationError({"params": {"filters": errors}})
        clean = {name: str(value) for name, value in filters.items() if value not in (None, "")}
        filterset = export_filter(clean)
        if not filterset.is_valid():
            raise serializers.ValidationError({"params": {"filters": filterset.errors}})
        return {"filters": clean}
    targets = params.get("targets")
    problems = {}
    if not isinstance(targets, list) or not targets or not all(isinstance(t, str) and t for t in targets):
        problems["targets"] = ["The orders' numbers, as a list."]
    elif len(set(targets)) != len(targets):
        problems["targets"] = ["Each order once."]
    elif kind == Kind.ORDERS_CANCEL and len(targets) > MAX_CANCEL:
        problems["targets"] = [f"At most {MAX_CANCEL} orders are cancelled at once: you chose {len(targets)}."]
    elif len(targets) > MAX_TARGETS:
        problems["targets"] = [f"At most {MAX_TARGETS:,} orders at once."]
    clean = {"targets": [str(target).strip().upper() for target in targets or []]}
    if kind == Kind.ORDERS_PRINT:
        if params.get("document") not in DOCUMENTS:
            problems["document"] = [f"One of {', '.join(DOCUMENTS)}."]
        clean["document"] = params.get("document")
    if kind == Kind.ORDERS_CANCEL:
        reason = " ".join(str(params.get("reason") or "").split())[:200]
        if not reason:
            problems["reason"] = ["Say why: the customers are told."]
        clean |= {"reason": reason, "customer_requested": bool(params.get("customer_requested"))}
    if problems:
        raise serializers.ValidationError({"params": problems})
    return clean


def export_filter(filters, queryset=None):
    from .staff_orders import OrderFilter  # (it imports staff.api, which imports staff.jobs)

    return OrderFilter(filters, queryset=queryset if queryset is not None else Order.objects.none())


def exported(user, params):
    """The orders an export holds: the list's filters over the orders its starter may export (their scope)."""
    orders = scoped(Order.objects.all(), user, PERMISSIONS[Kind.ORDERS_EXPORT])
    return export_filter(params["filters"], orders).qs.order_by("pk")


def size(kind, user, params):
    """The rows a job will go through (its total, against its starter's limit)."""
    return exported(user, params).count() if kind == Kind.ORDERS_EXPORT else len(params["targets"])


def targets(job):
    """{number: order} of the job's orders its starter reaches with the job's permission (others: not found)."""
    orders = scoped(Order.objects.all(), job.started_by, PERMISSIONS[job.kind]).filter(number__in=job.params["targets"])
    orders = orders.select_related("invoice", "quote", "user__board").prefetch_related(
        "items__product__bundle_items__product"
    )
    return {order.number: order for order in orders}


def each(job, progress, step):
    """Each target in order: `step(order)` for the ones found, an error for the others; progress per row."""
    found, done = targets(job), 0
    for number in job.params["targets"]:
        order = found.get(number)
        if order is None:
            progress.error(number, number, "No such order (or not one you may act on).")
        else:
            try:
                done += step(order) is not False
            except (services.ShopError, TransitionNotAllowed, exceptions.APIException) as error:
                progress.error(number, number, str(getattr(error, "detail", error) or "Not possible now."))
        progress.row()
    return done


def pack(job, progress):
    """Mark packed (the customers told); a held, test, unpaid or courses-only order is refused with its reason."""

    def step(order):
        if order.held_at:
            raise services.ShopError(f"On hold ({order.hold_reason}): release it first.")
        if not can_proceed(order.pack):
            raise services.ShopError(f"It is {order.get_status_display()}{' (a test order)' if order.is_test else ''}.")
        if job.dry_run:
            return True
        order = services.pack_order(order)
        audit.record("order.packed", actor=job.started_by, target=order, details={"job": job.pk})
        return True

    return {"packed" if not job.dry_run else "valid": each(job, progress, step)}


def print_documents(job, progress):
    """One PDF of the chosen documents of the orders that have them (in the order chosen), in the private storage."""
    document, printable = job.params["document"], []

    def step(order):
        if document == "invoices" and not (getattr(order, "invoice", None) and order.invoice.pdf):
            raise services.ShopError("No invoice yet.")
        if document != "invoices" and not invoices.books_of(order):
            raise services.ShopError("Courses alone: nothing to pack or send.")
        printable.append(order)
        return True

    each(job, progress, step)
    if job.dry_run or not printable:
        return {"printed": 0 if not job.dry_run else None, "valid": len(printable)}
    content = invoices.render_pdf(invoices.Print(document, printable))
    job.result_file = default_storage.save(
        f"staff/jobs/{job.pk}/{document}-{timezone.localdate():%Y%m%d}.pdf", ContentFile(content)
    )
    details = {"job": job.pk, "document": document, "orders": len(printable)}
    audit.record("order.documents_printed", actor=job.started_by, details=details)
    return {"printed": len(printable)}


def cancel(job, progress):
    """Cancel each order not yet sent, as its page does: paid online, through its refund (staff.approvals
    "order.refund": the starter's refund limit; above it each waits for FINANCE); paid by transfer, refused (its
    refund by bank cancels it); otherwise at once, its stock back, the customer told."""
    reason, outcomes, waiting = job.params["reason"], {"cancelled": 0, "pending": 0}, []

    def step(order):
        if not can_proceed(order.cancel):
            raise services.ShopError(f"It is {order.get_status_display()}: refund it, or ask for a return.")
        online = services.online_payment(order) is not None
        if not online and order.payments.filter(method=Order.Method.OFFLINE, status__in=services.PAID).exists():
            raise services.ShopError("Paid by transfer: refund it by bank or UPI from its page, which cancels it.")
        if job.dry_run:
            return True
        if online:
            key = f"job-{job.pk}-{order.number}"
            change, _ = approvals.ask(
                "order.refund",
                maker=job.started_by,
                target=order.number,
                payload={},
                reason=reason,
                idempotency_key=key,
            )
            if change.status == ChangeRequest.Status.PENDING:
                outcomes["pending"] += 1
                waiting.append(change.pk)
                return True
            if change.status == ChangeRequest.Status.FAILED:
                raise services.ShopError(change.result.get("error", "Not cancelled."))
        else:
            services.cancel_order(order, reason, by=job.started_by)
        details = {"job": job.pk, "customer_requested": job.params["customer_requested"]}
        audit.record("order.cancelled", actor=job.started_by, target=order, reason=reason, details=details)
        outcomes["cancelled"] += 1
        return True

    valid = each(job, progress, step)
    return {"valid": valid} if job.dry_run else {"outcomes": outcomes, "waiting": waiting}


COLUMNS = [
    *["number", "created", "placed_at", "status", "payment_method", "email", "name", "phone", "city", "district"],
    *["state", "pin", "books", "books value", "discount", "shipping", "total", "coupon_code", "tracking"],
    *["invoice", "invoice date", "place of supply", "line", "hsn", "gst rate", "quantity", "line value"],
    *["line discount", "taxable value", "cgst", "sgst", "igst"],
]


def export(job, progress):
    """The orders of the list's filters as CSV, one row per line: shop.export_order's columns (the admin's export) with
    each line's GST (HSN, rate, taxable value, CGST and SGST or IGST, as its invoice splits it), in the private
    storage; logged with the filters and the count (no personal data in the log)."""
    from django.conf import settings

    orders = (
        exported(job.started_by, job.params)
        .select_related("invoice")
        .prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.order_by("pk")),
            Prefetch("shipments", queryset=Shipment.objects.order_by("shipped_at", "pk")),
        )
    )
    job.total = orders.count()
    if job.dry_run:
        return {"rows": job.total}
    with tempfile.TemporaryFile() as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        writer = csv.writer(text)
        writer.writerow(COLUMNS)
        lines = 0
        for order in orders.iterator(chunk_size=200):
            address, invoice = order.shipping_address or {}, getattr(order, "invoice", None)
            intra = address.get("state") == settings.SHOP_SELLER["state"]
            items = list(order.items.all())
            common = [
                order.number,
                order.created.isoformat(),
                order.placed_at.isoformat() if order.placed_at else "",
                order.status,
                order.payment_method,
                order.email,
                address.get("name", ""),
                address.get("phone", ""),
                address.get("city", ""),
                address.get("district", ""),
                address.get("state", ""),
                address.get("pin", ""),
                "; ".join(f"{item.quantity} x {item.title}" for item in items),
                order.subtotal.amount,
                order.discount.amount,
                order.shipping_fee.amount,
                order.total.amount,
                order.coupon_code,
                "; ".join(f"{s.courier} {s.tracking_number}" for s in order.shipments.all()),
                invoice.number if invoice else "",
                invoice.created.date().isoformat() if invoice else "",
                STATES.get(address.get("state", ""), address.get("state", "")),
            ]
            for item, share in zip(items, invoices.discount_shares(order, items), strict=True):
                split = invoices.tax(item, item.line_total.amount - share, intra)
                writer.writerow(
                    [
                        *common,
                        item.title,
                        item.hsn_code,
                        item.gst_rate,
                        item.quantity,
                        item.line_total.amount,
                        share,
                        split["taxable"],
                        split["cgst"],
                        split["sgst"],
                        split["igst"],
                    ]
                )
                lines += 1
            progress.row()
        text.flush()
        raw.seek(0)
        job.result_file = default_storage.save(
            f"staff/jobs/{job.pk}/orders-{timezone.localdate():%Y%m%d}.csv", File(raw, name="orders.csv")
        )
        text.detach()
    details = {"filters": job.params["filters"], "orders": job.done, "rows": lines, "job": job.pk}
    audit.record("order.exported", actor=job.started_by, change_request=job.change_request_id, details=details)
    return {"rows": lines, "orders": job.done}


RUNNERS = {Kind.ORDERS_PACK: pack, Kind.ORDERS_PRINT: print_documents, Kind.ORDERS_CANCEL: cancel}
RUNNERS[Kind.ORDERS_EXPORT] = export
