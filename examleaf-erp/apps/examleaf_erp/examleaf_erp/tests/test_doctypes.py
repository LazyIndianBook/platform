"""The custom doctypes: the sale-or-return clock, exclusive districts, adoptions and specimen requests."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate

from examleaf_erp import tasks
from examleaf_erp.tests.utils import abbr, company, make_customer, make_item, receive, unique


def challan(customer, item_code, qty=2, posting_date=None):
    """A submitted Delivery Note: the challan goods on approval or specimen copies travel on."""
    note = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "customer": customer,
            "company": company(),
            "posting_date": str(posting_date or getdate()),
            "set_posting_time": 1,
            "items": [{"item_code": item_code, "qty": qty, "rate": 0, "warehouse": f"Main - {abbr()}"}],
        }
    )
    note.insert(ignore_permissions=True)
    for row in note.items:  # one batch is enough here; the FIFO picking is the API's (test_api)
        row.use_serial_batch_fields = 1
        row.batch_no = frappe.get_all("Batch", filters={"item": row.item_code}, pluck="name", limit=1)[0]
    note.save()
    note.submit()
    return note.name


class TestSORDispatch(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = make_item()
        receive(cls.book, 20, "2026-04-01")
        cls.distributor = make_customer("Distributor")
        frappe.db.commit()

    def dispatch(self, removed_on, **extra):
        return frappe.get_doc(
            {
                "doctype": "SOR Dispatch",
                "customer": self.distributor,
                "delivery_note": challan(self.distributor, self.book, posting_date=removed_on),
                "removed_on": removed_on,
                **extra,
            }
        ).insert(ignore_permissions=True)

    def test_the_six_month_clock(self):
        doc = self.dispatch("2026-04-15")
        self.assertEqual(str(doc.due_on), "2026-10-15")
        self.assertEqual(doc.status_on("2026-09-14"), "Open")
        self.assertEqual(doc.status_on("2026-09-15"), "Due Soon")  # five months
        self.assertEqual(doc.status_on("2026-10-15"), "Due Soon")  # the last day
        self.assertEqual(doc.status_on("2026-10-16"), "Overdue")

    def test_month_ends(self):
        doc = self.dispatch("2026-04-30")
        self.assertEqual(str(doc.due_on), "2026-10-30")
        self.assertEqual(doc.status_on("2026-09-29"), "Open")
        self.assertEqual(doc.status_on("2026-09-30"), "Due Soon")

    def test_the_daily_job_flags_at_five_months_and_billing_closes_it(self):
        removed = add_months(getdate(), -4)  # open today
        doc = self.dispatch(str(removed))
        self.assertEqual(doc.status, "Open")
        five_months = add_days(add_months(removed, 5), 3)
        tasks.flag_sor_dispatches(day=five_months)
        doc.reload()
        self.assertEqual((doc.status, str(doc.flagged_on)), ("Due Soon", str(five_months)))
        tasks.flag_sor_dispatches(day=add_days(add_months(removed, 6), 1))
        doc.reload()
        self.assertEqual(doc.status, "Overdue")
        doc.billed_on = str(getdate())
        doc.save()
        self.assertEqual(doc.status, "Billed")

    def test_the_challan_must_be_the_customers(self):
        other = make_customer("Distributor")
        with self.assertRaisesRegex(frappe.ValidationError, "went to"):
            frappe.get_doc(
                {
                    "doctype": "SOR Dispatch",
                    "customer": other,
                    "removed_on": "2026-04-15",
                    "delivery_note": challan(self.distributor, self.book),
                }
            ).insert(ignore_permissions=True)


class TestDistributorAgreement(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.first = make_customer("Distributor")
        cls.second = make_customer("Distributor")
        frappe.db.commit()

    def agreement(self, customer, districts, item_group="Sample Papers", valid=("2026-04-01", "2027-03-31"), **extra):
        return frappe.get_doc(
            {
                "doctype": "Distributor Agreement",
                "customer": customer,
                "item_group": item_group,
                "valid_from": valid[0],
                "valid_until": valid[1],
                "districts": [{"district": d, "exclusive": e} for d, e in districts],
                **extra,
            }
        )

    def approve(self, doc):
        doc.insert(ignore_permissions=True)
        doc = apply_workflow(doc, "Submit for Approval")
        return apply_workflow(doc, "Approve")

    def test_no_district_has_two_exclusive_distributors(self):
        approved = self.approve(
            self.agreement(
                self.first,
                [("Kamrup Metro", 1), ("Kamrup", 0)],
                discount_percent=12,
                payment_terms="Net 30",
                credit_limit=50000,
                sor_allowed=1,
                sor_return_cap_percent=10,
            )
        )
        self.assertEqual((approved.docstatus, approved.workflow_state), (1, "Approved"))
        with self.assertRaisesRegex(frappe.ValidationError, "Kamrup Metro"):
            self.agreement(self.second, [("Kamrup Metro", 1)]).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "exclusivity"):  # a parent group overlaps too
            self.agreement(self.second, [("Kamrup Metro", 1)], item_group="All Item Groups").insert(
                ignore_permissions=True
            )
        with self.assertRaisesRegex(
            frappe.ValidationError, "exclusivity"
        ):  # beside an exclusive one, even non-exclusive
            self.agreement(self.second, [("Kamrup Metro", 0)]).insert(ignore_permissions=True)
        # what does not collide: another line, a non-exclusive district beside a non-exclusive one, another period
        self.agreement(self.second, [("Kamrup Metro", 1)], item_group="Solutions").insert(ignore_permissions=True)
        self.agreement(self.second, [("Kamrup", 0)]).insert(ignore_permissions=True)
        self.agreement(self.second, [("Kamrup Metro", 1)], valid=("2027-04-01", "2028-03-31")).insert(
            ignore_permissions=True
        )

    def test_approval_applies_the_terms(self):
        doc = self.approve(
            self.agreement(
                self.second,
                [("Jorhat", 1)],
                item_group="Bundles",
                discount_percent=15,
                payment_terms="Net 15",
                credit_limit=25000,
                sor_allowed=1,
                sor_return_cap_percent=10,
                valid=("2026-04-01", "2026-12-31"),
            )
        )
        customer = frappe.get_doc("Customer", self.second)
        self.assertEqual(
            (customer.payment_terms, str(customer.agreement_until), customer.sor_return_cap_percent),
            ("Net 15", "2026-12-31", 10),
        )
        self.assertEqual([r.credit_limit for r in customer.credit_limits if r.company == company()], [25000])
        rule = frappe.get_doc("Pricing Rule", doc.pricing_rule)
        self.assertEqual((rule.customer, rule.discount_percentage, rule.disable), (self.second, 15, 0))

    def test_the_period_must_be_forwards(self):
        with self.assertRaisesRegex(frappe.ValidationError, "after"):
            self.agreement(self.first, [("Nagaon", 1)], valid=("2026-04-01", "2026-03-01")).insert(
                ignore_permissions=True
            )


class TestSchoolAdoption(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.school = make_customer("School")
        frappe.db.commit()

    def adoption(self, **extra):
        return frappe.get_doc(
            {
                "doctype": "School Adoption",
                "customer": self.school,
                "academic_year": "2026-27",
                "class_level": 12,
                "subject": "Physics",
                **extra,
            }
        )

    def test_one_adoption_per_school_year_class_subject(self):
        self.adoption().insert(ignore_permissions=True)
        with self.assertRaises(frappe.DuplicateEntryError):
            self.adoption().insert(ignore_permissions=True)
        self.adoption(subject="Chemistry").insert(ignore_permissions=True)

    def test_a_lost_school_says_why_and_decisions_are_dated(self):
        with self.assertRaisesRegex(frappe.ValidationError, "why"):
            self.adoption(subject="Biology", stage="Lost").insert(ignore_permissions=True)
        doc = self.adoption(subject="Biology", stage="Recommended").insert(ignore_permissions=True)
        self.assertEqual(str(doc.decided_on), str(getdate()))
        with self.assertRaisesRegex(frappe.ValidationError, "2026-27"):
            self.adoption(subject="Maths", academic_year="2026-28").insert(ignore_permissions=True)


class TestSpecimenRequest(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = make_item()
        receive(cls.book, 5, "2026-04-01")
        cls.school = make_customer("School")
        frappe.db.commit()

    def test_a_dispatched_request_names_its_challan(self):
        doc = frappe.get_doc(
            {"doctype": "Specimen Request", "customer": self.school, "items": [{"item": self.book, "qty": 1}]}
        ).insert(ignore_permissions=True)
        doc.status = "Dispatched"
        with self.assertRaisesRegex(frappe.ValidationError, "challan"):
            doc.save()
        doc.reload()
        doc.status = "Dispatched"
        doc.delivery_challan = challan(self.school, self.book, qty=1)
        doc.dispatched_on = getdate()
        doc.follow_up_on = add_days(getdate(), 21)
        doc.save()
        from examleaf_erp.printing import challan_purpose

        self.assertIn("Specimen", challan_purpose(doc.delivery_challan))
        self.assertTrue(unique())
