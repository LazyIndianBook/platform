"""A double of ERPNext with the examleaf_erp app (examleaf-erp/API.md), in memory, for the tests and ERP_MODE=fake
(development): an httpx MockTransport that answers as the app does and keeps what it was sent.

- Frappe's envelope on every answer ({"message": ...}); Frappe's own refusals before a method runs (no token 403, a
  wrong one 401, a GET 403) in Frappe's body; the app's refusals with their HTTP status and {ok: false, error}.
- Strict fields: a required one missing, an unknown one (anywhere, nested too), a reference or key not in its format,
  a total that does not add up, a date in the future: 400 invalid_request.
- Idempotency: the same key and body answer the first result again (duplicate: true); the same reference under a
  new key, the short form, unless its invoice is another order's (or its credit note another invoice's: 409
  conflict); the same key with another body, 409 idempotency_key_reused. Refusals are not remembered.
- What ERPNext refuses: an item not upserted (404), a document of an invoice it does not have (404), more paid or
  credited than there is (422), a delivery without the copies in the warehouse (422 insufficient_stock) or with
  nothing left to deliver (422). GST as ERPNext rounds it: once per tax and rate on the invoice's taxable value.
- Stock: the tests put copies in (receive(): a Purchase Receipt and its Stock Ledger Entry), or hold some for a B2B
  order (reserve()); delivery notes take them out (a bundle's books), oldest print run first.
- The pull's pages by (modified, name), the day's totals, Frappe's REST re-read of what the sync user may read.
- Scripting: fail(method, status, times, headers) makes the next calls fail (429 with a Retry-After, 503 ...);
  lose_answer(method) does the work and loses the answer (a 504); add_b2b() makes a B2B document; webhook() is the
  body (Frappe's JSON: sorted keys, one-space indent) and the signature ERPNext would post.
In development it lives in one process: a worker beside the web process has its own (as shipping's fake)."""

import base64
import copy
import hashlib
import hmac
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote

import httpx
from django.utils import timezone
from stdnum import isbn as isbn_number

from shop.models import STATES, rupees

METHOD = re.compile(r"^/api/method/examleaf_erp\.api\.(?P<method>\w+)$")
RESOURCE = re.compile(r"^/api/resource/(?P<doctype>[^/]+)/(?P<name>.+)$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]{0,139}$")
REF = re.compile(r"^[a-z][a-z0-9_-]{1,30}:[A-Za-z0-9][A-Za-z0-9/_.:-]{0,100}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?$")
NUMBER = re.compile(r"^(EL|T|CN|TC)/\d{4}-\d{2}/\d{5}$")
ORDER_NUMBER = re.compile(r"^[A-Z]{2}-\d{4}-\d{6,9}$")
STOCK_KINDS = ("sample-papers", "solutions")
MODES = ("razorpay", "cod", "upi", "neft", "cheque")
WAREHOUSES = ("Main", "Damaged", "At Printer")
SELLER_STATE = "AS"
READABLE = {  # what EL Sync may read over /api/resource (not stock documents: get_stock)
    *["Item", "Item Price", "Product Bundle", "Customer", "Address", "Contact", "Sales Invoice", "Payment Entry"],
    *["Journal Entry", "Delivery Note", "Quotation"],
}
CHANGE_DOCTYPES = {
    *["Item", "Item Price", "Customer", "Quotation", "Sales Order", "Sales Invoice", "Delivery Note"],
    *["Payment Entry", "Purchase Receipt", "Stock Reconciliation", "Stock Ledger Entry", "Bin", "Batch"],
    *["Distributor Agreement", "School Adoption"],
}
MUTATING = {"upsert_item", "upsert_bundle", "create_sales_invoice", "create_credit_note", "create_payment_entry"}
MUTATING |= {"record_settlement", "create_delivery_note", "upsert_b2b_customer"}
SIGNED = {"examleaf_ref", "idempotency_key"}
FIELDS = {  # method: (required, optional)
    "ping": (set(), set()),
    "upsert_item": (
        {*SIGNED, "item_code", "item_name", "kind", "hsn_code", "gst_rate", "mrp"},
        {"gst_rate_effective_from", "description", "isbn", "weight_grams", "subject", "class_level", "board"}
        | {"edition", "is_active"},
    ),
    "upsert_bundle": ({*SIGNED, "item_code", "items"}, {"is_active"}),
    "create_sales_invoice": (
        {*SIGNED, "invoice_number", "posting_date", "order_number", "shipping_address", "items", "total"},
        {"channel", "doc_kind", "shipping_fee", "shipping_hsn_code", "shipping_gst_rate"},
    ),
    "create_credit_note": (
        {*SIGNED, "credit_note_number", "invoice_number", "posting_date", "reason", "total"},
        {"items", "shipping_credit"},
    ),
    "create_payment_entry": (
        {*SIGNED, "invoice_number", "amount", "posting_date", "mode", "reference_no"},
        {"reference_date"},
    ),
    "record_settlement": (
        {*SIGNED, "kind", "settlement_id", "posting_date", "gross_amount", "net_amount"},
        {"fee", "tax_on_fee", "tax_type", "utr"},
    ),
    "create_delivery_note": (
        {*SIGNED, "invoice_number", "posting_date"},
        {"warehouse", "items", "courier", "tracking_number"},
    ),
    "get_stock": (set(), {"item_code", "warehouse", "by_batch"}),
    "get_changes_since": ({"doctype", "modified_after"}, {"after_name", "limit"}),
    "daily_totals": ({"date"}, set()),
    "upsert_b2b_customer": (
        {*SIGNED, "customer_name", "customer_group"},
        {"gstin", "udise_code", "school_board", "school_medium", "district", "address", "contact"},
    ),
}
NESTED = {  # (method, field): (required, optional) of each entry
    ("create_sales_invoice", "shipping_address"): ({"city", "state", "pin"}, {"district"}),
    ("create_sales_invoice", "items"): ({"item_code", "qty", "rate", "gst_rate"}, {"discount", "hsn_code"}),
    ("upsert_bundle", "items"): ({"item_code", "qty"}, set()),
    ("create_credit_note", "items"): ({"item_code", "amount"}, {"qty"}),
    ("create_delivery_note", "items"): ({"item_code", "qty"}, set()),
}
DOC_HEADINGS = {
    "tax_invoice": "Tax Invoice",
    "bill_of_supply": "Bill of Supply",
    "invoice_cum_bill_of_supply": "Invoice-cum-Bill of Supply",
}


class Refused(Exception):
    def __init__(self, code, message, status=400, field=None):
        super().__init__(message)
        self.code, self.message, self.status, self.field = code, message, status, field


def bad(field, message):
    return Refused("invalid_request", message, 400, field)


def missing(value):
    return value is None or value == ""


def check(data, required, optional, path=""):
    """The app's Fields: a required field missing or an unknown one, refused with its dotted name."""
    name = lambda key: f"{path}.{key}" if path else key  # noqa: E731
    if not isinstance(data, dict):
        raise bad(path or "body", "Send an object.")
    for key in sorted(required):
        if missing(data.get(key)):
            raise bad(name(key), "This field is required.")
    if extra := sorted(set(data) - required - optional):
        raise bad(name(extra[0]), "Unknown field.")


def amount(data, key, path="", positive=False):
    try:
        value = Decimal(str(data.get(key, "0") or "0"))
    except InvalidOperation:
        raise bad(f"{path}{key}", 'Send an amount in rupees, like "299.00".') from None
    if value != value.quantize(Decimal("0.01")) or value < 0 or (positive and value == 0):
        raise bad(f"{path}{key}", "An amount in rupees, positive, at most 2 decimals.")
    return value


def day(data, key):
    try:
        value = date.fromisoformat(str(data[key]))
    except TypeError, ValueError:
        raise bad(key, "Not a date (YYYY-MM-DD).") from None
    if value > timezone.localdate():
        raise bad(key, "This date is in the future.")
    return value


def taxes(rows, state):
    """(taxable value, exempt value, GST) as ERPNext rounds them: each taxed row's taxable value worked back out of
    its tax-inclusive amount, then each tax rounded once on a rate's taxable value (CGST and SGST in the seller's
    state, IGST elsewhere)."""
    taxable, exempt, by_rate = Decimal(0), Decimal(0), defaultdict(Decimal)
    for row in rows:
        if row["gst_rate"]:
            value = rupees(row["amount"] * 100 / (100 + row["gst_rate"]))
            taxable += value
            by_rate[row["gst_rate"]] += value
        else:
            exempt += row["amount"]
    tax = Decimal(0)
    for gst_rate, value in by_rate.items():
        tax += 2 * rupees(value * gst_rate / 200) if state == SELLER_STATE else rupees(value * gst_rate / 100)
    return taxable, exempt, tax


def kind_of(rows):
    taxed = {bool(row["gst_rate"]) for row in rows if not row.get("shipping")}
    if taxed == {True, False}:
        return "invoice_cum_bill_of_supply"
    return "tax_invoice" if True in taxed else "bill_of_supply"


def money_str(value):
    return f"{Decimal(value):.2f}"


class FakeErpNext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.docs = {}  # (doctype, name): the document
        self.refs = {}  # examleaf_ref: (doctype, name)
        self.keys = {}  # idempotency_key: (the request's digest, the first answer)
        self.bins = defaultdict(Decimal)  # (item code, warehouse): copies held
        self.reserved = defaultdict(Decimal)  # (item code, warehouse): copies a B2B order holds
        self.batches = defaultdict(list)  # (item code, warehouse): [{"batch_no", "qty", "print_date", "edition"}]
        self.changes = []  # (modified, doctype, name, examleaf_ref): what the pull reads
        self.failures = []  # [method or path, status, body, headers, times left]
        self.lost = defaultdict(int)  # method: answers to lose after doing the work
        self.calls = []  # (method or path, the body) of every request
        self.counter = 0
        self.log = 0

    def transport(self):
        return httpx.MockTransport(self.handle)

    # Scripting

    def fail(self, method, status=503, times=1, headers=None, body=None):
        """The next `times` calls of `method` (or a path's start) answer `status` (headers: e.g. Retry-After)."""
        self.failures.append([method, status, body, headers or {}, times])

    def lose_answer(self, method, times=1):
        """The next `times` calls of `method` do their work, then their answer is lost on the way (a 504)."""
        self.lost[method] += times

    def modified(self):
        """ERPNext's `modified`, increasing (its own time, without an offset)."""
        self.counter += 1
        return f"{timezone.localtime():%Y-%m-%d %H:%M:%S}.{self.counter:06d}"

    def changed(self, doctype, name, ref=""):
        stamp = self.modified()
        self.docs[(doctype, name)]["modified"] = stamp
        self.changes.append((stamp, doctype, name, ref))
        return stamp

    def next_name(self, prefix):
        self.counter += 1
        return f"{prefix}-{self.counter:05d}"

    def warehouse(self, name):
        name = name or "Main"
        short = name.removesuffix(" - EL")
        if short not in WAREHOUSES:
            raise bad("warehouse", f"No warehouse {short} - EL.")
        return f"{short} - EL"

    def receive(self, item_code, qty, warehouse="Main", batch="PR-1", print_date="2026-09-01"):
        """A printer's copies received (a Purchase Receipt and its Stock Ledger Entry): its name."""
        where = self.warehouse(warehouse)
        name = self.next_name("MAT-PRE")
        line = {"item_code": item_code, "qty": qty, "warehouse": where, "batch_no": batch}
        self.docs[("Purchase Receipt", name)] = {"name": name, "docstatus": 1, "items": [line]}
        self.changed("Purchase Receipt", name)
        found = next((b for b in self.batches[(item_code, where)] if b["batch_no"] == batch), None)
        if found:
            found["qty"] += float(qty)
        else:
            self.batches[(item_code, where)].append(
                {"batch_no": batch, "qty": float(qty), "print_date": print_date, "edition": "2027"}
            )
        self.move(item_code, where, Decimal(qty), voucher=name)
        return name

    def reserve(self, item_code, qty, warehouse="Main"):
        """Copies a B2B sales order holds in ERPNext (get_stock's reserved_qty)."""
        self.reserved[(item_code, self.warehouse(warehouse))] += Decimal(qty)

    def move(self, item_code, warehouse, qty, voucher=""):
        self.bins[(item_code, warehouse)] += qty
        sle = self.next_name("MAT-SLE")
        self.docs[("Stock Ledger Entry", sle)] = {
            "name": sle,
            "item_code": item_code,
            "warehouse": warehouse,
            "actual_qty": float(qty),
            "voucher_no": voucher,
            "docstatus": 1,
        }
        self.changed("Stock Ledger Entry", sle)
        return sle

    def add_b2b(self, doctype, name=None, **fields):
        """A B2B document made in ERPNext (a school's invoice, a quotation, a customer): its name."""
        name = name or self.next_name({"Sales Invoice": "SINV-26", "Quotation": "SAL-QTN"}.get(doctype, "CUST"))
        self.docs[(doctype, name)] = {"name": name, "docstatus": 1, "examleaf_ref": None, **fields}
        self.changed(doctype, name)
        return name

    def webhook(self, doctype, name, secret, event="on_submit"):
        """(body, signature) of the doorbell ERPNext would post for this document: Frappe's as_json (sorted keys, one
        space of indent), signed with HMAC-SHA256 and base64."""
        document = self.docs.get((doctype, name), {})
        data = {
            "doctype": doctype,
            "event": event,
            "examleaf_ref": document.get("examleaf_ref"),
            "modified": document.get("modified", ""),
            "name": name,
        }
        raw = json.dumps(data, sort_keys=True, indent=1).encode()
        signature = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
        return raw, signature

    def doc(self, doctype, name):
        return self.docs.get((doctype, name))

    def by_ref(self, ref):
        found = self.refs.get(ref)
        return self.docs.get(found) if found else None

    def of(self, doctype):
        return [document for (kind, _), document in self.docs.items() if kind == doctype]

    # The transport

    def json(self, status, data, headers=None):
        body = json.dumps(data, default=str)  # the documents keep Decimals; Frappe sends them as numbers or text
        return httpx.Response(status, content=body, headers={"Content-Type": "application/json", **(headers or {})})

    def frappe(self, status, exc_type, message=""):
        return self.json(status, {"exc_type": exc_type, "exception": message})

    def answer(self, status, answer):
        self.log += 1
        return self.json(status, {"message": {**answer, "log": f"SYNC-LOG-{self.log:05d}"}})

    def handle(self, request):
        path = unquote(request.url.path)
        method = (match.group("method") if (match := METHOD.match(path)) else "") or path
        payload = json.loads(request.content) if request.content else {}
        self.calls.append((method, payload))
        for failure in self.failures:
            wanted, status, body, headers, times = failure
            if times and (method == wanted or path.startswith(wanted)):
                failure[4] -= 1
                return self.json(status, body or {"exc_type": "ServiceUnavailable"}, headers)
        token = str(request.headers.get("Authorization", ""))
        if not token:
            return self.frappe(403, "PermissionError", "Not permitted")
        key_secret = token.removeprefix("token ").split(":")
        if not token.startswith("token ") or len(key_secret) != 2 or not all(key_secret):
            return self.frappe(401, "AuthenticationError", "Invalid key")
        if match := RESOURCE.match(path):
            doctype, name = match.group("doctype"), match.group("name")
            if request.method != "GET" or doctype not in READABLE:
                return self.frappe(403, "PermissionError", f"No permission for {doctype}")
            document = self.docs.get((doctype, name))
            if document is None:
                return self.frappe(404, "DoesNotExistError", f"{doctype} {name} not found")
            return self.json(200, {"data": copy.deepcopy(document)})
        if not METHOD.match(path) or method not in FIELDS:
            return self.frappe(404, "DoesNotExistError", f"No method {method}")
        if request.method != "POST":
            return self.frappe(403, "PermissionError", "POST only")
        return self.run(method, payload)

    def run(self, method, payload):
        ref = payload.get("examleaf_ref") if isinstance(payload.get("examleaf_ref"), str) else None
        key = payload.get("idempotency_key") if isinstance(payload.get("idempotency_key"), str) else None
        digest = hashlib.sha256(
            json.dumps({k: v for k, v in payload.items() if k != "idempotency_key"}, sort_keys=True).encode()
        ).hexdigest()
        try:
            check(payload, *FIELDS[method])
            if method in MUTATING:
                if not REF.match(ref or ""):
                    raise bad("examleaf_ref", "This value is not in the expected format.")
                if not KEY.match(key or ""):
                    raise bad("idempotency_key", "This value is not in the expected format.")
                if key in self.keys:
                    first_digest, first = self.keys[key]
                    if first_digest != digest:
                        message = "This idempotency_key was used before with a different request."
                        raise Refused("idempotency_key_reused", message, 409, "idempotency_key")
                    return self.answer(200, {**first, "duplicate": True})
            result = getattr(self, f"api_{method}")(payload)
        except Refused as error:
            refusal = {"code": error.code, "message": error.message, "field": error.field}
            failed = {"ok": False, "duplicate": False, "examleaf_ref": ref, "name": None, "error": refusal}
            return self.answer(error.status, failed)
        result = {"ok": True, "duplicate": False, **result}
        result.setdefault("examleaf_ref", ref)
        if method in MUTATING:
            self.keys[key] = (digest, result)
        if self.lost[method]:  # done, but the answer never reaches the platform
            self.lost[method] -= 1
            return self.json(504, {"exc_type": "GatewayTimeout"})
        return self.answer(200, result)

    def existing(self, doctype, ref, name=None, same=None):
        """The app's find_existing: the short form for a reference seen before, a 409 for a number taken, or for a
        reference whose document holds another value of `same` ({key: (field, value)}: a number issued again for
        another order)."""
        if ref in self.refs:
            kind, found = self.refs[ref]
            if name and found != name:
                raise Refused("conflict", f"{ref} is already {doctype} {found}.", 409, "examleaf_ref")
            for key, (field, value) in (same or {}).items():
                if (there := self.docs[(kind, found)].get(key)) != value:
                    raise Refused("conflict", f"{doctype} {found} is {there}'s, not {value}'s.", 409, field)
            return {"name": found, "duplicate": True, "docstatus": self.docs[(kind, found)]["docstatus"]}
        if name and (doctype, name) in self.docs:
            raise Refused("conflict", f"{doctype} {name} exists with another reference.", 409, "invoice_number")
        return None

    def store(self, doctype, name, ref, document):
        self.docs[(doctype, name)] = {"name": name, "examleaf_ref": ref, "docstatus": 1, **document}
        self.refs[ref] = (doctype, name)
        self.changed(doctype, name, ref)

    def item(self, code, field="item_code"):
        found = self.docs.get(("Item", code))
        if found is None:
            raise Refused("not_found", f"No Item {code}: upsert_item first.", 404, field)
        return found

    def invoice(self, number, field="invoice_number", returns=False):
        found = self.docs.get(("Sales Invoice", number))
        if not found or found["docstatus"] != 1 or not found["examleaf_ref"] or (found["is_return"] and not returns):
            raise Refused("not_found", f"No submitted platform invoice {number}.", 404, field)
        return found

    def summary(self, document):
        return {
            "name": document["name"],
            "doc_kind": document["doc_kind"],
            "print_heading": DOC_HEADINGS[document["doc_kind"]],
            "place_of_supply": document["place_of_supply"],
            "grand_total": money_str(document["grand_total"]),
            "taxable_value": money_str(document["taxable_value"]),
            "exempt_value": money_str(document["exempt_value"]),
            "tax_total": money_str(document["tax_total"]),
        }

    # The methods

    def api_ping(self, payload):
        versions = {"frappe": "16.50.0", "erpnext": "16.50.0", "india_compliance": "16.10.0", "examleaf_erp": "0.1.0"}
        return {"name": "erp.fake.test", "user": "erp-sync@examleaf.in", "time": self.modified(), "versions": versions}

    def api_upsert_item(self, payload):
        ref, code, kind = payload["examleaf_ref"], payload["item_code"], payload["kind"]
        if kind not in ("sample-papers", "solutions", "bundle", "digital"):
            raise bad("kind", "One of: sample-papers, solutions, bundle, digital.")
        if not re.fullmatch(r"\d{4}(\d{2}){0,2}", payload["hsn_code"]):
            raise bad("hsn_code", "This value is not in the expected format.")
        if kind == "digital" and payload["hsn_code"].startswith("49"):
            raise bad("hsn_code", "Chapter 49 is printed matter: a course takes its SAC code (99…).")
        if payload.get("isbn") and not isbn_number.is_valid(payload["isbn"]):
            raise bad("isbn", "Not a valid ISBN-10 or ISBN-13.")
        amount(payload, "mrp")
        existing = self.by_ref(ref)
        if existing and existing["name"] != code:
            raise Refused(
                "conflict", f"{ref} is the Item {existing['name']}: an item_code never changes.", 409, "item_code"
            )
        if not existing and ("Item", code) in self.docs:
            raise Refused("conflict", f"Item {code} exists without this examleaf_ref.", 409, "item_code")
        stock = kind in STOCK_KINDS
        if existing and existing["is_stock_item"] != stock:
            raise Refused("conflict", "This kind would change whether the Item holds stock.", 409, "kind")
        fields = {k: v for k, v in payload.items() if k not in SIGNED}
        self.store(
            "Item", code, ref, {**fields, "is_stock_item": stock, "disabled": not payload.get("is_active", True)}
        )
        return {"name": code, "created": not existing}

    def api_upsert_bundle(self, payload):
        code = payload["item_code"]
        item = self.docs.get(("Item", code))
        if not item or not item.get("examleaf_ref"):
            raise Refused("not_found", f"No platform Item {code}: upsert_item first.", 404, "item_code")
        if item["kind"] != "bundle":
            raise Refused("conflict", f"Item {code} is not a bundle (kind {item['kind']}).", 409, "item_code")
        rows = payload["items"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
            raise bad("items", "From 1 to 50 entries.")
        for index, row in enumerate(rows):
            check(row, *NESTED[("upsert_bundle", "items")], f"items[{index}]")
            self.item(row["item_code"], f"items[{index}].item_code")
            if ("Product Bundle", row["item_code"]) in self.docs:
                raise bad(f"items[{index}].item_code", "A bundle cannot hold a bundle.")
        created = ("Product Bundle", code) not in self.docs
        self.docs[("Product Bundle", code)] = {
            "name": code,
            "new_item_code": code,
            "items": [{"item_code": row["item_code"], "qty": row["qty"]} for row in rows],
            "disabled": not payload.get("is_active", True),
            "docstatus": 0,
        }
        self.changed("Product Bundle", code)
        return {"name": code, "created": created}

    def api_create_sales_invoice(self, payload):
        ref, number = payload["examleaf_ref"], payload["invoice_number"]
        if not NUMBER.match(number) or number.startswith(("CN", "TC")):
            raise bad("invoice_number", "Not an invoice number of the platform's series.")
        posting_date = day(payload, "posting_date")
        if not ORDER_NUMBER.match(payload["order_number"]):
            raise bad("order_number", "This value is not in the expected format.")
        address = payload["shipping_address"]
        check(address, *NESTED[("create_sales_invoice", "shipping_address")], "shipping_address")
        if address["state"] not in STATES:
            raise bad("shipping_address.state", "One of the two-letter state codes.")
        if not re.fullmatch(r"[1-9]\d{5}", str(address["pin"])):
            raise bad("shipping_address.pin", "This value is not in the expected format.")
        rows = []
        for index, line in enumerate(payload["items"]):
            path = f"items[{index}]"
            check(line, *NESTED[("create_sales_invoice", "items")], path)
            charge = amount(line, "rate", f"{path}.") * line["qty"] - amount(line, "discount", f"{path}.")
            if charge < 0:
                raise bad(f"{path}.discount", "The discount is more than the line.")
            item = self.item(line["item_code"], f"{path}.item_code")
            gst_rate = amount(line, "gst_rate", f"{path}.")
            rows.append({"item_code": item["name"], "qty": line["qty"], "amount": charge, "gst_rate": gst_rate})
        shipping = amount(payload, "shipping_fee")
        if shipping:
            goods = [row for row in rows if self.docs[("Item", row["item_code"])]["is_stock_item"]]
            goods = goods or [row for row in rows if ("Product Bundle", row["item_code"]) in self.docs]
            told = payload.get("shipping_gst_rate") not in (None, "")
            if not told and (not goods or len({row["gst_rate"] for row in goods}) > 1):
                raise bad("shipping_gst_rate", "Send shipping_hsn_code and shipping_gst_rate.")
            shipping_rate = (
                amount(payload, "shipping_gst_rate") if told else max(goods, key=lambda r: r["amount"])["gst_rate"]
            )
            rows.append(
                {"item_code": "EL-SHIPPING", "qty": 1, "amount": shipping, "gst_rate": shipping_rate, "shipping": True}
            )
        total = amount(payload, "total")
        if sum((row["amount"] for row in rows), Decimal(0)) != total:
            raise bad("total", "The lines and shipping do not add up to the total.")
        same_order = {"order_number": ("order_number", payload["order_number"])}
        if duplicate := self.existing("Sales Invoice", ref, number, same=same_order):
            return duplicate
        kind = kind_of(rows)
        if payload.get("doc_kind") and payload["doc_kind"] != kind:
            raise Refused("doc_kind_mismatch", f"The lines make this a {kind}.", 422, "doc_kind")
        taxable, exempt, tax = taxes(rows, address["state"])
        state = STATES[address["state"]]
        document = {
            "customer": "Online Customers (B2C)",
            "posting_date": posting_date.isoformat(),
            "order_number": payload["order_number"],
            "items": rows,
            "doc_kind": kind,
            "place_of_supply": f"{'18' if address['state'] == 'AS' else '00'}-{state}",
            "state": address["state"],
            "grand_total": total,
            "taxable_value": taxable,
            "exempt_value": exempt,
            "tax_total": tax,
            "outstanding_amount": total,
            "credited": defaultdict(Decimal),
            "delivered": defaultdict(int),
            "is_return": 0,
        }
        self.store("Sales Invoice", number, ref, document)
        return self.summary(self.docs[("Sales Invoice", number)])

    def api_create_credit_note(self, payload):
        ref, number = payload["examleaf_ref"], payload["credit_note_number"]
        if not NUMBER.match(number) or not number.startswith(("CN", "TC")):
            raise bad("credit_note_number", "Not a credit note number of the platform's series.")
        posting_date = day(payload, "posting_date")
        credits = payload.get("items") or []
        for index, credit in enumerate(credits):
            check(credit, *NESTED[("create_credit_note", "items")], f"items[{index}]")
            amount(credit, "amount", f"items[{index}].", positive=True)
        shipping = amount(payload, "shipping_credit")
        total = amount(payload, "total", positive=True)
        if sum((Decimal(c["amount"]) for c in credits), Decimal(0)) + shipping != total:
            raise bad("total", "The credits do not add up to the total.")
        same_invoice = {"return_against": ("invoice_number", payload["invoice_number"])}
        if duplicate := self.existing("Sales Invoice", ref, number, same=same_invoice):
            return duplicate
        original = self.invoice(payload["invoice_number"])
        if posting_date < date.fromisoformat(original["posting_date"]):
            raise bad("posting_date", "A credit note cannot be dated before its invoice.")
        lines = {row["item_code"]: row for row in original["items"]}
        rows = []
        for index, credit in enumerate(credits):
            line = lines.get(credit["item_code"])
            if line is None or line.get("shipping"):
                raise bad(f"items[{index}].item_code", f"{credit['item_code']} is not a line of the invoice.")
            value = Decimal(credit["amount"])
            if original["credited"][credit["item_code"]] + value > line["amount"]:
                raise Refused("over_credit", "More credited than the line has left.", 422, f"items[{index}]")
            rows.append({"item_code": line["item_code"], "amount": value, "gst_rate": line["gst_rate"]})
        if shipping:
            line = next((row for row in original["items"] if row.get("shipping")), None)
            if line is None:
                raise bad("shipping_credit", "The invoice charged no shipping.")
            rows.append(
                {"item_code": "EL-SHIPPING", "amount": shipping, "gst_rate": line["gst_rate"], "shipping": True}
            )
        for row in rows:
            original["credited"][row["item_code"]] += row["amount"]
        taxable, exempt, tax = taxes(rows, original["state"])
        document = {
            "posting_date": posting_date.isoformat(),
            "items": rows,
            "doc_kind": kind_of(rows),
            "place_of_supply": original["place_of_supply"],
            "state": original["state"],
            "grand_total": total,
            "taxable_value": taxable,
            "exempt_value": exempt,
            "tax_total": tax,
            "outstanding_amount": total,  # to be refunded
            "is_return": 1,
            "return_against": original["name"],
            "remarks": payload["reason"],
        }
        self.store("Sales Invoice", number, ref, document)
        note = self.docs[("Sales Invoice", number)]
        return {**self.summary(note), "return_against": original["name"], "total_credit": money_str(total)}

    def api_create_payment_entry(self, payload):
        ref = payload["examleaf_ref"]
        paid = amount(payload, "amount", positive=True)
        posting_date = day(payload, "posting_date")
        if payload["mode"] not in MODES:
            raise bad("mode", f"One of: {', '.join(MODES)}.")
        if duplicate := self.existing("Payment Entry", ref):
            return duplicate
        against = self.invoice(payload["invoice_number"], returns=True)
        if paid > against["outstanding_amount"]:
            raise Refused("overpayment", f"{against['name']} has less outstanding.", 422, "amount")
        against["outstanding_amount"] -= paid
        name = self.next_name("ACC-PAY")
        kind = "Pay" if against["is_return"] else "Receive"
        document = {
            "payment_type": kind,
            "mode": payload["mode"],
            "paid_amount": paid,
            "posting_date": posting_date.isoformat(),
            "reference_no": payload["reference_no"],
            "against": against["name"],
        }
        self.store("Payment Entry", name, ref, document)
        left = money_str(against["outstanding_amount"])
        return {"name": name, "payment_type": kind, "against": against["name"], "outstanding_after": left}

    def api_record_settlement(self, payload):
        ref = payload["examleaf_ref"]
        if payload["kind"] not in ("razorpay", "cod"):
            raise bad("kind", "One of: razorpay, cod.")
        posting_date = day(payload, "posting_date")
        gross, net = amount(payload, "gross_amount", positive=True), amount(payload, "net_amount", positive=True)
        fee, tax = amount(payload, "fee"), amount(payload, "tax_on_fee")
        if gross != net + fee + tax:
            raise bad("gross_amount", "gross_amount must be net_amount + fee + tax_on_fee.")
        if duplicate := self.existing("Journal Entry", ref):
            return duplicate
        name = self.next_name("ACC-JV")
        document = {"kind": payload["kind"], "gross": gross, "net": net, "fee": fee, "tax": tax}
        self.store(
            "Journal Entry",
            name,
            ref,
            {**document, "posting_date": posting_date.isoformat(), "utr": payload.get("utr")},
        )
        return {"name": name}

    def api_create_delivery_note(self, payload):
        ref = payload["examleaf_ref"]
        posting_date = day(payload, "posting_date")
        where = self.warehouse(payload.get("warehouse"))
        wanted = defaultdict(int)
        for index, row in enumerate(payload.get("items") or []):
            check(row, *NESTED[("create_delivery_note", "items")], f"items[{index}]")
            wanted[row["item_code"]] += row["qty"]
        if duplicate := self.existing("Delivery Note", ref):
            return duplicate
        invoice = self.invoice(payload["invoice_number"])
        asked = dict(wanted)  # empty: everything not yet delivered
        leaving = []  # (invoice line's item code, qty, its bundle)
        for row in invoice["items"]:
            item = self.docs.get(("Item", row["item_code"]), {})
            bundle = self.docs.get(("Product Bundle", row["item_code"]))
            if row.get("shipping") or not (item.get("is_stock_item") or bundle):
                continue  # the course and the delivery charge: nothing leaves the warehouse
            left = row["qty"] - invoice["delivered"][row["item_code"]]
            take = min(left, asked.get(row["item_code"], 0)) if asked else left
            if take > 0:
                leaving.append((row["item_code"], take, bundle))
                if asked:
                    asked[row["item_code"]] -= take
        if asked and any(qty > 0 for qty in asked.values()):
            raise bad("items", "The invoice has not that many more to deliver.")
        if not leaving:
            raise Refused("nothing_to_deliver", "The invoice has no goods left to deliver.", 422, "invoice_number")
        books = defaultdict(int)  # stock item: copies
        for code, qty, bundle in leaving:
            for part in bundle["items"] if bundle else [{"item_code": code, "qty": 1}]:
                if self.docs.get(("Item", part["item_code"]), {}).get("is_stock_item"):
                    books[part["item_code"]] += part["qty"] * qty
        for code, qty in books.items():
            if self.bins[(code, where)] < qty:
                raise Refused("insufficient_stock", f"{where} has fewer than {qty} of {code}.", 422, "items")
        name = self.next_name("MAT-DN")
        picked = []
        for code, qty in books.items():
            need = qty
            for batch in self.batches[(code, where)]:
                take = min(need, batch["qty"])
                if take > 0:
                    batch["qty"] -= take
                    picked.append({"item_code": code, "batch_no": batch["batch_no"], "qty": float(take)})
                    need -= take
            self.move(code, where, -Decimal(qty), voucher=name)
        for code, qty, _bundle in leaving:
            invoice["delivered"][code] += qty
        document = {
            "posting_date": posting_date.isoformat(),
            "against": invoice["name"],
            "warehouse": where,
            "books": dict(books),
            "courier": payload.get("courier"),
            "tracking_number": payload.get("tracking_number"),
        }
        self.store("Delivery Note", name, ref, document)
        return {"name": name, "against": invoice["name"], "warehouse": where, "batches": picked}

    def api_get_stock(self, payload):
        where = self.warehouse(payload["warehouse"]) if payload.get("warehouse") else None
        if payload.get("item_code"):
            self.item(payload["item_code"])
        out = []
        for (code, warehouse), actual in sorted(self.bins.items()):
            if (where and warehouse != where) or (payload.get("item_code") and code != payload["item_code"]):
                continue
            reserved = self.reserved[(code, warehouse)]
            entry = {
                "item_code": code,
                "warehouse": warehouse,
                "actual_qty": float(actual),
                "projected_qty": float(actual - reserved),
                "reserved_qty": float(reserved),
            }
            if payload.get("by_batch", True):
                entry["batches"] = [dict(b) for b in self.batches[(code, warehouse)] if b["qty"] > 0]
            out.append(entry)
        return {"name": None, "items": out}

    def api_get_changes_since(self, payload):
        doctype, since = payload["doctype"], payload["modified_after"]
        if doctype not in CHANGE_DOCTYPES:
            raise bad("doctype", "Not a doctype the pull reads.")
        if not DATETIME.match(since):
            raise bad("modified_after", "This value is not in the expected format.")
        after_name = payload.get("after_name") or ""
        limit = int(payload.get("limit") or 100)
        latest = {}  # a document changed twice: its last change only (its `modified` moved on)
        for stamp, kind, name, ref in self.changes:
            if kind == doctype:
                latest[name] = (stamp, name, ref)
        rows = sorted(
            row for row in latest.values() if row[0] > since or (after_name and row[0] == since and row[1] > after_name)
        )
        page = [
            {
                "name": name,
                "modified": stamp,
                "docstatus": self.docs[(doctype, name)].get("docstatus", 0),
                "examleaf_ref": ref or None,
            }
            for stamp, name, ref in rows[:limit]
        ]
        cursor = {"modified_after": page[-1]["modified"], "after_name": page[-1]["name"]} if page else None
        return {
            "name": None,
            "rows": page,
            "has_more": len(rows) > limit,
            "next": cursor or {"modified_after": since, "after_name": after_name or None},
        }

    def api_daily_totals(self, payload):
        try:
            when = date.fromisoformat(str(payload["date"])).isoformat()  # a day to come is allowed (and empty)
        except ValueError:
            raise bad("date", "Not a date (YYYY-MM-DD).") from None
        documents = [d for d in self.of("Sales Invoice") if d.get("posting_date") == when and d.get("examleaf_ref")]

        def summary(rows):
            by_kind = defaultdict(int)
            for row in rows:
                by_kind[row["doc_kind"]] += 1
            return {
                "count": len(rows),
                "total": money_str(sum((r["grand_total"] for r in rows), Decimal(0))),
                "taxable_value": money_str(sum((r["taxable_value"] for r in rows), Decimal(0))),
                "exempt_value": money_str(sum((r["exempt_value"] for r in rows), Decimal(0))),
                "tax_total": money_str(sum((r["tax_total"] for r in rows), Decimal(0))),
                "by_kind": dict(sorted(by_kind.items())),
            }

        payments = {"receive": {}, "refund": {}}
        for entry in self.of("Payment Entry"):
            if entry["posting_date"] == when:
                side = payments["receive" if entry["payment_type"] == "Receive" else "refund"]
                found = side.setdefault(entry["mode"], {"count": 0, "amount": Decimal(0)})
                found["count"] += 1
                found["amount"] += entry["paid_amount"]
        settlements = {}
        for entry in self.of("Journal Entry"):
            if entry["posting_date"] == when:
                found = settlements.setdefault(entry["kind"], {"count": 0, "total": Decimal(0)})
                found["count"] += 1
                found["total"] += entry["gross"]
        notes = [note for note in self.of("Delivery Note") if note["posting_date"] == when]
        shipped = defaultdict(float)
        for note in notes:
            for code, qty in note["books"].items():
                shipped[code] += qty
        return {
            "name": None,
            "date": when,
            "invoices": summary([d for d in documents if not d["is_return"]]),
            "credit_notes": summary([d for d in documents if d["is_return"]]),
            "payments": {
                side: {mode: {"count": e["count"], "amount": money_str(e["amount"])} for mode, e in entries.items()}
                for side, entries in payments.items()
            },
            "settlements": {k: {"count": v["count"], "total": money_str(v["total"])} for k, v in settlements.items()},
            "shipped": {"delivery_notes": len(notes), "items": dict(sorted(shipped.items()))},
        }

    def api_upsert_b2b_customer(self, payload):
        ref = payload["examleaf_ref"]
        if payload["customer_group"] not in ("School", "Distributor", "Bookseller"):
            raise bad("customer_group", "One of: School, Distributor, Bookseller.")
        existing = self.by_ref(ref)
        name = existing["name"] if existing else payload["customer_name"]
        fields = {k: v for k, v in payload.items() if k not in SIGNED}
        self.store("Customer", name, ref, fields)
        return {"name": name, "created": not existing}


FAKE = FakeErpNext()  # ERP_MODE=fake's, one per process
