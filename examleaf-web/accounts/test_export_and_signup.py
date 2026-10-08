"""What Download my data holds beyond the basics (roles, cart, payments, timeline), a sign-up that cannot be used to
find out which email addresses have an account (same answer, and no quicker for an address that has one), what the
deletion of an account leaves in the admin history, and a double click that must not end in a server error (teacher
access: api/test_contract.py)."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import Client

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import DeletionRequest, User
from accounts.views import export_user_data, request_deletion
from api.test_headless import pending
from content.models import Board
from content.tests import make_paper
from practice.models import Attempt
from shop.factories import ADDRESS, CouponFactory, ProductFactory, make_order
from shop.models import Address

pytestmark = pytest.mark.django_db


@pytest.fixture
def student():
    user = UserFactory(email="rahul@example.com")
    Attempt.objects.create(user=user, paper=make_paper(), marks_obtained=52)
    return user


def test_the_export_holds_the_roles_the_cart_and_each_orders_payment_and_timeline():
    user = UserFactory()
    user.groups.add(Group.objects.get(name=roles.STUDENT))
    product = ProductFactory(title="Physics Sample Papers", price=299)
    assert export_user_data(user)["cart"] is None  # nothing kept: nothing exported
    order = make_order((product, 2), user=user, email=user.email, coupon=CouponFactory(code="WELCOME10"))
    data = export_user_data(user)
    assert data["profile"]["roles"] == ["STUDENT"]
    assert data["cart"] == {"coupon": "WELCOME10", "items": [{"title": "Physics Sample Papers", "quantity": 2}]}
    [exported] = data["orders"]
    assert exported["payments"] == [
        {
            "method": "online (UPI, card, net banking)",
            "status": "created",
            "amount": "538.20",
            "razorpay_payment_id": None,
            "created": order.payments.get().created,
        }
    ]
    assert [entry["status"] for entry in exported["timeline"]] == ["ordered"]


def signup(client, email):
    """The website's sign-up (allauth.headless, the browser client)."""
    if not Board.objects.exists():
        make_paper()
    data = {
        **{"full_name": "Rahul Das", "email": email, "password": "Brahmaputra-2027", "class_level": 12},
        **{"board": Board.objects.get().pk, "date_of_birth": "2000-01-01", "consent": True},
    }
    return client.post("/_allauth/browser/v1/auth/signup", data, "application/json")


def test_an_address_that_has_an_account_gets_the_same_answer_and_the_same_hashing_work(client, monkeypatch):
    hashed = []
    monkeypatch.setattr("accounts.signup.make_password", lambda password: hashed.append(password))
    taken = UserFactory(email="taken@example.com")
    EmailAddress.objects.create(user=taken, email=taken.email, verified=True, primary=True)
    new = signup(client, "new@example.com")
    assert hashed == []  # the new account's password is hashed by allauth itself
    again = signup(Client(), "TAKEN@example.com")  # another browser: the first is waiting for its code
    assert (again.status_code, pending(again)) == (new.status_code, pending(new)) == (401, ["verify_email"])
    assert hashed == ["Brahmaputra-2027"]  # an address with an account: no account made, but the time is spent
    assert User.objects.filter(email__iexact="taken@example.com").count() == 1


def test_deleting_an_account_rewrites_the_admin_history_of_its_attempts_and_addresses(student):
    staff = UserFactory(is_staff=True)
    attempt, address = student.attempts.get(), Address.objects.create(user=student, **ADDRESS)
    for obj in (attempt, address):  # staff opened and saved them in the admin: the entry holds the object's text
        LogEntry.objects.log_actions(staff.pk, [obj], CHANGE, change_message="[]")
    assert student.email in str(attempt) and "Rahul Das" in str(address)
    DeletionRequest.objects.create(user=student).complete()
    types = ContentType.objects.get_for_models(Attempt, Address).values()
    texts = " ".join(LogEntry.objects.filter(content_type__in=types).values_list("object_repr", flat=True))
    assert texts.count("deleted") == 2 and not any(word in texts for word in ("rahul", "Rahul", "781001"))


def test_a_double_click_on_delete_my_account_asks_once_and_does_not_crash(client, monkeypatch):
    user = UserFactory()
    client.force_login(user)
    request = client.get("/").wsgi_request
    request.user = user
    first, created = request_deletion(request)
    assert created
    monkeypatch.setattr(User, "pending_deletion", property(lambda self: None))  # the other request had not seen it yet
    second, created = request_deletion(request)
    assert (second, created) == (first, False) and DeletionRequest.objects.filter(user=user).count() == 1
    assert sum("will be deleted" in m.subject for m in mail.outbox) == 1  # one email, from the request that won


