"""GST rules ExamLeaf applies on top of India Compliance: the document's kind, its heading, the e-way bill value."""

import frappe
from frappe import _
from frappe.utils import flt

from examleaf_erp.constants import NON_TAXABLE_TREATMENTS, PRINT_HEADINGS

TAXABLE_TREATMENTS = ("Taxable", "Zero-Rated")


def treatment(row) -> str:
    """The line's GST treatment: India Compliance sets it on every row in validate; a row read before that (or a row of
    a document saved without taxes) falls back to its Item Tax Template's treatment, then to Taxable."""
    if row.get("gst_treatment"):
        return row.gst_treatment
    if row.get("item_tax_template"):
        return frappe.get_cached_value("Item Tax Template", row.item_tax_template, "gst_treatment") or "Taxable"
    return "Taxable"


def document_kind(rows, registered_buyer: bool = False, submitting: bool = True) -> str:
    """tax_invoice when every line is taxed, bill_of_supply when none is (Rule 49), invoice_cum_bill_of_supply when both
    meet on one document for an unregistered buyer (Rule 46A). A registered buyer of both gets two documents: refused
    when submitted, provisional (tax_invoice) while a draft."""
    kinds = {treatment(row) in TAXABLE_TREATMENTS for row in rows}
    if kinds == {False}:
        return "bill_of_supply"
    if kinds == {True} or not kinds:
        return "tax_invoice"
    if not registered_buyer:
        return "invoice_cum_bill_of_supply"
    if submitting:
        frappe.throw(
            _(
                "This buyer is registered for GST: issue one tax invoice for the taxable lines and one bill of supply"
                " for the exempt ones (an invoice-cum-bill of supply is for unregistered buyers only, Rule 46A)."
            ),
            title=_("Separate documents needed"),
        )
    return "tax_invoice"


def print_heading(kind: str) -> str:
    return PRINT_HEADINGS[kind]


def e_waybill_threshold(doc):
    from india_compliance.gst_india.utils.e_waybill import _get_e_waybill_threshold

    return _get_e_waybill_threshold(doc)


def e_waybill_value(doc) -> float:
    """The consignment value Rule 138 compares with the threshold: taxable goods with their tax. Services (SAC 99…) do
    not move; exempt, nil-rated and non-GST goods are left out (Explanation 2 to Rule 138(1); books are also in the
    Annexure to Rule 138(14))."""
    total = 0.0
    for row in doc.items:
        if (row.get("gst_hsn_code") or "").startswith("99") or treatment(row) in NON_TAXABLE_TREATMENTS:
            continue
        taxes = sum(flt(row.get(f"{tax}_amount")) for tax in ("igst", "cgst", "sgst", "cess", "cess_non_advol"))
        total += abs(flt(row.get("taxable_value") or row.net_amount)) + abs(taxes)
    return total


def highest_discount_percent(doc) -> float:
    """The largest cut a quotation gives against its price list: a line's own discount, or the whole quotation's (line
    discounts and the additional discount together) when that is bigger. Rates and price list rates are compared on
    the same basis, so inclusive or exclusive tax does not matter. 0 without price list rates."""
    best = list_total = charged = 0.0
    for row in doc.items:
        list_rate = flt(row.price_list_rate)
        if not list_rate:
            continue
        list_total += list_rate * flt(row.qty)
        charged += flt(row.rate) * flt(row.qty)
        best = max(best, (list_rate - flt(row.rate)) * 100 / list_rate)
    if list_total:
        best = max(best, (list_total - charged + flt(doc.discount_amount)) * 100 / list_total)
    return flt(best, 2)
