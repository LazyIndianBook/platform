"""doc_events (hooks.py): the rules ExamLeaf adds to standard doctypes. No Server Scripts: everything is here, tested."""

import re

import frappe
from frappe import _
from frappe.utils import flt

from examleaf_erp import gst

# The platform's legal numbers (shop.models.next_number): EL/2026-27/00001, CN/2026-27/00001, T…/TC… in the test
# series; an amendment would add -1, -2 (which is why there are none).
PLATFORM_NUMBER = re.compile(r"^(EL|CN|T|TC)/\d{4}-\d{2}/\d{5}(-\d+)*$")
UDISE = re.compile(r"^\d{11}$")


def is_platform_invoice(name, examleaf_ref=None) -> bool:
    return bool(examleaf_ref) or bool(PLATFORM_NUMBER.match(name or ""))


def validate_examleaf_ref(doc, method=None):
    """examleaf_ref is unique (a database index says so too) and, once set, never changes: it is how the platform finds
    the document again, so relinking it would let two records answer to one id."""
    ref = doc.get("examleaf_ref")
    if not doc.is_new():
        before = doc.get_doc_before_save()
        if before and before.get("examleaf_ref") and before.examleaf_ref != ref:
            frappe.throw(
                _("The ExamLeaf reference {0} cannot change.").format(frappe.bold(before.examleaf_ref)),
                title=_("Reference is fixed"),
            )
    if not ref:
        return
    other = frappe.db.get_value(doc.doctype, {"examleaf_ref": ref, "name": ("!=", doc.name or "")}, "name")
    if other:
        frappe.throw(
            _("{0} {1} already carries the ExamLeaf reference {2}.").format(_(doc.doctype), other, ref),
            frappe.UniqueValidationError,
        )


def refuse_amendment(doc, method=None):
    """An amendment of a GST invoice gets a -1 suffix (17 characters, past Rule 46(b)'s 16) and a second number for one
    supply: the platform's invoices are corrected by credit notes, never by cancel and amend (research 5.6)."""
    if not doc.amended_from:
        return
    ref = frappe.db.get_value("Sales Invoice", doc.amended_from, "examleaf_ref")
    if is_platform_invoice(doc.amended_from, ref):
        frappe.throw(
            _("{0} carries the platform's legal number: issue a credit note instead of amending it.").format(
                doc.amended_from
            ),
            title=_("Amendment not allowed"),
        )


def refuse_cancel(doc, method=None):
    if is_platform_invoice(doc.name, doc.get("examleaf_ref")):
        frappe.throw(
            _("{0} carries the platform's legal number: issue a credit note instead of cancelling it.").format(
                doc.name
            ),
            title=_("Cancellation not allowed"),
        )


def set_document_kind(doc, method=None):
    """Bill of supply, tax invoice or invoice-cum-bill of supply, from the lines' GST treatment (Rules 46, 46A, 49), and
    the matching Print Heading on invoices (a credit note keeps its own title)."""
    kind = gst.document_kind(
        doc.items,
        registered_buyer=bool(doc.get("billing_address_gstin")),
        submitting=doc.docstatus == 1 and not doc.is_return,
    )
    doc.examleaf_doc_kind = kind
    if not doc.is_return:
        doc.select_print_heading = gst.print_heading(kind)


def apply_e_waybill_exemption(doc, method=None):
    """India Compliance compares the whole grand total with the e-way bill threshold. Rule 138 leaves exempt goods out:
    printed books (HSN 4901) are in the Annexure of Rule 138(14) and, on a mixed consignment, Explanation 2 to Rule
    138(1) counts the taxable goods only. Runs after India Compliance's validate (apps run in install order)."""
    if doc.get("e_waybill_status") != "Pending" or doc.get("ewaybill"):
        return
    threshold = gst.e_waybill_threshold(doc)
    if threshold is not None and gst.e_waybill_value(doc) < flt(threshold):
        doc.e_waybill_status = "Not Applicable"


def set_quotation_discount(doc, method=None):
    """The highest discount of a quotation against its price list, for the Quotation Approval workflow's condition."""
    doc.examleaf_discount_percent = gst.highest_discount_percent(doc)


def validate_school_fields(doc, method=None):
    if doc.get("udise_code") and not UDISE.match(doc.udise_code):
        frappe.throw(_("A UDISE+ code has 11 digits."), title=_("Invalid UDISE+ code"))
