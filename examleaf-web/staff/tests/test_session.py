"""A member of staff's session (research 1.7, 2.3): the capability manifest and the catalogue it is read with; the
idle limit (15 minutes for OWNER, ADMIN, FINANCE and PACKER, 30 for the others) and the absolute one (8 hours); a
second factor before anything; the admin host, the only one the staff API answers on."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from django.utils import timezone

from accounts import roles
from accounts.models import STAFF_SESSION
from examleaf.middleware import STAFF_LOGIN_AT, STAFF_SEEN, idle_limit
from staff.models import FeatureFlag, RoleGrant, StaffScope

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
SESSION = STAFF + "session/"


def test_the_manifest_says_what_the_panel_may_draw_and_is_never_kept():
    support = make_staff(roles.SUPPORT, roles.PACKER)
    RoleGrant.objects.create(user=support, role=roles.PACKER, expires_at=timezone.now() + timedelta(days=2))
    StaffScope.objects.create(user=support, kind="ticket_queue", value="data_request")
    FeatureFlag.objects.create(key="ERP_SYNC_ORDERS", value=True, reason="Cut over")
    client = signed_in(support)
    response = client.get(SESSION)
    assert response["Cache-Control"] == "no-store"
    data = response.json()
    assert data["user"]["email"] == support.email and not data["user"]["is_superuser"]
    assert [role["name"] for role in data["roles"]] == [roles.PACKER, roles.SUPPORT]
    assert data["roles"][0]["expires_at"] and data["roles"][1]["expires_at"] is None
    assert data["permissions"] == sorted(data["permissions"]) and "staff.reveal_contact" in data["permissions"]
    assert data["scopes"] == {"ticket_queue": ["data_request"]}
    assert data["role_scopes"] == {roles.PACKER: {"order_status": ["paid", "packed", "shipped"]}}
    assert data["limits"]["refund_inr"] == 1_000 and data["flags"] == {"ERP_SYNC_ORDERS": True}
    assert data["impersonating"] is None
    assert data["idle_timeout_s"] == 900 and data["reauth_valid_until"]  # PACKER: 15 minutes, the shorter
    version = data["manifest_version"]
    assert client.get(SESSION).json()["manifest_version"] == version  # the same while nothing changes
    support.groups.remove(*support.groups.filter(name=roles.PACKER))
    assert client.get(SESSION).json()["manifest_version"] != version  # a role went: fetch it again
    owner = signed_in(make_staff(roles.OWNER)).get(SESSION).json()
    assert [role["name"] for role in owner["roles"]] == [roles.OWNER] and owner["limits"]["refund_inr"] is None
    assert owner["idle_timeout_s"] == 900 and not owner["user"]["is_superuser"]  # the founder: a role, 15 minutes
    sealed = signed_in(make_staff(is_superuser=True)).get(SESSION).json()  # a break-glass account
    assert sealed["roles"] == [] and sealed["user"]["is_superuser"] and sealed["limits"]["refund_inr"] is None
    assert set(sealed["permissions"]) >= set(owner["permissions"])


def test_the_manifest_flags_a_deployment_that_is_not_production(settings):
    client = signed_in(make_staff(roles.SUPPORT))
    assert "test_mode" not in client.get(SESSION).json()["flags"]  # production: absent
    settings.STAFF_TEST_MODE = True  # (DEBUG's by default)
    assert client.get(SESSION).json()["flags"]["test_mode"] is True


def test_the_catalogue_endpoint_lists_permissions_and_roles():
    data = signed_in(make_staff(roles.SUPPORT)).get(STAFF + "catalogue/").json()
    by_perm = {row["perm"]: row for row in data["permissions"]}
    assert by_perm["staff.approve_refund"]["risk"] == "high" and by_perm["staff.approve_refund"]["reauth"]
    finance = next(row for row in data["roles"] if row["name"] == roles.FINANCE)
    assert roles.PACKER in finance["conflicts"] and finance["privileged"] and not finance["admin_site"]
    assert finance["limits"]["refund_inr"] == roles.ROLE_LIMITS[roles.FINANCE]["refund_inr"]
    owner = next(row for row in data["roles"] if row["name"] == roles.OWNER)
    assert owner["permissions"] == "everything"
    packer = next(row for row in data["roles"] if row["name"] == roles.PACKER)
    assert packer["scopes"] == {"order_status": ["paid", "packed", "shipped"]}


def test_the_idle_limit_is_the_shortest_of_the_persons_roles(settings):
    assert idle_limit(make_staff(roles.SUPPORT)) == idle_limit(make_staff(roles.CONTENT_EDITOR)) == 30 * 60
    for role in (roles.OWNER, roles.ADMIN, roles.FINANCE, roles.PACKER):
        assert idle_limit(make_staff(role)) == 15 * 60, role
    assert idle_limit(make_staff(roles.SUPPORT, roles.PACKER)) == 15 * 60
    assert idle_limit(make_staff(is_superuser=True)) == 15 * 60 and idle_limit(make_staff()) == 30 * 60
    settings.STAFF_IDLE_TIMEOUTS = {**settings.STAFF_IDLE_TIMEOUTS, roles.PACKER: 10 * 60}  # per role, from settings
    assert idle_limit(make_staff(roles.PACKER)) == 10 * 60


def test_an_admins_session_ends_after_15_idle_minutes():
    client = signed_in(make_staff(roles.ADMIN))
    assert client.get(SESSION).json()["idle_timeout_s"] == 900
    session = client.session
    session[STAFF_SEEN] = time.time() - 16 * 60
    session.save()
    response = client.get(SESSION)
    assert (response.status_code, response.json()["code"]) == (401, "session_idle")
    assert "15 minutes" in response.json()["detail"]


def test_a_staff_session_ends_after_30_idle_minutes():
    staff = make_staff(roles.SUPPORT)
    client = signed_in(staff)
    session = client.session
    session[STAFF_SEEN] = time.time() - 16 * 60
    session.save()
    assert client.get(SESSION).status_code == 200  # SUPPORT: 30 minutes
    assert client.get(SESSION).status_code == 200
    session = client.session
    session[STAFF_SEEN] = time.time() - 31 * 60
    session.save()
    response = client.get(SESSION)
    assert (response.status_code, response.json()["code"]) == (401, "session_idle")
    assert "30 minutes" in response.json()["detail"]
    assert client.get(SESSION).status_code == 401  # signed out
    assert events("session_expired", actor_id=staff.pk).get().details == {"why": "idle"}
    assert not events("session_logout", actor_id=staff.pk).exists()  # one event for it, not two


def test_activity_keeps_it_going_and_is_written_at_most_once_a_minute():
    client = signed_in(make_staff(roles.SUPPORT))
    client.get(SESSION)
    first = client.session[STAFF_SEEN]
    client.get(SESSION)
    assert client.session[STAFF_SEEN] == first  # within the minute: no write
    session = client.session
    session[STAFF_SEEN] = time.time() - 29 * 60
    session.save()
    assert client.get(SESSION).status_code == 200 and client.session[STAFF_SEEN] > first


def test_a_staff_session_ends_8_hours_after_its_log_in_however_busy():
    assert STAFF_SESSION == timedelta(hours=8)
    client = signed_in(make_staff(roles.SUPPORT))
    session = client.session
    session[STAFF_LOGIN_AT] = time.time() - 8 * 3600 - 1
    session[STAFF_SEEN] = time.time()
    session.save()
    response = client.get(SESSION)
    assert (response.status_code, response.json()["code"]) == (401, "session_expired")
    assert "8 hours" in response.json()["detail"]
    client = signed_in(make_staff(roles.SUPPORT))
    client.get(SESSION)
    login_at = client.session[STAFF_LOGIN_AT]
    ends = datetime.fromisoformat(client.get(SESSION).json()["absolute_expires_at"].replace("Z", "+00:00"))
    assert ends <= datetime.fromtimestamp(login_at, UTC) + timedelta(hours=8, seconds=1)


def test_an_idle_session_opens_no_admin_page_either():
    client = signed_in(make_staff(roles.SUPPORT))
    session = client.session
    session[STAFF_SEEN] = time.time() - 31 * 60
    session.save()
    response = client.get("/admin/")
    assert response.status_code == 302 and "login" in response["Location"]  # signed out: the log-in first


def test_customers_sessions_have_no_idle_limit_here():
    from api.tests import student

    client = signed_in(student())
    session = client.session
    session[STAFF_SEEN] = time.time() - 24 * 3600
    session.save()
    assert client.get("/api/v1/me/").status_code == 200


def test_a_member_of_staff_without_a_second_factor_reaches_nothing_and_that_is_logged():
    staff = make_staff(roles.ADMIN)
    staff.authenticator_set.all().delete()
    response = signed_in(staff).get(STAFF + "users/")
    assert (response.status_code, response.json()["code"]) == (403, "mfa_setup_required")
    assert events("authz_fail", actor_id=staff.pk).get().details["error"] == "mfa_setup_required"


def test_the_panels_session_needs_the_csrf_token_for_every_change():
    from django.middleware.csrf import _get_new_csrf_string
    from rest_framework.test import APIClient

    client = APIClient(enforce_csrf_checks=True)
    client.force_login(make_staff(roles.ADMIN))
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": time.time()}]
    session.save()
    assert client.get(STAFF + "session/").status_code == 200  # reading needs none
    body, url = {"value": True, "reason": "Cut over"}, f"{STAFF}flags/ERP_SYNC_ORDERS/"
    refused = client.put(url, body, format="json")
    assert refused.status_code == 403 and "CSRF" in refused.json()["detail"] and not FeatureFlag.objects.exists()
    token = _get_new_csrf_string()  # the csrftoken cookie, sent back in X-CSRFToken (API.md "Staff API")
    client.cookies["csrftoken"] = token
    assert client.put(url, body, format="json", HTTP_X_CSRFTOKEN=token).status_code == 200


def test_the_staff_api_answers_404_on_any_host_but_the_admin_host(settings):
    settings.ALLOWED_HOSTS = ["examleaf.in", "admin.examleaf.in", "testserver"]
    settings.ADMIN_HOSTS = ["admin.examleaf.in"]
    admin = make_staff(roles.ADMIN)
    client = signed_in(admin)
    public = client.get(SESSION, HTTP_HOST="examleaf.in")
    assert public.status_code == 404 and public.json() == {"detail": "Not found."}
    assert client.post(STAFF + "invites/accept/", {"token": "x"}, HTTP_HOST="examleaf.in").status_code == 404
    from rest_framework.test import APIClient

    assert APIClient().get(SESSION, HTTP_HOST="examleaf.in").status_code == 404  # signed out: the same
    assert client.get(SESSION, HTTP_HOST="admin.examleaf.in").status_code == 200
    assert client.get("/api/v1/config/", HTTP_HOST="examleaf.in").status_code == 200  # the rest of the API: anywhere
    assert not events("authz_fail", actor_id=admin.pk).exists()
    settings.ADMIN_HOSTS = []  # development: every host
    assert client.get(SESSION, HTTP_HOST="examleaf.in").status_code == 200
