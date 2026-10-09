"""Customers' accounts as support sees them (research 5): masked by default, each opening and each reveal logged,
the reveals rate-limited and re-authenticated; the account actions; logging in as a customer (15 minutes, never staff
or a child, refused payments and passwords while it lasts)."""

import re
import time

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.usersessions.models import UserSession
from axes.models import AccessAttempt
from django.core import mail
from django.test import Client
from rest_framework.throttling import SimpleRateThrottle

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import ConsentRecord, User
from accounts.tests import birthday
from api.tests import student
from staff import services
from staff.middleware import IMPERSONATING

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
USERS = STAFF + "users/"


def test_a_search_shows_customers_with_their_contacts_masked():
    rahul = student(email="rahul.das@example.com", full_name="Rahul Das", login_phone="+919864012345",
                    login_phone_verified=True)  # fmt: skip
    make_staff(roles.SUPPORT, email="support@examleaf.in", full_name="Rahul Staff")
    support = signed_in(make_staff(roles.SUPPORT))
    by_name = support.get(USERS, {"q": "rahul"}).json()["results"]
    assert [row["id"] for row in by_name] == [rahul.pk]  # staff are not customers (people/ lists them)
    row = by_name[0]
    assert (row["email"], row["phone"], row["status"], row["email_verified"]) == ("ra•••@example.com", "••••••2345",
                                                                                  "active", True)  # fmt: skip
    assert [r["id"] for r in support.get(USERS, {"q": "Rahul.Das@example.com"}).json()["results"]] == [rahul.pk]
    assert [r["id"] for r in support.get(USERS, {"q": "98640 12345"}).json()["results"]] == [rahul.pk]
    assert support.get(USERS, {"q": "ra"}).json()["results"] == []  # 3 letters at least


def test_a_page_of_customers_costs_the_same_few_queries_however_long(django_assert_max_num_queries, settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    for n in range(20):
        student(date_of_birth=birthday(15 if n % 2 else 30), parent_name="A", parent_contact="anita@example.com")
    client = signed_in(make_staff(roles.SUPPORT))
    client.get(USERS)  # the session's own queries once
    with django_assert_max_num_queries(20):
        rows = client.get(USERS).json()["results"]
    assert len(rows) == 20 and {row["consent"] for row in rows} == {"adult", "pending"}


def test_opening_a_record_is_logged_and_a_childs_says_so():
    child = student(date_of_birth=birthday(15), parent_name="Anita Das", parent_contact="anita@example.com")
    support_user = make_staff(roles.SUPPORT)
    data = signed_in(support_user).get(f"{USERS}{child.pk}/").json()
    assert data["under_18"] and data["consent"] == "declared" and data["parent_contact"] == "an•••@example.com"
    assert "date_of_birth" not in data and "Anita" not in str(data)
    read = events("sensitive_read", actor_id=support_user.pk).get()
    assert read.details == {"what": "record", "child": True} and read.target_id == str(child.pk)


def test_revealing_a_detail_needs_a_reason_a_recent_reauthentication_and_is_rate_limited(monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "staff_reveal", "3/hour")
    customer = student(phone="+919864012345", date_of_birth=birthday(30))
    support = make_staff(roles.SUPPORT)
    url = f"{USERS}{customer.pk}/reveal/"
    stale = signed_in(support, reauth=False).post(url, {"show": ["email"], "reason": "Call back"}, format="json")
    assert (stale.status_code, stale.json()["code"]) == (403, "reauthentication_required")
    assert stale.json()["flows"] == [{"id": "reauthenticate"}, {"id": "mfa_reauthenticate"}]  # allauth's, to step up
    assert not events("authz_fail").exists()  # a step-up, not a refusal
    assert signed_in(support).post(url, {"show": ["email"]}, format="json").status_code == 400  # a reason
    shown = signed_in(support).post(url, {"show": ["email", "phone", "date_of_birth"], "reason": "Call back"},
                                    format="json").json()  # fmt: skip
    assert shown == {"email": customer.email, "phone": "+919864012345", "date_of_birth": str(customer.date_of_birth)}
    read = events("sensitive_read", actor_id=support.pk).get()
    assert read.details["fields"] == ["date_of_birth", "email", "phone"] and read.reason == "Call back"
    assert customer.email not in str(read.details)
    client = signed_in(support)  # three an hour here (30 by default): the refused step-up did not count
    assert client.post(url, {"show": ["email"], "reason": "Again"}, format="json").status_code == 200
    assert client.post(url, {"show": ["email"], "reason": "Again"}, format="json").status_code == 429


def test_suspending_signs_the_customer_out_and_tells_them_and_reactivating_lets_them_in():
    customer = student()
    browser = Client()
    browser.force_login(customer)
    browser.get("/api/v1/me/")
    admin = make_staff(roles.ADMIN)
    response = signed_in(admin).post(f"{USERS}{customer.pk}/suspend/", {"reason": "Chargeback fraud"}, format="json")
    assert response.status_code == 200 and response.json()["status"] == "suspended"
    assert browser.get("/api/v1/me/").status_code in (401, 403) and not UserSession.objects.filter(user=customer)
    assert any(message.to == [customer.email] and "suspended" in message.subject for message in mail.outbox)
    signed_in(admin).post(f"{USERS}{customer.pk}/unsuspend/", {"reason": "Bank confirmed"}, format="json")
    assert User.objects.get(pk=customer.pk).is_active
    assert [event.action for event in events(target_id=str(customer.pk))] == ["user.suspended", "user.unsuspended"]
    assert (
        signed_in(make_staff(roles.SUPPORT)).post(f"{USERS}{customer.pk}/suspend/", {"reason": "x"}).status_code == 403
    )


def test_support_unlocks_a_lock_out_ends_sessions_and_sends_a_reset_link():
    customer = student(email="rahul@example.com")
    AccessAttempt.objects.create(username="rahul@example.com", ip_address="10.0.0.1", failures_since_start=10,
                                 user_agent="x", get_data="", post_data="", http_accept="", path_info="/")  # fmt: skip
    support = make_staff(roles.SUPPORT)
    assert signed_in(support).get(f"{USERS}{customer.pk}/").json()["locked"] is True
    assert signed_in(support).post(f"{USERS}{customer.pk}/unlock/").json() == {"attempts_cleared": 1}
    browser = Client()
    browser.force_login(customer)
    browser.get("/api/v1/me/")
    assert signed_in(support).post(f"{USERS}{customer.pk}/end-sessions/").json()["sessions"] == 1
    assert browser.get("/api/v1/me/").status_code in (401, 403)
    sent = signed_in(support).post(f"{USERS}{customer.pk}/password-reset/")
    assert sent.status_code == 200
    [reset] = [message for message in mail.outbox if message.to == ["rahul@example.com"]]
    assert re.search(r"/account/password/reset/key/[\w-]+/", reset.body)  # the website's page; staff saw no password
    assert [event.action for event in events(target_id=str(customer.pk))] == [
        "sensitive_read", "user.unlocked", "session_ended_by_staff", "user.password_reset_started"]  # fmt: skip


def test_the_parents_link_goes_again_only_while_a_consent_waits(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    child = student(date_of_birth=birthday(15), parent_name="Anita Das", parent_contact="anita@example.com")
    adult = student()
    support = signed_in(make_staff(roles.SUPPORT))
    assert support.post(f"{USERS}{child.pk}/resend-verification/").status_code == 200
    assert any(message.to == ["anita@example.com"] for message in mail.outbox)
    assert support.post(f"{USERS}{adult.pk}/resend-verification/").status_code == 400
    ConsentRecord.objects.create(user=child, by_parent=True, notice_version="1", verified_at="2026-10-01T00:00Z")
    assert support.post(f"{USERS}{child.pk}/resend-verification/").status_code == 400  # confirmed now


def impersonate(user, customer, **body):
    return signed_in(user).post(f"{USERS}{customer.pk}/impersonate/",
                                {"reason": "Sees an empty cart", "ticket": "HD-42", **body}, format="json")  # fmt: skip


def test_logging_in_as_a_customer_gives_a_15_minute_token_logged_and_alerted(
    settings, django_capture_on_commit_callbacks
):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    customer, support = student(date_of_birth=birthday(30)), make_staff(roles.SUPPORT)
    with django_capture_on_commit_callbacks(execute=True):
        response = impersonate(support, customer)
    assert response.status_code == 200
    token = response.json()["token"]
    data = services.read_impersonation_token(token)
    started = events("user.impersonation_started").get()
    assert data == {"staff": support.pk, "user": customer.pk, "event": started.pk}
    assert started.details["ticket"] == "HD-42" and started.reason == "Sees an empty cart"
    assert any("logs in as customer" in message.subject for message in mail.outbox)
    with pytest.MonkeyPatch.context() as patch:
        later = time.time() + 16 * 60
        patch.setattr(time, "time", lambda: later)
        assert services.read_impersonation_token(token) is None  # 15 minutes
    ended = signed_in(support, reauth=False).post(f"{USERS}{customer.pk}/impersonate/end/", {"token": token},
                                                  format="json")  # fmt: skip
    assert ended.status_code == 204 and events("user.impersonation_ended").get().details == {"started": started.pk}
    assert signed_in(support, reauth=False).post(f"{USERS}{customer.pk}/impersonate/").status_code == 403  # reauth
    panel = signed_in(support)  # the panel's session shows its banner while the token lasts
    body = {"reason": "Sees an empty cart", "ticket": "HD-42"}
    token = panel.post(f"{USERS}{customer.pk}/impersonate/", body, format="json").json()["token"]
    banner = panel.get(STAFF + "session/").json()["impersonating"]
    assert banner["user_id"] == customer.pk and "•••" in banner["email"] and banner["until"]
    panel.post(f"{USERS}{customer.pk}/impersonate/end/", {"token": token}, format="json")
    assert panel.get(STAFF + "session/").json()["impersonating"] is None


def test_children_and_staff_are_never_impersonated():
    support = make_staff(roles.SUPPORT)
    child = student(date_of_birth=birthday(15), parent_name="A", parent_contact="anita@example.com")
    assert impersonate(support, child).status_code == 403
    staff = make_staff(roles.SALES)
    assert impersonate(support, staff).status_code == 404  # users/ has customers only
    assert not events("user.impersonation_started").exists()


def test_while_impersonating_payments_passwords_and_the_account_are_refused():
    customer = student()
    browser = Client()
    browser.force_login(customer)
    session = browser.session
    session[IMPERSONATING] = {"staff": 1, "event": 1}
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": time.time()}]
    session.save()
    for url in ["/api/v1/orders/", "/api/v1/auth/password/change/", "/api/v1/me/deletion/", "/api/v1/addresses/",
                "/_allauth/browser/v1/account/password/change", "/_allauth/browser/v1/account/email"]:  # fmt: skip
        response = browser.post(url, {}, content_type="application/json")
        assert (response.status_code, response.json()["code"]) == (403, "impersonating"), url
    assert browser.get("/api/v1/me/").status_code == 200  # reading is the point
    assert browser.get("/api/v1/orders/").status_code == 200


def test_a_customers_second_factor_reset_by_support_waits_for_another(rzp):
    customer = UserFactory()
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    TOTP.activate(customer, generate_totp_secret())
    support, other = make_staff(roles.SUPPORT), make_staff(roles.SUPPORT)
    change = signed_in(support).post(f"{USERS}{customer.pk}/reset-mfa/", {"reason": "Lost phone, ID checked"}).json()
    url = f"{STAFF}change-requests/{change['id']}/"
    signed_in(other).post(url + "approve/", {"payload_sha256": change["payload_sha256"]})
    result = signed_in(support).post(url + "execute/").json()
    assert result["status"] == "executed" and not customer.authenticator_set.exists()
    assert any(
        message.to == [customer.email] and "second factor was reset" in message.subject for message in mail.outbox
    )
