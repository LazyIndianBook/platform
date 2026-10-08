"""Six-digit codes (SECURITY_REVIEW_PHASE5_6.md M1, I7): an address gets a few codes an hour and a day, and a code
gets three tries, also when the tries come together (allauth counts them in the session; the cache counts them too)."""

import re

import pytest
from allauth.account.internal.flows.code_verification import AbstractCodeVerificationProcess
from allauth.account.models import EmailAddress
from django.core import mail
from rest_framework.test import APIClient

from accounts.factories import PASSWORD, UserFactory
from accounts.forms import NO_TRIES_LEFT
from api.tests import emailed_code, student

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
    pytest.mark.filterwarnings("ignore:app_settings.AUTHENTICATION_METHOD is deprecated"),  # inside dj-rest-auth
]
PHONE = "+919864012345"
LOGIN, VERIFY = "/api/v1/auth/login/", "/api/v1/auth/registration/verify-email/"
CODE, CONFIRM = "/api/v1/auth/phone/code/", "/api/v1/auth/phone/confirm/"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def together(monkeypatch):
    """Tries as requests sent at the same moment see allauth's count: each read the session before any saved it."""
    monkeypatch.setattr(AbstractCodeVerificationProcess, "record_invalid_attempt", lambda self: True)


def texted_code(capsys):
    return re.findall(r"'otp': '(\d{6})'", capsys.readouterr().out)[-1]


@pytest.mark.parametrize("per_hour, per_day, given", [("5/h/key", "10/d/key", 5), ("100/h/key", "10/d/key", 10)])
def test_an_unconfirmed_address_gets_five_codes_an_hour_and_ten_a_day(api, settings, per_hour, per_day, given):
    """M1: each log-in of an unconfirmed address makes a code; the next one past the limit is refused, not made."""
    limits = {"confirm_email": "", "email_code_hour": per_hour, "email_code_day": per_day}  # not 10 s apart here
    settings.ACCOUNT_RATE_LIMITS = {**settings.ACCOUNT_RATE_LIMITS, **limits}
    user = student(verified=False, email="accounts@school.example")
    for _ in range(given):
        assert "verification_token" in api.post(LOGIN, {"email": user.email, "password": PASSWORD}).json()
    refused = api.post(LOGIN, {"email": user.email, "password": PASSWORD})
    assert refused.status_code == 429 and refused.json()["detail"].startswith("Too many codes")
    assert len([message for message in mail.outbox if message.to == [user.email]]) == given


def test_the_fourth_try_of_an_emailed_code_is_refused_even_when_the_tries_come_together(api, together):
    user = student(verified=False)
    token = api.post(LOGIN, {"email": user.email, "password": PASSWORD}).json()["verification_token"]
    code = emailed_code()
    for _ in range(3):
        assert api.post(VERIFY, {"verification_token": token, "code": "000000"}).status_code == 400
    response = api.post(VERIFY, {"verification_token": token, "code": code})
    assert response.status_code == 400 and response.json() == {"code": [NO_TRIES_LEFT]}
    assert not EmailAddress.objects.get(user=user).verified


def test_the_fourth_try_of_a_texted_code_is_refused_even_when_the_tries_come_together(api, capsys, together):
    student(login_phone=PHONE, login_phone_verified=True)
    token = api.post(CODE, {"phone": "98640 12345"}, format="json").json()["verification_token"]
    code = texted_code(capsys)
    for _ in range(3):
        api.post(CONFIRM, {"verification_token": token, "code": "000000"}, format="json")
    response = api.post(CONFIRM, {"verification_token": token, "code": code}, format="json")
    assert response.status_code == 400 and response.json() == {"code": [NO_TRIES_LEFT]}


def browser(client, path, data):
    """The website's code pages: allauth.headless, the browser client (examleaf/urls.py gives it the site's forms)."""
    return client.post(f"/_allauth/browser/v1/auth/{path}", data, content_type="application/json")


def test_the_websites_code_page_counts_tries_in_the_cache_too(client, capsys, together):
    user = UserFactory(login_phone=PHONE, login_phone_verified=True)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    browser(client, "code/request", {"phone": "98640 12345"})
    code = texted_code(capsys)
    for _ in range(3):
        browser(client, "code/confirm", {"code": "000000"})
    response = browser(client, "code/confirm", {"code": code})
    assert NO_TRIES_LEFT in response.text and "_auth_user_id" not in client.session


def test_the_websites_email_and_phone_codes_count_tries_in_the_cache_too(client, capsys, together):
    user = student(verified=False)
    browser(client, "login", {"email": user.email, "password": PASSWORD})  # an unconfirmed address: a code
    for _ in range(3):
        browser(client, "email/verify", {"key": "000000"})
    response = browser(client, "email/verify", {"key": emailed_code()})
    assert NO_TRIES_LEFT in response.text and not EmailAddress.objects.get(user=user).verified
    client.force_login(student())
    client.post("/_allauth/browser/v1/account/phone", {"phone": "98640 12345"}, content_type="application/json")
    code = texted_code(capsys)
    for _ in range(3):
        browser(client, "phone/verify", {"code": "000000"})
    assert NO_TRIES_LEFT in browser(client, "phone/verify", {"code": code}).text


def test_no_new_log_in_code_for_the_asking(client, capsys):
    """allauth's "send a new code" failed with a server error for an unknown number (a way to tell registered ones)."""
    browser(client, "code/request", {"phone": "98640 12345"})
    assert browser(client, "code/resend", {}).status_code == 409 and "SMS" not in capsys.readouterr().out
