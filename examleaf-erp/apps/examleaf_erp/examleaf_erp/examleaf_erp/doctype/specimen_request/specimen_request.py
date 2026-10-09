import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

SENT = ("Dispatched", "Followed Up", "Closed")


class SpecimenRequest(Document):
    def validate(self):
        if not (self.customer or self.contact):
            frappe.throw(_("Name the school or bookseller, or the teacher."), title=_("Who asked?"))
        seen = set()
        for row in self.items:
            if cint(row.qty) < 1:
                frappe.throw(_("Row {0}: at least one copy.").format(row.idx))
            if row.item in seen:
                frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.item))
            seen.add(row.item)
        if self.status in SENT:
            if not (self.delivery_challan and self.dispatched_on):
                frappe.throw(_("A dispatched request names its delivery challan and the day it left."))
            challan = frappe.db.get_value(
                "Delivery Note", self.delivery_challan, ["docstatus", "customer"], as_dict=True
            )
            if not challan or challan.docstatus != 1:
                frappe.throw(_("{0} is not a submitted delivery challan.").format(self.delivery_challan))
            if self.customer and challan.customer != self.customer:
                frappe.throw(
                    _("{0} went to {1}, not {2}.").format(self.delivery_challan, challan.customer, self.customer)
                )
        if self.follow_up_on and self.dispatched_on and getdate(self.follow_up_on) < getdate(self.dispatched_on):
            frappe.throw(_("Follow up after the copies have left."))
