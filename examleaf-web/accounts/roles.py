"""Roles are Django groups with model permissions. ROLES is the single source of truth: `sync_roles` makes every group
hold exactly these permissions. Migration 0004 creates the groups; `manage.py bootstrap_roles` must run after every
`migrate` (the Makefile, docker-compose.yml and DEPLOYMENT.md do so), because only then do the permissions of every
app, including apps added later, exist. Edit roles here, not in the admin: bootstrap_roles undoes changes made there."""

from django.db.models import Q

STUDENT, TEACHER, CONTENT_EDITOR, SALES, SUPPORT, ADMIN = (
    "STUDENT",
    "TEACHER",
    "CONTENT_EDITOR",
    "SALES",
    "SUPPORT",
    "ADMIN",
)
STAFF_ROLES = {CONTENT_EDITOR, SALES, SUPPORT, ADMIN}  # members need is_staff to open the admin
ALL = "__all__"


def crud(app, models, actions=("view", "add", "change")):
    return [f"{app}.{action}_{model}" for model in models for action in actions]


ROLES = {
    STUDENT: [],  # every registration; uses the site, not the admin
    TEACHER: [],  # verified teachers (TeacherProfile); site features for teachers come later
    CONTENT_EDITOR: [
        *crud("content", ["book", "paper", "question", "solution"]),
        *crud("content", ["board", "classlevel", "subject"], ["view"]),
        *crud("pages", ["page"], ["view", "change"]),
    ],
    SALES: [  # the shop: catalogue, prices and stock, coupons, shipping rates; orders, shipments and refunds
        "content.view_book",
        *crud("shop", ["product", "coupon", "shippingrate", "shipment"]),
        *crud("shop", ["productimage", "bundleitem"], ["view", "add", "change", "delete"]),
        *crud("shop", ["order"], ["view", "change"]),  # change: the pack / ship / deliver actions
        *crud("shop", ["refund"], ["view", "add"]),  # add: the refund action (Razorpay refund)
        *crud("shop", ["orderitem", "payment", "invoice", "creditnote"], ["view"]),
    ],
    SUPPORT: [  # help students: look up accounts and records, verify teachers, answer data requests
        *crud("accounts", ["user", "consentrecord", "deletionrequest"], ["view"]),
        *crud("accounts", ["teacherprofile"], ["view", "change"]),
        "account.view_emailaddress",  # allauth: is the address confirmed?
        "practice.view_attempt",
        # orders: view only (answer "where is my parcel?"; refunds and shipping are SALES')
        *crud(
            "shop",
            ["order", "orderitem", "payment", "shipment", "refund", "invoice", "creditnote", "product", "address"],
            ["view"],
        ),
    ],
    ADMIN: ALL,
}


def sync_roles(Group, Permission):
    """Create the role groups and set their permissions. Returns the permissions named in ROLES that do not exist
    (yet), e.g. those of an app whose migrations have not run."""
    missing = []
    for name, wanted in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        if wanted == ALL:
            perms = list(Permission.objects.all())
        else:
            query = Q(pk__in=[])
            for perm in wanted:
                app_label, codename = perm.split(".")
                query |= Q(content_type__app_label=app_label, codename=codename)
            perms = list(Permission.objects.filter(query).select_related("content_type"))
            found = {f"{p.content_type.app_label}.{p.codename}" for p in perms}
            missing += [perm for perm in wanted if perm not in found]
        group.permissions.set(perms)
    return missing
