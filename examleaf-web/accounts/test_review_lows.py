"""Smaller findings of SECURITY_REVIEW_PHASE5_6.md in accounts: one-step API log-ins of accounts with a second step
(L4), staff passkey log-ins (L5), notices when a mobile number moves (L6), deletion and Download my data (L10)."""

import pytest
from allauth.account.adapter import get_adapter
from allauth.account.authentication import get_authentication_records
from allauth.account.internal.flows.login import record_authentication
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from axes.models import AccessAttempt
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from rest_framework.test import APIClient

from accounts.factories import PASSWORD, UserFactory
from accounts.models import DeletionRequest
from accounts.views import export_user_data
from api.tests import student
from ops import sms
from ops.models import EmailSuppression, SmsLog

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
    pytest.mark.filterwarnings("ignore:app_settings.AUTHENTICATION_METHOD is deprecated"),  # inside dj-rest-auth
]
PHONE = "+919864012345"


def test_api_log_ins_with_one_step_refuse_staff_and_accounts_with_a_second_step():
    api, login = APIClient(), "/api/v1/auth/login/"
    for user in [student(is_staff=True), student()]:
        if not user.is_staff:
            TOTP.activate(user, generate_totp_secret())  # a student who added an authenticator app
        response = api.post(login, {"email": user.email, "password": PASSWORD})
        assert response.status_code == 403 and "second step" in response.json()["detail"]
    assert api.post(login, {"email": student().email, "password": PASSWORD}).status_code == 200


def staff_page_request(rf, user):
    request = rf.post("/_allauth/browser/v1/auth/webauthn/login")
    request.session, request.user = SessionStore(), user
    request._messages = FallbackStorage(request)
    record_authentication(request, user, method="mfa", type="webauthn", passwordless=True)
    return request


def test_staff_may_not_log_in_with_a_passkey_alone(rf):
    hooks = {"email_verification": "mandatory", "signal_kwargs": None, "email": None, "signup": False}
    staff = UserFactory(is_staff=True)
    request = staff_page_request(rf, staff)
    response = get_adapter(request).pre_login(request, staff, redirect_url=None, **hooks)
    assert response is not None and get_authentication_records(request) == []  # stopped: the password comes first
    learner = UserFactory()
    request = staff_page_request(rf, learner)
    assert get_adapter(request).pre_login(request, learner, redirect_url=None, **hooks) is None


def test_a_number_that_moves_tells_both_accounts_once(rf):
    old, new = UserFactory(login_phone=PHONE, login_phone_verified=True), UserFactory()
    adapter = get_adapter(rf.get("/"))
    adapter.set_phone_verified(new, PHONE)
    assert {(m.to[0], m.subject) for m in mail.outbox} == {
        (new.email, "[ExamLeaf] A mobile number was added to your account"),
        (old.email, "[ExamLeaf] Your mobile number was moved to another account"),
    }
    assert all("2345" in m.body and PHONE not in m.body for m in mail.outbox)
    adapter.set_phone_verified(new, PHONE)  # as at each log-in by SMS code: nothing new to tell
    assert len(mail.outbox) == 2


def test_deletion_takes_the_sms_log_and_failed_phone_log_ins_and_the_export_shows_them():
    user = UserFactory(login_phone=PHONE, login_phone_verified=True)
    sms.queue_sms("otp", PHONE, {"otp": "123456"}, user=user)
    EmailSuppression.objects.create(email=user.email, reason=EmailSuppression.Reason.BOUNCE, esp="test")
    AccessAttempt.objects.create(username=PHONE, ip_address="10.0.0.1", failures_since_start=1)
    data = export_user_data(user)
    assert [row["kind"] for row in data["sms"]] == ["otp"] and data["email_suppressed"]["reason"] == "bounce"
    DeletionRequest.objects.create(user=user).complete()
    # the SMS log is a processing log, kept its year (examleaf.retention), without the account or the last digits
    assert list(SmsLog.objects.values_list("user", "phone_last4")) == [(None, "")]
    assert not AccessAttempt.objects.exists()


def test_a_code_request_that_failed_turnstile_spends_none_of_the_numbers_three(client, settings, monkeypatch):
    """I1: Turnstile is checked first, and allauth's limit per number is not spent by a request that failed it;
    Cloudflare is given the client's address."""
    from accounts import forms

    settings.TURNSTILE, settings.TURNSTILE_SITE_KEY, settings.TURNSTILE_SECRET_KEY = True, "0x4AAA-site", "0x4AAA-sec"
    sent = []

    def siteverify(url, data, timeout):
        sent.append(data)
        return forms.httpx.Response(200, json={"success": data["response"] == "solved"})

    monkeypatch.setattr(forms.httpx, "post", siteverify)
    code = "/_allauth/browser/v1/auth/code/request"  # the website's "Log in with a code"
    for _ in range(4):
        response = client.post(code, {"phone": "98640 12345", "turnstile": "not-solved"}, "application/json")
        assert "Wait until the check above says it is done" in response.text
    response = client.post(code, {"phone": "98640 12345", "turnstile": "solved"}, "application/json")
    assert response.status_code == 401  # no refusal: the code's page comes next (flow login_by_code)
    assert sent[0]["remoteip"] == "127.0.0.1"
