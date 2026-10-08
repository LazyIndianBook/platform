"""Google sign-in (allauth.socialaccount): listed only with the keys set, and a new student always fills in the
student details (class, board, date of birth, parent, consent) after Google."""

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.urls import reverse

from accounts.models import ConsentRecord, User
from accounts.tests import birthday
from content.models import Board
from content.tests import make_paper

pytestmark = pytest.mark.django_db
GOOGLE = {
    "google": {"APPS": [{"client_id": "id.apps.googleusercontent.com", "secret": "s"}], "OAUTH_PKCE_ENABLED": True}
}


def test_google_is_offered_only_when_its_keys_are_set(client, settings):
    assert "/account/google/login/" not in client.get(reverse("account_login")).text
    assert "https://accounts.google.com" not in settings.CONTENT_SECURITY_POLICY["form-action"]
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    assert "/account/google/login/" in client.get(reverse("account_login")).text


def test_googles_urls_without_its_keys_are_not_found_and_with_them_work(client, settings):
    for url in ["/account/google/login/", "/account/google/login/callback/", "/account/google/login/token/"]:
        assert client.get(url).status_code == 404, url  # allauth raised SocialApp.DoesNotExist: a server error
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    assert client.get("/account/google/login/").status_code == 200  # the "continue with Google" page


def test_after_google_a_new_student_gives_the_student_details(client, settings, rf):
    settings.SOCIALACCOUNT_PROVIDERS = GOOGLE
    make_paper()  # a board
    email = "rahul@gmail.com"
    sociallogin = SocialLogin(  # what allauth keeps in the session when Google comes back with a new address
        provider=get_social_adapter().get_provider(rf.get("/"), "google"),
        user=User(email=email),
        account=SocialAccount(provider="google", uid="1093", extra_data={"name": "Rahul Das", "email": email}),
        email_addresses=[EmailAddress(email=email, verified=True, primary=True)],
    )
    session = client.session
    session["socialaccount_sociallogin"] = sociallogin.serialize()
    session.save()
    page = client.get(reverse("socialaccount_signup")).text
    assert "<h1>Register</h1>" in page and 'value="Rahul Das"' in page and 'name="date_of_birth"' in page
    assert 'name="phone"' not in page and 'name="password1"' not in page
    details = {"full_name": "Rahul Das", "email": email, "class_level": 12, "board": Board.objects.get().pk}
    response = client.post(reverse("socialaccount_signup"), {**details, "date_of_birth": birthday(16).isoformat()})
    assert "Required for a student under 18." in response.text and not User.objects.exists()
    parent = {"parent_name": "Anita Das", "parent_contact": "anita@example.com", "consent": "on"}
    client.post(reverse("socialaccount_signup"), {**details, "date_of_birth": birthday(16).isoformat(), **parent})
    user = User.objects.get()
    assert (user.full_name, user.parent_contact, user.is_student) == ("Rahul Das", "anita@example.com", True)
    assert SocialAccount.objects.get().user == user and ConsentRecord.objects.get(user=user).by_parent
    assert EmailAddress.objects.get(user=user).verified and client.session["_auth_user_id"] == str(user.pk)
