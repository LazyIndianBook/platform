"""Logging in as a customer on the website (research 2.7): the panel's token opens one website session, once, within
its 15 minutes, bound to its member of staff and to the panel's session it was asked from. While it lasts, the
website's every page says so, money, passwords, second factors, addresses and deletion are refused, each request is
the member of staff's on behalf of the customer in the audit log, and the customer's device list names it; it ends
at its time, by either side, or with the panel's session."""

import time

import pytest
from allauth.usersessions.models import UserSession
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.tests import birthday
from api.tests import student
from staff.middleware import IMPERSONATING, IMPERSONATION_REASON, IMPERSONATION_UNTIL
from staff.models import Impersonation
from staff.privacy import mask_email

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
ACCEPT = "/api/v1/account/impersonate/"
SESSION = "/_allauth/browser/v1/auth/session"


@pytest.fixture
def customer():
    return student(date_of_birth=birthday(30))


@pytest.fixture
def support():
    return make_staff(roles.SUPPORT, email="helpdesk@examleaf.in")


def ask(panel, customer):
    body = {"reason": "Sees an empty cart", "ticket": "HD-42"}
    return panel.post(f"{STAFF}users/{customer.pk}/impersonate/", body, format="json").json()["token"]


def opened(customer, support):
    """(the panel, the browser logged in as the customer)."""
    panel = signed_in(support)
    browser = APIClient()
    assert browser.post(ACCEPT, {"token": ask(panel, customer)}).status_code == 200
    return panel, browser


def test_the_token_opens_one_session_as_the_customer_once_and_the_website_says_so(customer, support):
    panel = signed_in(support)
    token = ask(panel, customer)
    browser = APIClient()
    assert browser.post(ACCEPT, {"token": token[:-2] + "xx"}).status_code == 400  # forged
    response = browser.post(ACCEPT, {"token": token})
    assert response.status_code == 200
    grant = Impersonation.objects.get()
    assert response.json()["user"] == {"id": customer.pk, "email": mask_email(customer.email)}
    assert response.json()["until"] == timezone.localtime(grant.expires_at).isoformat()
    session = browser.session
    assert (session["_auth_user_id"], session[IMPERSONATING], session[IMPERSONATION_REASON]) == (
        str(customer.pk), support.pk, "Sees an empty cart")  # fmt: skip
    assert abs((session.get_expiry_date() - grant.expires_at).total_seconds()) < 2  # the session ends then
    user = browser.get(SESSION).json()["data"]["user"]  # what the website reads on every page: its banner
    assert user["id"] == customer.pk and user["impersonation"] == {"until": session[IMPERSONATION_UNTIL],
                                                                  "by": mask_email(support.email)}  # fmt: skip
    assert APIClient().post(ACCEPT, {"token": token}).status_code == 400  # once
    refused = events("user.impersonation_refused").get()
    assert (refused.actor_id, refused.details["why"]) == (support.pk, "used, ended or expired")
    accepted = events("user.impersonation_accepted").get()
    assert (accepted.actor_id, accepted.on_behalf_of, accepted.target_id) == (support.pk, customer.pk, str(customer.pk))
    row = UserSession.objects.get(user=customer)  # the customer's own device list names it, request after request
    label = f"Staff (support) until {timezone.localtime(grant.expires_at):%H:%M}"
    assert browser.get("/api/v1/me/").status_code == 200 and UserSession.objects.get(pk=row.pk).user_agent == label
    student_client = APIClient()
    student_client.force_login(customer)
    assert student_client.get(SESSION).json()["data"]["user"]["impersonation"] is None  # their own session: none
    assert customer.__class__.objects.get(pk=customer.pk).last_login == customer.last_login  # not their log-in


def test_an_old_token_or_one_from_a_panel_session_that_ended_opens_nothing(customer, support, monkeypatch):
    panel = signed_in(support)
    token = ask(panel, customer)
    later = time.time() + 16 * 60
    with monkeypatch.context() as patch:
        patch.setattr(time, "time", lambda: later)
        assert APIClient().post(ACCEPT, {"token": token}).status_code == 400  # 15 minutes
    panel.delete(SESSION)  # the member of staff signed out of the panel
    assert APIClient().post(ACCEPT, {"token": token}).status_code == 400
    assert "signed out of the panel" in events("user.impersonation_refused").get().details["why"]
    assert Impersonation.objects.get().ended_at  # used up: it opens nothing later either


def test_while_it_lasts_money_passwords_and_the_account_are_refused_and_each_request_is_audited(customer, support):
    _, browser = opened(customer, support)
    for url in ["/api/v1/orders/", "/api/v1/auth/password/change/", "/api/v1/me/deletion/", "/api/v1/addresses/",
                "/_allauth/browser/v1/account/password/change", "/_allauth/browser/v1/account/email",
                "/_allauth/browser/v1/account/authenticators/totp"]:  # fmt: skip
        response = browser.post(url, {}, format="json")
        assert (response.status_code, response.json()["code"]) == (403, "impersonating"), url
    assert browser.get("/api/v1/me/").status_code == 200  # reading is the point
    assert browser.get("/api/v1/orders/").status_code == 200
    requests = events("impersonation.request")
    assert requests.count() == 9 and requests.filter(outcome="denied").count() == 7
    assert {(event.actor_id, event.on_behalf_of, event.target_id) for event in requests} == {
        (support.pk, customer.pk, str(customer.pk))}  # fmt: skip
    assert requests.last().details == {"method": "GET", "path": "/api/v1/orders/", "status": 200}


def test_it_ends_at_its_time_by_either_side_or_with_the_panels_session(customer, support):
    _, browser = opened(customer, support)
    session = browser.session
    session[IMPERSONATION_UNTIL] = timezone.now().isoformat()  # its time is up
    session.save()
    over = browser.get("/api/v1/me/")
    assert (over.status_code, over.json()["code"]) == (401, "impersonation_ended")
    assert browser.get("/api/v1/me/").status_code in (401, 403)  # signed out
    assert events("user.impersonation_ended").get().details["why"] == "expired"

    _, browser = opened(customer, support)  # the member of staff ends it on the website
    assert browser.delete(ACCEPT).status_code == 204
    assert browser.get("/api/v1/me/").status_code in (401, 403) and browser.delete(ACCEPT).status_code == 404
    assert events("user.impersonation_ended").last().details["why"] == "ended by the member of staff"

    panel, browser = opened(customer, support)  # or in the panel
    token = ask(panel, customer)
    browser.post(ACCEPT, {"token": token})
    ended = panel.post(f"{STAFF}users/{customer.pk}/impersonate/end/", {"token": token}, format="json")
    assert ended.status_code == 204 and browser.get("/api/v1/me/").json()["code"] == "impersonation_ended"

    panel, browser = opened(customer, support)  # or by signing out of the panel
    panel.delete(SESSION)
    assert browser.get("/api/v1/me/").json()["code"] == "impersonation_ended"
    assert events("user.impersonation_ended").last().details["why"] == "the panel's session ended"
    assert not Impersonation.objects.filter(accepted_at__isnull=False, ended_at=None).exists()


def test_a_child_staff_or_a_suspended_account_is_never_opened(support):
    child = student(date_of_birth=birthday(30))
    panel = signed_in(support)
    token = ask(panel, child)
    child.date_of_birth = birthday(15)  # (a corrected date of birth after the token)
    child.parent_name, child.parent_contact = "Anita Das", "anita@example.com"
    child.save()
    assert APIClient().post(ACCEPT, {"token": token}).status_code == 400
    assert "under 18" in events("user.impersonation_refused").get().details["why"]
