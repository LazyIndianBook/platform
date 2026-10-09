"""Google sign-in (allauth.socialaccount, through allauth.headless): listed only with the keys set
(api/test_headless.py), the redirect to Google and its callback to Django, back to the website, and a new student
always fills in the student details (class, board, date of birth, parent, consent) after Google. Google is mocked."""

from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client

from accounts.factories import UserFactory
from accounts.models import ConsentRecord, User
from accounts.tests import BROWSER, birthday
from content.models import Board
from content.tests import make_paper

pytestmark = pytest.mark.django_db
GOOGLE = {
    "google": {"APPS": [{"client_id": "id.apps.googleusercontent.com", "secret": "s"}], "OAUTH_PKCE_ENABLED": True}
}


def test_googles_urls_without_its_keys_are_not_found(client, settings):
    for url in ["/account/google/login/", "/account/google/login/callback/", "/account/google/login/token/"]:
        assert client.get(url).status_code == 404, url  # allauth raised SocialApp.DoesNotExist: a server error
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    assert client.get("/account/google/login/").status_code == 404  # headless only: the start is a POST to /_allauth/


def test_the_websites_google_button_goes_to_google_and_back_and_a_new_student_gives_the_details(
    client, settings, monkeypatch
):
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    make_paper()  # a board
    token = {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}
    monkeypatch.setattr(OAuth2Client, "get_access_token", lambda self, code, **kwargs: token)
    profile = {"sub": "1093", "email": "rahul@gmail.com", "email_verified": True, "name": "Rahul Das"}
    monkeypatch.setattr(GoogleOAuth2Adapter, "_fetch_user_info", lambda self, access_token: profile)
    start = {"provider": "google", "callback_url": "/s/PHY-E01/", "process": "login"}  # the button's form
    response = client.post(f"{BROWSER}/auth/provider/redirect", start)
    assert response.status_code == 302 and response["Location"].startswith("https://accounts.google.com/")
    query = parse_qs(urlparse(response["Location"]).query)
    assert query["redirect_uri"] == ["http://testserver/account/google/login/callback/"]  # Django's (Caddyfile)
    back = client.get("/account/google/login/callback/", {"code": "from-google", "state": query["state"][0]})
    assert (back.status_code, back["Location"]) == (302, "/s/PHY-E01/")  # back on the website's page
    session = client.get(f"{BROWSER}/auth/session").json()
    assert [flow["id"] for flow in session["data"]["flows"] if flow.get("is_pending")] == ["provider_signup"]
    details = {"email": "rahul@gmail.com", "full_name": "Rahul Das", "class_level": 12, "board": Board.objects.get().pk}
    details |= {"date_of_birth": birthday(16).isoformat(), "consent": True}
    signup = f"{BROWSER}/auth/provider/signup"
    refused = client.post(signup, details, content_type="application/json")
    assert {e["param"] for e in refused.json()["errors"]} == {"parent_name", "parent_contact"}
    assert not User.objects.exists()
    parent = {"parent_name": "Anita Das", "parent_contact": "anita@example.com"}
    assert client.post(signup, {**details, **parent}, content_type="application/json").status_code == 200
    user = User.objects.get()
    assert (user.full_name, user.parent_contact, user.is_student) == ("Rahul Das", "anita@example.com", True)
    assert SocialAccount.objects.get().user == user and ConsentRecord.objects.get(user=user).by_parent
    assert EmailAddress.objects.get(user=user).verified and client.session["_auth_user_id"] == str(user.pk)


# Google Workspace for staff (accounts.adapter.SocialAccountAdapter.pre_social_login)


@pytest.fixture
def workspace(settings):
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    settings.STAFF_GOOGLE_DOMAIN = "examleaf.in"
    settings.ALLOWED_HOSTS = ["testserver", "admin.examleaf.in"]


def google(client, monkeypatch, host="testserver", **claims):
    """A sign-in through Google, which says `claims` (an ID token's: `hd` for a Workspace account), back at Django's
    callback; returns its redirect to the frontend."""
    token = {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}
    monkeypatch.setattr(OAuth2Client, "get_access_token", lambda self, code, **kwargs: token)
    said = {"sub": "1093", "email": "ops@examleaf.in", "email_verified": True, "name": "Ops Person", **claims}
    monkeypatch.setattr(GoogleOAuth2Adapter, "_fetch_user_info", lambda self, access_token: said)
    start = {"provider": "google", "callback_url": "/signed-in/", "process": "login"}
    response = client.post(f"{BROWSER}/auth/provider/redirect", start, HTTP_HOST=host)
    state = parse_qs(urlparse(response["Location"]).query)["state"][0]
    return client.get("/account/google/login/callback/", {"code": "c", "state": state}, HTTP_HOST=host)["Location"]


def pending(client):
    session = client.get(f"{BROWSER}/auth/session").json()
    return [flow["id"] for flow in session["data"]["flows"] if flow.get("is_pending")]


def refusals(code):
    from staff.models import AuditEvent

    return AuditEvent.objects.filter(action="authz_fail", details__error=code)


def test_a_staff_google_sign_in_needs_the_workspace_domain_a_confirmed_address_then_the_second_factor(
    client, workspace, monkeypatch
):
    staff = UserFactory(is_staff=True, email="ops@examleaf.in")  # an authenticator app (UserFactory gives staff one)
    EmailAddress.objects.create(user=staff, email=staff.email, verified=True, primary=True)
    SocialAccount.objects.create(user=staff, provider="google", uid="1093")
    refused = "/signed-in/?error=staff_google_domain&error_process=login"
    assert google(client, monkeypatch) == refused  # a gmail account: no hd
    assert refusals("staff_google_domain").get().actor_id == staff.pk
    assert google(client, monkeypatch, hd="examleaf.in", email_verified=False) == refused
    assert google(client, monkeypatch, hd="other.example") == refused
    assert "_auth_user_id" not in client.session
    assert google(client, monkeypatch, hd="EXAMLEAF.IN") == "/signed-in/"  # the domain, any case
    assert pending(client) == ["mfa_authenticate"] and "_auth_user_id" not in client.session  # the code still asked


def test_a_new_workspace_account_signs_up_only_with_auto_staff_and_as_staff_without_a_role(
    client, workspace, monkeypatch, settings
):
    assert google(client, monkeypatch, hd="examleaf.in").endswith("error=staff_google_no_account&error_process=login")
    assert not User.objects.exists() and refusals("staff_google_no_account").get().actor_type == "anonymous"
    settings.STAFF_GOOGLE_AUTO_STAFF = True
    UserFactory(email="taken@examleaf.in")
    assert "staff_google_no_account" in google(client, monkeypatch, hd="examleaf.in", email="taken@examleaf.in")
    assert google(client, monkeypatch, hd="examleaf.in") == "/signed-in/"
    user = User.objects.get(email="ops@examleaf.in")
    assert (user.is_staff, user.full_name, list(user.groups.all())) == (True, "Ops Person", [])  # nothing opens yet
    assert SocialAccount.objects.get(user=user).uid == "1093" and EmailAddress.objects.get(user=user).verified
    refused = client.get("/api/v1/staff/session/")
    assert (refused.status_code, refused.json()["code"]) == (403, "mfa_setup_required")  # a second factor first


def test_a_students_google_is_as_before_but_never_on_the_admin_host_or_into_a_break_glass_account(
    client, workspace, monkeypatch, settings
):
    assert google(client, monkeypatch, email="rahul@gmail.com") == "/signed-in/"  # the website: a student's sign-up
    assert pending(client) == ["provider_signup"]
    settings.ADMIN_HOSTS = ["admin.examleaf.in"]
    on_admin = google(client, monkeypatch, host="admin.examleaf.in", email="rahul@gmail.com")
    assert on_admin.endswith("error=staff_google_domain&error_process=login")  # the panel: staff only
    sealed = UserFactory(is_staff=True, is_superuser=True, email="glass@examleaf.in")
    SocialAccount.objects.create(user=sealed, provider="google", uid="1093")
    assert "staff_google_break_glass" in google(client, monkeypatch, hd="examleaf.in", email="glass@examleaf.in")


def test_the_admin_host_uses_the_workspaces_own_google_client(client, workspace, settings):
    staff_client = {"client_id": "staff.apps", "secret": "t", "settings": {"staff": True}}  # STAFF_GOOGLE_CLIENT_ID's
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {**GOOGLE["google"], "APPS": [*GOOGLE["google"]["APPS"], staff_client]}
    }
    start = {"provider": "google", "callback_url": "/", "process": "login"}

    def client_id(host):
        response = client.post(f"{BROWSER}/auth/provider/redirect", start, HTTP_HOST=host)
        return parse_qs(urlparse(response["Location"]).query)["client_id"][0]

    assert client_id("testserver") == client_id("admin.examleaf.in") == "id.apps.googleusercontent.com"  # (no hosts)
    settings.ADMIN_HOSTS = ["admin.examleaf.in"]
    assert (client_id("testserver"), client_id("admin.examleaf.in")) == ("id.apps.googleusercontent.com", "staff.apps")
