"""Notes on records and the policies' acknowledgements (plan 7.1; research 6): a note only on a record its writer and
reader may see, its body never in the audit log; each policy's version acknowledged once, the manifest listing what
is due."""

import pytest

from accounts import roles
from api.tests import student
from shop.factories import ProductFactory, make_order
from staff.models import Note, PolicyAcknowledgement

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
NOTES = STAFF + "notes/"


def test_a_note_lives_on_a_record_its_writer_and_readers_may_see_and_never_in_the_log():
    customer = student()
    support = signed_in(make_staff(roles.SUPPORT))
    target = {"target_type": "accounts.user", "target_id": str(customer.pk)}
    body = "Called about the empty cart: the browser's cookies were off."
    first = support.post(NOTES, {**target, "body": body}, format="json")
    assert first.status_code == 201 and first.json()["body"] == body
    support.post(NOTES, {**target, "body": "Mind the class: 11, not 12.", "pinned": True}, format="json")
    listed = support.get(NOTES, target).json()
    assert [note["pinned"] for note in listed] == [True, False] and listed[1]["body"] == body  # pinned first
    event = events("note.created").first()
    assert (event.target_type, event.target_id, event.target_label) == ("accounts.user", str(customer.pk),
                                                                       f"User #{customer.pk}")  # fmt: skip
    assert body not in str(event.details) and set(event.details) == {"note", "pinned"}
    editor = signed_in(make_staff(roles.CONTENT_EDITOR))  # notes, but not the customers
    assert editor.get(NOTES, target).status_code == 404
    assert editor.post(NOTES, {**target, "body": "x"}, format="json").status_code == 404
    assert signed_in(make_staff(roles.PACKER)).get(NOTES, target).status_code == 403  # no notes at all
    assert support.get(NOTES, {"target_type": "accounts.user", "target_id": "999999"}).status_code == 404
    assert support.get(NOTES, {"target_type": "nothing.here", "target_id": "1"}).status_code == 400
    assert support.get(NOTES).status_code == 400  # a record's notes: say which


def test_a_note_on_an_order_out_of_a_scope_is_not_found(rzp):
    order = make_order((ProductFactory(), 1))  # pending: out of a packer's or a scoped reader's reach
    sales = signed_in(make_staff(roles.SALES))
    target = {"target_type": "shop.order", "target_id": str(order.pk)}
    assert sales.post(NOTES, {**target, "body": "Phone order: pays by UPI"}, format="json").status_code == 201
    note = Note.objects.get()
    assert (note.target_type, note.target_id) == ("shop.order", str(order.pk))
    assert events("note.created").get().target_label == order.number
    from staff.models import StaffScope

    scoped_sales = make_staff(roles.SALES)
    StaffScope.objects.create(user=scoped_sales, kind="order_status", value="shipped")
    assert signed_in(scoped_sales).get(NOTES, target).status_code == 404


def test_each_policy_version_is_acknowledged_once_and_the_manifest_lists_what_is_due(settings):
    settings.STAFF_POLICIES = {"acceptable_use": "2026-10", "childrens_data": "2026-10"}
    person = make_staff(roles.SUPPORT)
    client = signed_in(person)
    due = client.get(STAFF + "session/").json()["policies_due"]
    assert due == [
        {"policy": "acceptable_use", "version": "2026-10"},
        {"policy": "childrens_data", "version": "2026-10"},
    ]
    url = STAFF + "policies/ack/"
    wrong = client.post(url, {"policy": "acceptable_use", "version": "2025-01"}, format="json")
    assert wrong.status_code == 400 and "2026-10" in wrong.json()["version"][0]
    assert client.post(url, {"policy": "secrets", "version": "1"}, format="json").status_code == 400
    assert client.post(url, {"policy": "acceptable_use", "version": "2026-10"}, format="json").status_code == 201
    assert (
        client.post(url, {"policy": "acceptable_use", "version": "2026-10"}, format="json").status_code == 200
    )  # once
    assert PolicyAcknowledgement.objects.get().user == person
    assert events("policy.acknowledged").get().details == {"version": "2026-10"}
    assert client.get(STAFF + "session/").json()["policies_due"] == [{"policy": "childrens_data", "version": "2026-10"}]
    settings.STAFF_POLICIES = {**settings.STAFF_POLICIES, "acceptable_use": "2027-01"}  # a new version: asked again
    assert {row["policy"] for row in client.get(STAFF + "session/").json()["policies_due"]} == {
        "acceptable_use", "childrens_data"}  # fmt: skip
    assert [row["policy"] for row in client.get(url).json()] == ["acceptable_use"]
    other = make_staff(roles.SALES)
    assert client.get(url, {"user": other.pk}).status_code == 403  # someone else's: staff.view_staff
    assert signed_in(make_staff(roles.ADMIN)).get(url, {"user": person.pk}).json()[0]["user"] == person.pk
