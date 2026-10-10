"""OWASP API1, broken object-level authorization: an object out of a person's reach is 404, never the object.

Staff: every endpoint of the authorization tables that takes an object (each row's first placeholder names it; a row
that writes its object in the path, a setting's key say, is named by LITERALS), asked by a member of staff who holds
every permission (an OWNER) but whose StaffScope rows reach no fixture: another subject, order status, ticket category,
school and inbox queue (scoped() and ScopeBackend narrow an owner's rows as anyone's; only break-glass accounts and API
keys are not narrowed). A person's own objects (a job, a saved view, a session) are asked by another member of staff.
The objects no scope narrows are listed with why: the permission is their whole rule, which the matrix tests. A table
covers every object route of the walk, as the matrix's does for every route.

Customers: another customer's order (and its return, cancellation, payment, invoice and credit note), address and
attempt are 404 to a customer; their lists, their tickets ("My requests") and their nominee are never another's."""

import re
from collections import defaultdict

import pytest
from django.urls import resolve

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import Nominee
from erp.tests.test_matrix import ENDPOINTS as ERP_ENDPOINTS
from erp.tests.test_matrix import objects as erp_objects
from shop.factories import ProductFactory, make_order, verified_user
from shop.models import Address
from staff.backends import ORDER_STATUS, SCHOOL, SUBJECT, TICKET_CATEGORY, TICKET_QUEUE
from staff.models import StaffScope

from .conftest import STAFF, make_staff, signed_in
from .test_matrix import ANY_STAFF_ENDPOINTS, APP_ENDPOINTS, ENDPOINTS, app_objects, objects

pytestmark = pytest.mark.django_db
TABLES = {"staff": (STAFF, ENDPOINTS, objects), "app": ("/api/v1/", APP_ENDPOINTS, app_objects)}
TABLES["erp"] = (STAFF, ERP_ENDPOINTS, erp_objects)
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# The rows that write their object in the path: the object's kind by the path's start
LITERALS = {
    "settings/": "setting",
    "flags/": "flag",
    "tax/hsn/": "hsn",
    "connections/": "connection",
    "privacy/policies/": "policy",
    "people/me/sessions/": "session",
}
OUT_OF_REACH = {  # a StaffScope value no fixture has, per kind of scope
    SUBJECT: "CHE",
    ORDER_STATUS: "cancelled",
    TICKET_CATEGORY: "content_error",
    SCHOOL: "No such school",
    TICKET_QUEUE: "incident",
}
SCOPED = {  # the objects a scope narrows (staff.backends.MODEL_SCOPES): the kind of scope that does
    **dict.fromkeys(["order", "refund", "document", "payment"], ORDER_STATUS),
    **dict.fromkeys(["parcel", "exception", "remittance", "charge"], ORDER_STATUS),
    "quote": SCHOOL,
    "ticket": TICKET_CATEGORY,
    **dict.fromkeys(["book", "paper", "question", "solution", "review", "report", "deposit"], SUBJECT),
    **dict.fromkeys(["product", "course_subject", "chapter", "revision", "clip", "card", "quiz_item"], SUBJECT),
    **dict.fromkeys(["entitlement", "batch"], SUBJECT),
    "item": TICKET_QUEUE,
}
OWNED = {  # one person's: another member of staff, holding the permission, gets 404 (test_a_persons_own_objects…)
    "job": "its starter's (everyone's to staff.view_system, without the file: list and record)",
    "view": "its owner's, or a role's it is shared with",
    "session": "the member of staff's own (people/me/sessions/)",
}
UNSCOPED = {  # no scope narrows these: who holds the permission reaches every one (the matrix tests the permission)
    "customer": "accounts.user: support works every customer's case; no scope kind narrows accounts",
    "learner": "accounts.user, through the course: as customer",
    "person": "the staff: staff.view_staff and staff.assign_role reach every member (can_manage keeps superusers)",
    "invite": "a staff invitation: as person",
    "key": "an API key: OWNER makes them, ADMIN sees them",
    "change": "an approval: every holder of staff.view_changerequest sees them (payloads name no person's details)",
    "event": "the audit log: AUDITOR and OWNER read all of it",
    "request": "a data request: the privacy desk's (SUPPORT, ADMIN, OWNER) whole queue",
    "erasure": "a data request: as request",
    "deletion": "an account's deletion request: as request",
    "hold": "a legal hold: the privacy desk's and FINANCE's register",
    "incident": "the breach register",
    "processor": "the processor register",
    "audit": "the year's dark-pattern self-audit",
    "back": "a return: the packing room receives every returned parcel, whatever its order's status (the order is "
    "delivered, outside a PACKER's order scope by design)",
    "invoice_link": "a B2B invoice's payment link: ERPNext's invoice, no order behind it",
    "settlement": "a Razorpay settlement: the business's, no order's",
    "coupon": "the catalogue's coupons",
    "offer": "the catalogue's offers",
    "rate": "the shipping rates",
    "category": "the shelves",
    "collection": "the collections",
    "kind": "the product types",
    "template": "the message templates",
    "reply": "the saved replies",
    "inbound": "a provider's event (the connections page)",
    "failure": "a provider's dead letter",
    "erp_failure": "the ERPNext sync's dead letter",
    "pickup": "the pickup addresses",
    "signal": "a fraud signal: aggregates and keyed hashes",
    "row": "the ERPNext outbox",
    "dead": "the ERPNext outbox's dead letters",
    "run": "a nightly reconciliation",
    "difference": "a reconciliation's difference",
    "setting": "a site setting: one per site",
    "flag": "a feature flag: one per site",
    "hsn": "the HSN and SAC master",
    "connection": "a provider's account: one per provider",
    "policy": "a legal page",
}


def object_rows():
    """(table, method, path, kind) of every row whose route takes an object (a parameter besides the version)."""
    found = []
    tables = {**TABLES, "own": (STAFF, ANY_STAFF_ENDPOINTS, objects)}
    for table, (base, endpoints, _) in tables.items():
        for method, path, _ in endpoints:
            match = resolve(base + path.format_map(defaultdict(lambda: "1")).split("?")[0])
            if set(match.kwargs) - {"version"}:
                names = PLACEHOLDER.findall(path)
                literal = next((kind for start, kind in LITERALS.items() if path.startswith(start)), None)
                found.append((table, method, path, names[0] if names else literal))
    return found


ROWS = object_rows()


def named(rows):
    return [f"{method} {path}" for _, method, path, _ in rows]


def test_every_object_route_has_its_rule():
    kinds = {kind for *_, kind in ROWS}
    assert None not in kinds, [row for row in ROWS if row[3] is None]
    ruled = set(SCOPED) | set(OWNED) | set(UNSCOPED)
    assert kinds <= ruled, sorted(kinds - ruled)
    assert ruled <= kinds, sorted(ruled - kinds)  # no rule for an object no route takes any more
    assert not set(SCOPED) & set(UNSCOPED) and not set(OWNED) & (set(SCOPED) | set(UNSCOPED))
    assert len(ROWS) > 250, len(ROWS)


def outsider():
    """An OWNER (every permission) whose scopes reach no fixture."""
    owner = make_staff(roles.OWNER)
    for kind, value in OUT_OF_REACH.items():
        StaffScope.objects.create(user=owner, kind=kind, value=value)
    return owner


SCOPED_ROWS = [row for row in ROWS if row[3] in SCOPED]
REASON = {"reason": "Testing the scope"}
# The actions that read their body before their object: a valid body, so that the answer is the object's (an empty
# one is 400 whatever the object, which says nothing of it but shows nothing of the lookup either)
BODIES = {
    **dict.fromkeys(["tax/documents/{document}/cancel/", "orders/{order}/hold/", "orders/{order}/refunds/"], REASON),
    **dict.fromkeys(["orders/{order}/cancel/", "course/entitlements/{entitlement}/revoke/"], REASON),
    "course/codes/batches/{batch}/void/": REASON,
    "orders/{order}/notify/": {"kind": "placed"},
    "orders/{order}/offline-payment/": {"reference": "UTR123456", **REASON},
    "orders/{order}/returns/": {"lines": [{"item": 1, "quantity": 1}], "reason": "damaged"},
    "orders/{order}/ship/": {"courier": "India Post", "tracking_number": "EA123456789IN"},
    "orders/refunds/{refund}/mark-paid/": {"utr": "UTR123456"},
    "content/reviews/{review}/needs-changes/": {"comment": "A step is missing"},
    **dict.fromkeys(
        ["course/clips/{clip}/move/", "course/cards/{card}/move/", "course/items/{quiz_item}/move/"], {"to": "first"}
    ),  # fmt: skip
    "course/entitlements/{entitlement}/extend/": {"days": 7, **REASON},
    "shipping/shipments/{parcel}/ndr-action/": {"action": "re-attempt", "comments": "Call first"},
    "shipping/exceptions/{exception}/resolve/": {"resolution": "Delivered on the second try"},
    "shipping/cod/{remittance}/reconcile/": {"utr": "UTR123456", "amount": "299.00"},
}


@pytest.mark.parametrize(("table", "method", "path", "kind"), SCOPED_ROWS, ids=named(SCOPED_ROWS))
def test_an_object_out_of_scope_is_404_and_never_the_object(table, method, path, kind):
    base, _, made = TABLES[table]
    values = made()
    body = BODIES.get(path, {})
    response = getattr(signed_in(outsider()), method)(base + path.format(**values), body, format="json")
    assert response.status_code == 404, (response.status_code, response.content[:300])
    assert str(values[kind]) not in response.content.decode().replace(path.format(**values), "")


OWNED_ROWS = [row for row in ROWS if row[3] in OWNED and row[3] != "session"]


@pytest.mark.parametrize(("table", "method", "path", "kind"), OWNED_ROWS, ids=named(OWNED_ROWS))
def test_a_persons_own_objects_are_404_to_another_member_of_staff(table, method, path, kind):
    base, _, made = TABLES[table]
    url = base + path.format(**made())  # (the job and the saved view are a SUPPORT member's)
    other = make_staff(roles.SUPPORT)  # holds staff.view_job and the saved views' permissions, not staff.view_system
    response = getattr(signed_in(other), method)(url, {}, format="json")
    assert response.status_code == 404, (response.status_code, response.content[:300])


def other_version(model):
    def make(values):
        from content.conftest import make_paper

        paper = make_paper(subject="CHE")
        found = {"book": paper.book, "paper": paper, "question": paper.questions.get()}
        found["solution"] = found["question"].solution
        return found[model].history.order_by("-history_id").first().history_id

    return make


def other_attachment(values):
    from support import services as support

    ticket = support.create_ticket(source="email", channel="email", subject="Another", body="Hello",
                                   email="b@example.com", category="order")  # fmt: skip
    message = ticket.messages.get()
    support.save_attachments(message, [("other.png", "image/png", b"\x89PNG")])
    return message.attachments.get().pk


def other_picture(values):
    from shop.factories import picture
    from shop.models import ProductImage

    return ProductImage.objects.create(product=ProductFactory(), image=picture("products/other.png")).pk


def other_attribute(values):
    from shop.models import Attribute, ProductType

    kind = ProductType.objects.create(name="Another type")
    return Attribute.objects.create(product_type=kind, name="Binding", code="binding").pk


def other_device(values):
    from learn.models import Device

    return Device.objects.create(user=UserFactory(), token="fid-other", platform="android").pk


def other_scope(values):
    return StaffScope.objects.create(user=make_staff(roles.SUPPORT), kind="subject", value="MAT").pk


NESTED = {  # a route's second object, another parent's: 404 (the route checks the second belongs to the first)
    **{f"{model}_version": other_version(model) for model in ["book", "paper", "question", "solution"]},
    "attachment": other_attachment,
    "picture": other_picture,
    "attribute": other_attribute,
    "device": other_device,
    "scope": other_scope,
}
NESTED_ROWS = [row for row in ROWS if len(PLACEHOLDER.findall(row[2])) > 1]


def test_every_second_object_has_its_factory():
    assert {PLACEHOLDER.findall(path)[1] for _, _, path, _ in NESTED_ROWS} == set(NESTED)


@pytest.mark.parametrize(("table", "method", "path", "kind"), NESTED_ROWS, ids=named(NESTED_ROWS))
def test_a_second_object_of_another_parent_is_404(table, method, path, kind):
    base, _, made = TABLES[table]
    values = made()
    second = PLACEHOLDER.findall(path)[1]
    values[second] = NESTED[second](values)
    owner = make_staff(roles.OWNER)  # every permission, no scope: only the second object is out of place
    response = getattr(signed_in(owner), method)(base + path.format(**values), {}, format="json")
    assert response.status_code == 404, (response.status_code, response.content[:300])


def test_another_members_session_is_404_and_left_alone():
    from allauth.usersessions.models import UserSession

    mine, theirs = make_staff(roles.SUPPORT), make_staff(roles.SUPPORT)
    client = signed_in(theirs)
    client.get(STAFF + "people/me/sessions/")  # (the session's row)
    session = UserSession.objects.get(user=theirs)
    assert signed_in(mine).post(f"{STAFF}people/me/sessions/{session.pk}/end/").status_code == 404
    assert UserSession.objects.filter(pk=session.pk).exists()
    assert client.get(STAFF + "session/").status_code == 200


def test_a_note_on_a_record_out_of_scope_is_404_both_ways():
    order = make_order((ProductFactory(stock=5), 1))  # pending: out of a "cancelled" order scope
    client = signed_in(outsider())
    params = {"target_type": "shop.order", "target_id": order.pk}
    assert client.get(STAFF + "notes/", params).status_code == 404
    assert client.post(STAFF + "notes/", {**params, "body": "A note"}, format="json").status_code == 404


# Customers


@pytest.fixture
def theirs(commit):
    """Another customer's order, address, attempt, ticket and nominee."""
    from content.conftest import make_paper
    from practice.models import Attempt
    from shop.factories import ADDRESS
    from support.tests.conftest import make_ticket

    anita = verified_user("anita@example.com")
    order = make_order((ProductFactory(stock=5), 1), user=anita, email=anita.email)
    with commit():
        ticket = make_ticket(user=anita, email=anita.email, category="order")
    Nominee.objects.create(user=anita, name="Asha Das", contact="asha@example.com", relation="mother")
    return {
        "order": order.number,
        "address": Address.objects.create(user=anita, **{k: v for k, v in ADDRESS.items() if k != "state"}).pk,
        "attempt": Attempt.objects.create(user=anita, paper=make_paper(), marks_obtained=40).pk,
        "ticket": ticket.number,
    }


CUSTOMER_OBJECTS = [
    *[("get", f"orders/{{order}}/{tail}") for tail in ["", "invoice/", "credit-notes/1/"]],
    *[("post", f"orders/{{order}}/{tail}") for tail in ["cancel/", "returns/", "payment/", "payment/confirm/"]],
    *[(method, "addresses/{address}/") for method in ["get", "put", "patch", "delete"]],
    *[(method, "attempts/{attempt}/") for method in ["get", "put", "patch", "delete"]],
]


@pytest.mark.parametrize(("method", "path"), CUSTOMER_OBJECTS, ids=[f"{m} {p}" for m, p in CUSTOMER_OBJECTS])
def test_another_customers_object_is_404(theirs, method, path):
    me = signed_in(verified_user("rahul@example.com"))
    body = {"lines": [{"product": "x", "quantity": 1}], "reason": "damaged"} if path.endswith("returns/") else {}
    response = getattr(me, method)("/api/v1/" + path.format(**theirs), body, format="json")
    assert response.status_code == 404, (response.status_code, response.content[:300])


def test_the_customer_table_holds_every_route_of_a_customers_own_objects():
    from api.shop import AddressViewSet
    from api.shop import OrderViewSet as CustomerOrders
    from api.views import AttemptViewSet

    from .test_matrix import URLPattern, URLResolver, get_resolver

    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                yield pattern.callback

    owned = (AddressViewSet, CustomerOrders, AttemptViewSet)
    routes = {(cb, method) for cb in walk(get_resolver().url_patterns)
              if getattr(cb, "cls", None) in owned and cb.initkwargs.get("detail")
              for method in cb.actions if method in ("get", "post", "put", "patch", "delete")}  # fmt: skip
    each = defaultdict(lambda: "1")
    tabled = {(resolve("/api/v1/" + path.format_map(each)).func, method) for method, path in CUSTOMER_OBJECTS}
    assert routes == tabled, sorted(str(route) for route in routes ^ tabled)


def test_a_customers_lists_tickets_and_nominee_are_never_anothers(theirs):
    rahul = verified_user("rahul@example.com")
    me = signed_in(rahul)
    for path in ["orders/", "addresses/", "attempts/", "me/tickets/"]:
        rows = me.get("/api/v1/" + path).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        assert rows == [], (path, rows)
    assert me.get("/api/v1/me/nominee/").status_code == 404  # theirs exists; mine does not
    assert me.delete("/api/v1/me/nominee/").status_code == 404
    assert Nominee.objects.filter(user__email="anita@example.com").exists()
    assert UserFactory  # (the factory makes the accounts above through verified_user)
