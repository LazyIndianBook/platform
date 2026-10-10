"""Roles are Django groups with model permissions. ROLES is the single source of truth: `sync_roles` makes every group
hold exactly these permissions. Migration 0004 creates the groups; after every `migrate` the staff app's post_migrate
receiver syncs them (staff/apps.py), once the permissions of every app exist, and `manage.py bootstrap_roles` does the
same by hand (the Makefile, docker-compose.yml and DEPLOYMENT.md still run it). Edit roles here, not in the admin: the
next sync undoes changes made there.

Next to ROLES: ROLE_LIMITS (numbers on capabilities: a refund cap, a discount %), ROLE_SCOPES (which objects a role
reaches), SOD_CONFLICTS (roles one person may not hold together). staff/catalogue.py labels every permission named
here; staff/README.md explains how to add a permission or a role."""

import logging

from django.db.models import Q

logger = logging.getLogger(__name__)

STUDENT, TEACHER, CONTENT_EDITOR, SALES, SUPPORT, ADMIN = (
    "STUDENT",
    "TEACHER",
    "CONTENT_EDITOR",
    "SALES",
    "SUPPORT",
    "ADMIN",
)
# The Admin Control Panel's roles (docs/examleaf-admin-control-panel-plan.md 4.1). OWNER is the founder's: every
# catalogued permission, through the group. The superuser flag is only on the one or two sealed break-glass accounts
# outside Google sign-in (research-rbac-security.md 1.6): they pass every check, their log-in alerts the owners, and
# every audit event of their sessions is marked break_glass (staff.audit).
OWNER, FINANCE, PACKER, REVIEWER, MARKETING, AUDITOR, SALES_REP = (
    "OWNER",
    "FINANCE",
    "PACKER",
    "REVIEWER",
    "MARKETING",
    "AUDITOR",
    "SALES_REP",
)
STAFF_ROLES = {CONTENT_EDITOR, SALES, SUPPORT, ADMIN, OWNER, FINANCE, PACKER, REVIEWER, MARKETING, AUDITOR, SALES_REP}
# The roles that open the Django admin. The newer ones work through the staff API only, whose querysets are scoped
# (a PACKER sees paid, packed and shipped orders); the admin is not, so it stays closed to them (ops/admin.py).
ADMIN_SITE_ROLES = {CONTENT_EDITOR, SALES, SUPPORT, ADMIN, OWNER}
PRIVILEGED_ROLES = {OWNER, ADMIN, FINANCE, AUDITOR}  # given only with a second person's approval (staff.approvals)
EVERYTHING = "__everything__"  # every catalogued permission: all but SUPERUSER_ONLY's changes (OWNER's)
ALL = "__all__"  # EVERYTHING but OWNER_ONLY and MONEY_APPROVALS (ADMIN's)
VIEW_ALL = "__view_all__"  # every view_ permission (as an item of a role's list)
# Left to superusers; ADMIN may only view them (I7): the periodic tasks (any task, any arguments: an email to anyone, a
# real invoice number used up) and their results, who may do what (groups, permissions), the second factors and
# passkeys, and the Google sign-in apps and accounts.
SUPERUSER_ONLY = ["django_celery_beat", "django_celery_results", "auth", "mfa", "socialaccount"]
# The owners' own, beyond ADMIN's "everything" (plan 4.1): giving roles and making API keys (ADMIN sees both, and
# approves role changes), the owner's override (staff.break_glass), and the audit log (AU-9(4): AUDITOR and OWNER only).
OWNER_ONLY = [
    "staff.assign_role",
    "staff.manage_api_keys",
    "staff.break_glass",
    "staff.view_auditlog",
    "staff.export_auditlog",
]
# Separation of duties (plan 4.1): FINANCE approves money, ADMIN roles and exports, REVIEWER content. So money's
# approvals are FINANCE's and the owners', not ADMIN's.
MONEY_APPROVALS = ["staff.approve_refund", "staff.approve_payment", "staff.approve_discount"]


def crud(app, models, actions=("view", "add", "change")):
    return [f"{app}.{action}_{model}" for model in models for action in actions]


CATALOGUE = [  # the shop's catalogue structure (CONTENT_EDITOR's; SALES sees it)
    *["category", "collection", "collectionitem", "producttype", "attribute", "attributevalue"],
    *["productimage", "bundleitem"],
]
# What every member of staff has in the panel: their inbox and saved views, the approvals they take part in, their
# background jobs (each kind needs its own permission too: staff.jobs), and notes on the records they may see.
INBOX = ["staff.view_inbox", *crud("staff", ["savedview"], ["view", "add", "change", "delete"])]
PANEL = [*INBOX, "staff.view_changerequest", "staff.view_job", "staff.add_job", "staff.view_note", "staff.add_note"]
CONTENT = ["book", "paper", "question", "solution"]
COURSE = ["chapter", "revision", "clip", "flashcard", "quizitem"]
# the content module's queues (content/README.md): the reviews, the reported mistakes and their triage, the deposits
CONTENT_PANEL = [
    *["content.view_reviewtask", "content.view_errorreport", "staff.triage_report", "content.view_legaldeposit"]
]
ORDERS = ["order", "orderitem", "orderdiscount", "ordernote", "payment", "refund", "invoice", "creditnote", "shipment"]
ORDERS += ["returnrequest"]  # Phase B: orders

ROLES = {
    STUDENT: [],  # every registration; uses the site, not the admin
    TEACHER: [],  # verified teachers (TeacherProfile); site features for teachers come later
    CONTENT_EDITOR: [
        *crud("content", CONTENT),
        *crud("content", ["board", "classlevel", "subject"], ["view"]),
        *crud("pages", ["page"], ["view", "change"]),
        # the shop's catalogue (Phase 6 E): products, shelves, collections, product types and attributes, pictures
        *crud("shop", ["product"]),
        *crud("shop", CATALOGUE, ["view", "add", "change", "delete"]),
        "shop.view_slughistory",
        # the revision course's content (learn, Phase 6 D); not its learners' data (entitlements, progress, devices)
        *crud("learn", COURSE, ["view", "add", "change", "delete"]),
        # the panel's content module (content/README.md): drafts go to review, reported mistakes are triaged here,
        # legal deposits recorded; within the person's subjects (StaffScope)
        *CONTENT_PANEL,
        "content.add_legaldeposit",
        # support: the content-error tickets (ROLE_SCOPES), read and noted on, never answered (plan 5.14)
        *["support.view_ticket", "support.note_ticket"],
        "shop.view_hsncode",  # the catalogue (Phase B): a new product's code from the master (FINANCE changes it)
        *PANEL,
    ],
    SALES: [  # the shop: prices and stock, coupons, offers, shipping rates; storefront orders and payments. Packing
        # and shipping are PACKER's (staff.pack_order), approving refunds FINANCE's: SALES asks for them in the panel
        "content.view_book",
        *crud("shop", ["product", "coupon", "shippingrate"]),
        *crud("shop", ["productimage", "bundleitem", "offer"], ["view", "add", "change", "delete"]),
        *crud("shop", ["order"]),  # add: phone and school orders; change: edit, cancel, payment links
        *crud("shop", ["payment"], ["view", "add"]),  # add: a payment received offline (bank transfer, UPI)
        *crud("shop", ["ordernote"]),
        *crud("shop", ["orderitem", "orderdiscount", "invoice", "creditnote", "stockalert", "address"], ["view"]),
        *crud("shop", ["shipment", "refund"], ["view"]),
        *crud("shop", ["review", "quoterequest"], ["view", "change"]),  # approve reviews; quotations
        *crud("shop", [name for name in CATALOGUE if name not in ("productimage", "bundleitem")], ["view"]),
        # the panel: refunds and offline payments within ROLE_LIMITS, above them a ChangeRequest
        *["staff.refund_order", "staff.record_offline_payment", "staff.add_changerequest"],
        # shipping: the parcels, failed deliveries and exceptions (the customer's call), cash on delivery to see
        *["staff.view_parcels", "staff.act_on_exception", "staff.view_cod"],
        "staff.view_insights",  # the reports (plan 5.16 lists SALES among their readers; Phase B: Home and Reports)
        # returns: asked for, decided, received and inspected (plan 5.3; SALES does both halves)
        *["shop.view_returnrequest", "staff.handle_return", "staff.receive_return"],
        # support: the order, payment and school-order tickets (ROLE_SCOPES)
        *["support.view_ticket", "support.note_ticket", "staff.handle_ticket", "support.view_savedreply"],
        # the catalogue (Phase B, plan 5.5): prices (beyond discount_percent FINANCE approves) and stock by hand, a
        # school's single-use coupon codes, a new product's code chosen from the HSN and SAC master
        *["staff.change_price", "staff.set_stock", "shop.view_couponcode", "shop.add_couponcode", "shop.view_hsncode"],
        # the course (learn/staff_api.py): a school order's print run of book codes, made and marked dispatched
        *["staff.make_book_codes", "learn.view_codebatch", "learn.change_codebatch"],
        *PANEL,
    ],
    SUPPORT: [  # help students: look up accounts and records, verify teachers, answer data requests
        *crud("accounts", ["user", "consentrecord", "deletionrequest"], ["view"]),
        *crud("accounts", ["teacherprofile"], ["view", "change"]),
        "account.view_emailaddress",  # allauth: is the address confirmed?
        "ops.view_smslog",  # did the code go? (searched by the whole number; the log keeps no number)
        *crud("ops", ["emailsuppression"], ["view", "delete"]),  # "I get no emails": delete to email it again
        "practice.view_attempt",
        # orders: view only (answer "where is my parcel?"; refunds are asked for below, shipping is PACKER's)
        *crud(
            "shop",
            ["order", "orderitem", "payment", "shipment", "refund", "invoice", "creditnote", "product", "address"],
            ["view"],
        ),
        *crud("shop", ["orderdiscount", "ordernote", "review", "quoterequest", "stockalert"], ["view"]),
        "staff.view_parcels",  # "where is my parcel?": the parcel's timeline and its exceptions (the plan, 5.7)
        *crud("learn", ["entitlement"]),  # a course opened by hand (a lost book code, a school's pupils)
        "learn.view_bookcode",
        "learn.view_codebatch",  # the course's print runs, beside a code looked up (learn/staff_api.py)
        "content.view_errorreport",  # the mistakes readers report: to answer "did you get my report?"
        # the panel: masked contacts revealed with a reason (logged), the account actions, data requests, refunds
        # asked for (within ROLE_LIMITS; above them FINANCE approves), a second factor reset (a second person approves)
        *["staff.reveal_contact", "staff.unlock_user", "staff.resend_verification", "staff.end_user_sessions"],
        *["staff.initiate_password_reset", "staff.reset_user_mfa", "staff.impersonate_user"],
        *["staff.view_datarequest", "staff.handle_data_request", "staff.view_processorrecord"],
        *["staff.refund_order", "staff.add_changerequest"],
        *crud("accounts", ["legalhold", "nominee"], ["view"]),  # legal and privacy: what holds an erasure
        *["shop.view_returnrequest", "staff.handle_return"],  # returns asked for and decided (not received: PACKER)
        # support: every ticket; the saved replies read and inserted (their changes are ADMIN's)
        *["support.view_ticket", "support.note_ticket", "staff.handle_ticket", "support.view_savedreply"],
        *PANEL,
    ],
    ADMIN: ALL,  # but SUPERUSER_ONLY's changes, OWNER_ONLY and MONEY_APPROVALS
    OWNER: EVERYTHING,  # but SUPERUSER_ONLY's changes
    FINANCE: [  # the accountant: money in and out, tax documents, read-only orders and customers
        *crud("shop", ORDERS, ["view"]),
        *crud("shop", ["product", "coupon", "offer", "address"], ["view"]),
        "shop.export_order",
        "accounts.view_user",
        *["staff.refund_order", "staff.approve_refund", "staff.record_offline_payment", "staff.approve_payment"],
        *["staff.approve_discount", "staff.add_changerequest"],
        # the ERPNext sync: watch it and resolve the nightly reconciliation's differences (replaying is ADMIN's)
        *["erp.view_sync", "erp.resolve_difference"],
        *["staff.view_cod", "staff.reconcile_cod", "staff.view_insights"],  # COD remittances; the reports
        "staff.export_report",  # ... as files (Phase B: Home and Reports)
        # tax (shop/staff_tax.py): the HSN and SAC master, the series register, the thresholds and the calendar,
        # cancelling a document, the GSTR-1 export
        *["shop.view_hsncode", "shop.change_hsncode", "shop.view_documentseries", "shop.view_taxthreshold"],
        *["staff.cancel_document", "staff.run_gstr1"],
        *["accounts.view_legalhold", "staff.manage_holds"],  # legal holds: a chargeback, a dispute over money
        "integrations.view_integrationaccount",  # the payment settings: the connections' cards (plan 5.18)
        # Finance (shop/staff_finance.py): Razorpay's settlements and their lines, matched by hand and fetched for a
        # day; B2B links' payments recorded once posted in ERPNext; a stuck payment asked of Razorpay again
        *crud("shop", ["settlement", "settlementline", "invoicepaymentlink"], ["view"]),
        *["staff.reconcile_settlements", "staff.replay_webhook"],
        "staff.change_product_tax",  # the catalogue (Phase B): a product's HSN or SAC code, a bundle's treatment
        *PANEL,
    ],
    PACKER: [  # the packing queue only: the orders to pack and ship (ROLE_SCOPES) and their books; pick, pack, hand
        # over to the courier (staff.pack_order; the shipping app's screens). No customers, payments or approvals
        *crud("shop", ["order", "orderitem", "shipment", "product"], ["view"]),
        *["staff.pack_order", "staff.view_parcels", "staff.book_parcel"],  # booking, labels, pickups, manifests
        *["shop.view_returnrequest", "staff.receive_return"],  # parcels sent back: received and inspected
        *["staff.view_job", "staff.add_job"],  # orders packed or printed in bulk (shop/order_jobs.py), up to bulk_rows
        *INBOX,
    ],
    REVIEWER: [  # senior editors: read content and the course, publish: REVIEWER approves content (scoped by subject)
        *crud("content", CONTENT, ["view"]),
        *crud("learn", COURSE, ["view"]),
        "staff.publish_paper",
        "staff.publish_course",  # the course's revisions approved and published, now or at a time (learn/staff_api.py)
        # approve, publish and roll back drafts, triage reported mistakes, import from the books repository
        *CONTENT_PANEL,
        "staff.import_content",
        *PANEL,
    ],
    MARKETING: [  # coupons and offers (approval above ROLE_LIMITS' discount), reviews
        *crud("shop", ["coupon", "offer"]),
        *crud("shop", ["review"], ["view", "change"]),
        "shop.view_product",
        *["staff.add_changerequest", "staff.view_insights"],  # the insights: aggregates only (insights/README.md)
        "ops.view_messagetemplate",  # the message templates (ADMIN changes them)
        # the catalogue (Phase B): a school's single-use coupon codes; the shelves and collections an offer covers
        *["shop.view_couponcode", "shop.add_couponcode", "shop.view_category", "shop.view_collection"],
        *PANEL,
    ],
    # read-only; no reveals, no writes; the exports a review needs (the audit log, the grievance register)
    AUDITOR: [
        VIEW_ALL,
        "staff.view_auditlog",
        "staff.export_auditlog",
        "staff.export_grievances",
        "staff.export_report",
    ],
    SALES_REP: [  # school and phone orders, quotations, payment links; no refunds or shipping (SALES has them)
        "content.view_book",
        *crud("shop", ["order"]),
        *crud("shop", ["product", "coupon", "orderitem", "orderdiscount", "address"], ["view"]),
        *crud("shop", ["ordernote"]),
        *crud("shop", ["quoterequest"], ["view", "change"]),
        "staff.add_changerequest",
        *PANEL,
    ],
}

# What each role is for, in two lines for the role catalogue (staff.api: people/roles/; research 1.8): "for people who
# need to ..." and "they can't ...", per language (English now; "as" and "bn" join with the same keys).
ROLE_CARDS = {
    OWNER: {
        "en": {
            "for": "For the founder: everything, including giving roles, making API keys, the audit log and the "
            "override when nobody else can approve.",
            "cannot": "They can't change the periodic tasks, groups, second factors or sign-in apps: those stay with "
            "the sealed break-glass accounts.",
        }
    },
    ADMIN: {
        "en": {
            "for": "For the operations head: every module of the panel, and approving role changes, exports and "
            "erasures.",
            "cannot": "They can't give roles or make API keys (they see both), approve money, or read the audit log.",
        }
    },
    FINANCE: {
        "en": {
            "for": "For the accountant: payments, refunds and their approval, offline payments, Razorpay's "
            "settlements, invoices, cash on delivery and the ERPNext reconciliation.",
            "cannot": "They can't pack or ship orders, change prices or coupons without approval, or manage staff.",
        }
    },
    SALES: {
        "en": {
            "for": "For sales and school orders: storefront orders, payment links, coupons and offers, prices and "
            "stock, quotations.",
            "cannot": "They can't approve refunds (FINANCE does), pack or ship parcels, or read the audit log.",
        }
    },
    SALES_REP: {
        "en": {
            "for": "For school and phone orders: orders, quotations and payment links.",
            "cannot": "They can't refund, ship, change prices or approve anything.",
        }
    },
    PACKER: {
        "en": {
            "for": "For the packing room: the orders to pack, their parcels, labels, pickups and manifests.",
            "cannot": "They can't see customers, payments or anything outside the packing queue.",
        }
    },
    SUPPORT: {
        "en": {
            "for": "For support agents: customers (masked, revealed with a reason), account help, data requests, "
            "and refunds asked for.",
            "cannot": "They can't approve refunds or erasures, change settings, or read the audit log.",
        }
    },
    CONTENT_EDITOR: {
        "en": {
            "for": "For authors and editors: books, papers, questions, solutions, legal pages and the course's "
            "content.",
            "cannot": "They can't publish papers (REVIEWER does), or see customers, orders or money.",
        }
    },
    REVIEWER: {
        "en": {
            "for": "For senior editors: reading content and the course, and publishing papers.",
            "cannot": "They can't see customers, orders or money, or change the shop.",
        }
    },
    MARKETING: {
        "en": {
            "for": "For marketing: coupons and offers (large discounts approved by FINANCE), reviews, the insights "
            "and the message templates.",
            "cannot": "They can't approve their own discounts, see customers' details, or also hold FINANCE.",
        }
    },
    AUDITOR: {
        "en": {
            "for": "For an accountant or a lawyer who reviews: everything read-only, the audit log and its export.",
            "cannot": "They can't change anything, reveal customers' details, or hold any other role.",
        }
    },
}

# Numbers on capabilities (research 1.4): a refund up to `refund_inr` rupees, an offline payment up to `offline_inr`,
# a price or coupon up to `discount_percent` off, an export of `export_rows` rows and a bulk action on `bulk_rows` go
# through at once; above them a ChangeRequest waits for a second person (staff.approvals). None: no limit. A person's
# limit is the highest of their roles'; a role not listed has 0. Placeholders: the owner sets them (research 8.6).
ROLE_LIMITS = {
    OWNER: dict.fromkeys(["refund_inr", "offline_inr", "discount_percent", "export_rows", "bulk_rows"]),
    ADMIN: {
        "refund_inr": 10_000,
        "offline_inr": 50_000,
        "discount_percent": 50,
        "export_rows": 10_000,
        "bulk_rows": 1_000,
    },
    FINANCE: {
        "refund_inr": 10_000,
        "offline_inr": 50_000,
        "discount_percent": 50,
        "export_rows": 10_000,
        "bulk_rows": 500,
    },
    SALES: {"refund_inr": 2_000, "offline_inr": 5_000, "discount_percent": 20, "export_rows": 500, "bulk_rows": 100},
    SALES_REP: {"refund_inr": 0, "offline_inr": 0, "discount_percent": 10, "export_rows": 200, "bulk_rows": 50},
    SUPPORT: {"refund_inr": 1_000, "offline_inr": 0, "discount_percent": 0, "export_rows": 100, "bulk_rows": 50},
    MARKETING: {"refund_inr": 0, "offline_inr": 0, "discount_percent": 20, "export_rows": 0, "bulk_rows": 100},
    AUDITOR: {"refund_inr": 0, "offline_inr": 0, "discount_percent": 0, "export_rows": 5_000, "bulk_rows": 0},
    PACKER: {"refund_inr": 0, "offline_inr": 0, "discount_percent": 0, "export_rows": 0, "bulk_rows": 100},
    # the course's quiz bank: its metadata edited in bulk (learn/staff_api.py)
    CONTENT_EDITOR: {"refund_inr": 0, "offline_inr": 0, "discount_percent": 0, "export_rows": 0, "bulk_rows": 200},
}
LIMITS = ["refund_inr", "offline_inr", "discount_percent", "export_rows", "bulk_rows"]

# Which objects a role reaches, by scope kind (staff.backends): a PACKER's orders are those to pack and on their way.
# A permission held only through scoped roles is narrowed to their values; StaffScope rows narrow one person further.
# "placed" is no status: a cash-on-delivery order placed and not yet paid (its status pending), which is to be packed
# like a paid one (staff.backends.PLACED).
ROLE_SCOPES = {
    PACKER: {"order_status": ["paid", "packed", "shipped", "placed"]},
    # support (plan 5.14): SALES answers the tickets about orders, CONTENT_EDITOR notes on the content errors
    SALES: {"ticket_category": ["order", "payment", "school_order"]},
    CONTENT_EDITOR: {"ticket_category": ["content_error"]},
}

# Static separation of duties (NIST RBAC SSD, research 1.2): roles one person may not hold together. The panel's role
# grant refuses them (staff.services.grant_role); sync_roles warns about anyone who holds a pair (given in the admin).
SOD_CONFLICTS = [
    (FINANCE, PACKER),  # marking an order paid, then shipping it
    (MARKETING, FINANCE),  # making a coupon, then approving its discount
    *[(AUDITOR, role) for role in sorted(STAFF_ROLES - {AUDITOR})],  # the auditor writes nothing
]


def conflicts(roles):
    """The SOD_CONFLICTS pairs within a set of role names."""
    return [(a, b) for a, b in SOD_CONFLICTS if a in roles and b in roles]


def limit(role_names, name):
    """A person's limit `name` (ROLE_LIMITS): the highest of their roles', None for no limit, 0 without one."""
    values = [ROLE_LIMITS[role].get(name, 0) for role in role_names if role in ROLE_LIMITS]
    if any(value is None for value in values):
        return None
    return max(values, default=0)


def role_permissions(name, Permission):
    """The Permission rows of role `name`, and the permission names in ROLES that do not exist (yet)."""
    wanted = ROLES[name]
    if wanted in (EVERYTHING, ALL):
        left_out = Q(content_type__app_label__in=SUPERUSER_ONLY) & ~Q(codename__startswith="view_")
        for perm in [*OWNER_ONLY, *MONEY_APPROVALS] if wanted == ALL else []:
            app_label, codename = perm.split(".")
            left_out |= Q(content_type__app_label=app_label, codename=codename)
        return list(Permission.objects.exclude(left_out)), []
    query = Q(codename__startswith="view_") if VIEW_ALL in wanted else Q(pk__in=[])
    named = [perm for perm in wanted if perm != VIEW_ALL]
    for perm in named:
        app_label, codename = perm.split(".")
        query |= Q(content_type__app_label=app_label, codename=codename)
    perms = list(Permission.objects.filter(query).select_related("content_type"))
    found = {f"{p.content_type.app_label}.{p.codename}" for p in perms}
    return perms, [perm for perm in named if perm not in found]


def sync_roles(Group, Permission):
    """Create the role groups and set their permissions. Returns the permissions named in ROLES that do not exist
    (yet), e.g. those of an app whose migrations have not run. Logs a warning for each member holding two roles that
    SOD_CONFLICTS keeps apart (given in the admin, or before the rule): the owner takes one away."""
    missing = []
    for name in ROLES:
        group, _ = Group.objects.get_or_create(name=name)
        perms, absent = role_permissions(name, Permission)
        missing += absent
        group.permissions.set(perms)
    paired = {name for pair in SOD_CONFLICTS for name in pair}  # staff roles: few members (never STUDENT's)
    members = {
        group.name: set(group.user_set.values_list("pk", flat=True)) for group in Group.objects.filter(name__in=paired)
    }
    for a, b in SOD_CONFLICTS:
        for pk in sorted(members.get(a, set()) & members.get(b, set())):
            logger.warning("Separation of duties: user #%s holds both %s and %s", pk, a, b)
    return missing
