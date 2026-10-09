import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, today

DECIDED = ("Recommended", "Ordered", "Delivered", "Paid", "Lost")


class SchoolAdoption(Document):
    def validate(self):
        year = self.academic_year or ""
        if not re.fullmatch(r"\d{4}-\d{2}", year) or int(year[5:]) != (int(year[:4]) + 1) % 100:
            frappe.throw(_("An academic year is written 2026-27."), title=_("Invalid academic year"))
        if not 1 <= cint(self.class_level) <= 12:
            frappe.throw(_("Class is from 1 to 12."), title=_("Invalid class"))
        if cint(self.expected_copies) < 0:
            frappe.throw(_("Expected copies cannot be negative."))
        if self.stage == "Lost" and not (self.lost_reason or "").strip():
            frappe.throw(_("Say why the school was lost."), title=_("Lost reason needed"))
        if self.stage in DECIDED and not self.decided_on:
            self.decided_on = today()
        other = frappe.db.get_value(
            "School Adoption",
            {
                "customer": self.customer,
                "academic_year": self.academic_year,
                "class_level": self.class_level,
                "subject": self.subject,
                "name": ("!=", self.name),
            },
        )
        if other:
            frappe.throw(
                _("{0} already follows {1}, class {2}, {3} in {4}.").format(
                    other, self.customer, self.class_level, self.subject, self.academic_year
                ),
                frappe.DuplicateEntryError,
            )


def on_doctype_update():
    """One adoption per school, year, class and subject: the database says so too (two staff saving at once)."""
    frappe.db.add_unique(
        "School Adoption", ["customer", "academic_year", "class_level", "subject"], constraint_name="unique_adoption"
    )
