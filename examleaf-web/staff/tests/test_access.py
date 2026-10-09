"""What a role and a person may do (research 1.8): the role catalogue, the Access tab, a role change's preview (gains,
losses, limits, conflicts) that changes nothing, temporary grants ended by the nightly task once; the passkey the
privileged roles need first; a person's own sessions, ended one by one or all at once, and the offer after a second
factor changed; the per-staff throttles; an API key never acting as staff."""

from datetime import timedelta

import pytest
from allauth.mfa import signals as mfa_signals
from allauth.mfa.models import Authenticator
from allauth.usersessions.models import UserSession
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import roles
from accounts.factories import UserFactory
from staff import audit
from staff.models import ApiKey, AuditEvent, ChangeRequest, InboxItem, RoleGrant, StaffScope
from staff.permissions import make_key
from staff.tasks import expire_access

from .conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
PEOPLE = STAFF + "people/"


def test_the_role_catalogue_says_what_each_role_is_for_and_what_it_holds():
    make_staff(roles.SUPPORT), make_staff(roles.SUPPORT), make_staff(roles.FINANCE)
    catalogue = {row["name"]: row for row in signed_in(make_staff(roles.ADMIN)).get(PEOPLE + "roles/").json()}
    assert set(catalogue) == roles.STAFF_ROLES and list(catalogue)[0] == roles.OWNER
    support, finance = catalogue[roles.SUPPORT], catalogue[roles.FINANCE]
    assert support["members"] == 2 and support["card"]["for"] and support["card"]["cannot"]
    assert support["limits"]["refund_inr"] == 1_000 and not support["passkey"] and finance["passkey"]
    assert set(finance["conflicts"]) == {roles.PACKER, roles.MARKETING, roles.AUDITOR}
    areas = {area["area"]: area["permissions"] for area in support["capabilities"]}
    reveal = next(row for row in areas["Customers"] if row["perm"] == "staff.reveal_contact")
    assert reveal["risk"] == "high" and reveal["reauth"]
    assert catalogue[roles.OWNER]["limits"]["refund_inr"] is None and finance["erp_profiles"] == ["EL Finance"]
    assert signed_in(make_staff(roles.SALES)).get(PEOPLE + "roles/").status_code == 403


def test_the_access_tab_shows_grants_scopes_limits_and_the_last_use_of_risky_permissions():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    until = timezone.now() + timedelta(days=3)
    RoleGrant.objects.create(user=person, role=roles.SUPPORT, granted_by=owner, reason="Help desk", expires_at=until)
    StaffScope.objects.create(user=person, kind="subject", value="PHY", granted_by=owner)
    audit.record("user.revealed", actor=person, permission="staff.reveal_contact")
    audit.record("user.viewed", actor=person, permission="accounts.view_user")  # low risk: no last use shown
    ChangeRequest.objects.create(action="order.refund", payload={}, payload_sha256="0", maker=person, reason="r",
                                 expires_at=until)  # fmt: skip
    access = signed_in(owner).get(f"{PEOPLE}{person.pk}/access/").json()
    [role] = access["roles"]
    assert (role["source"], role["granted_by"], role["reason"]) == ("panel", owner.pk, "Help desk")
    assert role["expires_at"] and access["scopes"][0]["value"] == "PHY" and access["limits"]["refund_inr"] == 1_000
    permissions = {row["perm"]: row for area in access["capabilities"] for row in area["permissions"]}
    assert permissions["staff.reveal_contact"]["last_used"] and permissions["accounts.view_user"]["last_used"] is None
    assert access["pending"][0]["by_them"] and access["second_factors"]["authenticator_app"]
    assert access["passkey_required"] is False


def test_a_preview_shows_gains_losses_limits_and_conflicts_and_changes_nothing():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    client, url = signed_in(owner), f"{PEOPLE}{person.pk}/roles/preview/"
    grant = client.post(url, {"role": roles.FINANCE}, format="json").json()
    gained = {row["perm"] for area in grant["gains"] for row in area["permissions"]}
    assert "staff.approve_refund" in gained and grant["losses"] == []
    assert {"name": "refund_inr", "before": 1_000, "after": 10_000} in grant["limits"]
    assert grant["needs_approval"] and grant["checker"] == "staff.approve_role_change" and not grant["blocked"]
    assert grant["erp_profiles"] == {"before": [], "after": ["EL Finance"]}
    revoke = client.post(url, {"role": roles.SUPPORT, "action": "revoke"}, format="json").json()
    assert "staff.reveal_contact" in {row["perm"] for area in revoke["losses"] for row in area["permissions"]}
    finance = make_staff(roles.FINANCE)
    conflict = client.post(f"{PEOPLE}{finance.pk}/roles/preview/", {"role": roles.PACKER}, format="json").json()
    assert conflict["blocked"] and conflict["conflicts"][0]["roles"] == [roles.FINANCE, roles.PACKER]
    assert client.post(url, {"role": roles.PACKER, "action": "revoke"}, format="json").status_code == 400
    assert person.groups.count() == 1 and not AuditEvent.objects.filter(action__startswith="role.").exists()


def test_a_temporary_role_is_taken_away_once_by_the_nightly_task_with_a_note_to_the_owner():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    until = (timezone.now() + timedelta(days=7)).isoformat()
    grant = {"role": roles.SALES, "reason": "Cover for a week", "expires_at": until}
    response = signed_in(owner).post(f"{PEOPLE}{person.pk}/roles/", grant, format="json")
    assert response.status_code in (200, 201), response.content
    assert person.groups.filter(name=roles.SALES).exists()
    RoleGrant.objects.filter(user=person, role=roles.SALES).update(expires_at=timezone.now() - timedelta(minutes=1))
    expire_access()
    expire_access()  # again: nothing more to take, no second note
    assert not person.groups.filter(name=roles.SALES).exists() and person.groups.filter(name=roles.SUPPORT).exists()
    [item] = InboxItem.objects.filter(kind="role_expired")
    assert item.permission == "staff.assign_role" and item.data == {"roles": [roles.SALES]}
    removed = AuditEvent.objects.filter(action="authz_change", target_id=str(person.pk), details__removed=[roles.SALES])
    assert removed.count() == 1 and removed.get().reason == "Its time was over."


def test_a_privileged_member_without_a_passkey_adds_one_before_anything_else():
    finance = make_staff(roles.FINANCE, passkey=False)
    client = signed_in(finance)
    manifest = client.get(STAFF + "session/").json()
    assert manifest["steps"] == ["passkey_required"]
    refused = client.get(STAFF + "inbox/")
    assert refused.status_code == 403 and refused.json()["code"] == "passkey_required"
    assert client.get(PEOPLE + "me/sessions/").status_code == 200  # their own sessions stay theirs
    assert signed_in(make_staff(roles.SUPPORT, passkey=False)).get(STAFF + "session/").json()["steps"] == []
    Authenticator.objects.create(user=finance, type=Authenticator.Type.WEBAUTHN, data={"name": "YubiKey"})
    assert signed_in(finance).get(STAFF + "session/").json()["steps"] == []
    assert signed_in(finance).get(STAFF + "inbox/").status_code == 200


def test_own_sessions_are_listed_and_ended_one_by_one_or_all_but_this_one():
    person = make_staff(roles.SUPPORT)
    here, phone, tablet = signed_in(person), signed_in(person), signed_in(person)
    firefox = "Mozilla/5.0 (Macintosh) Firefox/131.0"
    here.defaults.update(HTTP_USER_AGENT=firefox, REMOTE_ADDR="203.0.113.7")  # each request says which device
    for client, agent in [(phone, "Mozilla/5.0 (Linux; Android 14) Chrome/129.0 Mobile"), (tablet,
                          "Mozilla/5.0 (iPad) Safari/604.1")]:  # fmt: skip
        client.get(STAFF + "session/", HTTP_USER_AGENT=agent, REMOTE_ADDR="203.0.113.7")
    sessions = here.get(PEOPLE + "me/sessions/").json()
    assert len(sessions) == 3 and sum(row["current"] for row in sessions) == 1
    devices = {(row["browser"], row["system"]) for row in sessions}
    assert devices == {("Firefox", "macOS"), ("Chrome", "Android"), ("Safari", "iOS")}
    assert all(row["place"] != "203.0.113.7" for row in sessions)  # the address cut short
    current = next(row["id"] for row in sessions if row["current"])
    assert here.post(f"{PEOPLE}me/sessions/{current}/end/").status_code == 400  # this one: sign out instead
    other = next(row["id"] for row in sessions if not row["current"])
    assert here.post(f"{PEOPLE}me/sessions/{other}/end/").status_code == 204
    assert here.post(f"{PEOPLE}me/sessions/{other}/end/").status_code == 404
    RefreshToken.for_user(person)  # the app's
    assert here.post(PEOPLE + "me/sessions/end-others/").json() == {"sessions": 1, "tokens": 1}
    assert UserSession.objects.filter(user=person).count() == 1
    assert phone.get(STAFF + "session/").status_code == 401 and tablet.get(STAFF + "session/").status_code == 401
    assert here.get(STAFF + "session/").status_code == 200
    stranger = make_staff(roles.SUPPORT)
    assert signed_in(stranger).post(f"{PEOPLE}me/sessions/{current}/end/").status_code == 404  # not theirs
    assert AuditEvent.objects.filter(action="session_ended_by_self").count() == 2


def test_after_a_second_factor_changes_the_manifest_offers_once_to_end_the_other_sessions():
    person = make_staff(roles.SUPPORT)
    client = signed_in(person)
    assert client.get(STAFF + "session/").json()["offer_end_sessions"] is False
    mfa_signals.authenticator_added.send(sender=Authenticator, request=None, user=person, authenticator=None)
    assert client.get(STAFF + "session/").json()["offer_end_sessions"] is True
    assert client.get(STAFF + "session/").json()["offer_end_sessions"] is False  # once
    mfa_signals.authenticator_removed.send(sender=Authenticator, request=None, user=UserFactory(), authenticator=None)
    assert client.get(STAFF + "session/").json()["offer_end_sessions"] is False  # a customer's: no offer to staff


@pytest.mark.parametrize(
    ("scope", "who", "method", "path", "body"),
    [
        ("staff_bulk", roles.ADMIN, "post", "jobs/", {"kind": "bulk_action"}),
        ("staff_export", roles.OWNER, "post", "jobs/", {"kind": "audit_export"}),
        ("staff_search", roles.SUPPORT, "get", "users/?search=rahul", None),
    ],
)
def test_the_per_staff_throttles_answer_429_at_their_limits(monkeypatch, scope, who, method, path, body):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, "2/hour")
    client = signed_in(make_staff(who))
    statuses = [getattr(client, method)(STAFF + path, body, format="json").status_code for _ in range(3)]
    assert statuses[2] == 429 and 429 not in statuses[:2], statuses
    assert signed_in(make_staff(who)).get(STAFF + "session/").status_code == 200  # per member of staff


def test_an_api_key_is_never_staff_and_a_key_widened_by_hand_is_refused():
    owner = make_staff(roles.OWNER)
    key, prefix, digest = make_key()
    row = ApiKey.objects.create(name="Reports", prefix=prefix, secret_hash=digest, scopes=["accounts.view_user"],
                                sponsor=owner, expires_at=timezone.now() + timedelta(days=30))  # fmt: skip
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    assert client.get(STAFF + "users/").status_code == 200
    assert client.get(STAFF + "session/").status_code == 403  # the manifest is a person's
    ApiKey.objects.filter(pk=row.pk).update(scopes=["accounts.view_user", "staff.refund_order"])
    refused = client.get(STAFF + "users/")
    assert refused.status_code == 401 and "more than catalogued view permissions" in refused.json()["detail"]
    assert not get_user_staff_rows(key)


def get_user_staff_rows(key):
    """No user row was made for a key, and none is staff because of it."""
    from accounts.models import User

    return User.objects.filter(email__icontains=key[:12]).exists()
