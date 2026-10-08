"""Cloudflare Turnstile on sign-up and code requests (accounts.forms.TurnstileMixin): only with both keys set, checked
with Cloudflare, let through (logged) when Cloudflare cannot be reached; not on the app's API."""

import logging

import httpx
import pytest
from django.test import Client
from django.urls import reverse

from accounts import forms
from accounts.models import User
from accounts.test_security import sign_up
from content.tests import make_paper

pytestmark = pytest.mark.django_db


@pytest.fixture
def turnstile(settings, monkeypatch):
    settings.TURNSTILE, settings.TURNSTILE_SITE_KEY, settings.TURNSTILE_SECRET_KEY = (
        True,
        "0x4AAA-site",
        "0x4AAA-secret",
    )
    answers = []

    def post(url, data, timeout):
        assert url.endswith("/siteverify") and data["secret"] == "0x4AAA-secret" and timeout == 5
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(200, json=answer)

    monkeypatch.setattr(forms.httpx, "post", post)
    return answers


def test_off_without_its_keys(client, settings):
    assert "cf-turnstile" not in client.get(reverse("account_signup")).text
    assert "https://challenges.cloudflare.com" not in settings.CONTENT_SECURITY_POLICY["script-src"]


def test_sign_up_needs_cloudflares_yes(client, turnstile):
    make_paper()  # a board
    page = client.get(reverse("account_signup")).text
    assert 'data-sitekey="0x4AAA-site"' in page and "turnstile/v0/api.js" in page
    assert "turnstile" in sign_up(client, parent_contact="anita@example.com").context["form"].errors  # no token
    turnstile.append({"success": False, "error-codes": ["invalid-input-response"]})
    sign_up(client, parent_contact="anita@example.com", **{"cf-turnstile-response": "forged"})
    assert not User.objects.exists()
    turnstile.append({"success": True})
    sign_up(client, parent_contact="anita@example.com", **{"cf-turnstile-response": "token"})
    assert User.objects.exists()


def test_cloudflare_out_of_reach_lets_the_code_request_through_and_says_so(turnstile, caplog):
    turnstile.append(httpx.ConnectTimeout("no answer"))
    with caplog.at_level(logging.WARNING, logger="accounts.forms"):
        response = Client().post(
            reverse("account_request_login_code"), {"email": "rahul@example.com", "cf-turnstile-response": "token"}
        )
    assert response["Location"] == reverse("account_confirm_login_code") and "could not be reached" in caplog.text
