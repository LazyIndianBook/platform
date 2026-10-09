"""The bootstrap and the install hooks are safe to run again; what they set is what research-erpnext.md asks for."""

import frappe
from frappe.tests import IntegrationTestCase

from examleaf_erp import constants as C
from examleaf_erp import setup
from examleaf_erp.tests.utils import abbr, as_user, company, make_customer, sync_user, unique

COUNTED = (
    "Company",
    "Account",
    "Warehouse",
    "Item Tax Template",
    "Customer",
    "User",
    "Address",
    "Social Login Key",
    "Territory",
    "Customer Group",
    "Item Group",
    "Custom DocPerm",
    "Webhook",
)


class TestSetup(IntegrationTestCase):
    def test_bootstrap_twice_changes_nothing(self):
        setup.bootstrap()
        before = {doctype: frappe.db.count(doctype) for doctype in COUNTED}
        setup.bootstrap()
        setup.after_install()
        setup.after_sync()
        self.assertEqual({doctype: frappe.db.count(doctype) for doctype in COUNTED}, before)

    def test_the_company(self):
        name = company()
        self.assertEqual((name, abbr()), ("ExamLeaf LLP", "EL"))
        self.assertEqual(frappe.db.get_value("Company", name, "country"), "India")
        for account in ("Razorpay Clearing", "COD in Transit", "Payment Gateway Charges"):
            self.assertTrue(frappe.db.exists("Account", f"{account} - EL"), account)
        for warehouse in ("Main", "Damaged", "At Printer"):
            self.assertTrue(frappe.db.exists("Warehouse", f"{warehouse} - EL"), warehouse)
        self.assertEqual(frappe.db.get_value("Item Tax Template", "GST Exempted - EL", "gst_treatment"), "Exempted")
        self.assertEqual(frappe.db.get_value("Item Tax Template", "GST 18% - EL", "gst_treatment"), "Taxable")
        links = {
            row.parent: row.item_tax_template
            for row in frappe.get_all(
                "Item Tax",
                filters={"parenttype": "GST HSN Code", "parent": ["in", ["4901", "999293"]]},
                fields=["parent", "item_tax_template"],
            )
        }
        self.assertEqual(links, {"4901": "GST Exempted - EL", "999293": "GST 18% - EL"})
        self.assertEqual(frappe.db.get_value("Customer", C.B2C_CUSTOMER, "customer_group"), C.B2C_GROUP)
        self.assertEqual(
            frappe.db.get_value("Address", {"examleaf_ref": "company:address"}, "gstin"), frappe.conf.examleaf_gstin
        )

    def test_the_settings(self):
        system = frappe.get_doc("System Settings")
        self.assertEqual(
            (
                system.session_expiry,
                system.login_with_email_link,
                system.deny_multiple_sessions,
                system.minimum_password_score,
                system.allow_consecutive_login_attempts,
                system.enable_two_factor_auth,
            ),
            ("08:00", 0, 1, "3", 5, 1),
        )
        self.assertEqual(frappe.db.get_single_value("Website Settings", "disable_signup"), 1)
        self.assertEqual(
            {r.name for r in frappe.get_all("Role", filters={"two_factor_auth": 1, "name": ["like", "EL %"]})},
            {"EL Admin", "EL Finance"},
        )
        key = frappe.get_doc("Social Login Key", "google")
        self.assertEqual((key.sign_ups, frappe.parse_json(key.auth_url_data)["hd"]), ("Deny", "examleaf.in"))
        self.assertEqual(frappe.db.get_single_value("Accounts Settings", "enable_audit_trail"), 1)
        self.assertEqual(
            frappe.db.get_single_value("Accounts Settings", "determine_address_tax_category_from"), "Shipping Address"
        )
        gst = frappe.get_doc("GST Settings")
        self.assertEqual((gst.enable_e_invoice, gst.min_hsn_digits, gst.e_waybill_threshold), (0, "4", 50000))

    def test_the_trees(self):
        self.assertEqual(frappe.db.get_value("Territory", "Assam", "parent_territory"), "India")
        lft, rgt = frappe.db.get_value("Territory", "Assam", ["lft", "rgt"])
        inside = frappe.get_all("Territory", filters={"lft": [">", lft], "rgt": ["<", rgt]}, pluck="name")
        self.assertEqual(sorted(inside), sorted(C.ASSAM_DISTRICTS))
        for doctype, root in setup.TREES:
            self.assertEqual(frappe.get_all(doctype, filters={"lft": 1}, pluck="name"), [root])

    def test_state_names_are_india_compliances(self):
        from india_compliance.gst_india.constants import STATE_NUMBERS

        self.assertFalse(set(C.STATE_NAMES.values()) - set(STATE_NUMBERS))

    def test_the_sync_role_holds_only_what_the_api_writes(self):
        rows = frappe.get_all("Custom DocPerm", filters={"role": C.SYNC_ROLE}, fields=["parent"], pluck="parent")
        self.assertEqual(sorted(rows), sorted(setup.SYNC_PERMISSIONS))
        self.assertEqual(frappe.db.get_value("User", sync_user(), "user_type"), "Website User")  # no Desk
        with as_user(sync_user()):
            self.assertTrue(frappe.has_permission("Sales Invoice", "submit"))
            self.assertFalse(frappe.has_permission("Sales Invoice", "cancel"))
            self.assertFalse(frappe.has_permission("Journal Entry", "delete"))
            self.assertFalse(frappe.has_permission("GL Entry", "read"))
            self.assertTrue(frappe.has_permission("Quotation", "read"))  # re-read when the webhook rings
            self.assertFalse(frappe.has_permission("Quotation", "write"))

    def test_the_webhooks_are_off_until_configured(self):
        from frappe.integrations.doctype.webhook.webhook import get_webhook_data

        # the site's own values put back after (the shadow run's site had its platform configured, and this test
        # assumed none: examleaf-web/erp/SHADOW-RUN.md)
        conf, keys = frappe.local.conf, ("examleaf_webhook_base", "examleaf_webhook_secret")
        saved = {key: conf.pop(key) for key in keys if key in conf}
        try:
            setup.configure_webhooks()
            self.assertEqual(frappe.get_all("Webhook", filters={"name": ["like", "EL %"], "enabled": 1}), [])
            for name in frappe.get_all("Webhook", filters={"name": ["like", "EL %"]}, pluck="name"):
                hook = frappe.get_doc("Webhook", name)  # the body API.md promises, also for doctypes without a ref
                body = get_webhook_data(frappe.new_doc(hook.webhook_doctype), hook)
                self.assertEqual(sorted(body), ["doctype", "event", "examleaf_ref", "modified", "name"])
                self.assertEqual((body["doctype"], body["event"]), (hook.webhook_doctype, hook.webhook_docevent))
            conf.examleaf_webhook_base, conf.examleaf_webhook_secret = "https://platform.example/erp/hooks/", "s3cret"
            setup.configure_webhooks()
            hook = frappe.get_doc("Webhook", "EL Stock Ledger Entry after_insert")
            self.assertEqual((hook.enabled, hook.request_url, hook.enable_security), (1, conf.examleaf_webhook_base, 1))
            self.assertEqual(hook.get_password("webhook_secret"), "s3cret")
        finally:
            for key in keys:
                conf.pop(key, None)
            conf.update(saved)
            setup.configure_webhooks()

    def test_user_data_fields_redact_a_b2b_contact(self):
        from frappe.website.doctype.personal_data_deletion_request.personal_data_deletion_request import (
            PersonalDataDeletionRequest,
        )

        self.assertIn(
            {"doctype": "Customer", "filter_by": "email_id", "redact_fields": ["mobile_no"]},
            frappe.get_hooks("user_data_fields", app_name="examleaf_erp"),
        )
        email = f"{unique('teacher-')}@example.com"
        customer = frappe.get_doc("Customer", make_customer("School"))
        contact = frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": "Rima",
                "last_name": "Bora",
                "email_ids": [{"email_id": email, "is_primary": 1}],
                "phone_nos": [{"phone": "+919864000000", "is_primary_mobile_no": 1}],
                "links": [{"link_doctype": "Customer", "link_name": customer.name}],
            }
        ).insert(ignore_permissions=True)
        customer.customer_primary_contact = contact.name
        customer.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Customer", customer.name, "email_id"), email)
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Rima", "send_welcome_email": 0}).insert(
            ignore_permissions=True
        )
        request = frappe.get_doc({"doctype": "Personal Data Deletion Request", "email": email})
        request.flags.ignore_permissions = True
        request.set_new_name()
        request.db_insert()  # not insert(): its after_insert mails the person a confirmation link
        PersonalDataDeletionRequest._anonymize_data(request)
        mobile, stored_email = frappe.db.get_value("Customer", customer.name, ["mobile_no", "email_id"])
        self.assertNotIn("9864000000", mobile or "")
        self.assertNotEqual(stored_email, email)
