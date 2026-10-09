"""Jinja methods for the print formats (hooks.py jinja): the numbers a GST document prints, worked out once in Python."""

from collections import defaultdict
from datetime import date

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate

from examleaf_erp.gst import TAXABLE_TREATMENTS, treatment

BUCKETS = (("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None))


def invoice_lines(doc):
    """Each line as Rules 46, 46A and 49 print it: HSN, quantity and unit, rate, discount, taxable value, each tax's rate
    and amount (India Compliance keeps them per line), exempt lines marked; and the HSN summary under the table."""
    lines, by_hsn = [], defaultdict(lambda: defaultdict(float))
    for row in doc.items:
        exempt = treatment(row) not in TAXABLE_TREATMENTS
        taxable = flt(row.get("taxable_value") or row.net_amount)
        taxes = {tax: (flt(row.get(f"{tax}_rate")), flt(row.get(f"{tax}_amount"))) for tax in ("cgst", "sgst", "igst")}
        discount = (flt(row.price_list_rate) - flt(row.rate)) * flt(row.qty) if row.price_list_rate else 0
        lines.append(
            {
                "row": row,
                "hsn": row.get("gst_hsn_code") or "",
                "qty": flt(row.qty),
                "uom": row.uom or row.stock_uom,
                "rate": flt(row.price_list_rate or row.rate),
                "discount": discount,
                "taxable": taxable,
                "taxes": taxes,
                "total": taxable + sum(amount for _rate, amount in taxes.values()),
                "exempt": exempt,
                "treatment": treatment(row),
            }
        )
        summary = by_hsn[(row.get("gst_hsn_code") or "", "Exempt" if exempt else treatment(row))]
        summary["qty"] += flt(row.qty)
        summary["taxable"] += taxable
        for tax, (_rate, amount) in taxes.items():
            summary[tax] += amount
    hsn_summary = [{"hsn": hsn, "treatment": kind, **values} for (hsn, kind), values in sorted(by_hsn.items())]
    return {"lines": lines, "hsn_summary": hsn_summary, "intra_state": is_intra_state(doc)}


def is_intra_state(doc):
    company_gstin = doc.get("company_gstin") or ""
    return bool(doc.get("place_of_supply")) and doc.place_of_supply[:2] == company_gstin[:2]


def einvoice_qr(doc):
    """The signed QR code of an e-invoice (Rules 46(r), 48(4)) as a base64 PNG, or None before there is an IRN."""
    if not doc.get("irn"):
        return None
    signed = frappe.db.get_value("e-Invoice Log", doc.irn, "signed_qr_code")
    if not signed:
        return None
    from india_compliance.gst_india.utils.jinja import get_qr_code

    return get_qr_code(signed)


def challan_batches(doc):
    """The print runs a Delivery Note took its copies from (its Serial and Batch Bundles, or the plain batch field)."""
    out = []
    for row in [*doc.items, *doc.get("packed_items", [])]:
        if row.get("serial_and_batch_bundle"):
            entries = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": row.serial_and_batch_bundle},
                fields=["batch_no", "qty"],
                order_by="idx asc",
            )
        elif row.get("batch_no"):
            entries = [frappe._dict(batch_no=row.batch_no, qty=row.get("stock_qty") or row.qty)]
        else:
            continue
        for entry in entries:
            out.append(
                {
                    "item_name": row.item_name,
                    "batch_no": entry.batch_no,
                    "qty": abs(flt(entry.qty)),
                    "print_date": frappe.db.get_value("Batch", entry.batch_no, "manufacturing_date"),
                }
            )
    return out


def challan_purpose(delivery_note):
    """Rule 55(1): why goods travel on a challan rather than an invoice."""
    if frappe.db.exists("SOR Dispatch", {"delivery_note": delivery_note}):
        return "Supply on approval, sale or return (CGST s.31(7)): to be invoiced on acceptance or within six months"
    if frappe.db.exists("Specimen Request", {"delivery_challan": delivery_note}):
        return "Specimen copies, free of charge: not a supply"
    invoice = frappe.db.get_value("Delivery Note Item", {"parent": delivery_note}, "against_sales_invoice")
    if invoice:
        return f"Goods sent against invoice {invoice}"
    return "Supply of goods"


def statement_of_account(customer, from_date=None, to_date=None, company=None):
    """The ledger of a customer between two dates (default: the financial year so far) with its opening and closing
    balance, and what is still owed, aged by due date in the buckets research-b2b-predictive 1.2 names."""
    company = company or frappe.defaults.get_global_default("company")
    to_date = getdate(to_date)
    if from_date:
        from_date = getdate(from_date)
    else:
        start_year = to_date.year if to_date.month >= 4 else to_date.year - 1
        from_date = date(start_year, 4, 1)
    gle = frappe.qb.DocType("GL Entry")
    base = (gle.party_type == "Customer") & (gle.party == customer) & (gle.company == company) & (gle.is_cancelled == 0)
    opening = (
        frappe.qb.from_(gle)
        .select((Sum(gle.debit) - Sum(gle.credit)).as_("balance"))
        .where(base & (gle.posting_date < from_date))
        .run(as_dict=True)
    )
    balance = flt(opening[0].balance) if opening else 0.0
    rows = (
        frappe.qb.from_(gle)
        .select(gle.posting_date, gle.voucher_type, gle.voucher_no, gle.debit, gle.credit, gle.remarks)
        .where(base & (gle.posting_date >= from_date) & (gle.posting_date <= to_date))
        .orderby(gle.posting_date)
        .orderby(gle.creation)
        .run(as_dict=True)
    )
    lines, opening_balance = [], balance
    for row in rows:
        balance += flt(row.debit) - flt(row.credit)
        lines.append({**row, "balance": balance})
    ageing = {label: 0.0 for label, _low, _high in BUCKETS}
    not_due = credit = 0.0
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"customer": customer, "company": company, "docstatus": 1, "outstanding_amount": ["!=", 0]},
        fields=["name", "posting_date", "due_date", "outstanding_amount"],
        order_by="due_date asc",
    )
    open_items = []
    for invoice in invoices:
        amount = flt(invoice.outstanding_amount)
        if amount < 0:
            credit += -amount
            continue
        days = (to_date - getdate(invoice.due_date or invoice.posting_date)).days
        if days < 0:
            not_due += amount
        else:
            label = next(label for label, low, high in BUCKETS if days >= low and (high is None or days <= high))
            ageing[label] += amount
        open_items.append({**invoice, "days": days})
    return {
        "customer": customer,
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "opening": opening_balance,
        "lines": lines,
        "closing": balance,
        "not_due": not_due,
        "ageing": ageing,
        "unallocated_credit": credit,
        "open_items": open_items,
    }
