"""allauth.headless (/_allauth/): the app's and the browser's JSON flows under the site's rules (student details and
consent at sign-up, Turnstile, staff authenticators, the website's links in emails), and the app's session token
exchanged for the JWT pair of API v1 (POST /api/v1/auth/exchange/)."""

import re
import time

import pytest
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from accounts import forms as account_forms
from accounts.factories import PASSWORD
from accounts.models import ConsentRecord, User
from accounts.tests import birthday
from api.test_phone import texted_codes
from api.tests import emailed_code, student
from content.tests import make_paper

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
APP, BROWSER, EXCHANGE = "/_allauth/app/v1", "/_allauth/browser/v1", "/api/v1/auth/exchange/"
GOOGLE = {"google": {"APPS": [{"client_id": "id.apps.googleusercontent.com", "secret": "s"}]}}
PARENT = {"parent_name", "parent_contact"}


@pytest.fixture
def api():
    return APIClient()


class App:
    """The app: JSON to /_allauth/app/v1/, keeping the session token that answers carry (meta.session_token)."""

    def __init__(self, api):
        self.api, self.token = api, None

    def call(self, method, path, data=None):
        headers = {"HTTP_X_SESSION_TOKEN": self.token} if self.token else {}
        response = getattr(self.api, method)(APP + path, data, format="json", **headers)
        self.token = response.json().get("meta", {}).get("session_token", self.token)
        return response

    def post(self, path, data=None):
        return self.call("post", path, data or {})

    def exchange(self):
        return self.api.post(EXCHANGE, HTTP_X_SESSION_TOKEN=self.token)


def pending(response):
    return [flow["id"] for flow in response.json()["data"]["flows"] if flow.get("is_pending")]


def totp_code(secret):
    return format_hotp_value(hotp_value(secret, int(time.time()) // 30))


def test_a_code_by_email_signs_the_app_in_and_its_session_token_becomes_the_jwt_pair(api):
    user, app = student(), App(api)
    response = app.post("/auth/code/request", {"email": user.email})
    assert response.status_code == 401 and pending(response) == ["login_by_code"] and app.token
    assert app.exchange().status_code == 401  # the log-in is not finished: no tokens yet
    response = app.post("/auth/code/confirm", {"code": emailed_code()})
    assert response.status_code == 200 and response.json()["data"]["user"]["email"] == user.email
    assert api.post(EXCHANGE).status_code == 401  # no session token
    assert api.post(EXCHANGE, HTTP_X_SESSION_TOKEN="not-a-session").status_code == 401
    response = app.exchange()
    tokens = response.json()
    assert response.status_code == 200 and tokens["user"]["email"] == user.email and tokens["refresh"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api.get("/api/v1/me/").json()["email"] == user.email
    assert "no-store" in api.get(APP + "/auth/session", HTTP_X_SESSION_TOKEN=app.token)["Cache-Control"]


def test_a_code_by_sms_through_headless_uses_the_sites_number_rules(api, capsys):
    user, app = student(login_phone="+919864012345", login_phone_verified=True), App(api)
    response = app.post("/auth/code/request", {})  # neither box: the website's message, not a server error
    assert response.status_code == 400 and "email address or your mobile number" in response.text
    assert app.post("/auth/code/request", {"phone": "98640 12345"}).status_code == 401
    [code] = texted_codes(capsys)
    assert app.post("/auth/code/confirm", {"code": code}).status_code == 200
    assert app.exchange().json()["user"]["email"] == user.email


def test_staff_finish_the_second_step_before_the_exchange_and_set_up_an_app_first(api, settings):
    settings.MFA_TOTP_TOLERANCE = 1  # a code of the previous or next 30 seconds too: no failure at a boundary
    staff, secret = student(is_staff=True, totp=False), generate_totp_secret()
    TOTP.activate(staff, secret)
    app = App(api)
    response = app.post("/auth/login", {"email": staff.email, "password": PASSWORD})
    assert response.status_code == 401 and pending(response) == ["mfa_authenticate"]
    assert app.exchange().status_code == 401  # the password alone is not enough
    assert app.post("/auth/2fa/authenticate", {"code": totp_code(secret)}).status_code == 200
    assert app.exchange().status_code == 200

    newcomer, app = student(is_staff=True, totp=False), App(APIClient())
    assert app.post("/auth/login", {"email": newcomer.email, "password": PASSWORD}).status_code == 200
    response = app.exchange()
    assert response.status_code == 403 and "authenticator app" in response.json()["detail"]
    setup = app.api.get(APP + "/account/authenticators/totp", HTTP_X_SESSION_TOKEN=app.token).json()
    response = app.post("/account/authenticators/totp", {"code": totp_code(setup["meta"]["secret"])})
    assert response.status_code == 200 and app.exchange().status_code == 200


def test_the_browser_client_keeps_the_staff_rule_in_json(client):
    staff = student(is_staff=True, totp=False)
    response = client.post(BROWSER + "/auth/login", {"email": staff.email, "password": PASSWORD}, "application/json")
    assert response.status_code == 200
    assert client.get(BROWSER + "/account/authenticators/totp").status_code == 404  # open: the set-up's secret
    response = client.get("/api/v1/me/")
    assert response.status_code == 403 and response.json()["code"] == "mfa_setup_required"
    assert client.get(reverse("account"))["Location"] == reverse("mfa_activate_totp")


def test_a_passkey_log_in_starts_with_a_challenge_for_the_sites_host(api, settings):
    settings.SITE_URL = "https://examleaf.in"
    response = api.get(APP + "/auth/webauthn/login")
    options = response.json()["data"]["request_options"]["publicKey"]
    assert response.status_code == 200 and options["challenge"] and options["rpId"] == "examleaf.in"


def test_google_is_listed_only_when_its_keys_are_set(api, settings):
    assert api.get(APP + "/config").json()["data"]["socialaccount"]["providers"] == []
    assert api.get("/api/v1/config/").json()["auth"]["google"] is False
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    [google] = api.get(APP + "/config").json()["data"]["socialaccount"]["providers"]
    assert google["id"] == "google" and api.get("/api/v1/config/").json()["auth"]["google"] is True


def test_sign_up_through_headless_asks_the_student_details_and_records_the_consent(api, monkeypatch, settings):
    board, app = make_paper().book.subject.board, App(api)
    response = app.post("/auth/signup", {"email": "rahul@example.com", "password": PASSWORD})
    errors = {error["param"] for error in response.json()["errors"]}
    assert response.status_code == 400 and {"full_name", "board", "date_of_birth", "consent"} <= errors
    details = {
        "email": "rahul@example.com", "password": PASSWORD, "full_name": "Rahul Das", "class_level": 12,
        "board": board.pk, "date_of_birth": birthday(16).isoformat(), "phone": "+919864012345",
    }  # fmt: skip
    response = app.post("/auth/signup", {**details, "consent": True})
    assert response.status_code == 400 and {e["param"] for e in response.json()["errors"]} == PARENT
    parent = {"parent_name": "Anita Das", "parent_contact": "anita@example.com", "consent": True}
    settings.TURNSTILE = True  # the bot check, as on the website's form
    monkeypatch.setattr(account_forms, "turnstile_passed", lambda token: token == "passed")
    assert app.post("/auth/signup", {**details, **parent}).status_code == 400
    response = app.post("/auth/signup", {**details, **parent, "turnstile": "passed"})
    assert response.status_code == 401 and pending(response) == ["verify_email"]
    user = User.objects.get()
    assert (user.full_name, user.board, user.parent_contact) == ("Rahul Das", board, "anita@example.com")
    assert user.login_phone == ""  # a number comes later, through account/phone and its code
    assert user.is_student and ConsentRecord.objects.get(user=user).by_parent
    assert app.post("/auth/email/verify", {"key": emailed_code()}).status_code == 200
    assert app.exchange().json()["user"]["roles"] == ["STUDENT"]


def test_emails_link_to_the_websites_pages_whichever_client_asked(api, settings):
    for name, url in settings.HEADLESS_FRONTEND_URLS.items():
        kwargs = {"kwargs": {"uidb36": "UID", "key": "KEY"}} if "{key}" in url else {}
        page = reverse(name, **kwargs).replace("UID-KEY", "{key}")
        assert url == settings.SITE_URL + page, name
    user = student()
    assert api.post(APP + "/auth/password/request", {"email": user.email}, format="json").status_code == 200
    link = re.search(r"https?://\S+", mail.outbox[-1].body).group()
    assert link.startswith(settings.SITE_URL + "/account/password/reset/key/")


def test_the_app_adds_a_mobile_number_with_a_code_and_a_second_request_waits_a_minute(api, capsys):
    user, app = student(), App(api)
    app.post("/auth/code/request", {"email": user.email})
    assert app.post("/auth/code/confirm", {"code": emailed_code()}).status_code == 200
    assert app.post("/account/phone", {"phone": "98640 12345"}).status_code == 202
    [code] = texted_codes(capsys)
    again = app.post("/account/phone", {"phone": "98640 12345"})  # the website's form: no server error
    assert again.status_code == 400 and "wait a minute" in again.text
    assert app.post("/auth/phone/verify", {"code": code}).status_code == 200
    user.refresh_from_db()
    assert (user.login_phone, user.login_phone_verified) == ("+919864012345", True)
