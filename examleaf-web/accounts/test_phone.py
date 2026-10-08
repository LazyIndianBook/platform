"""Log-in by mobile number (allauth's phone method, accounts.adapter): the number is added on My account, confirmed by
an SMS code, and then logs in with the password or a code by SMS; on the website through allauth.headless."""

import re

import pytest
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from django.test import Client

from accounts.factories import PASSWORD, UserFactory
from accounts.forms import axes_username, normalise_phone
from accounts.models import DeletionRequest, User
from accounts.test_security import sign_up
from accounts.tests import BROWSER
from accounts.views import export_user_data
from content.tests import make_paper

pytestmark = pytest.mark.django_db
PHONE = "+919864012345"


def browser(client, path, data):
    return client.post(f"{BROWSER}/{path}", data, content_type="application/json")


def texted_code(capsys):
    return re.findall(r"'otp': '(\d{6})'", capsys.readouterr().out)[-1]


def confirmed(phone=PHONE, **fields):
    user = UserFactory(login_phone=phone, login_phone_verified=True, **fields)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def test_indian_mobile_numbers_are_read_as_people_type_them(rf):
    for typed in ["98640 12345", "098640-12345", "+91 98640 12345", "919864012345", "(98640) 12345"]:
        assert normalise_phone(typed) == PHONE, typed
    for typed in ["12345", "58640 12345", "+1 415 555 0123", "", None]:
        assert normalise_phone(typed) is None, typed
    assert axes_username(rf.post("/"), {"phone": "098640 12345", "password": "x"}) == PHONE


def test_registering_ignores_a_phone_posted(client, capsys):
    make_paper()  # a board
    sign_up(client, parent_contact="anita@example.com", phone="98640 12345")
    assert User.objects.get().login_phone == "" and "SMS" not in capsys.readouterr().out


def test_a_number_added_on_my_account_is_kept_once_its_code_is_confirmed(client, capsys):
    user = UserFactory()
    client.force_login(user)
    browser(client, "auth/reauthenticate", {"password": PASSWORD})  # the password again first
    assert browser(client, "account/phone", {"phone": "98640 12345"}).status_code == 202  # the code's box next
    user.refresh_from_db()
    assert user.login_phone == ""  # not before the code
    assert browser(client, "auth/phone/verify", {"code": texted_code(capsys)}).status_code == 200
    user.refresh_from_db()
    assert (user.login_phone, user.login_phone_verified) == (PHONE, True)
    # the same number again within a minute: words, not a server error
    browser(client, "account/phone", {"phone": "98641 12345"})
    response = browser(client, "account/phone", {"phone": "98641 12345"})
    assert response.status_code == 400 and "wait a minute" in response.text


def test_log_in_by_sms_code_and_by_password_with_the_number_as_typed(client, capsys):
    user = confirmed()
    assert browser(client, "auth/code/request", {"phone": "98640 12345"}).status_code == 401  # on to the code
    browser(client, "auth/code/confirm", {"code": texted_code(capsys)})
    assert client.session["_auth_user_id"] == str(user.pk)
    client.logout()
    browser(client, "auth/login", {"phone": "098640 12345", "password": PASSWORD})
    assert client.session["_auth_user_id"] == str(user.pk)


def test_unknown_numbers_get_the_same_answer_and_no_sms(client, capsys):
    UserFactory(login_phone=PHONE)  # not confirmed: not a log-in number
    response = browser(client, "auth/code/request", {"phone": "98640 12345"})
    assert response.status_code == 401 and "SMS" not in capsys.readouterr().out  # as for a known number
    response = browser(Client(), "auth/code/request", {"phone": "+1 415 555 0123"})
    assert "Enter a 10-digit Indian mobile number." in response.text
    response = browser(Client(), "auth/code/request", {})  # was a server error in allauth
    assert "Enter your email address or your mobile number." in response.text


def test_failed_password_log_ins_are_limited_per_number(client):
    confirmed(), confirmed(phone="+919864099999")
    for _ in range(5):
        browser(client, "auth/login", {"phone": "98640 12345", "password": "wrong-password"})
    response = browser(client, "auth/login", {"phone": "98640 12345", "password": PASSWORD})
    assert "Too many failed login attempts" in response.text
    response = browser(client, "auth/login", {"phone": "98640 99999", "password": "wrong-password"})
    assert "Too many failed login attempts" not in response.text  # not one key for every phone log-in


def test_a_number_belongs_to_one_account_and_goes_with_the_deletion(rf):
    old, new = confirmed(sms_updates=True), UserFactory()
    get_adapter(rf.get("/")).set_phone_verified(new, PHONE)
    old.refresh_from_db()
    assert (old.login_phone, old.login_phone_verified, old.sms_updates) == ("", False, False)
    assert export_user_data(new)["profile"]["login_phone"] == PHONE
    DeletionRequest.objects.create(user=new).complete()
    new.refresh_from_db()
    assert (new.login_phone, new.login_phone_verified) == ("", False)
