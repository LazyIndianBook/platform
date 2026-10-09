"""The contract with ERPNext's side, the Frappe app `examleaf_erp` (examleaf-erp/API.md), in one module: its method
names, fields, references and answers live here and nowhere else, so that a change on either side is a change to
this file.

- The calls: POST /api/method/examleaf_erp.api.<method> with a JSON object of exactly the documented fields (an
  unknown one is refused). The eight mutating methods take `examleaf_ref` (the platform's stable id of the entity,
  kind:id: REFS) and `idempotency_key` (the outbox row's id); the four read methods take neither. Every answer is
  Frappe's envelope {"message": <answer>}: {ok: true, name, duplicate, examleaf_ref, log, ...} or, with an HTTP
  status (400, 404, 409, 422, 500), {ok: false, error: {code, message, field}}. The same key with the same body
  answers its first result again (duplicate: true); the same reference under a new key, the short form {ok, name,
  duplicate: true, docstatus}, unless its invoice is another order's (or its credit note another invoice's): 409
  conflict, a number issued again; the same key with another body is 409 idempotency_key_reused, a bug: never
  retried.
  Re-reads go through Frappe's REST (GET /api/resource/<Doctype>/<name>) for Sales Invoice, Quotation and Customer;
  stock only through get_stock.
- The payloads (EVENTS), built from the platform's own documents through the functions their PDFs use
  (shop.invoices), so that the mirror is the legal document. No personal data of a B2C customer: every storefront
  invoice goes to ERPNext's one B2C customer with the parcel's city, district, state and PIN only. Money as decimal
  strings in rupees ("299.00"), dates as ISO dates in India's time.
- The doorbells ERPNext rings (webhooks: {doctype, name, modified, examleaf_ref, event}, signed with
  SIGNATURE_HEADER) and what is read back: stock, B2B documents and the fields kept of them, the pull's pages and
  the day's totals for the reconciliation (deviation 7: ERPNext rounds each tax once per invoice, so taxes and taxable
  values may differ by 0.01 a taxed document; totals never do)."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.apps import apps
from django.conf import settings
from django.utils import timezone
from stdnum import isbn as isbn_number

from integrations.redact import scrub
from shipping.models import ShipmentDetail
from shipping.status import LEFT
from shop import invoices
from shop.models import Invoice, Order, Payment, Product, rupees

from .models import ErpLink

METHOD_PATH = "/api/method/examleaf_erp.api.{method}"
RESOURCE_PATH = "/api/resource/{doctype}/{name}"
FAKE_URL = "https://erpnext.fake.test"  # ERP_MODE=fake: the in-memory double's (fake.py)
SIGNATURE_HEADER = "X-Frappe-Webhook-Signature"  # base64 HMAC-SHA256 of the raw body with the webhook secret
SITE_HEADER = "X-Frappe-Site-Name"  # which site, when the base URL is the cluster's service rather than the site's
B2C_CUSTOMER = "Online Customers (B2C)"  # ERPNext's one customer of every storefront invoice (not sent: implied)
ITEM_CODE = "EL-{pk:05d}"  # a product's item code (the Item's name, fixed for ever once made)
STOCK_KINDS = (Product.Kind.SAMPLE_PAPERS, Product.Kind.SOLUTIONS)  # printed books: stock items in ERPNext
CAPTURED = [Payment.Status.CAPTURED, Payment.Status.REFUNDED]  # money that came in (a refund goes out separately)
MODES = ("razorpay", "cod", "upi", "neft", "cheque")
START = "2000-01-01 00:00:00"  # the pull's cursor before its first read (modified_after is required)

# The doctypes ERPNext rings us about and the pull reads. Stock: any of them refreshes our stock (read with get_stock:
# the sync user may not read stock documents), and the Stock Ledger Entry, which every movement writes, is the one
# pulled. B2B: read again over REST and mirrored, the B2B ones only.
STOCK_DOCTYPES = ["Stock Ledger Entry", "Purchase Receipt", "Stock Reconciliation", "Stock Entry", "Bin"]
STOCK_PULLED = ["Stock Ledger Entry"]
B2B_DOCTYPES = ["Sales Invoice", "Quotation", "Customer"]
B2B_GROUPS = {"School", "Distributor", "Bookseller", "Teacher"}  # ERPNext's B2B customer groups
MIRROR_FIELDS = {  # what a mirror keeps: never a contact's email address or phone number
    "Sales Invoice": [
        *["name", "customer", "customer_name", "customer_group", "territory", "posting_date", "due_date"],
        *["grand_total", "outstanding_amount", "status", "docstatus", "is_return", "return_against", "modified"],
    ],
    "Quotation": [
        *["name", "quotation_to", "party_name", "customer_name", "transaction_date", "valid_till", "grand_total"],
        *["status", "docstatus", "modified"],
    ],
    "Customer": [
        *["name", "customer_name", "customer_group", "customer_type", "territory", "gstin", "disabled"],
        *["udise_code", "school_board", "school_medium", "district", "modified"],
    ],
}
MIRROR_ITEM_FIELDS = ["item_code", "item_name", "qty", "rate", "amount"]

# What a refusal's code says about trying again (API.md "Errors"): these never succeed unchanged, so the row is dead
# at once and staff look (an invalid date excepted: a clock just past midnight on one side). The others (a document
# not there yet, stock not received yet, an item's new rate not yet upserted, ERPNext not set up) are tried again.
PERMANENT = {
    *["idempotency_key_reused", "invalid_request", "conflict", "cancelled", "amendment_refused"],
    *["doc_kind_mismatch", "total_mismatch", "over_credit", "overpayment", "nothing_to_deliver"],
}
DATE_FIELDS = {"posting_date", "date", "reference_date"}


@dataclass(frozen=True)
class Event:
    method: str  # examleaf_erp.api.<method>
    doctype: str  # what it makes in ERPNext (ErpLink.doctype)
    flow: str  # its switch: producers.FLOWS
    model: str  # the platform object it describes


EVENTS = {
    "item.upserted": Event("upsert_item", "Item", "catalogue", "shop.product"),
    "bundle.upserted": Event("upsert_bundle", "Product Bundle", "catalogue", "shop.product"),
    "invoice.issued": Event("create_sales_invoice", "Sales Invoice", "invoices", "shop.invoice"),
    "credit_note.issued": Event("create_credit_note", "Sales Invoice", "invoices", "shop.creditnote"),
    "payment.received": Event("create_payment_entry", "Payment Entry", "payments", "shop.payment"),
    "refund.paid": Event("create_payment_entry", "Payment Entry", "payments", "shop.refund"),
    "parcel.dispatched": Event("create_delivery_note", "Delivery Note", "deliveries", "shop.shipment"),
    "settlement.received": Event("record_settlement", "Journal Entry", "settlements", "shipping.codremittance"),
}


# References (examleaf_ref: kind:id, unique on ERPNext's side)


def item_ref(product):
    return f"item:{product.pk}"


def bundle_ref(product):
    return f"bundle:{product.pk}"


def invoice_ref(invoice):
    return f"invoice:{invoice.number}"


def credit_note_ref(note):
    return f"credit_note:{note.number}"


def payment_ref(payment):
    return f"payment:{payment.pk}"


def refund_ref(refund):
    return f"refund:{refund.pk}"


def delivery_ref(shipment):
    return f"delivery:{shipment.pk}"


def settlement_ref(settlement_id):
    return f"settlement:{settlement_id}"


def cod_settlement_id(remittance):
    return f"cod-{remittance.pk}"


# Values


def money(value):
    """Rupees as a decimal string, to the paisa (a Money or a number)."""
    return f"{rupees(getattr(value, 'amount', value)):.2f}"


def rate(value):
    return f"{Decimal(value):.2f}"


def iso(moment):
    """A moment's day in India's time, as an ISO date."""
    return timezone.localdate(moment).isoformat()


def doc_kind(rates):
    """Tax invoice when every line is taxed, bill of supply when none is, invoice-cum-bill of supply (Rule 46A) for a
    mixed cart: as ERPNext derives it from the lines (it checks the one sent)."""
    taxed = {bool(value) for value in rates}
    if taxed == {True, False}:
        return "invoice_cum_bill_of_supply"
    return "tax_invoice" if True in taxed else "bill_of_supply"


def reference_numbers(text):
    """What may go of a reference typed by staff (a bank's UTR, a UPI reference): its words with a digit in them,
    phone numbers and email addresses masked; so no name typed beside it leaves."""
    words = [word for word in str(text or "").split() if any(character.isdigit() for character in word)]
    return scrub(" ".join(words))[:140]


def payment_mode(payment):
    """ERPNext's mode of a payment: Razorpay, cash on delivery, or (recorded by staff) neft, unless its reference
    says it came by UPI or cheque."""
    if payment.method in (Order.Method.RAZORPAY, Order.Method.COD):
        return payment.method
    said = str(payment.reference or "").lower()
    return "upi" if "upi" in said else "cheque" if re.search(r"\bch(e)?q(ue)?\b|\bcheck\b", said) else "neft"


def item_codes(products):
    """{product id: item code}: the name ERPNext gave its item (ErpLink), else the code it is made with."""
    products = list(products)
    refs = [item_ref(product) for product in products]
    linked = dict(ErpLink.objects.filter(examleaf_ref__in=refs).values_list("examleaf_ref", "name"))
    return {product.pk: linked.get(item_ref(product)) or ITEM_CODE.format(pk=product.pk) for product in products}


def item_code(product):
    return item_codes([product])[product.pk]


def captured_on(payment):
    """The day the payment was captured (its history: Payment keeps every change), else the day it was last saved."""
    first = payment.history.filter(status=Payment.Status.CAPTURED).order_by("history_date").first()
    return timezone.localdate(first.history_date if first else payment.modified)


def has_left(shipment):
    """Whether the parcel has left us: typed by hand (no courier side, or the manual carrier's), or a courier's scans
    say so (shipping.status.LEFT)."""
    detail = ShipmentDetail.objects.filter(shipment=shipment).first()
    return detail is None or detail.status in LEFT


def dispatched_on(shipment):
    """The day the parcel left: a courier's first scan that says so, else the day it was handed over by hand."""
    first = shipment.events.filter(status__in=LEFT).order_by("occurred_at").first()
    return timezone.localdate(first.occurred_at if first else shipment.shipped_at)


def physical_items(order):
    """The order's lines that travel in a parcel (not the course, nor a bundle of courses only)."""
    return [item for item in order.items.select_related("product") if not item.product.digital_only]


def valid_isbn(value):
    """The ISBN, compact, when its checksum holds (ERPNext refuses a wrong one, which would hold the item); else ""."""
    return isbn_number.compact(value) if value and isbn_number.is_valid(value) else ""


# The payloads


def item(product):
    """upsert_item: the product as ERPNext's Item (a bundle's too, kind "bundle": it is sold on invoices)."""
    subject = product.subject
    payload = {
        "item_code": item_code(product),
        "item_name": product.title[:140],
        "kind": product.kind,
        "hsn_code": product.hsn_code,
        "gst_rate": rate(product.gst_rate),
        "mrp": money(product.mrp),
        "weight_grams": product.weight_grams,
        "is_active": product.is_active,
    }
    optional = {
        "isbn": valid_isbn(product.isbn),
        "subject": subject.name if subject else "",
        "class_level": str(subject.class_level.number) if subject else "",
        "board": subject.board.short_name if subject else "",
        "edition": (product.book.edition if product.book_id else "")[:40],
    }
    return {**payload, **{key: value for key, value in optional.items() if value}}


def bundle(product):
    """upsert_bundle: a bundle's components with their quantities (ERPNext's Product Bundle on its Item)."""
    components = list(product.bundle_items.select_related("product"))
    codes = item_codes(component.product for component in components)
    return {
        "item_code": item_code(product),
        "items": [{"item_code": codes[c.product_id], "qty": c.quantity} for c in components],
        "is_active": product.is_active,
    }


def shipping_supply(lines):
    """The shipping's HSN and rate as ERPNext gives them (a composite supply follows its principal goods: the
    printed lines, else the bundles), or None when ERPNext must be told (no goods, or goods at several rates): then
    the principal line's."""
    goods = [entry for entry in lines if entry["item"].product.kind in STOCK_KINDS]
    goods = goods or [entry for entry in lines if entry["item"].product.kind == Product.Kind.BUNDLE]
    principal = max(goods or lines, key=lambda entry: entry["amount"])
    told = not goods or len({entry["item"].gst_rate for entry in goods}) > 1
    return principal["item"].hsn_code, principal["item"].gst_rate, told


def invoice(document):
    """create_sales_invoice: the storefront's invoice as issued (its number becomes ERPNext's name)."""
    data = invoices.context(document)
    order, lines = document.order, data["lines"]
    codes = item_codes(entry["item"].product for entry in lines)
    address = order.shipping_address
    payload = {
        "invoice_number": document.number,
        "posting_date": iso(document.created),
        "order_number": order.number,
        "channel": "staff" if order.created_by_id else "web",
        "doc_kind": doc_kind(entry["item"].gst_rate for entry in lines),
        "shipping_address": {
            key: value
            for key, value in {
                "city": address.get("city", ""),
                "district": address.get("district", ""),
                "state": address.get("state", ""),
                "pin": address.get("pin", ""),
            }.items()
            if value
        },
        "items": [
            {
                "item_code": codes[entry["item"].product_id],
                "qty": entry["item"].quantity,
                "rate": money(entry["item"].unit_price),
                "discount": money(entry["discount"]),
                "hsn_code": entry["item"].hsn_code,
                "gst_rate": rate(entry["item"].gst_rate),
            }
            for entry in lines
        ],
        "shipping_fee": money(order.shipping_fee),
        "total": money(order.total),
    }
    if order.shipping_fee.amount:
        hsn, gst_rate, told = shipping_supply(lines)
        if told:
            payload.update(shipping_hsn_code=hsn, shipping_gst_rate=rate(gst_rate))
    return payload


def credit_note(note):
    """create_credit_note: the refund's credit note as issued, against its invoice (a return Sales Invoice there):
    each line's credit, tax included, without the copies (the platform does not know which came back). The reason
    names the refund and the order, never staff's words (which might name the customer)."""
    data = invoices.credit_note_context(note)
    order, lines = note.invoice.order, data["lines"]
    codes = item_codes(entry["item"].product for entry in lines)
    return {
        "credit_note_number": note.number,
        "invoice_number": note.invoice.number,
        "posting_date": iso(note.created),
        "reason": f"Refund {note.refund_id} of order {order.number}",
        "items": [
            {"item_code": codes[entry["item"].product_id], "amount": money(entry["amount"])}
            for entry in lines
            if entry["amount"] > 0
        ],
        "shipping_credit": money(data["shipping_credit"]),
        "total": money(data["total_credit"]),
    }


def payment(document):
    """create_payment_entry: money received for the invoice (Razorpay with its payment id; cash on delivery with the
    parcel's AWB; a transfer recorded by staff with its reference's numbers)."""
    order = document.order
    reference = document.razorpay_payment_id or reference_numbers(document.reference)
    if document.method == Order.Method.COD:
        reference = order.shipments.order_by("-pk").values_list("tracking_number", flat=True).first() or reference
    return {
        "invoice_number": Invoice.objects.get(order=order).number,
        "amount": money(document.amount),
        "posting_date": captured_on(document).isoformat(),
        "mode": payment_mode(document),
        "reference_no": reference or f"payment-{document.pk}",
    }


def refund(document):
    """create_payment_entry of a refund (money out, against its credit note): Razorpay's refund id."""
    note = document.credit_note
    total = invoices.credit_note_context(note)["total_credit"]
    return {
        "invoice_number": note.number,
        "amount": money(total),
        "posting_date": iso(document.processed_at or document.modified),
        "mode": payment_mode(document.payment),
        "reference_no": document.razorpay_refund_id or f"refund-{document.pk}",
    }


def delivery(shipment):
    """create_delivery_note: the parcel, against the invoice, from the storefront's warehouse in ERPNext (everything
    not yet delivered: ERPNext ships a bundle's books and skips the course and the delivery charge)."""
    return {
        "invoice_number": Invoice.objects.get(order=shipment.order_id).number,
        "posting_date": dispatched_on(shipment).isoformat(),
        "warehouse": settings.ERP_WAREHOUSE,
        "courier": shipment.courier[:80],
        "tracking_number": shipment.tracking_number[:80],
    }


def cod_settlement(remittance):
    """record_settlement of a courier's COD remittance (one parcel's cash, with the bank's UTR); the courier's
    charges are its statement's, apart."""
    amount = money(remittance.remitted_amount)
    return {
        "kind": "cod",
        "settlement_id": cod_settlement_id(remittance),
        "posting_date": (remittance.remitted_at or timezone.localdate()).isoformat(),
        "gross_amount": amount,
        "fee": "0.00",
        "tax_on_fee": "0.00",
        "net_amount": amount,
        "utr": remittance.utr[:40],
    }


def razorpay_settlement(settlement):
    """record_settlement of a Razorpay settlement: {id, date, gross, fees, tax, net, utr} as Razorpay's settlement
    recon gives it (the platform does not fetch it yet: erp/README.md "Who owns what")."""
    return {
        "kind": "razorpay",
        "settlement_id": settlement["id"],
        "posting_date": str(settlement["date"]),
        "gross_amount": money(settlement["gross"]),
        "fee": money(settlement.get("fees", 0)),
        "tax_on_fee": money(settlement.get("tax", 0)),
        "net_amount": money(settlement["net"]),
        "utr": str(settlement.get("utr", ""))[:40],
    }


BUILDERS = {
    "item.upserted": item,
    "bundle.upserted": bundle,
    "invoice.issued": invoice,
    "credit_note.issued": credit_note,
    "payment.received": payment,
    "refund.paid": refund,
    "parcel.dispatched": delivery,
    "settlement.received": cod_settlement,
}


def build(event, obj):
    """The payload of an event about a platform object."""
    return BUILDERS[event](obj)


def build_again(event, model, object_id):
    """The payload of an outbox row written without one (its builder failed then): from the object as it is now."""
    return build(event, apps.get_model(model).objects.get(pk=object_id))


def request_body(row):
    """What is posted for an outbox row: its payload, its reference and its idempotency key."""
    return {"examleaf_ref": row.examleaf_ref, "idempotency_key": row.idempotency_key, **row.payload}


# The day as ERPNext totals it (daily_totals), worked out from the platform's documents


def values(lines, shipping, shipping_rate):
    """A document's taxable value, exempt value and GST, its shipping in the shipping's treatment."""
    taxable = sum((entry["taxable"] for entry in lines if entry["item"].gst_rate), Decimal(0))
    exempt = sum((entry["amount"] for entry in lines if not entry["item"].gst_rate), Decimal(0))
    tax = sum((entry["cgst"] + entry["sgst"] + entry["igst"] for entry in lines), Decimal(0))
    if shipping and shipping_rate:
        shipping_taxable = rupees(shipping * 100 / (100 + shipping_rate))
        taxable, tax = taxable + shipping_taxable, tax + shipping - shipping_taxable
    elif shipping:
        exempt += shipping
    return taxable, exempt, tax


def invoice_values(document):
    """(total, taxable value, exempt value, GST, taxed?) of an invoice."""
    lines = invoices.context(document)["lines"]
    shipping = document.order.shipping_fee.amount
    _hsn, shipping_rate, _told = shipping_supply(lines) if shipping else ("", 0, False)
    taxable, exempt, tax = values(lines, shipping, shipping_rate)
    return document.order.total.amount, taxable, exempt, tax, bool(taxable)


def credit_note_values(note):
    data = invoices.credit_note_context(note)
    lines = [entry for entry in data["lines"] if entry["amount"] > 0]
    shipping = data["shipping_credit"]
    _hsn, shipping_rate, _told = shipping_supply(data["lines"]) if shipping else ("", 0, False)
    taxable, exempt, tax = values(lines, shipping, shipping_rate)
    return data["total_credit"], taxable, exempt, tax, bool(taxable)


# Answers


def method_path(method):
    return METHOD_PATH.format(method=method)


def resource_path(doctype, name):
    return RESOURCE_PATH.format(doctype=quote(doctype, safe=""), name=quote(str(name), safe=""))


def unwrap(data):
    """What a method answered: Frappe's envelope is {"message": <it>}."""
    if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict | list):
        return data["message"]
    return data


def error_of(data):
    """The refusal in an answer ({ok: false, error: {code, message, field}}), or None."""
    data = unwrap(data)
    if isinstance(data, dict) and data.get("ok") is False:
        return data.get("error") if isinstance(data.get("error"), dict) else {"code": "", "message": "refused"}
    return None


def describe(error):
    words = f"{error.get('code') or 'refused'}: {scrub(str(error.get('message') or ''))[:300]}".rstrip(": ")
    return f"{words} ({error['field']})" if error.get("field") else words


def refusal(data):
    """Why a 2xx answer is a refusal all the same, or ""."""
    error = error_of(data)
    return describe(error) if error else ""


def frappe_error(data):
    """Frappe's own words for an error it raised before the method ran (exc_type, its messages), scrubbed."""
    if not isinstance(data, dict):
        return ""
    messages = []
    try:
        for message in json.loads(data.get("_server_messages") or "[]"):
            message = json.loads(message) if isinstance(message, str) else message
            messages.append(str(message.get("message", message) if isinstance(message, dict) else message))
    except TypeError, ValueError:
        pass
    text = " ".join([str(data.get("exc_type") or ""), str(data.get("exception") or ""), *messages]).strip()
    return scrub(re.sub(r"<[^>]+>", "", text))[:300]


def permanent(code, field):
    """Whether a refusal never succeeds unchanged (PERMANENT; an invalid date excepted)."""
    if code == "invalid_request" and str(field or "").rsplit(".", 1)[-1] in DATE_FIELDS:
        return False
    return code in PERMANENT


def copies(value):
    """A quantity as text without a needless decimal point ("13", "12.5")."""
    return f"{Decimal(value).normalize():f}"


def number(value):
    """A quantity or an amount from ERPNext (a float, a string or nothing) as a Decimal."""
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except InvalidOperation:
        return Decimal(0)


def stock_rows(answer):
    """get_stock's rows: [(item code, actual, projected, reserved, batches)]."""
    rows = answer.get("items") or [] if isinstance(answer, dict) else []
    found = []
    for row in rows:
        if code := row.get("item_code"):
            actual, reserved = number(row.get("actual_qty")), number(row.get("reserved_qty"))
            found.append((code, actual, number(row.get("projected_qty", actual)), reserved, row.get("batches") or []))
    return found


def changes(answer):
    """get_changes_since's page: ([{name, modified, docstatus, examleaf_ref}], has_more, the next cursor)."""
    answer = answer if isinstance(answer, dict) else {}
    rows = [row for row in answer.get("rows") or [] if row.get("name") and row.get("modified")]
    after = answer.get("next") if isinstance(answer.get("next"), dict) else {}
    cursor = (str(after.get("modified_after") or ""), str(after.get("after_name") or ""))
    return rows, bool(answer.get("has_more")), cursor


def doorbell(raw):
    """A webhook's (doctype, name): what to read again."""
    data = json.loads(raw)
    return str(data.get("doctype") or ""), str(data.get("name") or "")


def own(doctype, row):
    """Whether a row of the pull ({name, modified, docstatus, examleaf_ref}) is ERPNext's copy of a storefront
    invoice or credit note (its examleaf_ref): never B2B (is_b2b), so not read again over REST for nothing."""
    return doctype == "Sales Invoice" and bool(row.get("examleaf_ref"))


def is_b2b(doctype, document):
    """Whether a document read back is B2B, to mirror (the storefront's own invoices and the B2C customer are not)."""
    if doctype == "Sales Invoice":
        return not document.get("examleaf_ref") and document.get("customer") != B2C_CUSTOMER
    if doctype == "Customer":
        return document.get("customer_group") in B2B_GROUPS
    return doctype in B2B_DOCTYPES


def mirror(doctype, document):
    """What a mirror keeps of a B2B document: (examleaf_ref, status, data, modified)."""
    data = {field: document.get(field) for field in MIRROR_FIELDS.get(doctype, ["name", "modified"])}
    if document.get("items"):
        data["items"] = [{field: entry.get(field) for field in MIRROR_ITEM_FIELDS} for entry in document["items"]]
    states = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
    status = document.get("status") or states.get(document.get("docstatus"), "")
    if doctype == "Customer":  # a master, never submitted (docstatus 0 would read "Draft"): enabled or not
        status = "Disabled" if document.get("disabled") else "Enabled"
    return str(document.get("examleaf_ref") or ""), str(status), data, str(document.get("modified") or "")


def day_totals(answer):
    """daily_totals' answer in the reconciliation's terms: every amount a decimal string, every count a number."""
    answer = answer if isinstance(answer, dict) else {}

    def documents(part):
        part = answer.get(part) or {}
        keys = ("total", "taxable_value", "exempt_value", "tax_total")
        return {"count": int(number(part.get("count"))), **{key: money(number(part.get(key))) for key in keys}}

    def counted(side):
        return {
            mode: {"count": int(number(entry.get("count"))), "amount": money(number(entry.get("amount")))}
            for mode, entry in sorted(((answer.get("payments") or {}).get(side) or {}).items())
        }

    shipped = answer.get("shipped") or {}
    return {
        "invoices": documents("invoices"),
        "credit_notes": documents("credit_notes"),
        "payments": {"receive": counted("receive"), "refund": counted("refund")},
        "settlements": {
            kind: {"count": int(number(entry.get("count"))), "total": money(number(entry.get("total")))}
            for kind, entry in sorted((answer.get("settlements") or {}).items())
        },
        "shipped": {
            "delivery_notes": int(number(shipped.get("delivery_notes"))),
            "items": {code: int(number(qty)) for code, qty in sorted((shipped.get("items") or {}).items())},
        },
    }
