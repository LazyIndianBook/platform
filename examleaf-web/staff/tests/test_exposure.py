"""OWASP API3, excessive data exposure and mass assignment (plan 5.4 and 9.2; research 1.1's field level):

- every serializer of the staff and public APIs lists its fields (no `__all__`, no `exclude`);
- no answer of any staff endpoint holds a customer's raw email address, mobile number, date of birth or parent's
  contact: each GET of the authorization tables is read with the fixture's customer made whole (a number, a log-in
  number, a date of birth, a parent, a saved address, a nominee, a ticket and an order from their number), and only
  a reveal (a reason, a re-authentication, a sensitive_read) answers one;
- no answer and no audit event holds a secret: an API key, a provider's credentials, a webhook token, SECRET_KEY;
- a write never takes a protected field (a publish flag, a number, a hash, an owner, a verification, a superuser
  flag, an API key's prefix): refused or ignored."""

import json
import re
from datetime import date

import httpx
import pytest
from django.conf import settings
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts import roles
from accounts.models import Nominee, User
from shop.factories import ADDRESS, ProductFactory, make_order, verified_user
from shop.models import Address, Product
from staff.models import ApiKey, AuditEvent, DataRequest, SavedView
from support import services as support

from .conftest import STAFF, make_staff, signed_in
from .test_matrix import objects, rows_with_objects

pytestmark = pytest.mark.django_db


def project_serializers():
    """Every ModelSerializer class of the project's own modules (the URLs import every API module)."""
    import examleaf.urls  # noqa: F401  (every view, so every serializer, imported)

    found, todo = set(), [serializers.ModelSerializer]
    while todo:
        for cls in todo.pop().__subclasses__():
            todo.append(cls)
            if not cls.__module__.startswith(("rest_framework", "drf_spectacular", "dj_rest_auth", "allauth")):
                found.add(cls)
    return found


def test_every_serializer_lists_its_fields():
    found = project_serializers()
    assert len(found) > 150, len(found)
    for cls in found:
        meta = getattr(cls, "Meta", None)
        if meta is None:  # a base of others (insights.api.TitledSerializer): never a serializer of its own
            assert all(hasattr(sub, "Meta") for sub in cls.__subclasses__()), cls
            continue
        assert not hasattr(meta, "exclude"), cls
        assert isinstance(getattr(meta, "fields", None), list | tuple), (cls, getattr(meta, "fields", None))


def text_of(response):
    body = b"".join(response.streaming_content) if response.streaming else response.content
    return body.decode("utf-8", "replace")


def made_whole(made):
    """The matrix's customer with every personal detail plan 5.4 masks, and what hangs on their number: the raw
    values no answer may hold (digits only for the numbers: an answer may space them)."""
    customer = User.objects.get(pk=made["customer"])
    User.objects.filter(pk=customer.pk).update(
        phone="+919811122233", login_phone="+919811122244", date_of_birth=date(1990, 3, 14),
        parent_name="Parent Zz", parent_contact="parent.zz@example.com",
    )  # fmt: skip
    address = {k: v for k, v in ADDRESS.items() if k != "state"} | {"phone": "+919822233344"}
    Address.objects.create(user=customer, **address)
    Nominee.objects.create(user=customer, name="Nominee Zz", contact="nominee.zz@example.com", relation="mother")
    support.create_ticket(source="phone", channel="phone", subject="A call", body="Called about an order",
                          phone="+919833344455", user=customer, category="order")  # fmt: skip
    make_order((ProductFactory(stock=5), 1), user=customer, email=customer.email, phone="+919844455566")
    words = [customer.email, "1990-03-14", "parent.zz@example.com", "nominee.zz@example.com"]
    words += ["rahul@example.com", "o@example.com", "a@example.com"]  # the matrix's order, quote and ticket
    numbers = ["9811122233", "9811122244", "9822233344", "9833344455", "9844455566", "9864012345"]
    return words, numbers


# Answers that hold a whole contact by their nature: a parcel's documents carry its address (the packing room's).
WHOLE = {"/documents/packing-slip/", "/documents/label/", "/label/"}


def test_no_answer_holds_a_customers_raw_contact(subtests):
    made = objects()
    words, numbers = made_whole(made)
    rows = [(method, url) for method, url in rows_with_objects(made) if method == "get"]
    client = signed_in(make_staff(roles.OWNER))
    for _, url in rows:
        if any(url.split("?")[0].endswith(end) for end in WHOLE):
            continue
        text = text_of(client.get(url))
        digits = re.sub(r"\D", "", text)
        with subtests.test(url=url):
            assert not [w for w in words if w in text.lower()] and not [n for n in numbers if n in digits]


def test_a_data_requests_requester_is_masked_and_revealed_with_a_reason():
    made = objects()
    owner, request = make_staff(roles.OWNER), DataRequest.objects.get(pk=made["request"])
    client = signed_in(owner)
    record = client.get(f"{STAFF}data-requests/{request.pk}/").json()
    assert record["requester"] == "••••••2345"  # "98640 12345"
    url = f"{STAFF}data-requests/{request.pk}/reveal/"
    assert client.post(url, {}, format="json").status_code == 400  # say why
    assert signed_in(owner, reauth=False).post(url, {"reason": "Calling back"}, format="json").status_code == 403
    shown = client.post(url, {"reason": "Calling them back about the letter"}, format="json")
    assert shown.status_code == 200 and shown.json() == {"requester": "98640 12345"}
    [event] = AuditEvent.objects.filter(action="sensitive_read", actor_id=owner.pk)
    assert event.details["what"] == "reveal" and event.details["fields"] == ["requester"]
    assert event.reason == "Calling them back about the letter" and "12345" not in json.dumps(event.details)
    support_member = make_staff(roles.AUDITOR)  # reads the queue, reveals nothing
    assert signed_in(support_member).post(url, {"reason": "x"}, format="json").status_code == 403


@pytest.fixture
def providers(monkeypatch):
    """The providers' APIs answered here (a credentials test passes); nothing leaves the test."""
    answer = httpx.MockTransport(lambda request: httpx.Response(200, json={"entity": "collection", "items": []}))
    monkeypatch.setattr("integrations.connections.transport_for", lambda provider: answer)


def test_no_answer_and_no_audit_event_holds_a_secret(providers, subtests):
    owner = make_staff(roles.OWNER)
    client = signed_in(owner)
    keys = {"key_id": "rzp_test_PlantedKey1234", "key_secret": "planted-secret-0000zzzz"}
    body = {"mode": "test", "credentials": keys, "reason": "Planting the keys"}
    assert client.post(f"{STAFF}connections/razorpay/credentials/", body, format="json").status_code == 200
    token = client.post(f"{STAFF}connections/msg91/webhooks/rotate/", {"reason": "Set up"}, format="json").json()
    key = client.post(f"{STAFF}api-keys/", {"name": "Planted", "scopes": ["shop.view_order"]}, format="json").json()
    secrets = [keys["key_secret"], token["token"], key["key"], key["key"].rsplit("_", 1)[-1], settings.SECRET_KEY]
    extra = ["connections/razorpay/", "connections/msg91/", "connections/msg91/webhooks/", f"api-keys/{key['id']}/"]
    rows = [url for method, url in rows_with_objects() if method == "get"] + [STAFF + path for path in extra]
    for url in rows:
        text = text_of(client.get(url))
        with subtests.test(url=url):
            assert not [secret for secret in secrets if secret in text]
    logged = json.dumps([[e.changes, e.details, e.reason, e.target_label] for e in AuditEvent.objects.all()])
    assert not [secret for secret in secrets if secret in logged]
    assert ApiKey.objects.get(pk=key["id"]).secret_hash not in text_of(client.get(f"{STAFF}api-keys/"))


def changed_nothing(before, after, fields):
    return {name: (before[name], after[name]) for name in fields if before[name] != after[name]}


def test_a_write_never_takes_a_protected_field():
    """Each body adds what its serializer must not take; the answer refuses it (400) or ignores it."""
    from content.models import Paper
    from learn.models import Revision
    from support.models import Ticket

    made = objects()
    owner = make_staff(roles.OWNER)  # every permission: the field, not the person, is refused
    client = signed_in(owner)
    other = make_staff(roles.SUPPORT)
    cases = [
        (Paper, made["paper"], "patch", f"content/papers/{made['paper']}/",
         {"title": "A new title", "is_published": False, "is_sample": True, "code": "PHY-X99"},
         ["is_published", "is_sample", "code"]),
        (Ticket, None, "patch", f"support/tickets/{made['ticket']}/",
         {"priority": "high", "number": "SR-2026-999999", "requester_email_hash": "0" * 64, "user": other.pk},
         ["number", "requester_email_hash", "user_id"]),
        (DataRequest, made["request"], "patch", f"data-requests/{made['request']}/",
         {"summary": "A copy of my data", "identity_verified": True, "status": "closed", "outcome": "done"},
         ["identity_verified", "status", "outcome", "verified_by_id"]),
        (SavedView, made["view"], "patch", f"saved-views/{made['view']}/", {"name": "Mine", "owner": owner.pk},
         ["owner_id"]),
        (Revision, made["revision"], "patch", f"course/revisions/{made['revision']}/",
         {"title": "A title", "status": "published", "publish_at": "2026-10-01T00:00:00Z"},
         ["status", "publish_at"]),
    ]  # fmt: skip
    for model, pk, method, path, body, fields in cases:
        rows = model.objects.filter(pk=pk) if pk else model.objects.filter(number=made["ticket"])
        before = rows.values(*fields).get()
        view = SavedView.objects.get(pk=made["view"])
        acting = signed_in(view.owner) if model is SavedView else client
        response = getattr(acting, method)(STAFF + path, body, format="json")
        assert response.status_code in (200, 400), (path, response.status_code, response.content[:200])
        assert not changed_nothing(before, rows.values(*fields).get(), fields), path
    made_key = client.post(f"{STAFF}api-keys/", {"name": "Hm", "scopes": ["shop.view_order"], "prefix": "deadbeef",
                                                  "secret_hash": "0" * 64}, format="json").json()  # fmt: skip
    row = ApiKey.objects.get(pk=made_key["id"])
    assert row.prefix != "deadbeef" and row.secret_hash != "0" * 64
    person = User.objects.get(pk=made["person"])
    grant = {"role": roles.SALES, "reason": "Covering", "is_superuser": True, "is_staff": False}
    client.post(f"{STAFF}people/{person.pk}/roles/", grant, format="json")
    person.refresh_from_db()
    assert not person.is_superuser and person.is_staff
    product = Product.objects.get(slug=made["product"])
    stock = client.patch(f"{STAFF}catalogue/products/{product.slug}/", {"stock": 999}, format="json")
    assert stock.status_code == 400 and Product.objects.get(pk=product.pk).stock == product.stock  # stock/'s
    coupon = client.patch(f"{STAFF}catalogue/coupons/{made['coupon']}/", {"code": "OTHER10", "reason": "x"},
                          format="json")  # fmt: skip
    assert coupon.status_code == 400  # a coupon's code stays: customers hold it


def test_the_publics_writes_never_take_a_protected_field():
    customer = verified_user("rahul@example.com")
    me = APIClient()
    me.force_login(customer)
    me.patch("/api/v1/me/", {"full_name": "Rahul D", "is_staff": True, "is_superuser": True}, format="json")
    customer.refresh_from_db()
    assert not customer.is_staff and not customer.is_superuser and not customer.groups.exists()
    nominee = {"name": "Asha Das", "contact": "asha@example.com", "relation": "mother"}
    me.put("/api/v1/me/nominee/", {**nominee, "verified_at": "2026-01-01T00:00:00Z"}, format="json")
    assert Nominee.objects.get(user=customer).verified_at is None
