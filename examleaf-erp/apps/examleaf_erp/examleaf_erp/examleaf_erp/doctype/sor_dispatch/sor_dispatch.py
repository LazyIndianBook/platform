import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, getdate


class SORDispatch(Document):
    """Goods sent on sale or return. CGST s.31(7): they are invoiced when the distributor accepts them or six months
    after their removal, whichever is earlier. The daily job (tasks.flag_sor_dispatches) moves the status to Due Soon at
    five months and Overdue after six; a Notification tells EL Sales and EL Finance."""

    def validate(self):
        note = frappe.db.get_value(
            "Delivery Note", self.delivery_note, ["docstatus", "customer", "posting_date", "is_return"], as_dict=True
        )
        if not note or note.docstatus != 1 or note.is_return:
            frappe.throw(_("{0} is not a submitted delivery challan.").format(self.delivery_note))
        if note.customer != self.customer:
            frappe.throw(_("{0} went to {1}, not {2}.").format(self.delivery_note, note.customer, self.customer))
        self.removed_on = self.removed_on or note.posting_date
        self.due_on = add_months(self.removed_on, 6)
        if self.billed_on and self.returned_on:
            frappe.throw(_("Goods are either billed or returned, not both."))
        for field in ("billed_on", "returned_on"):
            if self.get(field) and getdate(self.get(field)) < getdate(self.removed_on):
                frappe.throw(_("{0} is before the goods left.").format(self.meta.get_label(field)))
        if self.sales_invoice:
            invoice = frappe.db.get_value("Sales Invoice", self.sales_invoice, ["docstatus", "customer"], as_dict=True)
            if not invoice or invoice.docstatus != 1 or invoice.customer != self.customer:
                frappe.throw(_("{0} is not a submitted invoice of {1}.").format(self.sales_invoice, self.customer))
        self.status = self.status_on(self.flags.status_date)
        if self.status == "Due Soon" and not self.flagged_on:
            self.flagged_on = getdate(self.flags.status_date)

    def status_on(self, day=None):
        day = getdate(day)
        if self.billed_on:
            return "Billed"
        if self.returned_on:
            return "Returned"
        if day > getdate(self.due_on):
            return "Overdue"
        if day >= getdate(add_months(self.removed_on, 5)):
            return "Due Soon"
        return "Open"
