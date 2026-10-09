"""Install hooks, and `bench --site <site> execute examleaf_erp.setup.bootstrap`: the company and everything ExamLeaf needs
around it. Every step looks before it makes, so running it twice changes nothing. Values come from the site config
(keys examleaf_*: compose/site_config.example.json, README "Site config"); secrets never come from this repository.

The settings are applied on the first run only (or with reset_settings=1): after go-live they belong to the people who
run ERPNext (Finance turns e-invoicing on at ₹5 crore), and a later bootstrap must not quietly undo that. The
references "research n" are to docs/research/2026-10-09-admin-control-panel/research-erpnext.md."""

import json

import frappe
from frappe import _
from frappe.permissions import add_permission, update_permission_property
from frappe.utils import getdate, now
from frappe.utils.nestedset import rebuild_tree

from examleaf_erp import constants as C

DEFAULTS = {
    "examleaf_company_name": "ExamLeaf LLP",
    "examleaf_company_abbr": "EL",
    "examleaf_bank_account": "Main Bank",
    "examleaf_state": "Assam",
    "examleaf_sync_user": "erp-sync@examleaf.in",
}
TREES = (
    ("Territory", C.ROOT_TERRITORY),
    ("Customer Group", C.ROOT_CUSTOMER_GROUP),
    ("Item Group", C.ROOT_ITEM_GROUP),
)
WAREHOUSES = ("Main", "Damaged", "At Printer")
BOOK_HSN, COURSE_SAC = "4901", "999293"  # printed books (exempt); commercial training and coaching (18 %)
RIGHTS = (
    "select",
    "read",
    "write",
    "create",
    "submit",
    "cancel",
    "amend",
    "delete",
    "report",
    "export",
    "print",
    "email",
    "share",
)
# What EL Sync may do, and nothing else: the doctypes examleaf_erp.api writes (research 5.5 "SERVICE"), and Quotation
# to read, which the platform re-reads (/api/resource) when its webhook rings. The rest of the read side (get_stock,
# get_changes_since, daily_totals) reads through the endpoint, which only EL Sync may call, not through DocPerms, so
# the key opens no /api/resource listing of stock or ledgers.
SYNC_PERMISSIONS = {
    "Quotation": ("read",),
    "Item": ("read", "write", "create"),
    "Item Price": ("read", "write", "create"),
    "Product Bundle": ("read", "write", "create"),
    "Customer": ("read", "write", "create"),
    "Address": ("read", "write", "create"),
    "Contact": ("read", "write", "create"),
    "Sales Invoice": ("read", "write", "create", "submit"),  # submit saves, and saving needs write (drafts only)
    "Payment Entry": ("read", "write", "create", "submit"),
    "Journal Entry": ("read", "write", "create", "submit"),
    "Delivery Note": ("read", "write", "create", "submit"),
    "Serial and Batch Bundle": ("read", "write", "create", "submit"),
    # masters ERPNext checks before it lets a user link them (erpnext.accounts.party.get_party_account and the like):
    # select only, which shows a record's name in a link field and nothing else
    "Account": ("select", "read"),  # get_payment_entry reads the bank account (a name and a type, not balances)
    "Company": ("select", "read"),  # India Compliance reads the company's GSTINs for a journal with GST accounts
    "Sales Taxes and Charges Template": ("select",),
}


def conf(key):
    return frappe.conf.get(key) or DEFAULTS.get(key)


def real(key):
    """A site config value, or None while it is still empty or a [placeholder]."""
    value = frappe.conf.get(key)
    return value if value and "[" not in str(value) else None


# ------------------------------------------------------------------------------------------------------- install hooks
def after_install():
    """Before the fixtures are imported: the tree roots they hang under (ERPNext makes them in its setup wizard, which
    may not have run yet). Safe to run twice."""
    ensure_tree_roots()


def after_sync():
    """After install and after every migrate (both import the fixtures again): rebuild the trees the fixtures touched,
    put back the permissions, webhooks and accounts the fixtures cannot carry."""
    ensure_tree_roots()
    rebuild_trees()
    apply_role_permissions()
    configure_webhooks()
    if company := frappe.defaults.get_global_default("company"):
        set_mode_of_payment_accounts(company)


def before_tests():
    bootstrap()


def ensure_tree_roots():
    for doctype, root in TREES:
        if not frappe.db.exists(doctype, root):
            doc = frappe.get_doc({"doctype": doctype, f"{frappe.scrub(doctype)}_name": root, "is_group": 1})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)


def rebuild_trees():
    """Fixtures are deleted and inserted again on every migrate, which leaves lft/rgt holes and strands any node staff
    added under them; rebuilding from the parent links is cheap at this size."""
    for doctype, _root in TREES:
        rebuild_tree(doctype)


def apply_role_permissions():
    """EL Sync's rights on standard doctypes, as Custom DocPerms. add_permission first copies the doctype's standard
    rules into Custom DocPerm (Frappe's own behaviour when anyone edits permissions), so other roles keep theirs."""
    if not frappe.db.exists("Role", C.SYNC_ROLE):  # the Role fixture brings it; nothing to grant before that
        return
    for doctype, rights in SYNC_PERMISSIONS.items():
        add_permission(doctype, C.SYNC_ROLE, 0)
        for right in RIGHTS:
            update_permission_property(doctype, C.SYNC_ROLE, 0, right, 1 if right in rights else 0, validate=False)


def configure_webhooks():
    """The fixtures ship the webhooks disabled with a placeholder URL. With examleaf_webhook_base (the platform's
    receiver URL) and examleaf_webhook_secret (HMAC key, X-Frappe-Webhook-Signature) in the site config they are turned
    on; without them they stay off."""
    base, secret = frappe.conf.get("examleaf_webhook_base"), frappe.conf.get("examleaf_webhook_secret")
    for name in frappe.get_all("Webhook", filters={"name": ["like", "EL %"]}, pluck="name"):
        hook = frappe.get_doc("Webhook", name)
        hook.enabled = int(bool(base and secret))
        if hook.enabled:
            hook.request_url = base
            hook.enable_security = 1
            hook.webhook_secret = secret
        hook.flags.ignore_permissions = True
        hook.save()


# ------------------------------------------------------------------------------------------------------------ bootstrap
def bootstrap(reset_settings=False):
    """Make or complete the ExamLeaf company and its masters. reset_settings=1 applies the settings again (they are
    applied on the first run only, see the module's docstring)."""
    ensure_tree_roots()
    gstin = frappe.conf.get("examleaf_gstin")
    if not gstin:
        frappe.throw(_("Set examleaf_gstin (and the other examleaf_* keys) in the site config first: README."))
    company = conf("examleaf_company_name")
    first_run = not frappe.db.exists("Company", company)
    if first_run:
        run_setup_wizard(company, gstin)
    rebuild_trees()
    abbr = frappe.get_cached_value("Company", company, "abbr")
    ensure_company_details(company, gstin)
    ensure_accounts(company, abbr)
    ensure_warehouses(company, abbr)
    # before HSN links and items: India Compliance refuses a 4-digit HSN (4901) until min_hsn_digits is 4
    if first_run or reset_settings or not frappe.db.get_default("examleaf_settings_applied"):
        apply_settings(company, abbr)
        frappe.db.set_default("examleaf_settings_applied", now())
    ensure_tax_templates(company, abbr)
    ensure_shipping_item(company)
    ensure_b2c_customer()
    set_mode_of_payment_accounts(company)
    ensure_sync_user()
    apply_role_permissions()
    configure_webhooks()
    frappe.db.commit()  # bench execute commits too; a console run should not lose the work
    return company


def run_setup_wizard(company, gstin):
    """ERPNext's own setup (fiscal year, the company with India's standard chart of accounts, the default masters),
    with India Compliance's stage (the audit trail on, the GST accounts and templates, the company GSTIN)."""
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    today = getdate()
    start = today.year if today.month >= 4 else today.year - 1
    result = setup_complete(
        {
            "language": "English",
            "country": "India",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "company_name": company,
            "company_abbr": conf("examleaf_company_abbr"),
            "chart_of_accounts": "India - Chart of Accounts",
            "fy_start_date": f"{start}-04-01",
            "fy_end_date": f"{start + 1}-03-31",
            "bank_account": conf("examleaf_bank_account"),
            "company_gstin": gstin,
            "default_gst_rate": "18.0",  # India Compliance takes its rates as "18.0"
            "enable_audit_trail": 1,
            "enable_telemetry": 0,
            "setup_demo": 0,
        }
    )
    if (result or {}).get("status") != "ok":
        frappe.throw(_("ERPNext's setup did not finish: {0}").format(result))
    frappe.clear_cache()


def ensure_company_details(company, gstin):
    """The company's GSTIN and its address (with the GSTIN: India Compliance reads the company GSTIN of an invoice from
    the company address)."""
    doc = frappe.get_doc("Company", company)
    if doc.gstin != gstin:
        doc.gstin = gstin
        doc.save(ignore_permissions=True)
    if frappe.db.exists("Address", {"examleaf_ref": "company:address"}):
        return
    address = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": company,
            "address_type": "Billing",
            "address_line1": frappe.conf.get("examleaf_address_line1") or "[address line 1]",
            "address_line2": frappe.conf.get("examleaf_address_line2"),
            "city": frappe.conf.get("examleaf_city") or "Guwahati",
            "state": conf("examleaf_state"),
            "pincode": frappe.conf.get("examleaf_pincode") or "781001",
            "country": "India",
            "email_id": real("examleaf_email"),
            "phone": real("examleaf_phone"),
            "gstin": gstin,
            "is_your_company_address": 1,
            "is_primary_address": 1,
            "examleaf_ref": "company:address",
            "links": [{"link_doctype": "Company", "link_name": company}],
        }
    )
    address.insert(ignore_permissions=True)


def ensure_account(company, abbr, name, parent, account_type=None):
    full = f"{name} - {abbr}"
    if not frappe.db.exists("Account", full):
        frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": name,
                "parent_account": f"{parent} - {abbr}",
                "company": company,
                "account_type": account_type,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
    return full


def ensure_accounts(company, abbr):
    """Money between the payment and the bank (research 4.3): Razorpay holds online payments until its settlement, the
    courier holds COD until its remittance. Both are Bank-type, so a Payment Entry can pay into them with a reference."""
    ensure_account(company, abbr, "Razorpay Clearing", "Bank Accounts", "Bank")
    ensure_account(company, abbr, "COD in Transit", "Bank Accounts", "Bank")
    ensure_account(company, abbr, "Payment Gateway Charges", "Indirect Expenses")


def ensure_warehouses(company, abbr):
    for name in WAREHOUSES:
        if not frappe.db.exists("Warehouse", f"{name} - {abbr}"):
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": name,
                    "company": company,
                    "parent_warehouse": f"All Warehouses - {abbr}",
                }
            ).insert(ignore_permissions=True)


def ensure_tax_templates(company, abbr):
    """GST Exempted (books, HSN 4901: Notification 10/2025-CT(R) S.No. 132, research 4.1) and GST 18 % (the course),
    and the HSN master's links to them, so an Item made in ERPNext with that HSN takes the right template."""
    from india_compliance.gst_india.overrides.company import make_default_tax_templates

    taxed = f"GST 18% - {abbr}"
    if not frappe.db.exists("Item Tax Template", taxed):
        make_default_tax_templates(company, 18)
    exempt = f"GST Exempted - {abbr}"
    if not frappe.db.exists("Item Tax Template", exempt):
        accounts = frappe.get_all(
            "Item Tax Template Detail", filters={"parent": taxed}, pluck="tax_type", order_by="idx asc"
        )
        frappe.get_doc(
            {
                "doctype": "Item Tax Template",
                "title": "GST Exempted",
                "company": company,
                "gst_treatment": "Exempted",
                "gst_rate": 0,
                "taxes": [{"tax_type": account, "tax_rate": 0} for account in accounts],
            }
        ).insert(ignore_permissions=True)
    for hsn, template in ((BOOK_HSN, exempt), (COURSE_SAC, taxed)):
        doc = frappe.get_doc("GST HSN Code", hsn)
        if not any(row.item_tax_template == template for row in doc.taxes):
            doc.append("taxes", {"item_tax_template": template})
            doc.save(ignore_permissions=True)


def ensure_shipping_item(company):
    """The delivery charge's line. It carries every GST template of the company so that each invoice line can name
    the one its goods take (ERPNext keeps an explicit template only when the Item lists it)."""
    templates = frappe.get_all(
        "Item Tax Template", filters={"company": company, "disabled": 0, "title": ["like", "GST %"]}, pluck="name"
    )
    if frappe.db.exists("Item", C.SHIPPING_ITEM):
        doc = frappe.get_doc("Item", C.SHIPPING_ITEM)
    else:
        doc = frappe.new_doc("Item")
        doc.update(
            {
                "item_code": C.SHIPPING_ITEM,
                "item_name": "Delivery charge",
                "item_group": "Services" if frappe.db.exists("Item Group", "Services") else C.ROOT_ITEM_GROUP,
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_sales_item": 1,
                "is_purchase_item": 0,
                "gst_hsn_code": BOOK_HSN,
                "description": "Delivery charged with the goods: part of a composite supply, so it takes their HSN and rate.",
            }
        )
    listed = {row.item_tax_template for row in doc.taxes}
    for template in templates:
        if template not in listed:
            doc.append("taxes", {"item_tax_template": template})
    doc.flags.ignore_permissions = True
    doc.save() if not doc.is_new() else doc.insert()


def ensure_b2c_customer():
    if not frappe.db.exists("Customer", C.B2C_CUSTOMER):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": C.B2C_CUSTOMER,
                "customer_type": "Individual",
                "customer_group": C.B2C_GROUP,
                "territory": "India",
                "gst_category": "Unregistered",
            }
        ).insert(ignore_permissions=True)


def set_mode_of_payment_accounts(company):
    """Razorpay pays into Razorpay Clearing, COD into COD in Transit (until the courier remits), the rest into the
    company's bank. The fixture cannot hold these rows: they name the company's accounts."""
    abbr = frappe.get_cached_value("Company", company, "abbr")
    bank = frappe.get_cached_value("Company", company, "default_bank_account")
    targets = {"Razorpay": f"Razorpay Clearing - {abbr}", "COD": f"COD in Transit - {abbr}"}
    for mode in C.MODES_OF_PAYMENT:
        account = targets.get(mode, bank)
        if not (account and frappe.db.exists("Account", account) and frappe.db.exists("Mode of Payment", mode)):
            continue
        doc = frappe.get_doc("Mode of Payment", mode)
        row = next((r for r in doc.accounts if r.company == company), None)
        if row and row.default_account == account:
            continue
        if not row:
            row = doc.append("accounts", {"company": company})
        row.default_account = account
        doc.save(ignore_permissions=True)


def ensure_sync_user():
    """The integration user (research 5.5 SERVICE): role EL Sync only, no password, API keys made by an operator
    (README "The sync user"); restrict_ip from examleaf_sync_user_restrict_ip when set."""
    email = conf("examleaf_sync_user")
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.new_doc("User")
        user.update({"email": email, "first_name": "ERP", "last_name": "sync", "send_welcome_email": 0})
    user.restrict_ip = frappe.conf.get("examleaf_sync_user_restrict_ip") or user.restrict_ip
    user.set("roles", [{"role": C.SYNC_ROLE}])
    user.flags.ignore_permissions = True
    user.flags.no_welcome_mail = True
    user.save() if not user.is_new() else user.insert()


def apply_settings(company, abbr):
    """The settings research-erpnext.md asks for, each with its reason."""
    accounts = frappe.get_doc("Accounts Settings")
    # 4.1: place of supply of a B2C book delivery is where the parcel goes
    accounts.determine_address_tax_category_from = "Shipping Address"
    # 4.1: MCA audit trail (in force since 1 Apr 2023); India Compliance makes it irreversible
    accounts.enable_audit_trail = 1
    accounts.save(ignore_permissions=True)

    gst = frappe.get_doc("GST Settings")
    gst.enable_e_invoice = 0  # 4.1, research-commerce-gst 5.9: e-invoicing applies above ₹5 crore turnover, B2B only
    gst.nil_exempt_e_invoice_treatment = "Do Not Generate"  # 4.1: bills of supply are outside e-invoicing
    gst.enable_e_waybill = 1  # 4.1: kept for any mixed or taxable consignment ...
    gst.e_waybill_threshold = 50000  # ... above ₹50,000; books are exempt (events.apply_e_waybill_exemption)
    gst.validate_hsn_code = 1
    gst.min_hsn_digits = "4"  # Notification 78/2020: 4 digits up to ₹5 crore turnover (research-commerce-gst 5.3)
    gst.flags.ignore_mandatory = True
    gst.save(ignore_permissions=True)

    stock = frappe.get_doc("Stock Settings")
    stock.default_warehouse = f"Main - {abbr}"
    stock.enable_serial_and_batch_no_for_item = 1  # 4.3: one Batch per print run
    stock.pick_serial_and_batch_based_on = "FIFO"
    stock.allow_negative_stock = 0
    stock.save(ignore_permissions=True)

    selling = frappe.get_doc("Selling Settings")
    selling.selling_price_list = "MRP"
    selling.territory = "India"
    selling.save(ignore_permissions=True)

    system = frappe.get_doc("System Settings")
    system.update(
        {
            "session_expiry": "08:00",  # 6.5: the default 170 hours is far too long for staff
            "enable_two_factor_auth": 1,  # 6.5: required for the roles marked so (EL Admin, EL Finance: Role fixture)
            "two_factor_method": "OTP App",
            "login_with_email_link": 0,  # 6.5: on by default, turn it off
            "deny_multiple_sessions": 1,  # 6.5
            "enable_password_policy": 1,
            "minimum_password_score": "3",  # 6.5: raise from 2 of 4
            "allow_consecutive_login_attempts": 5,  # 6.5: lockout after 5 (default 10)
            "allow_error_traceback": 0,  # 6.5: tracebacks stay in the Error Log, not on screen
            "rounding_method": "Commercial Rounding",  # the platform rounds halves up (shop.models.rupees)
            "enable_telemetry": 0,
            "otp_issuer_name": "ExamLeaf ERP",
        }
    )
    system.save(ignore_permissions=True)

    frappe.db.set_single_value("Website Settings", "disable_signup", 1)  # 5.4, 6.6: staff only, no portal sign-ups
    configure_google_login()


def configure_google_login():
    """Google Workspace sign-in (research 5.4). sign_ups Deny: only Users made beforehand get in. The hd parameter only
    hints Google's account chooser; the real domain lock is the OAuth client's Internal audience in Google Cloud.
    Enabled once the client id and secret are in the site config; the secret is stored encrypted, never in git."""
    domain = frappe.conf.get("examleaf_google_domain") or "examleaf.in"
    client_id, secret = frappe.conf.get("examleaf_google_client_id"), frappe.conf.get("examleaf_google_client_secret")
    key = frappe.get_doc("Social Login Key", "google") if frappe.db.exists("Social Login Key", "google") else None
    if not key:
        key = frappe.new_doc("Social Login Key")
        key.social_login_provider = "Google"
        key.update(key.get_social_login_provider("Google"))
    data = json.loads(key.auth_url_data or "{}")
    data["hd"] = domain
    key.auth_url_data = json.dumps(data)
    key.sign_ups = "Deny"
    key.enable_social_login = int(bool(client_id and secret))
    if client_id:
        key.client_id = client_id
    if secret:
        key.client_secret = secret
    key.flags.ignore_permissions = True
    key.save() if not key.is_new() else key.insert()
