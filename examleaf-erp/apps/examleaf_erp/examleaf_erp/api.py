"""The platform's API into ERPNext (API.md): POST /api/method/examleaf_erp.api.<method>, JSON body, token auth of the
EL Sync user. Each method validates its input strictly, is idempotent by examleaf_ref and by idempotency_key, logs one
ExamLeaf Sync Log row, and answers {ok, name, duplicate, examleaf_ref, ...} or {ok: false, error: {code, message,
field}} with an HTTP status (sync.endpoint)."""

import re
from collections import defaultdict
from decimal import Decimal

import frappe
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime

from examleaf_erp import constants as C
from examleaf_erp import gst
from examleaf_erp.sync import (
    DATETIME,
    ApiError,
    Fields,
    bad,
    company,
    endpoint,
    iso,
    money_str,
    ref_and_key,
    to_decimal,
)

ITEM_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,139}$")
HSN = re.compile(r"^\d{4}(\d{2}){0,2}$")  # 4, 6 or 8 digits
PIN = re.compile(r"^[1-9]\d{5}$")
ORDER_NUMBER = re.compile(r"^[A-Z]{2}-\d{4}-\d{6,9}$")  # shop.Order.number: EL-2026-000123
GSTIN = re.compile(r"^\d{2}[A-Z0-9]{13}$")
NUMBER = re.compile(r"^(?P<prefix>[A-Z]{1,2})/(?P<fy>\d{4}-\d{2})/\d{5}$")
INVOICE_PREFIXES, NOTE_PREFIXES = ("EL",), ("CN",)
TEST_INVOICE_PREFIXES, TEST_NOTE_PREFIXES = ("T",), ("TC",)
# the platform's payment method: ERPNext's Mode of Payment
MODES = {"razorpay": "Razorpay", "cod": "COD", "upi": "UPI", "neft": "NEFT/RTGS", "cheque": "Cheque"}
CHANGE_DOCTYPES = (
    "Item",
    "Item Price",
    "Customer",
    "Quotation",
    "Sales Order",
    "Sales Invoice",
    "Delivery Note",
    "Payment Entry",
    "Purchase Receipt",
    "Stock Reconciliation",
    "Stock Ledger Entry",
    "Bin",
    "Batch",
    "Distributor Agreement",
    "School Adoption",
)


def whitelisted(mutating):
    """POST only (research 1.1: v16 refuses state changes over GET anyway), then the shared endpoint plumbing."""

    def wrap(fn):
        return frappe.whitelist(methods=["POST"])(endpoint(mutating)(fn))

    return wrap


# ------------------------------------------------------------------------------------------------------------ ping
@whitelisted(mutating=False)
def ping(data):
    Fields(data).done()
    versions = {app: frappe.get_attr(f"{app}.__version__") for app in frappe.get_installed_apps()}
    return {
        "name": frappe.local.site,
        "user": frappe.session.user,
        "time": str(now_datetime()),
        "versions": versions,
    }, None


# ------------------------------------------------------------------------------------------------------- catalogue
@whitelisted(mutating=True)
def upsert_item(data):
    """A shop.Product as an Item: created the first time its examleaf_ref is seen, updated after. The item_code is set
    once (it is the Item's name); kind decides stock (printed books, one Batch per print run) or not (bundles, courses)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    item_code = f.str("item_code", pattern=ITEM_CODE)
    item_name = f.str("item_name")
    kind = f.str("kind", choices=tuple(C.ITEM_GROUP_BY_KIND))
    hsn = f.str("hsn_code", max_length=8, pattern=HSN)
    rate = f.rate("gst_rate")
    effective_from = f.date("gst_rate_effective_from", required=False, not_after_today=False)
    mrp = f.money("mrp")
    description = f.str("description", required=False, max_length=2000)
    isbn = f.str("isbn", required=False, max_length=17)
    weight = f.int("weight_grams", required=False, minimum=0, maximum=100_000)
    extra = {
        "examleaf_subject": f.str("subject", required=False),
        "examleaf_class": f.str("class_level", required=False, max_length=20),
        "examleaf_board": f.str("board", required=False, max_length=40),
        "examleaf_edition": f.str("edition", required=False, max_length=40),
    }
    is_active = f.bool("is_active", default=True)
    f.done()

    if isbn:
        isbn = normalise_isbn(isbn)
    if not frappe.db.exists("GST HSN Code", hsn):
        raise bad("hsn_code", f"{hsn} is not in India Compliance's HSN/SAC master.")
    if kind == "digital" and hsn.startswith("49"):
        raise bad("hsn_code", "Chapter 49 is printed matter: a course takes its SAC code (99…).")
    template = tax_template(rate, "gst_rate")
    is_stock = kind in C.STOCK_KINDS

    existing = frappe.db.get_value("Item", {"examleaf_ref": ref}, ["name", "is_stock_item"], as_dict=True)
    if existing and existing.name != item_code:
        raise ApiError("conflict", f"{ref} is the Item {existing.name}: an item_code never changes.", 409, "item_code")
    if not existing and frappe.db.exists("Item", item_code):
        raise ApiError("conflict", f"Item {item_code} exists without this examleaf_ref.", 409, "item_code")
    if existing and cint(existing.is_stock_item) != is_stock:
        raise ApiError("conflict", "This kind would change whether the Item holds stock.", 409, "kind")

    doc = frappe.get_doc("Item", item_code) if existing else frappe.new_doc("Item")
    if not existing:
        doc.update(
            {
                "item_code": item_code,
                "examleaf_ref": ref,
                "stock_uom": "Nos",
                "is_stock_item": is_stock,
                "has_batch_no": is_stock,
                "is_purchase_item": is_stock,
                "is_sales_item": 1,
                "include_item_in_manufacturing": 0,
            }
        )
    doc.update(
        {
            "item_name": item_name,
            "item_group": C.ITEM_GROUP_BY_KIND[kind],
            "description": description or item_name,
            "gst_hsn_code": hsn,
            "disabled": not is_active,
            "examleaf_kind": kind,
            "isbn": isbn,
            "weight_per_unit": weight or 0,
            "weight_uom": "Gram" if weight else None,
            **extra,
        }
    )
    set_item_tax(doc, template, effective_from)
    doc.save() if existing else doc.insert()
    set_price(item_code, "MRP", mrp)
    return {"name": doc.name, "created": not existing}, "Item"


@whitelisted(mutating=True)
def upsert_bundle(data):
    """A shop bundle (BundleItem rows) as a Product Bundle on its non-stock Item, made first with upsert_item. The
    bundle's examleaf_ref (bundle:<id>) may differ from its Item's (item:<id>): a Product Bundle has no examleaf_ref,
    and setting the same rows again changes nothing, so the Item is found by item_code."""
    f = Fields(data)
    _ref, _key = ref_and_key(f)
    item_code = f.str("item_code", pattern=ITEM_CODE)
    rows = f.list("items", max_items=50)
    components = []
    for row in rows:
        components.append((row.str("item_code", pattern=ITEM_CODE), row.int("qty", minimum=1, maximum=999)))
        row.done()
    is_active = f.bool("is_active", default=True)
    f.done()

    item = frappe.db.get_value(
        "Item", item_code, ["name", "examleaf_ref", "examleaf_kind", "is_stock_item"], as_dict=True
    )
    if not item or not item.examleaf_ref:
        raise ApiError("not_found", f"No platform Item {item_code}: upsert_item first.", 404, "item_code")
    if item.examleaf_kind != "bundle" or item.is_stock_item:
        raise ApiError("conflict", f"Item {item_code} is not a bundle (kind {item.examleaf_kind}).", 409, "item_code")
    seen = set()
    for index, (code, _qty) in enumerate(components):
        if code in seen:
            raise bad(f"items[{index}].item_code", "Listed twice.")
        seen.add(code)
        if not frappe.db.exists("Item", code):
            raise ApiError("not_found", f"No Item {code}.", 404, f"items[{index}].item_code")
        if code == item_code or frappe.db.exists("Product Bundle", code):
            raise bad(f"items[{index}].item_code", "A bundle cannot hold a bundle.")

    exists = frappe.db.exists("Product Bundle", item_code)
    bundle = frappe.get_doc("Product Bundle", item_code) if exists else frappe.new_doc("Product Bundle")
    bundle.new_item_code = item_code
    bundle.disabled = not is_active
    bundle.set("items", [{"item_code": code, "qty": qty} for code, qty in components])
    bundle.save() if exists else bundle.insert()
    return {"name": bundle.name, "created": not exists}, "Product Bundle"


# -------------------------------------------------------------------------------------------------------- invoices
@whitelisted(mutating=True)
def create_sales_invoice(data):
    """A platform invoice (shop.Invoice) as a submitted Sales Invoice named with its legal number. B2C: one customer,
    and a shipping Address of city, state and PIN only, which is all the place of supply needs (research 5.8)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    number = invoice_number(f, "invoice_number", test=False)
    posting_date = f.date("posting_date")
    check_financial_year(number, posting_date, "invoice_number")
    order_number = f.str("order_number", pattern=ORDER_NUMBER)
    channel = f.str("channel", required=False, choices=C.CHANNELS, default="web")
    doc_kind = f.str("doc_kind", required=False, choices=C.DOC_KINDS)
    address = read_address(f.obj("shipping_address"))
    lines = []
    for row in f.list("items"):
        lines.append(
            {
                "item_code": row.str("item_code", pattern=ITEM_CODE),
                "qty": row.int("qty", minimum=1, maximum=9999),
                "rate": row.money("rate"),
                "discount": row.money("discount", required=False, default=Decimal("0.00")),
                "hsn_code": row.str("hsn_code", required=False, max_length=8, pattern=HSN),
                "gst_rate": row.rate("gst_rate"),
                "field": row.path,
            }
        )
        row.done()
    shipping_fee = f.money("shipping_fee", required=False, default=Decimal("0.00"))
    shipping_hsn = f.str("shipping_hsn_code", required=False, max_length=8, pattern=HSN)
    shipping_rate = f.rate("shipping_gst_rate", required=False)
    total = f.money("total")
    f.done()

    same_order = {"examleaf_order_no": ("order_number", order_number)}
    if duplicate := find_existing("Sales Invoice", ref, number, same=same_order):
        return duplicate, "Sales Invoice"

    items = []
    for line in lines:
        item = frappe.db.get_value("Item", line["item_code"], ["name", "gst_hsn_code", "disabled"], as_dict=True)
        if not item:
            raise ApiError(
                "not_found", f"No Item {line['item_code']}: upsert_item first.", 404, f"{line['field']}.item_code"
            )
        if line["discount"] > line["rate"] * line["qty"]:
            raise bad(f"{line['field']}.discount", "The discount is more than the line.")
        line["hsn_code"] = line["hsn_code"] or item.gst_hsn_code
        line["template"] = tax_template(line["gst_rate"], f"{line['field']}.gst_rate")
        line["amount"] = line["rate"] * line["qty"] - line["discount"]
        items += exact_rows(line)
    if shipping_fee:
        hsn, rate = shipping_supply(lines, shipping_hsn, shipping_rate)
        items.append(
            {
                "item_code": C.SHIPPING_ITEM,
                "qty": 1,
                "price_list_rate": float(shipping_fee),
                "rate": float(shipping_fee),
                "gst_hsn_code": hsn,
                "item_tax_template": tax_template(rate, "shipping_gst_rate"),
            }
        )
    expected = sum((line["amount"] for line in lines), Decimal("0.00")) + shipping_fee
    if expected != total:
        raise bad("total", f"The lines and shipping add up to {expected:.2f}, not {total:.2f}.")

    the_company = company()
    address_name = b2c_address(address)
    si = frappe.new_doc("Sales Invoice")
    si.update(
        {
            "customer": C.B2C_CUSTOMER,
            "company": the_company,
            "posting_date": str(posting_date),  # strings: whitelisted ERPNext helpers type-check dates
            "set_posting_time": 1,
            "due_date": str(posting_date),
            "currency": "INR",
            "selling_price_list": "MRP",
            "ignore_pricing_rule": 1,
            "disable_rounded_total": 1,
            "update_stock": 0,
            "customer_address": address_name,
            "shipping_address_name": address_name,
            "territory": territory_for(address),
            "examleaf_ref": ref,
            "examleaf_order_no": order_number,
            "examleaf_channel": channel,
            "remarks": f"Platform order {order_number}",
        }
    )
    for row in items:
        si.append("items", row)
    set_inclusive_taxes(si, address["state"])
    si.insert(set_name=number)

    for row, wanted in zip(si.items, items, strict=True):
        if row.item_tax_template != wanted["item_tax_template"]:
            raise ApiError(
                "tax_template_mismatch",
                f"Row {row.idx} ({row.item_code}): ERPNext's dated GST rate for this item on {posting_date} gives"
                f" {row.item_tax_template}, the order says {wanted['item_tax_template']}: sync the item (upsert_item"
                " with gst_rate_effective_from) first.",
                422,
                "items",
            )
    if to_decimal(si.grand_total) != total:
        raise ApiError(
            "total_mismatch", f"ERPNext computes {si.grand_total:.2f}, the order says {total:.2f}.", 422, "total"
        )
    if doc_kind and si.examleaf_doc_kind != doc_kind:
        raise ApiError(
            "doc_kind_mismatch",
            f"The lines make this a {si.examleaf_doc_kind}, not a {doc_kind} (Rules 46, 46A, 49).",
            422,
            "doc_kind",
        )
    si.submit()
    return invoice_answer(si), "Sales Invoice"


@whitelisted(mutating=True)
def create_credit_note(data):
    """A platform credit note (shop.CreditNote, for a Refund) as a return Sales Invoice against the original, named with
    its CN number. Credits are tax-inclusive amounts per item, as the platform shares a refund out; qty is the copies
    returned, if any (ERPNext counts units, so a value-only credit uses the fewest units it can: API.md)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    number = invoice_number(f, "credit_note_number", test=False, credit=True)
    original_number = invoice_number(f, "invoice_number", test=False)
    posting_date = f.date("posting_date")
    check_financial_year(number, posting_date, "credit_note_number")
    reason = f.str("reason")
    credits = []
    for row in f.list("items", required=False, min_items=0):
        credits.append(
            {
                "item_code": row.str("item_code", pattern=ITEM_CODE),
                "amount": row.money("amount", allow_zero=False),
                "qty": row.int("qty", required=False, minimum=1, maximum=9999),
                "field": row.path,
            }
        )
        row.done()
    shipping_credit = f.money("shipping_credit", required=False, default=Decimal("0.00"))
    total = f.money("total", allow_zero=False)
    f.done()

    same_invoice = {"return_against": ("invoice_number", original_number)}
    if duplicate := find_existing("Sales Invoice", ref, number, same=same_invoice):
        return duplicate, "Sales Invoice"
    expected = sum((c["amount"] for c in credits), Decimal("0.00")) + shipping_credit
    if expected != total:
        raise bad("total", f"The credits add up to {expected:.2f}, not {total:.2f}.")
    original = frappe.db.get_value(
        "Sales Invoice",
        original_number,
        ["name", "docstatus", "is_return", "examleaf_ref", "posting_date"],
        as_dict=True,
    )
    if not original or original.docstatus != 1 or original.is_return or not original.examleaf_ref:
        raise ApiError("not_found", f"No submitted platform invoice {original_number}.", 404, "invoice_number")
    if posting_date < getdate(original.posting_date):
        raise bad("posting_date", "A credit note cannot be dated before its invoice.")

    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

    note = make_sales_return(original.name)
    source_rows = defaultdict(list)
    for row in frappe.get_doc("Sales Invoice", original.name).items:
        source_rows[row.item_code].append(row)
    returned = returned_quantities(original.name)
    rows = []
    for credit in credits:
        if credit["item_code"] not in source_rows or credit["item_code"] == C.SHIPPING_ITEM:
            raise bad(f"{credit['field']}.item_code", f"{credit['item_code']} is not a line of {original_number}.")
        rows += credit_rows(source_rows[credit["item_code"]], credit, returned)
    if shipping_credit:
        if C.SHIPPING_ITEM not in source_rows:
            raise bad("shipping_credit", f"{original_number} charged no shipping.")
        rows += credit_rows(
            source_rows[C.SHIPPING_ITEM], {"amount": shipping_credit, "qty": 1, "field": "shipping_credit"}, returned
        )
    if not rows:
        raise bad("items", "Credit at least one line or the shipping.")
    by_source = {row.sales_invoice_item: row.as_dict(no_default_fields=True) for row in note.items}
    note.set("items", [])
    for source, qty, rate in rows:
        line = {**by_source[source.name], "qty": -qty, "rate": float(rate), "price_list_rate": source.price_list_rate}
        line.pop("stock_qty", None)
        note.append("items", line)
    note.update(
        {
            "posting_date": str(posting_date),  # strings: whitelisted ERPNext helpers type-check dates
            "set_posting_time": 1,
            "due_date": str(posting_date),
            "examleaf_ref": ref,
            "remarks": reason,
            "select_print_heading": None,  # the credit note format prints its own title
        }
    )
    note.insert(set_name=number)
    if to_decimal(-note.grand_total) != total:
        raise ApiError(
            "total_mismatch", f"ERPNext credits {-note.grand_total:.2f}, the note says {total:.2f}.", 422, "total"
        )
    note.submit()
    return {**invoice_answer(note), "return_against": original.name, "total_credit": money_str(-note.grand_total)}, (
        "Sales Invoice"
    )


# -------------------------------------------------------------------------------------------------------- payments
@whitelisted(mutating=True)
def create_payment_entry(data):
    """A payment (Razorpay, COD, UPI, bank, cheque) against a platform invoice, or a refund against its credit note: a
    submitted Payment Entry into the mode's account (Razorpay Clearing, COD in Transit, the bank)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    against = f.str("invoice_number", max_length=16, pattern=NUMBER)
    amount = f.money("amount", allow_zero=False)
    posting_date = f.date("posting_date")
    mode = MODES[f.str("mode", choices=tuple(MODES))]
    reference_no = f.str("reference_no")
    reference_date = f.date("reference_date", required=False) or posting_date
    f.done()

    if duplicate := find_existing("Payment Entry", ref):
        return duplicate, "Payment Entry"
    invoice = frappe.db.get_value(
        "Sales Invoice", against, ["name", "docstatus", "outstanding_amount", "examleaf_ref", "is_return"], as_dict=True
    )
    if not invoice or invoice.docstatus != 1 or not invoice.examleaf_ref:
        raise ApiError("not_found", f"No submitted platform invoice or credit note {against}.", 404, "invoice_number")
    outstanding = abs(to_decimal(invoice.outstanding_amount))
    if amount > outstanding:
        raise ApiError(
            "overpayment", f"{against} has {outstanding:.2f} outstanding, less than {amount:.2f}.", 422, "amount"
        )

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    # a credit note's outstanding is negative: the refund is allocated as a negative amount (payment_type Pay)
    signed = -amount if invoice.is_return else amount
    pe = get_payment_entry(
        "Sales Invoice",
        invoice.name,
        party_amount=float(signed),
        bank_account=mode_account(mode),
        reference_date=str(reference_date),
    )
    pe.update(
        {
            "mode_of_payment": mode,
            "posting_date": str(posting_date),  # strings: whitelisted ERPNext helpers type-check dates
            "reference_no": reference_no,
            "reference_date": str(reference_date),
            "examleaf_ref": ref,
        }
    )
    pe.insert()
    pe.submit()
    left = frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")
    return {
        "name": pe.name,
        "payment_type": pe.payment_type,
        "against": invoice.name,
        "outstanding_after": money_str(abs(flt(left))),
    }, "Payment Entry"


@whitelisted(mutating=True)
def record_settlement(data):
    """A Razorpay settlement or a courier's COD remittance as a Journal Entry: the clearing account is emptied into the
    bank, the fee and the GST on it are booked (research 4.3)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    kind = f.str("kind", choices=("razorpay", "cod"))
    settlement_id = f.str("settlement_id")
    posting_date = f.date("posting_date")
    gross = f.money("gross_amount", allow_zero=False)
    fee = f.money("fee", required=False, default=Decimal("0.00"))
    tax = f.money("tax_on_fee", required=False, default=Decimal("0.00"))
    net = f.money("net_amount", allow_zero=False)
    tax_type = f.str("tax_type", required=False, choices=("igst", "cgst_sgst"), default="igst")
    utr = f.str("utr", required=False, max_length=40)  # the bank's reference, which bank reconciliation matches
    f.done()

    if gross != net + fee + tax:
        raise bad("gross_amount", f"gross_amount must be net_amount + fee + tax_on_fee ({net + fee + tax:.2f}).")
    if duplicate := find_existing("Journal Entry", ref):
        return duplicate, "Journal Entry"

    the_company = company()
    abbr = frappe.get_cached_value("Company", the_company, "abbr")
    bank = frappe.get_cached_value("Company", the_company, "default_bank_account")
    if not bank:
        raise ApiError("not_configured", "The company has no default bank account: run the bootstrap.", 500)
    clearing = mode_account(MODES[kind])
    fee_account = f"{'Payment Gateway Charges' if kind == 'razorpay' else 'Freight and Forwarding Charges'} - {abbr}"
    cost_center = frappe.get_cached_value("Company", the_company, "cost_center")
    rows = [
        {"account": bank, "debit_in_account_currency": float(net)},
        {"account": clearing, "credit_in_account_currency": float(gross)},
    ]
    if fee:
        rows.append({"account": fee_account, "debit_in_account_currency": float(fee), "cost_center": cost_center})
    if tax:
        if tax_type == "igst":
            rows.append({"account": f"Input Tax IGST - {abbr}", "debit_in_account_currency": float(tax)})
        else:
            half = (tax / 2).quantize(Decimal("0.01"))
            rows.append({"account": f"Input Tax CGST - {abbr}", "debit_in_account_currency": float(half)})
            rows.append({"account": f"Input Tax SGST - {abbr}", "debit_in_account_currency": float(tax - half)})
    je = frappe.new_doc("Journal Entry")
    je.update(
        {
            "voucher_type": "Bank Entry",
            "company": the_company,
            "posting_date": str(posting_date),  # strings: whitelisted ERPNext helpers type-check dates
            "cheque_no": utr or settlement_id,
            "cheque_date": str(posting_date),
            "user_remark": f"{'Razorpay settlement' if kind == 'razorpay' else 'COD remittance'} {settlement_id}",
            "examleaf_ref": ref,
        }
    )
    for row in rows:
        je.append("accounts", row)
    je.insert()
    je.submit()
    return {"name": je.name}, "Journal Entry"


# --------------------------------------------------------------------------------------------------------- dispatch
@whitelisted(mutating=True)
def create_delivery_note(data):
    """A parcel leaving (shop.Shipment) as a submitted Delivery Note against the invoice: stock goes out of the
    warehouse, each book from its oldest print run first (Batch print date, FIFO)."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    against = invoice_number(f, "invoice_number", test=False)
    posting_date = f.date("posting_date")
    warehouse = f.str("warehouse", required=False, default="Main")
    wanted = {}
    for row in f.list("items", required=False, min_items=0):
        code = row.str("item_code", pattern=ITEM_CODE)
        wanted[code] = wanted.get(code, 0) + row.int("qty", minimum=1, maximum=9999)
        row.done()
    courier = f.str("courier", required=False, max_length=80)
    tracking = f.str("tracking_number", required=False, max_length=80)
    f.done()

    if duplicate := find_existing("Delivery Note", ref):
        return duplicate, "Delivery Note"
    invoice = frappe.db.get_value(
        "Sales Invoice", against, ["name", "docstatus", "is_return", "examleaf_ref"], as_dict=True
    )
    if not invoice or invoice.docstatus != 1 or invoice.is_return or not invoice.examleaf_ref:
        raise ApiError("not_found", f"No submitted platform invoice {against}.", 404, "invoice_number")
    the_company = company()
    warehouse = warehouse_name(warehouse, the_company)

    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_delivery_note

    dn = make_delivery_note(invoice.name)
    keep = []
    for row in dn.items:
        is_stock, bundle = (
            frappe.db.get_value("Item", row.item_code, "is_stock_item"),
            frappe.db.exists("Product Bundle", {"new_item_code": row.item_code, "disabled": 0}),
        )
        if not (is_stock or bundle):
            continue  # courses and the shipping line: nothing leaves the warehouse
        if wanted:
            take = min(row.qty, wanted.get(row.item_code, 0))
            if not take:
                continue
            wanted[row.item_code] -= take
            row.qty = take
        row.warehouse = warehouse
        keep.append(row)
    if wanted and any(wanted.values()):
        code = next(code for code, qty in wanted.items() if qty)
        raise bad("items", f"{against} has no {wanted[code]} more of {code} to deliver.")
    if not keep:
        raise ApiError("nothing_to_deliver", f"{against} has no goods left to deliver.", 422, "invoice_number")
    dn.set("items", keep)
    dn.update(
        {
            "posting_date": str(posting_date),  # strings: whitelisted ERPNext helpers type-check dates
            "set_posting_time": 1,
            "set_warehouse": warehouse,
            "transporter_name": courier,
            "lr_no": tracking,
            "lr_date": str(posting_date) if tracking else None,
            "examleaf_ref": ref,
        }
    )
    dn.insert()
    picked = []
    for row in [*dn.items, *dn.packed_items]:
        if not frappe.db.get_value("Item", row.item_code, "has_batch_no"):
            continue
        allocation = fifo_batches(row.item_code, row.warehouse or warehouse, row.get("stock_qty") or row.qty, dn)
        row.serial_and_batch_bundle = batch_bundle(dn, row, allocation)
        row.use_serial_batch_fields = 0
        picked += [{"item_code": row.item_code, "batch_no": batch, "qty": qty} for batch, qty in allocation.items()]
    dn.save()
    dn.submit()
    return {"name": dn.name, "against": invoice.name, "warehouse": warehouse, "batches": picked}, "Delivery Note"


# -------------------------------------------------------------------------------------------------------- read side
@whitelisted(mutating=False)
def get_stock(data):
    """Stock on hand (Bin): actual and projected quantity per item and warehouse, and by batch (print run)."""
    f = Fields(data)
    item_code = f.str("item_code", required=False, pattern=ITEM_CODE)
    warehouse = f.str("warehouse", required=False)
    by_batch = f.bool("by_batch", default=True)
    f.done()
    the_company = company()
    filters = {"warehouse": ["in", frappe.get_all("Warehouse", {"company": the_company, "is_group": 0}, pluck="name")]}
    if warehouse:
        filters["warehouse"] = warehouse_name(warehouse, the_company)
    if item_code:
        if not frappe.db.exists("Item", item_code):
            raise ApiError("not_found", f"No Item {item_code}.", 404, "item_code")
        filters["item_code"] = item_code
    bins = frappe.get_all(
        "Bin",
        filters=filters,
        fields=["item_code", "warehouse", "actual_qty", "projected_qty", "reserved_qty", "ordered_qty"],
        order_by="item_code asc, warehouse asc",
    )
    out = []
    for b in bins:
        entry = {
            "item_code": b.item_code,
            "warehouse": b.warehouse,
            "actual_qty": flt(b.actual_qty),
            "projected_qty": flt(b.projected_qty),
            "reserved_qty": flt(b.reserved_qty),
        }
        if by_batch and frappe.get_cached_value("Item", b.item_code, "has_batch_no"):
            entry["batches"] = batches_in(b.item_code, b.warehouse)
        out.append(entry)
    return {"name": None, "items": out}, None


@whitelisted(mutating=False)
def get_changes_since(data):
    """Names of documents changed after a cursor, oldest first, for the platform's pull (research 5.8): the cursor is
    (modified, name), so documents saved in the same microsecond are neither skipped nor repeated."""
    f = Fields(data)
    doctype = f.str("doctype", choices=CHANGE_DOCTYPES)
    since = f.str("modified_after", max_length=26, pattern=DATETIME)
    after_name = f.str("after_name", required=False)
    limit = f.int("limit", required=False, minimum=1, maximum=500, default=100)
    f.done()
    try:
        since_dt = get_datetime(since)
    except Exception:
        raise bad("modified_after", "Not a date and time (YYYY-MM-DD HH:MM:SS.ffffff).")
    table = frappe.qb.DocType(doctype)
    has_ref = frappe.get_meta(doctype).has_field("examleaf_ref")
    fields = [table.name, table.modified, table.docstatus]
    if has_ref:
        fields.append(table.examleaf_ref)
    condition = table.modified > since_dt
    if after_name:
        condition = condition | ((table.modified == since_dt) & (table.name > after_name))
    rows = (
        frappe.qb.from_(table)
        .select(*fields)
        .where(condition)
        .orderby(table.modified)
        .orderby(table.name)
        .limit(limit + 1)
        .run(as_dict=True)
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        {"name": r.name, "modified": iso(r.modified), "docstatus": r.docstatus, "examleaf_ref": r.get("examleaf_ref")}
        for r in rows
    ]
    # the arguments of the next call (the same cursor again when nothing changed)
    cursor = {"modified_after": items[-1]["modified"], "after_name": items[-1]["name"]} if items else None
    return {
        "name": None,
        "rows": items,
        "has_more": has_more,
        "next": cursor or {"modified_after": since, "after_name": after_name},
    }, None


@whitelisted(mutating=False)
def daily_totals(data):
    """What ERPNext holds of the platform's documents for one day, for the nightly reconciliation (research 5.8)."""
    f = Fields(data)
    day = f.date("date", not_after_today=False)
    f.done()
    return {"name": None, **totals_for(day)}, None


# ----------------------------------------------------------------------------------------------------------- B2B
@whitelisted(mutating=True)
def upsert_b2b_customer(data):
    """Schools, distributors and booksellers are made in ERPNext (credit, price lists, terms): this is for the first
    load from the platform's QuoteRequest and partner records only."""
    f = Fields(data)
    ref, _key = ref_and_key(f)
    name = f.str("customer_name")
    group = f.str("customer_group", choices=("School", "Distributor", "Bookseller"))
    gstin = f.str("gstin", required=False, max_length=15, pattern=GSTIN)
    udise = f.str("udise_code", required=False, max_length=11, pattern=re.compile(r"^\d{11}$"))
    board = f.str("school_board", required=False, max_length=40)
    medium = f.str("school_medium", required=False, max_length=40)
    district = f.str("district", required=False, max_length=80)
    address = f.obj("address", required=False)
    contact = f.obj("contact", required=False)
    address_fields = read_address(address, street=True) if address else None
    contact_fields = None
    if contact:
        contact_fields = {
            "name": contact.str("name", max_length=120),
            "email": contact.str(
                "email", required=False, max_length=140, pattern=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
            ),
            "phone": contact.str("phone", required=False, max_length=20, pattern=re.compile(r"^\+?[0-9 ]{7,20}$")),
        }
        contact.done()
    f.done()
    if group != "School" and (udise or board or medium):
        raise bad("udise_code", "UDISE+ code, board and medium are for schools.")

    existing = frappe.db.get_value("Customer", {"examleaf_ref": ref}, "name")
    doc = frappe.get_doc("Customer", existing) if existing else frappe.new_doc("Customer")
    doc.update(
        {
            "customer_name": name,
            "customer_type": "Company",
            "customer_group": group,
            "territory": district_territory(district, address_fields),
            "gstin": gstin,
            "udise_code": udise,
            "school_board": board,
            "school_medium": medium,
            "district": district,
        }
    )
    if not existing:
        doc.examleaf_ref = ref
    doc.save() if existing else doc.insert()
    if address_fields:
        upsert_party_address(doc, ref, address_fields, gstin)
    if contact_fields:
        upsert_party_contact(doc, contact_fields)
    return {"name": doc.name, "created": not existing}, "Customer"


# ======================================================================================================== helpers
def normalise_isbn(value):
    digits = value.replace("-", "").replace(" ", "").upper()
    if re.fullmatch(r"\d{13}", digits):
        if sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10 == 0:
            return digits
    elif re.fullmatch(r"\d{9}[\dX]", digits):
        if sum((10 - i) * (10 if d == "X" else int(d)) for i, d in enumerate(digits)) % 11 == 0:
            return digits
    raise bad("isbn", "Not a valid ISBN-10 or ISBN-13.")


def tax_template(rate: Decimal, field: str) -> str:
    """0 % is the exempt template (printed books, HSN 4901); a taxed rate is India Compliance's GST n% template."""
    abbr = frappe.get_cached_value("Company", company(), "abbr")
    label = f"{rate.normalize():f}" if rate else None
    name = f"GST Exempted - {abbr}" if not rate else f"GST {label}% - {abbr}"
    row = frappe.db.get_value("Item Tax Template", name, ["disabled", "gst_treatment", "gst_rate"], as_dict=True)
    if not row or row.disabled or (rate and (row.gst_treatment != "Taxable" or flt(row.gst_rate) != flt(rate))):
        raise ApiError("no_tax_template", f"ERPNext has no usable Item Tax Template {name} for {rate}%.", 422, field)
    return name


def set_item_tax(doc, template, effective_from):
    """Keep the Item's dated GST rate: a change of rate adds a row from its effective date (research 5.15), so an
    invoice dated before the change still takes the old rate."""
    today = getdate()
    current = None
    for row in sorted(doc.taxes, key=lambda r: getdate(r.valid_from) if r.valid_from else getdate("1900-01-01")):
        if not row.tax_category and (not row.valid_from or getdate(row.valid_from) <= today):
            current = row
    if not doc.taxes:
        doc.append(
            "taxes", {"item_tax_template": template, "valid_from": str(effective_from) if effective_from else None}
        )
    elif not current or current.item_tax_template != template:
        when = effective_from or today
        same_day = next((r for r in doc.taxes if r.valid_from and getdate(r.valid_from) == when), None)
        if same_day:
            same_day.item_tax_template = template
        else:
            doc.append("taxes", {"item_tax_template": template, "valid_from": str(when)})


def set_price(item_code, price_list, rate):
    name = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": price_list,
            "customer": ("is", "not set"),
            "batch_no": ("is", "not set"),
        },
        "name",
    )
    price = frappe.get_doc("Item Price", name) if name else frappe.new_doc("Item Price")
    price.update({"item_code": item_code, "price_list": price_list, "price_list_rate": float(rate)})
    price.save() if name else price.insert()


def invoice_number(f, field, test=False, credit=False):
    value = f.str(field, max_length=16, pattern=NUMBER)
    prefix = NUMBER.match(value).group("prefix")
    allowed = NOTE_PREFIXES if credit else INVOICE_PREFIXES
    if frappe.conf.get("examleaf_allow_test_series"):
        allowed = allowed + (TEST_NOTE_PREFIXES if credit else TEST_INVOICE_PREFIXES)
    if prefix not in allowed:
        raise bad(field, f"The {'credit note' if credit else 'invoice'} series here is {', '.join(allowed)}.")
    from india_compliance.gst_india.utils import validate_invoice_number

    if not validate_invoice_number(frappe._dict(name=value, doctype="Sales Invoice"), throw=False):
        raise bad(field, "Not a valid GST document number (Rule 46(b): 16 characters, letters, digits, - and /).")
    return value


def financial_year(day) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def check_financial_year(number, day, field):
    if NUMBER.match(number).group("fy") != financial_year(day):
        raise bad(field, f"{number} is not a number of the financial year of {day} ({financial_year(day)}).")


def find_existing(doctype, ref, name=None, same=None):
    """The idempotency by examleaf_ref (and, for invoices, by their legal number): an answer for the document already
    made from this reference, a 409 when the reference or the number belongs to something else. `same`: {column: (the
    request's field, its value)} the document of this reference must hold, so that a number issued again for another
    order (a restored database, a second platform) is refused rather than answered as its duplicate."""
    same = same or {}
    by_ref = frappe.db.get_value(doctype, {"examleaf_ref": ref}, ["name", "docstatus", *same], as_dict=True)
    if by_ref:
        if name and by_ref.name != name:
            raise ApiError("conflict", f"{ref} is already {doctype} {by_ref.name}.", 409, "examleaf_ref")
        for column, (field, value) in same.items():
            if by_ref.get(column) != value:
                there = by_ref.get(column) or "nothing"
                raise ApiError("conflict", f"{doctype} {by_ref.name} is {there}'s, not {value}'s.", 409, field)
        if by_ref.docstatus == 2:
            raise ApiError(
                "cancelled", f"{doctype} {by_ref.name} of {ref} was cancelled in ERPNext.", 409, "examleaf_ref"
            )
        return {"name": by_ref.name, "duplicate": True, "docstatus": by_ref.docstatus}
    if name and (other := frappe.db.get_value(doctype, name, ["docstatus", "examleaf_ref"], as_dict=True)):
        if other.docstatus == 2:
            raise ApiError(
                "amendment_refused",
                f"{name} was cancelled; its number is not issued again and it is never amended: credit it instead.",
                409,
                "invoice_number",
            )
        raise ApiError("conflict", f"{doctype} {name} exists with another reference.", 409, "invoice_number")
    return None


def read_address(fields, street=False):
    out = {}
    if street:
        out["line1"] = fields.str("line1", max_length=200)
        out["line2"] = fields.str("line2", required=False, max_length=200)
    out["city"] = fields.str("city", max_length=80)
    out["district"] = fields.str("district", required=False, max_length=80)
    out["state"] = fields.str("state", max_length=2, choices=tuple(C.STATE_NAMES))
    out["pin"] = fields.str("pin", max_length=6, pattern=PIN)
    fields.done()
    return out


def b2c_address(address):
    """One shipping Address per PIN and city, shared by every order to it: no name, phone or street. The invoice keeps
    its own copy of the text and its place of supply, so sharing the record changes nothing printed."""
    city = address["city"]
    ref = f"b2c-address:{address['pin']}:{re.sub(r'[^a-z0-9]+', '-', city.lower()).strip('-')}"
    if name := frappe.db.get_value("Address", {"examleaf_ref": ref}, "name"):
        return name
    doc = frappe.new_doc("Address")
    doc.update(
        {
            "address_title": f"B2C {address['pin']} {city}"[:140],
            "address_type": "Shipping",
            "address_line1": city,
            "city": city,
            "county": address.get("district"),
            "state": C.STATE_NAMES[address["state"]],
            "country": "India",
            "pincode": address["pin"],
            "examleaf_ref": ref,
            "links": [{"link_doctype": "Customer", "link_name": C.B2C_CUSTOMER}],
        }
    )
    doc.insert()
    return doc.name


def territory_for(address):
    """Assam's district when known, else Assam; a north-eastern state; else Rest of India."""
    state = C.STATE_NAMES[address["state"]]
    district = (address.get("district") or "").strip().title()
    if state == "Assam":
        return district if district in C.ASSAM_DISTRICTS else "Assam"
    return state if state in C.NORTH_EAST_STATES else "Rest of India"


def district_territory(district, address):
    if address:
        return territory_for({**address, "district": district or address.get("district")})
    district = (district or "").strip().title()
    return district if district in C.ASSAM_DISTRICTS else "India"


def set_inclusive_taxes(si, state_code):
    """India Compliance's own template for the place of supply (In-state: CGST and SGST, Out-state: IGST), with every
    row inclusive: the platform's prices include tax, so the line rates stay as charged and ERPNext works the taxable
    value back out of them (shop/invoices.py does the same)."""
    from india_compliance.gst_india.constants import STATE_NUMBERS
    from india_compliance.gst_india.overrides.transaction import get_tax_template

    company_gstin = frappe.db.get_value("Company", si.company, "gstin") or ""
    is_inter_state = STATE_NUMBERS[C.STATE_NAMES[state_code]] != company_gstin[:2]
    template = get_tax_template("Sales Taxes and Charges Template", si.company, is_inter_state, False)
    if not template:
        raise ApiError("not_configured", "India Compliance's sales tax templates are missing: run the bootstrap.", 500)
    si.taxes_and_charges = template
    si.set("taxes", [])
    for row in frappe.get_doc("Sales Taxes and Charges Template", template).taxes:
        si.append(
            "taxes",
            {
                "charge_type": row.charge_type,
                "account_head": row.account_head,
                "description": row.description,
                "rate": row.rate,
                "cost_center": row.cost_center,
                "included_in_print_rate": 1,
            },
        )


def exact_rows(line):
    """A line's charge (rate × qty − discount) as rows whose unit rate is exact to the paisa: one row when the discount
    divides, else two (n units at r, m at r + 0.01). ERPNext keeps rates to 2 decimals, so this is the only way its
    total equals the platform's to the paisa. ponytail: a taxed line that splits may differ by 0.01 in taxable value;
    taxed lines are courses, sold one at a time, so they never split."""
    paise = int(line["amount"] * 100)
    qty = line["qty"]
    base, extra = divmod(paise, qty)
    rows = []
    for count, unit in ((qty - extra, base), (extra, base + 1)):
        if count:
            rows.append(
                {
                    "item_code": line["item_code"],
                    "qty": count,
                    "price_list_rate": float(line["rate"]),
                    "rate": float(Decimal(unit) / 100),
                    "gst_hsn_code": line["hsn_code"],
                    "item_tax_template": line["template"],
                }
            )
    return rows


def shipping_supply(lines, hsn, rate):
    """Shipping billed with goods is part of a composite supply and follows the goods it carries (CGST s.2(30)): the HSN
    and rate of the order's principal goods, unless the platform says otherwise. Goods at different rates need it said."""
    if hsn and rate is not None:
        return hsn, rate
    goods = [line for line in lines if frappe.db.get_value("Item", line["item_code"], "is_stock_item")]
    goods = goods or [line for line in lines if frappe.db.exists("Product Bundle", line["item_code"])]
    if not goods:
        raise bad("shipping_fee", "Shipping on an order with no goods: send shipping_hsn_code and shipping_gst_rate.")
    if len({line["gst_rate"] for line in goods}) > 1:
        raise bad(
            "shipping_gst_rate", "The goods are at different GST rates: send shipping_hsn_code and shipping_gst_rate."
        )
    principal = max(goods, key=lambda line: line["amount"])
    return hsn or principal["hsn_code"], principal["gst_rate"] if rate is None else rate


def invoice_answer(si):
    taxable = exempt = Decimal("0.00")
    for row in si.items:
        value = to_decimal(row.get("taxable_value") or row.net_amount)
        if gst.treatment(row) in gst.TAXABLE_TREATMENTS:
            taxable += value
        else:
            exempt += value
    return {
        "name": si.name,
        "doc_kind": si.examleaf_doc_kind,
        "print_heading": si.select_print_heading,
        "place_of_supply": si.place_of_supply,
        "grand_total": money_str(si.grand_total),
        "taxable_value": money_str(abs(taxable)),
        "exempt_value": money_str(abs(exempt)),
        "tax_total": money_str(si.total_taxes_and_charges),
    }


def returned_quantities(invoice):
    """Units already credited per invoice row (earlier credit notes), which ERPNext will not let a return exceed."""
    item = frappe.qb.DocType("Sales Invoice Item")
    invoice_table = frappe.qb.DocType("Sales Invoice")
    rows = (
        frappe.qb.from_(item)
        .join(invoice_table)
        .on(item.parent == invoice_table.name)
        .select(item.sales_invoice_item, Sum(item.qty).as_("qty"))
        .where((invoice_table.return_against == invoice) & (invoice_table.docstatus == 1))
        .groupby(item.sales_invoice_item)
        .run(as_dict=True)
    )
    return {r.sales_invoice_item: -flt(r.qty) for r in rows}


def credit_rows(sources, credit, returned):
    """Split a tax-inclusive credit over the units of an invoice line: qty units if given (copies returned), else the
    fewest units that carry it at no more than the rate charged; unit rates exact to the paisa (as exact_rows).
    Returns (source row, units, rate) triples. ponytail: ERPNext caps returns by units, so a line credited on every
    unit cannot take a further value-only credit; that credit goes on another line (API.md)."""
    paise = int(credit["amount"] * 100)
    sources = sorted(sources, key=lambda r: -flt(r.rate))
    room = [(row, int(flt(row.qty) - returned.get(row.name, 0))) for row in sources]
    room = [(row, left) for row, left in room if left > 0]
    available = sum(left for _row, left in room)
    top = round(flt(sources[0].rate) * 100) if sources else 0
    units = credit.get("qty") or (-(-paise // top) if top else 0)
    if not room or units > available or units < 1:
        raise ApiError(
            "over_credit",
            f"{credit['field']}: the line has {available} unit(s) left to credit, {units} needed.",
            422,
            credit["field"],
        )
    base, extra = divmod(paise, units)
    out = []
    for row, left in room:
        if not units:
            break
        take = min(left, units)
        charged = round(flt(row.rate) * 100)
        high = min(take, extra)
        for count, unit in ((high, base + 1), (take - high, base)):
            if not count:
                continue
            if unit > charged:
                raise ApiError(
                    "over_credit",
                    f"{credit['field']}: more than was charged per unit ({row.rate}).",
                    422,
                    credit["field"],
                )
            out.append((row, count, Decimal(unit) / 100))
        units -= take
        extra -= high
    return out


def mode_account(mode):
    account = frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": company()}, "default_account")
    if not account:
        raise ApiError(
            "not_configured", f"Mode of Payment {mode} has no account for the company: run the bootstrap.", 500
        )
    return account


def warehouse_name(name, the_company):
    abbr = frappe.get_cached_value("Company", the_company, "abbr")
    full = name if name.endswith(f" - {abbr}") else f"{name} - {abbr}"
    if frappe.db.get_value("Warehouse", full, "company") != the_company:
        raise bad("warehouse", f"No warehouse {full}.")
    return full


def batches_in(item_code, warehouse, posting_date=None, posting_time=None):
    """Batches with stock in a warehouse, oldest print run first (Batch.manufacturing_date is the print date)."""
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    rows = get_batch_qty(item_code=item_code, warehouse=warehouse, posting_date=posting_date, posting_time=posting_time)
    qty = defaultdict(float)
    for row in rows or []:
        qty[row.get("batch_no")] += flt(row.get("qty"))
    if not qty:
        return []
    meta = {
        b.name: b
        for b in frappe.get_all(
            "Batch",
            filters={"name": ["in", list(qty)]},
            fields=["name", "manufacturing_date", "creation", "examleaf_edition", "disabled", "expiry_date"],
        )
    }
    ordered = sorted(
        (name for name in qty if qty[name] > 0 and name in meta and not meta[name].disabled),
        key=lambda name: (getdate(meta[name].manufacturing_date or "9999-12-31"), meta[name].creation, name),
    )
    return [
        {
            "batch_no": name,
            "qty": qty[name],
            "print_date": str(meta[name].manufacturing_date) if meta[name].manufacturing_date else None,
            "edition": meta[name].examleaf_edition,
        }
        for name in ordered
    ]


def fifo_batches(item_code, warehouse, qty, dn):
    left = flt(qty)
    allocation = {}
    for batch in batches_in(item_code, warehouse, dn.posting_date, dn.posting_time):
        if left <= 0:
            break
        take = min(left, batch["qty"])
        allocation[batch["batch_no"]] = take
        left -= take
    if left > 0:
        raise ApiError(
            "insufficient_stock",
            f"{warehouse} has {flt(qty) - left:g} of {item_code} in its batches, {flt(qty):g} needed.",
            422,
            "items",
        )
    return allocation


def batch_bundle(dn, row, allocation):
    from erpnext.stock.serial_batch_bundle import SerialBatchCreation

    bundle = SerialBatchCreation(
        {
            "item_code": row.item_code,
            "warehouse": row.warehouse,
            "voucher_type": "Delivery Note",
            "voucher_no": dn.name,
            "voucher_detail_no": row.name,
            "posting_date": dn.posting_date,
            "posting_time": dn.posting_time,
            "qty": sum(allocation.values()),
            "type_of_transaction": "Outward",
            "company": dn.company,
            "batches": frappe._dict(allocation),
            "do_not_submit": True,
        }
    ).make_serial_and_batch_bundle()
    return bundle.name


def totals_for(day):
    """Counts and sums of the platform's submitted documents dated `day` (examleaf_ref set). Money as strings."""
    si = frappe.qb.DocType("Sales Invoice")
    item = frappe.qb.DocType("Sales Invoice Item")
    invoices = (
        frappe.qb.from_(si)
        .select(si.name, si.is_return, si.grand_total, si.total_taxes_and_charges, si.examleaf_doc_kind)
        .where((si.posting_date == day) & (si.docstatus == 1) & si.examleaf_ref.isnotnull())
        .run(as_dict=True)
    )
    lines = defaultdict(lambda: defaultdict(Decimal))
    if invoices:
        for row in (
            frappe.qb.from_(item)
            .select(item.parent, item.gst_treatment, item.taxable_value, item.net_amount)
            .where(item.parent.isin([i.name for i in invoices]))
            .run(as_dict=True)
        ):
            lines[row.parent][row.gst_treatment or "Taxable"] += to_decimal(row.taxable_value or row.net_amount)

    def summary(docs, sign):
        out = {
            "count": len(docs),
            "total": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "by_treatment": defaultdict(Decimal),
        }
        kinds = defaultdict(int)
        for doc in docs:
            out["total"] += sign * to_decimal(doc.grand_total)
            out["tax_total"] += sign * to_decimal(doc.total_taxes_and_charges)
            kinds[doc.examleaf_doc_kind or ""] += 1
            for treatment, value in lines[doc.name].items():
                out["by_treatment"][treatment] += sign * value
        taxable = sum((v for t, v in out["by_treatment"].items() if t in gst.TAXABLE_TREATMENTS), Decimal("0.00"))
        exempt = sum((v for t, v in out["by_treatment"].items() if t not in gst.TAXABLE_TREATMENTS), Decimal("0.00"))
        return {
            "count": out["count"],
            "total": money_str(out["total"]),
            "taxable_value": money_str(taxable),
            "exempt_value": money_str(exempt),
            "tax_total": money_str(out["tax_total"]),
            "by_treatment": {t: money_str(v) for t, v in sorted(out["by_treatment"].items())},
            "by_kind": dict(sorted(kinds.items())),
        }

    pe = frappe.qb.DocType("Payment Entry")
    payments = defaultdict(dict)
    for row in (
        frappe.qb.from_(pe)
        .select(pe.payment_type, pe.mode_of_payment, Count(pe.name).as_("count"), Sum(pe.paid_amount).as_("amount"))
        .where((pe.posting_date == day) & (pe.docstatus == 1) & pe.examleaf_ref.isnotnull())
        .groupby(pe.payment_type, pe.mode_of_payment)
        .run(as_dict=True)
    ):
        side = "receive" if row.payment_type == "Receive" else "refund"
        mode = next((code for code, name in MODES.items() if name == row.mode_of_payment), row.mode_of_payment)
        payments[side][mode] = {"count": row.count, "amount": money_str(row.amount)}

    dn = frappe.qb.DocType("Delivery Note")
    notes = (
        frappe.qb.from_(dn)
        .select(dn.name)
        .where((dn.posting_date == day) & (dn.docstatus == 1) & dn.examleaf_ref.isnotnull())
        .run(pluck=True)
    )
    shipped = {}
    if notes:
        sle = frappe.qb.DocType("Stock Ledger Entry")
        for row in (
            frappe.qb.from_(sle)
            .select(sle.item_code, Sum(sle.actual_qty).as_("qty"))
            .where((sle.voucher_type == "Delivery Note") & sle.voucher_no.isin(notes) & (sle.is_cancelled == 0))
            .groupby(sle.item_code)
            .orderby(sle.item_code)
            .run(as_dict=True)
        ):
            shipped[row.item_code] = -flt(row.qty)

    # settlements by kind, told by the clearing account they empty; total is the gross (net + fee + tax on the fee)
    je, jea = frappe.qb.DocType("Journal Entry"), frappe.qb.DocType("Journal Entry Account")
    clearing = {mode_account(MODES[kind]): kind for kind in ("razorpay", "cod")}
    settlements = {}
    for row in (
        frappe.qb.from_(je)
        .join(jea)
        .on(jea.parent == je.name)
        .select(jea.account, jea.credit_in_account_currency)
        .where(
            (je.posting_date == day)
            & (je.docstatus == 1)
            & je.examleaf_ref.isnotnull()
            & jea.account.isin(list(clearing))
            & (jea.credit_in_account_currency > 0)
        )
        .run(as_dict=True)
    ):
        entry = settlements.setdefault(clearing[row.account], {"count": 0, "total": Decimal("0.00")})
        entry["count"] += 1
        entry["total"] += to_decimal(row.credit_in_account_currency)

    return {
        "date": str(day),
        "invoices": summary([i for i in invoices if not i.is_return], 1),
        "credit_notes": summary([i for i in invoices if i.is_return], -1),
        "payments": {"receive": payments.get("receive", {}), "refund": payments.get("refund", {})},
        "settlements": {
            k: {"count": v["count"], "total": money_str(v["total"])} for k, v in sorted(settlements.items())
        },
        "shipped": {"delivery_notes": len(notes), "items": shipped},
    }


def upsert_party_address(customer, ref, fields, gstin):
    address_ref = f"{ref}:address"
    name = frappe.db.get_value("Address", {"examleaf_ref": address_ref}, "name")
    doc = frappe.get_doc("Address", name) if name else frappe.new_doc("Address")
    doc.update(
        {
            "address_title": customer.customer_name,
            "address_type": "Billing",
            "address_line1": fields["line1"],
            "address_line2": fields.get("line2"),
            "city": fields["city"],
            "county": fields.get("district"),
            "state": C.STATE_NAMES[fields["state"]],
            "country": "India",
            "pincode": fields["pin"],
            "gstin": gstin,
            "is_primary_address": 1,
            "is_shipping_address": 1,
        }
    )
    if not name:
        doc.examleaf_ref = address_ref
        doc.append("links", {"link_doctype": "Customer", "link_name": customer.name})
    doc.save() if name else doc.insert()
    if customer.customer_primary_address != doc.name:
        customer.db_set("customer_primary_address", doc.name)


def upsert_party_contact(customer, fields):
    name = customer.customer_primary_contact
    doc = frappe.get_doc("Contact", name) if name else frappe.new_doc("Contact")
    first, _, last = fields["name"].partition(" ")
    doc.update({"first_name": first, "last_name": last or None, "is_primary_contact": 1})
    doc.set("email_ids", [{"email_id": fields["email"], "is_primary": 1}] if fields.get("email") else [])
    doc.set("phone_nos", [{"phone": fields["phone"], "is_primary_mobile_no": 1}] if fields.get("phone") else [])
    if not name:
        doc.append("links", {"link_doctype": "Customer", "link_name": customer.name})
    doc.save() if name else doc.insert()
    if not name:
        customer.reload()
        customer.customer_primary_contact = doc.name
        customer.save()
