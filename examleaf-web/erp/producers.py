"""When the platform's facts become outbox rows (erp/README.md, "The flows"): each written in the transaction of the
change it describes, by a receiver of the shop's and the shipping app's signals (post_save of an invoice, a credit
note, a payment, a product or a bundle line, a COD remittance; shop's order_shipped, shipping's parcel_left), and only
while its flow's switch is on (FLOWS; all off by default). The relay sends them (tasks.relay) once ERP_ENABLED is on.

An order's rows are one aggregate, in this order: its invoice first, then what hangs on it, each once (by reference):
its payments (once captured), its delivery notes (once a parcel has left), its credit notes and their refunds (money
out against the credit note), its COD settlement. What hangs on an invoice is written only once the invoice is in the
outbox: when it comes first (a cash-on-delivery order leaves before its bill is made; a payment is captured before
its invoice), the invoice's own producer writes it. The order's row is locked meanwhile, so the two never miss each
other. Test-mode orders never sync. A product's rows are another aggregate: its item, then (a bundle) its
components; a newer upsert of either replaces an older one that failed (a product fixed after ERPNext refused it).

A producer never breaks the change it describes: if it fails, its writes are undone (a savepoint), the error is
logged (Sentry), the change goes on, and the nightly reconciliation reports the document missing. A payload that
cannot be built is not a failure of the change either: the row is written without it and built again at the send."""

import functools
import logging
from collections import Counter

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from shipping.models import CodRemittance
from shipping.signals import parcel_left
from shop.models import BundleItem, CreditNote, Invoice, Order, Payment, Product, Refund
from shop.signals import order_shipped

from . import contract
from .models import ErpOutbox

logger = logging.getLogger(__name__)
FLOWS = {  # a flow's switch (settings, from the environment; all off by default)
    "catalogue": "ERP_SYNC_CATALOGUE",
    "invoices": "ERP_SYNC_INVOICES",
    "payments": "ERP_SYNC_PAYMENTS",
    "deliveries": "ERP_SYNC_DELIVERIES",
    "settlements": "ERP_SYNC_SETTLEMENTS",
}
REMITTED = [CodRemittance.State.REMITTED, CodRemittance.State.MISMATCH]


def switch(name):
    """An ERP_* switch: the staff panel's feature flag of the same name once one is set (staff.config: switched
    without a deploy, with its history and an audit event), else the environment's setting (settings.py)."""
    from staff.config import feature_flag

    value = feature_flag(name)
    return bool(getattr(settings, name)) if value is None else bool(value)


def enabled(flow):
    return switch(FLOWS[flow])


def enabled_events():
    """The events whose flow is on (the relay sends only these; the others' rows wait)."""
    return [name for name, event in contract.EVENTS.items() if enabled(event.flow)]


def guarded(function):
    """A producer that cannot break the change it describes (the module's docstring)."""

    @functools.wraps(function)
    def run(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except Exception:
            logger.exception("erp: %s failed; the change goes on without its outbox row", function.__name__)
            return None

    return run


def _relay_soon():
    from .tasks import relay

    relay.delay()


def nudge():
    """Run the relay once the transaction is committed, once per transaction (beat's minute is the net under it)."""
    connection = transaction.get_connection()
    if connection.in_atomic_block and any(func is _relay_soon for _, func, _ in connection.run_on_commit):
        return
    transaction.on_commit(_relay_soon, robust=True)


def written(ref):
    """Whether a reference is in the outbox (sent or not, even discarded: what hangs on it may go)."""
    return ErpOutbox.objects.filter(examleaf_ref=ref).exists()


def enqueue(event, *, aggregate, ref, obj=None, payload=None, upsert=False):
    """Write an outbox row: next in its aggregate (`aggregate`: (type, id)), its payload built now from `obj` unless
    given. A document created once is written once (by `ref`: None the second time); an upsert is written again only
    when its payload changed. Returns the row, or None."""
    problem = ""
    if payload is None and obj is not None:
        try:
            payload = contract.build(event, obj)
        except Exception as error:  # written all the same; built again at the send (tasks.deliver)
            logger.exception("erp: the payload of %s %s could not be built", event, ref)
            problem = f"Payload not built: {type(error).__name__}: {error}"[:500]
    earlier = ErpOutbox.objects.filter(examleaf_ref=ref)
    if upsert:
        last = earlier.filter(event=event).exclude(state=ErpOutbox.State.DISCARDED).order_by("-pk").first()
        if last is not None and payload is not None and last.payload == payload:
            return None
    elif earlier.exists():
        return None
    kind, key = aggregate
    fields = {
        "aggregate_type": kind,
        "aggregate_id": str(key),
        "event": event,
        "examleaf_ref": ref,
        "model": contract.EVENTS[event].model if obj is not None else "",
        "object_id": str(obj.pk) if obj is not None else "",
        "payload": payload,
        "last_error": problem,
    }
    row = None
    for tries in range(5):  # two transactions taking the same next number: the second waits, then takes the next
        last = ErpOutbox.objects.filter(aggregate_type=kind, aggregate_id=str(key)).aggregate(Max("sequence"))
        try:
            with transaction.atomic():
                row = ErpOutbox.objects.create(sequence=(last["sequence__max"] or 0) + 1, **fields)
            break
        except IntegrityError:
            if tries == 4:
                raise
    if upsert:
        supersede(row)
    nudge()
    return row


def supersede(row):
    """An upsert's older rows of the same reference that failed, or died, give way to it (the product was fixed
    since ERPNext refused it): discarded, a dead one's dead letter with them."""
    failed = [ErpOutbox.State.FAILED, ErpOutbox.State.DEAD]
    older = ErpOutbox.objects.filter(examleaf_ref=row.examleaf_ref, event=row.event, pk__lt=row.pk, state__in=failed)
    for stale in older:
        reason = f"Superseded by outbox row #{row.pk}."
        if stale.state == ErpOutbox.State.DEAD:
            stale.discard(reason)
        else:
            ErpOutbox.objects.filter(pk=stale.pk, state=stale.state).update(
                state=ErpOutbox.State.DISCARDED, last_error=reason
            )


# The catalogue: a product's item (and a bundle's components), its aggregate the product


def product_aggregate(product):
    return ("product", product.pk)


def upsert_product(product, payload=None):
    """The product's item (a bundle's components: upsert_bundle, after it)."""
    ref = contract.item_ref(product)
    enqueue("item.upserted", aggregate=product_aggregate(product), ref=ref, obj=product, payload=payload, upsert=True)


def upsert_bundle(product):
    """A bundle's components (none yet: nothing, ERPNext takes 1 to 50)."""
    if product.bundle_items.exists():
        ref = contract.bundle_ref(product)
        enqueue("bundle.upserted", aggregate=product_aggregate(product), ref=ref, obj=product, upsert=True)


@receiver(post_save, sender=Product, dispatch_uid="erp_product_saved")
@guarded
def product_saved(sender, instance, raw=False, **kwargs):
    if not raw and enabled("catalogue"):
        upsert_product(instance)
        if instance.kind == Product.Kind.BUNDLE:
            upsert_bundle(instance)


@receiver(post_delete, sender=Product, dispatch_uid="erp_product_deleted")
@guarded
def product_deleted(sender, instance, **kwargs):
    """A product deleted (never sold): its item disabled in ERPNext (the payload built now, from what was deleted),
    if ERPNext has it."""
    if enabled("catalogue") and written(contract.item_ref(instance)):
        upsert_product(instance, payload={**contract.item(instance), "is_active": False})


@receiver(post_save, sender=BundleItem, dispatch_uid="erp_bundle_item_saved")
@receiver(post_delete, sender=BundleItem, dispatch_uid="erp_bundle_item_deleted")
@guarded
def bundle_changed(sender, instance, raw=False, **kwargs):
    if not raw and enabled("catalogue"):
        bundle = Product.objects.filter(pk=instance.bundle_id).first()  # gone too: the product's deletion says it
        if bundle is not None:
            upsert_bundle(bundle)


# An order's documents: its aggregate the order


def order_aggregate(order):
    return ("order", order.number)


def locked_order(order_id):
    """The order, its row locked: an invoice and what hangs on it, written at once, never miss each other."""
    return Order.objects.select_for_update().get(pk=order_id)


def invoice_written(order):
    """The order's invoice, once it is in the outbox; else None (its own producer writes what hangs on it later)."""
    invoice = Invoice.objects.filter(order=order).first()
    return invoice if invoice and written(contract.invoice_ref(invoice)) else None


def invoice_issued(invoice):
    """The invoice, then what already hangs on it: its credit notes, its captured payments, its parcels that have
    left, its COD settlement (each by its own flow)."""
    order = locked_order(invoice.order_id)
    if order.is_test or not enabled("invoices"):
        return
    enqueue("invoice.issued", aggregate=order_aggregate(order), ref=contract.invoice_ref(invoice), obj=invoice)
    for note in invoice.credit_notes.order_by("pk"):
        credit_note_issued(note, order)
    for payment in order.payments.filter(status__in=contract.CAPTURED).order_by("pk"):
        payment_received(payment, order)
    for shipment in order.shipments.order_by("pk"):
        parcel_dispatched(shipment, order)
    for remittance in CodRemittance.objects.filter(shipment__order=order, state__in=REMITTED).order_by("pk"):
        cod_remitted(remittance, order)


def credit_note_issued(note, order):
    """The credit note, then its refund's money going out against it."""
    if order.is_test or not enabled("invoices") or not invoice_written(order):
        return
    enqueue("credit_note.issued", aggregate=order_aggregate(order), ref=contract.credit_note_ref(note), obj=note)
    refund_paid(note.refund, order)


def refund_paid(refund, order):
    """A processed refund, as money out against its credit note (once the credit note is in the outbox; a refund of
    an order never invoiced has no document in ERPNext to go against)."""
    if order.is_test or not enabled("payments") or refund.status != Refund.Status.PROCESSED:
        return
    if refund.method == Refund.Method.NONE:  # a parcel back undelivered: its credit note moves no money
        return
    note = CreditNote.objects.filter(refund=refund).first()
    if note is not None and written(contract.credit_note_ref(note)):
        enqueue("refund.paid", aggregate=order_aggregate(order), ref=contract.refund_ref(refund), obj=refund)


def payment_received(payment, order):
    if order.is_test or not enabled("payments") or payment.status not in contract.CAPTURED:
        return
    if invoice_written(order):
        enqueue("payment.received", aggregate=order_aggregate(order), ref=contract.payment_ref(payment), obj=payment)


def parcel_dispatched(shipment, order):
    if order.is_test or not enabled("deliveries") or not contract.physical_items(order):
        return
    if invoice_written(order) and contract.has_left(shipment):
        ref = contract.delivery_ref(shipment)
        enqueue("parcel.dispatched", aggregate=order_aggregate(order), ref=ref, obj=shipment)


def cod_remitted(remittance, order):
    if order.is_test or not enabled("settlements") or remittance.state not in REMITTED:
        return
    if remittance.remitted_amount is not None and invoice_written(order):
        ref = contract.settlement_ref(contract.cod_settlement_id(remittance))
        enqueue("settlement.received", aggregate=order_aggregate(order), ref=ref, obj=remittance)


def razorpay_settlement(settlement):
    """A Razorpay settlement ({id, date, gross, fees, tax, net, utr, payment_ids}), its own aggregate: called once a
    settlement is matched (shop/settlements.py `post`; the payment ids are not ERPNext's to take)."""
    if enabled("settlements"):
        ref = contract.settlement_ref(settlement["id"])
        payload = contract.razorpay_settlement(settlement)
        return enqueue("settlement.received", aggregate=("settlement", settlement["id"]), ref=ref, payload=payload)
    return None


@receiver(post_save, sender=Invoice, dispatch_uid="erp_invoice_saved")
@guarded
def invoice_saved(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        invoice_issued(instance)


@receiver(post_save, sender=CreditNote, dispatch_uid="erp_credit_note_saved")
@guarded
def credit_note_saved(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        credit_note_issued(instance, locked_order(instance.invoice.order_id))


@receiver(post_save, sender=Payment, dispatch_uid="erp_payment_saved")
@guarded
def payment_saved(sender, instance, raw=False, **kwargs):
    if not raw and instance.status == Payment.Status.CAPTURED:
        payment_received(instance, locked_order(instance.order_id))


@receiver(order_shipped, dispatch_uid="erp_order_shipped")
@guarded
def order_was_shipped(sender, order, shipment, **kwargs):
    parcel_dispatched(shipment, locked_order(order.pk))


@receiver(parcel_left, dispatch_uid="erp_parcel_left")
@guarded
def parcel_has_left(sender, shipment, **kwargs):
    parcel_dispatched(shipment, locked_order(shipment.order_id))


@receiver(post_save, sender=CodRemittance, dispatch_uid="erp_cod_remittance_saved")
@guarded
def cod_remittance_saved(sender, instance, raw=False, **kwargs):
    if not raw and instance.state in REMITTED:
        cod_remitted(instance, locked_order(instance.shipment.order_id))


# The initial load (erp/README.md, "Operations"): erp_initial_load, or the panel's job of that kind

LOAD_BATCH = 200  # documents per transaction


def load_steps(invoices_from=None):
    """What the initial load does, in its order: every product's item, then the bundles' components (once every item
    is before them), then each invoice issued since `invoices_from` with what hangs on it. Each flow only while it is
    switched on. [(document, the producer that writes it)]."""
    products = list(Product.objects.order_by("pk")) if enabled("catalogue") else []
    steps = [(product, upsert_product) for product in products]
    steps += [(product, upsert_bundle) for product in products if product.kind == Product.Kind.BUNDLE]
    if invoices_from:
        invoices = Invoice.objects.filter(created__date__gte=invoices_from).order_by("created", "pk")
        steps += [(invoice, invoice_issued) for invoice in invoices]
    return steps


def initial_load_size(invoices_from=None):
    """The staff job's rows: the documents the load goes through."""
    return len(load_steps(invoices_from))


def initial_load(invoices_from=None, apply=False, progress=None):
    """Write the outbox rows of the initial load (a dry run without `apply`: counted in transactions rolled back), each
    document once: what the outbox has already is not written again. `progress`: a staff job's (a row a document).
    Returns ({event: rows}, [the flows switched off, not loaded])."""
    steps = load_steps(invoices_from)
    written = Counter()
    for start in range(0, len(steps), LOAD_BATCH):
        with transaction.atomic():
            last = ErpOutbox.objects.aggregate(Max("pk"))["pk__max"] or 0
            for obj, write in steps[start : start + LOAD_BATCH]:
                write(obj)
                if progress is not None:
                    progress.row()
            written.update(ErpOutbox.objects.filter(pk__gt=last).values_list("event", flat=True))
            if not apply:
                transaction.set_rollback(True)
    return dict(sorted(written.items())), [setting for flow, setting in FLOWS.items() if not enabled(flow)]


def initial_load_job(job, progress):
    """The staff job erp_initial_load (staff.jobs): the load, an audit event `erp.initial_load` with what it wrote, and
    the owners told when it wrote anything (erp.run_initial_load alerts)."""
    from staff.audit import alert, record

    since = job.params.get("invoices_from")
    written, off = initial_load(since, apply=not job.dry_run, progress=progress)
    details = {"invoices_from": since, "dry_run": job.dry_run, "written": written, "flows_off": off, "job": job.pk}
    record("erp.initial_load", actor=job.started_by, permission="erp.run_initial_load", details=details)
    if written and not job.dry_run:
        rows = ", ".join(f"{count} {event}" for event, count in written.items())
        alert("ERPNext initial load written", f"Job #{job.pk} wrote {rows} into the outbox (from {since or '-'}).")
    return {"written": written, "flows_off": off}
