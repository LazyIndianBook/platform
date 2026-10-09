from examleaf_erp.constants import (
    CUSTOMER_GROUPS,
    ITEM_GROUPS,
    MODES_OF_PAYMENT,
    PAYMENT_TERMS,
    PRICE_LISTS,
    PRINT_HEADINGS,
    REF_DOCTYPES,
    TERRITORIES,
)

app_name = "examleaf_erp"
app_title = "ExamLeaf ERP"
app_publisher = "ExamLeaf LLP"
app_description = (
    "ExamLeaf's ERPNext app: GST documents and print formats, the platform's sync API, schools and distributors"
)
app_license = "gpl-3.0"
required_apps = ["erpnext", "india_compliance"]

after_install = "examleaf_erp.setup.after_install"  # tree roots, before the fixtures are imported
after_sync = "examleaf_erp.setup.after_sync"  # install: after the fixtures
after_migrate = "examleaf_erp.setup.after_sync"  # every migrate imports the fixtures again, then this
before_tests = "examleaf_erp.setup.before_tests"

# Fixtures are code: `bench migrate` imports every one of them again (force), so they are changed in git and exported
# with `bench --site <site> export-fixtures --app examleaf_erp`, never edited in Desk (README "Fixtures").
# fixture_auto_order numbers the files in this order, so they import in it (Roles before Role Profiles, ...).
fixture_auto_order = True
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "ExamLeaf ERP"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "ExamLeaf ERP"]]},
    {"dt": "Role", "filters": [["name", "like", "EL %"]]},
    {"dt": "Role Profile", "filters": [["name", "like", "EL %"]]},
    {"dt": "Price List", "filters": [["name", "in", PRICE_LISTS]]},
    {"dt": "Payment Term", "filters": [["name", "in", PAYMENT_TERMS]]},
    {"dt": "Payment Terms Template", "filters": [["name", "in", PAYMENT_TERMS]]},
    {"dt": "Mode of Payment", "filters": [["name", "in", MODES_OF_PAYMENT]]},
    {"dt": "Print Heading", "filters": [["name", "in", list(PRINT_HEADINGS.values())]]},
    {"dt": "Customer Group", "filters": [["name", "in", CUSTOMER_GROUPS]]},
    {"dt": "Territory", "filters": [["name", "in", TERRITORIES]]},
    {"dt": "Item Group", "filters": [["name", "in", ITEM_GROUPS]]},
    {"dt": "Pricing Rule", "filters": [["name", "like", "EL %"]]},
    {
        "dt": "Workflow State",
        "filters": [["name", "in", ["Draft", "Pending Approval", "Approved", "Rejected", "Cancelled"]]],
    },
    {
        "dt": "Workflow Action Master",
        "filters": [["name", "in", ["Submit", "Submit for Approval", "Approve", "Reject", "Revise", "Cancel"]]],
    },
    {"dt": "Workflow", "filters": [["name", "in", ["Quotation Approval", "Distributor Agreement Approval"]]]},
    {"dt": "Webhook", "filters": [["name", "like", "EL %"]]},
    {"dt": "Notification", "filters": [["name", "like", "EL %"]]},
]

_ref = "examleaf_erp.events.validate_examleaf_ref"
doc_events = {
    **{doctype: {"validate": _ref} for doctype in REF_DOCTYPES},
    "Sales Invoice": {
        "before_insert": "examleaf_erp.events.refuse_amendment",
        "validate": [_ref, "examleaf_erp.events.set_document_kind", "examleaf_erp.events.apply_e_waybill_exemption"],
        "before_cancel": "examleaf_erp.events.refuse_cancel",
    },
    "Delivery Note": {"validate": [_ref, "examleaf_erp.events.apply_e_waybill_exemption"]},
    "Quotation": {"validate": [_ref, "examleaf_erp.events.set_quotation_discount"]},
    "Customer": {"validate": [_ref, "examleaf_erp.events.validate_school_fields"]},
}

scheduler_events = {
    "daily": [
        "examleaf_erp.tasks.flag_sor_dispatches",
        "examleaf_erp.tasks.purge_sync_log",
    ],
    "cron": {
        # 02:00 IST, after the platform's late retries: what ERPNext held for yesterday, kept in the Sync Log
        "0 2 * * *": ["examleaf_erp.tasks.snapshot_daily_totals"],
    },
}

# DPDP: what a Personal Data Deletion Request redacts. Only B2B contacts reach ERPNext (B2C invoices carry no name,
# phone or street: research 5.8); frappe's own hooks already cover Contact, Address and Communication. A Customer keeps
# its name (a business on GST invoices kept for 72 months) and loses its primary contact's phone and email.
user_data_fields = [
    {"doctype": "Customer", "filter_by": "email_id", "redact_fields": ["mobile_no"]},
    # upsert_b2b_customer's requests in the Sync Log carry the contact's name and email: replaced in every row
    {"doctype": "ExamLeaf Sync Log", "strict": True},
]

jinja = {
    "methods": [
        "examleaf_erp.printing.statement_of_account",
        "examleaf_erp.printing.challan_purpose",
        "examleaf_erp.printing.challan_batches",
        "examleaf_erp.printing.invoice_lines",
        "examleaf_erp.printing.einvoice_qr",
    ],
}
