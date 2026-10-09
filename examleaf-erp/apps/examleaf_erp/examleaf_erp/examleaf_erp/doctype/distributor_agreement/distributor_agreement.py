import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class DistributorAgreement(Document):
    def validate(self):
        if getdate(self.valid_until) <= getdate(self.valid_from):
            frappe.throw(_("Valid until must be after valid from."), title=_("Invalid period"))
        for field in ("discount_percent", "sor_return_cap_percent"):
            if not 0 <= flt(self.get(field)) <= 100:
                frappe.throw(_("{0} is a percentage from 0 to 100.").format(self.meta.get_label(field)))
        if not self.sor_allowed:
            self.sor_return_cap_percent = 0
        if not self.districts:
            frappe.throw(_("Name at least one district."), title=_("No districts"))
        seen = set()
        for row in self.districts:
            if row.district in seen:
                frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.district))
            seen.add(row.district)
        self.check_exclusivity()

    def check_exclusivity(self):
        """An exclusive district belongs to one distributor for a line: no approved agreement of another distributor may
        cover the same district for an overlapping item group (one inside the other in the tree) over an overlapping
        period, when either side is exclusive. Two exclusive distributors is the case research-b2b-predictive 1.2 names;
        an exclusive one beside a non-exclusive one breaks the same promise, so it is refused too."""
        mine = {row.district: row.exclusive for row in self.districts}
        lft, rgt = frappe.db.get_value("Item Group", self.item_group, ["lft", "rgt"])
        agreement = frappe.qb.DocType("Distributor Agreement")
        district = frappe.qb.DocType("Distributor Agreement District")
        group = frappe.qb.DocType("Item Group")
        rows = (
            frappe.qb.from_(agreement)
            .join(district)
            .on(district.parent == agreement.name)
            .join(group)
            .on(group.name == agreement.item_group)
            .select(agreement.name, agreement.customer, agreement.item_group, district.district, district.exclusive)
            .where(
                (agreement.docstatus == 1)
                & (agreement.name != (self.name or ""))
                & (agreement.customer != self.customer)
                & (agreement.valid_from <= self.valid_until)
                & (agreement.valid_until >= self.valid_from)
                & district.district.isin(list(mine))
                & (((group.lft <= lft) & (group.rgt >= rgt)) | ((group.lft >= lft) & (group.rgt <= rgt)))
            )
            .run(as_dict=True)
        )
        for row in rows:
            if mine[row.district] or row.exclusive:
                frappe.throw(
                    _(
                        "{0}: {1} ({2}) already covers it for {3} under {4}, and exclusivity allows one distributor."
                    ).format(
                        row.district,
                        row.customer,
                        "exclusive" if row.exclusive else "not exclusive",
                        row.item_group,
                        row.name,
                    ),
                    title=_("District taken"),
                )

    def on_submit(self):
        self.apply_terms()
        self.make_pricing_rule()

    def on_cancel(self):
        if self.pricing_rule:
            frappe.db.set_value("Pricing Rule", self.pricing_rule, "disable", 1)

    def apply_terms(self):
        """The approved terms become the customer's: payment terms, the credit limit for the company, the agreement's
        end and the returns cap (Customer fields agreement_until and sor_return_cap_percent)."""
        customer = frappe.get_doc("Customer", self.customer)
        company = frappe.defaults.get_global_default("company")
        if self.payment_terms:
            customer.payment_terms = self.payment_terms
        if flt(self.credit_limit) and company:
            row = next((r for r in customer.credit_limits if r.company == company), None) or customer.append(
                "credit_limits", {"company": company}
            )
            row.credit_limit = self.credit_limit
        customer.agreement_until = self.valid_until
        customer.sor_return_cap_percent = self.sor_return_cap_percent if self.sor_allowed else 0
        customer.flags.ignore_permissions = True  # an approval's consequence, whoever approved
        customer.save()

    def make_pricing_rule(self):
        if not flt(self.discount_percent):
            return
        rule = frappe.get_doc(
            {
                "doctype": "Pricing Rule",
                "title": f"{self.name} trade discount",
                "apply_on": "Item Group",
                "item_groups": [{"item_group": self.item_group}],
                "price_or_product_discount": "Price",
                "selling": 1,
                "applicable_for": "Customer",
                "customer": self.customer,
                "rate_or_discount": "Discount Percentage",
                "discount_percentage": self.discount_percent,
                "valid_from": self.valid_from,
                "valid_upto": self.valid_until,
                "company": frappe.defaults.get_global_default("company"),
                "currency": "INR",
            }
        )
        rule.insert(ignore_permissions=True)
        self.db_set("pricing_rule", rule.name)
