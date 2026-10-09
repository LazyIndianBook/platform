"""Staff management (research 6, 2.9): invitations, roles (given by an owner; ADMIN sees them) with separation of
duties and a second person's approval for the privileged ones, just-in-time roles that expire, scopes, sessions ended,
offboarding in one step, the access review."""

import re
from datetime import timedelta

import pytest
from allauth.usersessions.models import UserSession
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import User
from staff import audit
from staff.models import ApiKey, ChangeRequest, RoleGrant, StaffInvite, StaffScope
from staff.tasks import expire_access

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
PEOPLE = STAFF + "people/"


def grant(actor, person, role, **body):
    return signed_in(actor).post(f"{PEOPLE}{person.pk}/roles/", {"role": role, "reason": "Joins the team", **body},
                                 format="json")  # fmt: skip


def test_a_role_is_given_with_who_why_and_until_when_and_ssd_refuses_a_conflicting_one():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    assert grant(make_staff(roles.ADMIN), person, roles.PACKER).status_code == 403  # ADMIN sees roles, owners give them
    until = timezone.now() + timedelta(days=3)
    response = grant(owner, person, roles.PACKER, expires_at=until.isoformat())
    assert response.status_code == 200 and roles.PACKER in response.json()["roles"]
    row = RoleGrant.objects.get(user=person, role=roles.PACKER)
    assert (row.granted_by, row.reason) == (owner, "Joins the team")
    assert abs(row.expires_at - until) < timedelta(milliseconds=1)  # (kept to the millisecond, as the payload is)
    change = events("authz_change", target_id=str(person.pk)).last()
    assert change.details["added"] == [roles.PACKER] and change.reason == "Joins the team"
    refused = grant(make_staff(roles.OWNER), person, roles.FINANCE)  # FINANCE ✕ PACKER
    assert refused.status_code == 400 and "separation of duties" in refused.json()["role"][0]
    assert grant(owner, person, roles.AUDITOR).status_code == 400  # the auditor holds nothing else


def test_a_privileged_role_waits_for_a_second_person_and_so_does_any_role_for_yourself(
    settings, django_capture_on_commit_callbacks
):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    owner, person, admin = make_staff(roles.OWNER), make_staff(roles.SUPPORT), make_staff(roles.ADMIN)
    asked = grant(owner, person, roles.FINANCE)
    assert asked.status_code == 202 and "privileged role" in asked.json()["rule"]
    assert not User.objects.get(pk=person.pk).groups.filter(name=roles.FINANCE).exists()
    change = asked.json()
    url = f"{STAFF}change-requests/{change['id']}/"
    assert signed_in(owner).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}).status_code == 403
    finance = make_staff(roles.FINANCE)
    assert signed_in(finance).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}).status_code == 403
    signed_in(admin).post(url + "approve/", {"payload_sha256": change["payload_sha256"]})  # ADMIN approves roles
    with django_capture_on_commit_callbacks(execute=True):
        done = signed_in(owner).post(url + "execute/").json()
    assert done["status"] == "executed" and User.objects.get(pk=person.pk).groups.filter(name=roles.FINANCE).exists()
    assert events("authz_change", change_request_id=change["id"]).exists()
    assert any("FINANCE given to user" in message.subject for message in mail.outbox)  # an alert
    me = grant(owner, owner, roles.PACKER)  # just-in-time elevation: a second person approves it
    assert me.status_code == 202 and "for yourself" in me.json()["rule"]


def test_a_role_given_until_a_time_and_a_scope_are_taken_away_when_it_passes():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    grant(owner, person, roles.PACKER, expires_at=(timezone.now() + timedelta(hours=1)).isoformat())
    StaffScope.objects.create(
        user=person, kind="subject", value="PHY", expires_at=timezone.now() - timedelta(minutes=1)
    )
    RoleGrant.objects.filter(user=person, role=roles.PACKER).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_access() == {"roles": 1, "scopes": 1, "change_requests": 0, "job_files": 0}
    person = User.objects.get(pk=person.pk)
    assert person.role_names == {roles.SUPPORT} and person.is_staff and not StaffScope.objects.exists()
    assert events("authz_change", target_id=str(person.pk)).filter(details__expired=True).exists()


def test_a_role_is_taken_away_at_once_and_the_last_one_closes_the_admin():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    response = signed_in(owner).delete(f"{PEOPLE}{person.pk}/roles/{roles.SUPPORT}/?reason=Moved")
    assert response.status_code == 200 and response.json()["roles"] == []
    assert not User.objects.get(pk=person.pk).is_staff  # no staff role left: the person is a customer again
    assert signed_in(owner).delete(f"{PEOPLE}{person.pk}/roles/{roles.SUPPORT}/").status_code == 404


def test_only_owners_change_access_and_only_a_break_glass_account_a_break_glass_accounts():
    owner, sealed = make_staff(roles.OWNER), make_staff(is_superuser=True)
    assert grant(owner, sealed, roles.SUPPORT).status_code == 403  # a break-glass account: by another one only
    assert signed_in(owner).post(f"{PEOPLE}{sealed.pk}/offboard/", {"reason": "x"}).status_code == 403
    admin, partner = make_staff(roles.ADMIN), make_staff(roles.OWNER)
    assert grant(admin, partner, roles.SUPPORT).status_code == 403  # ADMIN sees roles; owners give them (plan 4.1)
    assert signed_in(admin).post(f"{PEOPLE}{partner.pk}/offboard/", {"reason": "x"}).status_code == 403
    assert signed_in(admin).delete(f"{PEOPLE}{partner.pk}/roles/{roles.OWNER}/").status_code == 403
    assert events("authz_fail", actor_id=admin.pk).count() == 3
    assert signed_in(owner).delete(f"{PEOPLE}{partner.pk}/roles/{roles.OWNER}/").status_code == 200


def test_scopes_are_given_and_taken_away():
    owner, editor = make_staff(roles.OWNER), make_staff(roles.CONTENT_EDITOR)
    added = signed_in(owner).post(f"{PEOPLE}{editor.pk}/scopes/", {"kind": "subject", "value": "PHY"}, format="json")
    assert added.status_code == 201
    assert signed_in(owner).post(f"{PEOPLE}{editor.pk}/scopes/", {"kind": "subject", "value": "PHY"}).status_code == 400
    assert signed_in(editor).get(STAFF + "session/").json()["scopes"] == {"subject": ["PHY"]}
    assert signed_in(owner).delete(f"{PEOPLE}{editor.pk}/scopes/{added.json()['id']}/").status_code == 204
    assert [event.details["added"] for event in events("authz_change", target_id=str(editor.pk))][-2:] == [True, False]


def test_an_invitation_is_emailed_once_accepted_by_a_new_account_or_the_signed_in_one(
    django_capture_on_commit_callbacks,
):
    owner = make_staff(roles.OWNER)  # owners invite
    response = signed_in(owner).post(f"{PEOPLE}invite/", {"email": "Packer@Examleaf.in", "role": roles.PACKER,
                                                          "reason": "The new packer"}, format="json")  # fmt: skip
    assert response.status_code == 201 and response.json()["email"] == "pa•••@examleaf.in"
    [invitation] = [message for message in mail.outbox if message.to == ["packer@examleaf.in"]]
    token = re.search(r"/invite/([\w-]+)/", invitation.body).group(1)
    invite = StaffInvite.objects.get()
    assert invite.token_hash != token and token not in str(audit.AuditEvent.objects.values_list("details"))
    accept = APIClient().post(STAFF + "invites/accept/", {"token": token, "full_name": "Bikash Das",
                                                          "password": "Lakhimpur-2027"}, format="json")  # fmt: skip
    assert accept.status_code == 200, accept.content
    user = User.objects.get(email="packer@examleaf.in")
    assert user.is_staff and user.role_names == {roles.PACKER} and user.emailaddress_set.get().verified
    assert APIClient().post(STAFF + "invites/accept/", {"token": token}, format="json").status_code == 400  # once
    existing = UserFactory(email="teacher@examleaf.in")
    signed_in(owner).post(f"{PEOPLE}invite/", {"email": existing.email, "role": roles.REVIEWER, "reason": "Reviews"})
    token = re.search(r"/invite/([\w-]+)/", mail.outbox[-1].body).group(1)
    stranger = APIClient().post(STAFF + "invites/accept/", {"token": token, "full_name": "X", "password": "Y"})
    assert stranger.status_code in (401, 403)  # an account has the address: it logs in first
    from allauth.account.models import EmailAddress

    EmailAddress.objects.create(user=existing, email=existing.email, verified=True, primary=True)
    client = APIClient()
    client.force_login(existing)
    assert client.post(STAFF + "invites/accept/", {"token": token}, format="json").status_code == 200
    assert User.objects.get(pk=existing.pk).role_names == {roles.REVIEWER}
    privileged = signed_in(owner).post(f"{PEOPLE}invite/", {"email": "cfo@examleaf.in", "role": roles.FINANCE,
                                                            "reason": "Our accountant"}, format="json")  # fmt: skip
    assert privileged.status_code == 202 and not StaffInvite.objects.filter(email="cfo@examleaf.in").exists()


def test_ending_a_members_sessions_signs_them_out_everywhere():
    owner, person = make_staff(roles.OWNER), make_staff(roles.SUPPORT)
    browser = signed_in(person)
    assert browser.get(STAFF + "session/").status_code == 200  # the device list records the session
    refresh = RefreshToken.for_user(person)
    ended = signed_in(owner).post(f"{PEOPLE}{person.pk}/end-sessions/").json()
    assert ended == {"sessions": 1, "tokens": 1}
    assert browser.get(STAFF + "session/").status_code == 401 and not UserSession.objects.filter(user=person).exists()
    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()


def test_offboarding_takes_everything_away_in_one_step(settings, django_capture_on_commit_callbacks):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    owner, person = make_staff(roles.OWNER), make_staff(roles.SALES, roles.SUPPORT)
    browser = signed_in(person)
    browser.get(STAFF + "session/")
    StaffScope.objects.create(user=person, kind="school", value="Cotton")
    key = ApiKey.objects.create(name="Courier", prefix="k1", secret_hash="0" * 64, scopes=["shop.view_order"],
                                sponsor=person, expires_at=timezone.now() + timedelta(days=9))  # fmt: skip
    soon = timezone.now() + timedelta(days=1)
    change = ChangeRequest.objects.create(
        action="order.refund", payload={}, payload_sha256="0", maker=person, reason="r", expires_at=soon
    )
    with django_capture_on_commit_callbacks(execute=True):
        done = signed_in(owner).post(f"{PEOPLE}{person.pk}/offboard/", {"reason": "Left the company"}).json()
    assert done == {"roles": [roles.SALES, roles.SUPPORT], "scopes": 1, "api_keys": 1, "change_requests": 1,
                    "sessions": 1, "tokens": 0}  # fmt: skip
    person = User.objects.get(pk=person.pk)
    assert not (person.is_active or person.is_staff) and not person.groups.exists()
    assert ApiKey.objects.get(pk=key.pk).revoked_at and ChangeRequest.objects.get(pk=change.pk).status == "expired"
    assert browser.get(STAFF + "session/").status_code == 401
    assert events("user.offboarded").get().reason == "Left the company"
    assert any("offboarded" in message.subject for message in mail.outbox)
    assert signed_in(owner).post(f"{PEOPLE}{owner.pk}/offboard/", {"reason": "x"}).status_code == 403  # not oneself


def test_the_access_review_lists_roles_last_log_ins_and_unused_permissions():
    admin, sales = make_staff(roles.ADMIN), make_staff(roles.SALES)
    audit.record("order.refund.requested", actor=sales, permission="staff.refund_order")
    review = {row["email"]: row for row in signed_in(admin).get(STAFF + "access-review/").json()}
    row = review[sales.email]
    assert row["roles"] == [roles.SALES] and row["mfa"] and row["dormant"]  # never logged in
    assert "staff.refund_order" in row["last_used"] and "staff.refund_order" not in row["unused"]
    assert "staff.record_offline_payment" in row["unused"] and not any(".view_" in perm for perm in row["unused"])
    assert signed_in(sales).get(STAFF + "access-review/").status_code == 403
