"""Passkeys (allauth.mfa WebAuthn): one relying party for every host name (the log-in's challenge:
api/test_headless.py), a passkey enough for staff, gone with the account."""

import pytest
from allauth.mfa.models import Authenticator
from django.urls import reverse

from accounts.adapter import MFAAdapter
from accounts.factories import UserFactory
from accounts.models import DeletionRequest
from accounts.views import export_user_data

pytestmark = pytest.mark.django_db


def passkey(user):
    return Authenticator.objects.create(user=user, type=Authenticator.Type.WEBAUTHN, data={"name": "Phone"})


def test_passkeys_belong_to_the_site_url_host(settings):
    settings.SITE_URL = "https://examleaf.in"
    assert MFAAdapter().get_public_key_credential_rp_entity() == {"id": "examleaf.in", "name": "ExamLeaf"}


def test_staff_may_use_a_passkey_instead_of_an_authenticator_app(client):  # H2
    staff = UserFactory(is_staff=True, is_superuser=True, totp=False)
    passkey(staff)
    client.force_login(staff)
    assert client.get(reverse("admin:index")).status_code == 200


def test_passkeys_are_in_the_data_export_and_go_with_the_account():
    user = UserFactory()
    passkey(user)
    assert export_user_data(user)["passkeys_and_authenticators"][0]["type"] == "webauthn"
    DeletionRequest.objects.create(user=user).complete()
    assert not Authenticator.objects.exists()
