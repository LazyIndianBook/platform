"""The permission catalogue: for every permission a role or a staff endpoint names, a label for the panel, an area, a
risk, and what the risk triggers. One rule everywhere (research 1.4): high and critical permissions need a recent
re-authentication (allauth's 5 minutes), critical ones alert the owners, and those marked `approval` may wait for a
second person (staff.approvals). Django's own verbs (view, add, change, delete) of any model are catalogued by rule,
but the changes accounts.roles.SUPERUSER_ONLY keeps for the break-glass accounts; every other permission must be
listed here (staff/tests/test_catalogue.py). OWNER holds every catalogued permission."""

from dataclasses import dataclass

from accounts.roles import SUPERUSER_ONLY

LOW, MEDIUM, HIGH, CRITICAL = "low", "medium", "high", "critical"
RISKS = [LOW, MEDIUM, HIGH, CRITICAL]

ORDERS, PAYMENTS, CUSTOMERS, CONTENT, COURSE = "Orders", "Payments & refunds", "Customers", "Content", "Course"
CATALOGUE, MARKETING, STAFF, AUDIT = "Catalogue", "Marketing", "Staff & roles", "Audit"
PRIVACY, SETTINGS, OPERATIONS, ERP_SYNC = "Privacy", "Settings", "Operations", "ERP sync"
SHIPPING, REPORTS, TAX, SUPPORT = "Shipping", "Reports", "Tax", "Support"


@dataclass(frozen=True)
class Capability:
    perm: str
    label: str
    area: str
    risk: str
    approval: bool = False  # the action may wait for a second person's approval
    alert: bool = False

    @property
    def reauth(self):
        return self.risk in (HIGH, CRITICAL)

    @property
    def alerts(self):
        return self.alert or self.risk == CRITICAL

    def as_dict(self):
        return {
            "perm": self.perm,
            "label": self.label,
            "area": self.area,
            "risk": self.risk,
            "reauth": self.reauth,
            "approval": self.approval,
            "alert": self.alerts,
        }


def _entries(app, rows):
    return {f"{app}.{codename}": Capability(f"{app}.{codename}", *row) for codename, *row in rows}


# The staff app's permissions: the action permissions (staff.models.StaffPermissions) and its models' own.
STAFF_ACTIONS = [
    ("refund_order", "Refund orders (above your limit a second person approves)", PAYMENTS, HIGH, True),
    ("approve_refund", "Approve refunds above the maker's limit", PAYMENTS, HIGH),
    (
        "record_offline_payment",
        "Record payments received offline (above a value a second person approves)",
        PAYMENTS,
        HIGH,
        True,
    ),
    ("approve_payment", "Approve offline payments above the limit", PAYMENTS, HIGH),
    ("approve_discount", "Approve prices and coupons beyond the discount limit", MARKETING, HIGH),
    ("pack_order", "Pack orders, hand them to the courier and mark them delivered", ORDERS, MEDIUM),
    ("publish_paper", "Publish and unpublish papers", CONTENT, MEDIUM),
    ("reveal_contact", "Reveal a customer's masked details, with a reason (logged)", CUSTOMERS, HIGH),
    ("suspend_user", "Suspend and reactivate customer accounts", CUSTOMERS, HIGH),
    ("unlock_user", "Lift a customer's log-in lock-out", CUSTOMERS, LOW),
    ("resend_verification", "Send a parent's consent link again", CUSTOMERS, LOW),
    ("end_user_sessions", "Sign a customer out of every device", CUSTOMERS, MEDIUM),
    ("initiate_password_reset", "Email a customer a link to set a new password", CUSTOMERS, MEDIUM),
    ("reset_user_mfa", "Reset a second factor (a second person approves)", CUSTOMERS, HIGH, True),
    ("impersonate_user", "Log in as a customer for 15 minutes, with a reason", CUSTOMERS, CRITICAL),
    ("export_personal_data", "Send a person their data for an access request", PRIVACY, HIGH),
    ("handle_data_request", "Handle data requests: access, correction, erasure, grievances", PRIVACY, MEDIUM, True),
    ("approve_erasure", "Approve an erasure started by staff", PRIVACY, HIGH),
    ("manage_incident", "Keep the breach register: incidents and their reports", PRIVACY, HIGH, False, True),
    ("view_staff", "See staff, their roles, scopes and the access review", STAFF, LOW),
    ("assign_role", "Invite staff; give and take away roles and scopes", STAFF, HIGH, True),
    ("approve_role_change", "Approve privileged roles and staff second-factor resets", STAFF, CRITICAL),
    ("manage_api_keys", "Create and revoke API keys", STAFF, CRITICAL),
    ("break_glass", "Approve your own request when nobody else can (a reason; the owners are told)", STAFF, CRITICAL),
    ("view_auditlog", "Read the audit log (each read is logged)", AUDIT, MEDIUM),
    ("export_auditlog", "Export the audit log", AUDIT, HIGH, True),
    ("approve_export", "Approve large exports and bulk actions", AUDIT, HIGH),
    ("manage_settings", "Change the site's settings: shop open, cash on delivery, consent mode", SETTINGS, HIGH),
    ("manage_flags", "Switch feature flags", SETTINGS, HIGH),
    ("toggle_maintenance", "Switch maintenance mode and its banner", SETTINGS, CRITICAL),
    ("view_system", "See the system: health, queues, webhooks, mail and SMS, backups", OPERATIONS, LOW),
    (
        "replay_webhook",
        "Replay webhooks and dead letters; ask Razorpay again what became of a payment",
        OPERATIONS,
        MEDIUM,
    ),
    ("view_inbox", "Use the inbox of things that wait", OPERATIONS, LOW),
    # the shipping app's staff API (shipping/api.py) and the insights' (insights/api.py)
    ("view_parcels", "See parcels, their timelines and exceptions, and the pickup addresses", SHIPPING, LOW),
    ("book_parcel", "Book parcels: quotes, labels, pickups, manifests, cancellations", SHIPPING, MEDIUM),
    ("act_on_exception", "Act on failed deliveries and resolve parcel exceptions", SHIPPING, MEDIUM),
    ("view_cod", "See cash-on-delivery remittances and the courier's charges", PAYMENTS, LOW),
    ("reconcile_cod", "Match cash-on-delivery remittances with the bank's credits", PAYMENTS, MEDIUM),
    ("manage_pickup_locations", "Add and change the pickup addresses", SHIPPING, MEDIUM),
    ("view_insights", "See the insights: forecasts, print runs, item analysis, cohorts, fraud signals", REPORTS, LOW),
    ("acknowledge_signal", "Acknowledge fraud signals (looked at and handled)", REPORTS, LOW),
    # Tax (shop/staff_tax.py): cancelling an invoice or a credit note (it keeps its number), the GSTR-1 export job
    ("cancel_document", "Cancel an invoice or a credit note (it keeps its number)", TAX, HIGH),
    ("run_gstr1", "Run the month's GSTR-1 export (the accountant's files)", TAX, HIGH),  # an export: re-authenticated
    # Legal and privacy (Phase B, staff/privacy_api.py): legal holds, and the compliance duties
    ("manage_holds", "Put legal holds on a person or a record, and release them", PRIVACY, HIGH),
    ("manage_compliance", "Keep the compliance duties: the dark-pattern self-audit and its certificate", PRIVACY, HIGH),
    # Orders (shop/staff_orders.py): returns, asked for and decided apart from the parcel's receipt and inspection
    (
        "handle_return",
        "Handle returns: ask for one for a customer, approve or decline it, send its label",
        ORDERS,
        MEDIUM,
    ),
    ("receive_return", "Receive returned parcels and inspect them: back into stock, or damaged", ORDERS, MEDIUM),
    # Phase B: staff, settings and integrations, system (the connections page, the system's pages)
    (
        "manage_connections",
        "Test and switch the connections: credentials, webhook tokens, circuits, test and live (the owners are told)",
        SETTINGS,
        HIGH,
        False,
        True,
    ),
    ("manage_system", "Record restore drills and act on the system's pages", OPERATIONS, HIGH),
    # Content (Phase B): the triage of reported mistakes and the import from the books repository (content/README.md)
    ("triage_report", "Triage reported mistakes: confirm, reject, mark fixed, tell the reporter", CONTENT, MEDIUM),
    ("import_content", "Import papers and solutions from the books repository (a dry run first)", CONTENT, HIGH),
    # support (support/README.md): tickets and the grievance register
    ("handle_ticket", "Handle support tickets: reply, assign, change, move on, close, acknowledge", SUPPORT, MEDIUM),
    ("export_grievances", "Export the grievance register (a dated CSV, no personal data)", SUPPORT, HIGH, True),
    # Finance (shop/staff_finance.py): Razorpay's settlements fetched for a day, their lines matched by hand, a B2B
    # link's payment entry recorded once posted in ERPNext
    (
        "reconcile_settlements",
        "Reconcile Razorpay settlements: fetch a day, match a line by hand, record a B2B payment posted in ERPNext",
        PAYMENTS,
        MEDIUM,
    ),
    # Home and Reports (Phase B, insights/exports.py): any report as a file, with the filters it was read with
    ("export_report", "Export a report as a file (above your limit a second person approves)", REPORTS, HIGH, True),
    # Catalogue (shop/staff_catalogue.py): SALES prices and stock, FINANCE a product's tax (plan 5.5)
    (
        "change_price",
        "Change prices: a product's MRP and selling price (beyond your discount limit a second person approves)",
        CATALOGUE,
        MEDIUM,
        True,
    ),
    ("set_stock", "Set a product's stock by hand, with the reason", CATALOGUE, MEDIUM),
    ("change_product_tax", "Set a product's HSN or SAC code and a bundle's tax treatment", TAX, MEDIUM),
    # Course (learn/staff_api.py): publishing the course's revisions, making a print run's book codes (the owners are
    # told), voiding a code or a whole batch (critical: the owners are told)
    ("publish_course", "Approve and publish the course's revisions, now or at a set time", COURSE, MEDIUM),
    (
        "make_book_codes",
        "Make a print run's book codes and download the printer's file (the owners are told)",
        COURSE,
        HIGH,
        False,
        True,
    ),
    ("void_book_codes", "Void a book code, or every unused code of a batch", COURSE, CRITICAL),
    # Customers (Phase B, staff/customers_api.py): a parent's consent recorded by hand, with the evidence
    (
        "verify_consent",
        "Record a student's parental consent by hand, with a method and where the evidence is (the parent is told)",
        CUSTOMERS,
        HIGH,
    ),
]
STAFF_MODELS = [
    ("view_changerequest", "See the approvals you take part in", STAFF, LOW),
    ("add_changerequest", "Ask for an approval", STAFF, LOW),
    ("view_job", "See your background jobs: exports and bulk actions", OPERATIONS, LOW),
    ("add_job", "Start background jobs (each also needs its own permission)", OPERATIONS, LOW),
    ("view_savedview", "See saved views", SETTINGS, LOW),
    ("add_savedview", "Save views", SETTINGS, LOW),
    ("change_savedview", "Change your saved views", SETTINGS, LOW),
    ("delete_savedview", "Delete your saved views", SETTINGS, LOW),
    ("view_sitesetting", "See the site's settings", SETTINGS, LOW),
    ("view_featureflag", "See feature flags", SETTINGS, LOW),
    ("view_apikey", "See API keys (never their secrets)", STAFF, LOW),
    ("view_staffscope", "See staff scopes", STAFF, LOW),
    ("view_rolegrant", "See role grants and their expiry", STAFF, LOW),
    ("view_staffinvite", "See staff invitations", STAFF, LOW),
    ("view_datarequest", "See data requests", PRIVACY, LOW),
    ("view_incident", "See the breach register", PRIVACY, LOW),
    ("view_note", "See staff notes on the records you can see", OPERATIONS, LOW),
    ("add_note", "Write notes on the records you can see", OPERATIONS, LOW),
    ("view_processorrecord", "See the processor register", PRIVACY, LOW),
    ("add_processorrecord", "Add processors", PRIVACY, MEDIUM),
    ("change_processorrecord", "Change processors", PRIVACY, MEDIUM),
    ("delete_processorrecord", "Delete processors", PRIVACY, HIGH),
    ("view_darkpatternaudit", "See the dark-pattern self-audits and their certificates", PRIVACY, LOW),
    # Phase B: offboarding's checklists, the restore drills, the scripts of the checkout and the console's sign-in
    ("view_staffoffboarding", "See offboarding checklists", STAFF, LOW),
    ("view_restoredrill", "See the backups' restore drills", OPERATIONS, LOW),
    ("view_scriptinventory", "See the scripts the checkout and the console's sign-in load", OPERATIONS, LOW),
]
# Custom permissions of the other apps (Django's verbs are catalogued by rule, below).
OTHERS = {
    **_entries(
        "accounts",
        [
            ("export_user", "Export users (CSV)", CUSTOMERS, HIGH),
            ("export_consentrecord", "Export consent records (CSV)", PRIVACY, HIGH),
        ],
    ),
    **_entries("practice", [("export_attempt", "Export attempts (CSV)", CUSTOMERS, HIGH)]),
    **_entries(
        "shop",
        [
            ("export_product", "Export products", CATALOGUE, HIGH),  # every export: re-authenticated (plan 9.2)
            ("import_product", "Import products", CATALOGUE, HIGH),
            ("export_category", "Export categories", CATALOGUE, HIGH),
            # a coupon's single-use codes, made as a file for a school: money that leaves as a file, as book codes do
            ("add_couponcode", "Make a coupon's single-use codes as a file", MARKETING, HIGH),
            ("import_category", "Import categories", CATALOGUE, HIGH),
            ("export_order", "Export orders", ORDERS, HIGH),
        ],
    ),
    # Support (support/README.md): notes only, a content editor's on content-error tickets
    **_entries("support", [("note_ticket", "Write internal notes on the tickets you can see", SUPPORT, LOW)]),
    # The ERPNext sync (erp/README.md): its outbox, dead letters, reconciliation and initial load
    **_entries(
        "erp",
        [
            (
                "view_sync",
                "See the ERPNext sync: outbox, dead letters, reconciliations, cursors, status",
                ERP_SYNC,
                LOW,
            ),
            ("replay_sync", "Replay or discard the ERPNext sync's dead letters (a reason to discard)", ERP_SYNC, HIGH),
            ("resolve_difference", "Resolve the nightly reconciliation's differences, with a note", ERP_SYNC, MEDIUM),
            (
                "run_initial_load",
                "Run the initial load into ERPNext: the catalogue, past invoices (the owners are told)",
                ERP_SYNC,
                HIGH,
                False,
                True,
            ),
        ],
    ),
}
EXPLICIT = {**_entries("staff", STAFF_ACTIONS), **_entries("staff", STAFF_MODELS), **OTHERS}
# Model permissions that start an action which may need approval (staff.approvals: a coupon or an offer made or
# changed; a price is staff.change_price's, whose row says so).
APPROVAL = {"shop.add_coupon", "shop.change_coupon", "shop.add_offer", "shop.change_offer"}

VERB_RISK = {"view": LOW, "add": MEDIUM, "change": MEDIUM, "delete": HIGH}
APP_AREAS = {
    "accounts": CUSTOMERS,
    "account": CUSTOMERS,
    "practice": CUSTOMERS,
    "content": CONTENT,
    "pages": CONTENT,
    "learn": COURSE,
    "ops": OPERATIONS,
    "staff": STAFF,
    "shop": ORDERS,
    "erp": ERP_SYNC,
    "shipping": SHIPPING,
    "insights": REPORTS,
    "integrations": SETTINGS,
    "support": SUPPORT,
}
SHOP_AREAS = {
    **dict.fromkeys(["payment", "refund", "invoice", "creditnote"], PAYMENTS),
    **dict.fromkeys(["coupon", "couponcode", "offer", "review"], MARKETING),
    **dict.fromkeys(
        ["product", "productimage", "bundleitem", "slughistory", "category", "collection", "collectionitem"], CATALOGUE
    ),
    **dict.fromkeys(["producttype", "attribute", "attributevalue", "shippingrate", "pincode", "stockalert"], CATALOGUE),
    **dict.fromkeys(["hsncode", "hsnrate", "documentseries", "taxthreshold"], TAX),  # Phase B: tax
    **dict.fromkeys(["settlement", "settlementline", "invoicepaymentlink"], PAYMENTS),  # Phase B: finance
}


def entry(perm):
    """The Capability of `app_label.codename`, or None for a permission nobody catalogued (only Django's verbs of a
    model are catalogued by rule: view low, add and change medium, delete high; not the superusers' own)."""
    if perm in EXPLICIT:
        return EXPLICIT[perm]
    app_label, _, codename = perm.partition(".")
    verb, _, model_name = codename.partition("_")
    if verb not in VERB_RISK or not model_name or (app_label in SUPERUSER_ONLY and verb != "view"):
        return None
    from django.apps import apps

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return None
    area = SHOP_AREAS.get(model_name, ORDERS) if app_label == "shop" else APP_AREAS.get(app_label, OPERATIONS)
    label = f"{verb.capitalize()} {model._meta.verbose_name_plural}"
    return Capability(perm, label, area, VERB_RISK[verb], approval=perm in APPROVAL)


def risk(perm):
    found = entry(perm)
    return found.risk if found else CRITICAL  # not catalogued: treated as the riskiest (deny by default elsewhere)


def needs_reauth(perm):
    return risk(perm) in (HIGH, CRITICAL)
