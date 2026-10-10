"""The access log (plan 9.2's exit criteria; research 4.3 and 5): every lookup of a person by what staff typed (an email
address, a mobile number, a name) is one `customer.lookup` event with the query's keyed hash and the count found,
whichever list's search box it was typed in; and every view of a child's record (the customer record, its timeline and
spending, a minor's order, ticket, learner page and nominee) is a `sensitive_read` with `child: true`. Neither keeps
the query nor the child's details."""

from datetime import date

import pytest

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import Nominee
from shop.factories import ProductFactory, make_order
from staff.audit import mask

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
EMAIL, PHONE, NAME = "riya.das@example.com", "98640 12345", "Riya Das"


@pytest.fixture
def child(commit):
    """A student of 15 with an order, a ticket and a nominee."""
    from support.tests.conftest import make_ticket

    today = date.today()
    born = today.replace(year=today.year - 15)
    riya = UserFactory(email=EMAIL, full_name=NAME, phone="+919864012345", parent_name="Asha Das",
                       parent_contact="asha@example.com", date_of_birth=born)  # fmt: skip
    order = make_order((ProductFactory(stock=5), 1), user=riya, email=EMAIL)
    with commit():
        ticket = make_ticket(user=riya, email=EMAIL, category="order")
    Nominee.objects.create(user=riya, name="Asha Das", contact="asha@example.com", relation="mother")
    return {"child": riya.pk, "order": order.number, "ticket": ticket.number}


LOOKUPS = [  # (the list's search, what it is taken for, the list the event names)
    ("users/?q={email}", "email", "users"),
    ("users/?q={phone}", "phone", "users"),
    ("users/?q={name}", "name", "users"),
    ("users/?kind=guests&q={email}", "email", "guests"),
    ("orders/?q={email}", "email", "orders"),
    ("orders/?q={phone}", "phone", "orders"),
    ("orders/?q={name}", "name", "orders"),
    ("support/tickets/?q={email}", "email", "tickets"),
    ("support/tickets/?q={phone}", "phone", "tickets"),
    ("course/entitlements/?q={email}", "email", "entitlements"),
]


@pytest.mark.parametrize(("path", "kind", "source"), LOOKUPS, ids=[path for path, _, _ in LOOKUPS])
def test_every_lookup_of_a_person_is_one_customer_lookup_with_the_querys_hash(child, path, kind, source):
    owner = make_staff(roles.OWNER)
    response = signed_in(owner).get(STAFF + path.format(email=EMAIL.upper(), phone=PHONE, name=NAME))
    assert response.status_code == 200, response.content[:200]
    [event] = events("customer.lookup", actor_id=owner.pk)
    assert (event.details["kind"], event.details["list"]) == (kind, source)
    assert event.details["query"].startswith("hash:") and isinstance(event.details["found"], int)
    if kind == "email":  # comparable across the lists: one helper's keyed hash of the address in lower case
        assert event.details["query"] == mask(EMAIL, "contact")
    kept = str([event.details, event.target_label, event.reason, event.changes]).lower()
    assert not any(word in kept for word in ["riya", "12345", "example.com"])


VIEWS = [  # (a view of the child's record, what the event says it opened)
    ("users/{child}/", "record"),
    ("users/{child}/timeline/", "timeline"),
    ("users/{child}/commerce/", "commerce"),
    ("orders/{order}/", "order"),
    ("support/tickets/{ticket}/", "ticket"),
    ("course/learners/{child}/", "learner"),
    ("privacy/nominees/{child}/", "nominee"),
]


@pytest.mark.parametrize(("path", "what"), VIEWS, ids=[path for path, _ in VIEWS])
def test_every_view_of_a_childs_record_is_a_sensitive_read_marked_child(child, path, what):
    owner = make_staff(roles.OWNER)
    assert signed_in(owner).get(STAFF + path.format(**child)).status_code == 200
    [event] = events("sensitive_read", actor_id=owner.pk)
    assert event.details["what"] == what and event.details["child"] is True
    kept = str([event.details, event.target_label, event.reason]).lower()
    assert "riya" not in kept and "asha" not in kept and EMAIL not in kept
