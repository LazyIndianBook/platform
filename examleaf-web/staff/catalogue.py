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
SHIPPING, REPORTS = "Shipping", "Reports"


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
    ("replay_webhook", "Ask Razorpay again what became of an order's payment", OPERATIONS, MEDIUM),
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
    # Orders (shop/staff_orders.py): returns, asked for and decided apart from the parcel's receipt and inspection
    (
        "handle_return",
        "Handle returns: ask for one for a customer, approve or decline it, send its label",
        ORDERS,
        MEDIUM,
    ),
    ("receive_return", "Receive returned parcels and inspect them: back into stock, or damaged", ORDERS, MEDIUM),
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
            ("export_product", "Export products", CATALOGUE, MEDIUM),
            ("import_product", "Import products", CATALOGUE, HIGH),
            ("export_category", "Export categories", CATALOGUE, LOW),
            ("import_category", "Import categories", CATALOGUE, HIGH),
            ("export_order", "Export orders", ORDERS, HIGH),
        ],
    ),
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
# Model permissions that start an action which may need approval (staff.approvals: a price, a coupon).
APPROVAL = {"shop.change_product", "shop.add_coupon"}

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
}
SHOP_AREAS = {
    **dict.fromkeys(["payment", "refund", "invoice", "creditnote"], PAYMENTS),
    **dict.fromkeys(["coupon", "offer", "review"], MARKETING),
    **dict.fromkeys(
        ["product", "productimage", "bundleitem", "slughistory", "category", "collection", "collectionitem"], CATALOGUE
    ),
    **dict.fromkeys(["producttype", "attribute", "attributevalue", "shippingrate", "pincode", "stockalert"], CATALOGUE),
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
