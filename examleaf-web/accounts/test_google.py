"""Google sign-in (allauth.socialaccount, through allauth.headless): listed only with the keys set
(api/test_headless.py), the redirect to Google and its callback to Django, back to the website, and a new student
always fills in the student details (class, board, date of birth, parent, consent) after Google. Google is mocked."""

from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client

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
