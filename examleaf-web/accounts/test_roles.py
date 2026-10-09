"""Roles (groups and their permissions), sign-up as a student, and teacher access."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.urls import reverse

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import ConsentRecord, TeacherProfile
from content.tests import make_paper
from pages.models import Page

pytestmark = pytest.mark.django_db


def member(*role_names, **fields):
    user = UserFactory(**fields)
    user.groups.set(Group.objects.filter(name__in=role_names))
    return user


def test_each_role_has_its_permissions_and_nothing_more():
    editor, support, sales = member(roles.CONTENT_EDITOR), member(roles.SUPPORT), member(roles.SALES)
    assert editor.has_perms(["content.change_question", "content.add_solution", "pages.change_page"])
    assert not editor.has_perm("content.delete_paper") and not editor.has_perm("accounts.view_user")
    assert support.has_perms(
        [
            "accounts.view_user",
            "practice.view_attempt",
            "accounts.view_consentrecord",
            "accounts.change_teacherprofile",
            "account.view_emailaddress",
        ]
    )
    assert not support.has_perm("accounts.change_user") and not support.has_perm("content.change_question")
    assert sales.has_perms(["content.view_book", "shop.change_order", "shop.add_payment", "shop.change_product"])
    assert not sales.has_perm("accounts.view_user") and not sales.has_perm("shop.delete_order")
    assert support.has_perm("shop.view_order") and not support.has_perm("shop.change_order")
    assert not member(roles.STUDENT).get_all_permissions() and not member(roles.TEACHER).get_all_permissions()


def test_owner_and_admin_get_every_permission_but_their_exceptions_after_every_migrate():
    # The staff app's post_migrate receiver synced the roles when the test database was migrated (bootstrap_roles
    # does the same by hand); every app's permissions existed by then.
    superusers_only = Permission.objects.filter(content_type__app_label__in=roles.SUPERUSER_ONLY).exclude(
        codename__startswith="view_"
    )
    beyond_admin = [perm.split(".")[1] for perm in [*roles.OWNER_ONLY, *roles.MONEY_APPROVALS]]
    owners = Permission.objects.filter(content_type__app_label="staff", codename__in=beyond_admin)
    assert owners.count() == len(beyond_admin)  # roles and keys, the override, the audit log, money's approvals
    everything = Permission.objects.count() - superusers_only.count()  # every catalogued permission
    assert Group.objects.get(name=roles.OWNER).permissions.count() == everything
    assert Group.objects.get(name=roles.ADMIN).permissions.count() == everything - owners.count()


def test_bootstrap_roles_is_idempotent_and_undoes_changes_made_elsewhere():
    editors = Group.objects.get(name=roles.CONTENT_EDITOR)
    editors.permissions.remove(Permission.objects.get(codename="change_question"))
    editors.permissions.add(Permission.objects.get(codename="delete_user"))
    call_command("bootstrap_roles", stdout=open("/dev/null", "w"))
    call_command("bootstrap_roles", stdout=open("/dev/null", "w"))
    assert Group.objects.filter(name__in=roles.ROLES).count() == len(roles.ROLES)
    codenames = set(editors.permissions.values_list("codename", flat=True))
    assert "change_question" in codenames and "delete_user" not in codenames


def test_role_helpers_follow_group_membership():
    user = member(roles.STUDENT, roles.TEACHER)
    assert user.is_student and user.is_teacher and not user.is_editor and not user.is_admin
    assert member(roles.CONTENT_EDITOR).is_editor and member(roles.SUPPORT).is_support
    assert UserFactory(is_superuser=True).is_admin and member(roles.ADMIN).is_admin


def test_signup_makes_a_student_and_records_the_consent(client):
    board = make_paper().book.subject.board
    client.post(
        "/_allauth/browser/v1/auth/signup",  # the website's sign-up
        {
            "full_name": "Rahul Das",
            "email": "rahul@example.com",
            "password": "Brahmaputra-2027",
            "class_level": 12,
            "board": board.pk,
            "date_of_birth": "2010-05-01",
            "parent_name": "Anita Das",
            "parent_contact": "98640 12345",
            "consent": True,
        },
        content_type="application/json",
    )
    consent = ConsentRecord.objects.get()
    assert consent.user.is_student
    assert (consent.event, consent.by_parent) == ("given", True)
    assert consent.notice_version == Page.objects.get(slug="privacy").version
    assert len(consent.ip_hash) == 64 and "127.0.0.1" not in consent.ip_hash


def run_action(client, action, ids, url="/admin/accounts/user/"):
    return client.post(url, {"action": action, "_selected_action": ids}, follow=True)


def test_admin_assigns_staff_roles_with_admin_access(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    user = UserFactory()
    run_action(client, "add_role_content_editor", [user.pk])
    user.refresh_from_db()
    assert user.is_staff and user.has_role(roles.CONTENT_EDITOR)
    run_action(client, "remove_role_content_editor", [user.pk])
    user.refresh_from_db()
    assert not user.is_staff and not user.groups.exists()


def test_support_staff_cannot_hand_out_roles(client):
    client.force_login(member(roles.SUPPORT, is_staff=True))
    user = UserFactory()
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200  # may look users up
    run_action(client, "add_role_admin", [user.pk])
    assert not user.groups.exists()


def test_teacher_asks_for_access_and_staff_verify_it(client):
    teacher = member(roles.STUDENT)
    EmailAddress.objects.create(user=teacher, email=teacher.email, verified=True, primary=True)
    client.force_login(teacher)
    asked = {"school_name": "Cotton Collegiate HS School", "district": "Kamrup Metro", "subject": "Physics"}
    response = client.post("/api/v1/me/teacher/", asked, content_type="application/json")  # My account's request
    assert response.status_code == 201 and client.get("/api/v1/me/teacher/").json()["verified"] is False  # checking
    assert client.post("/api/v1/me/teacher/", asked, content_type="application/json").status_code == 400  # once
    profile = TeacherProfile.objects.get(user=teacher)
    assert not profile.verified and not teacher.is_teacher

    staff = member(roles.SUPPORT, is_staff=True)
    client.force_login(staff)
    run_action(client, "verify", [profile.pk], reverse("admin:accounts_teacherprofile_changelist"))
    profile.refresh_from_db()
    assert profile.verified and profile.verified_by == staff
    client.force_login(teacher)
    assert client.get("/api/v1/me/teacher/").json()["verified"] is True  # "You are a verified teacher"
    assert teacher.__class__.objects.get(pk=teacher.pk).is_teacher


def test_the_panels_roles_have_their_permissions_and_nothing_more():
    call_command("bootstrap_roles", stdout=open("/dev/null", "w"))
    finance, packer, reviewer = member(roles.FINANCE), member(roles.PACKER), member(roles.REVIEWER)
    marketing, auditor, rep = member(roles.MARKETING), member(roles.AUDITOR), member(roles.SALES_REP)
    assert finance.has_perms(["staff.approve_refund", "staff.record_offline_payment", "shop.view_invoice"])
    assert not finance.has_perm("shop.change_order") and not finance.has_perm("staff.assign_role")
    assert packer.has_perms(["shop.view_order", "shop.view_shipment", "staff.pack_order"])  # its scope's orders
    assert not packer.has_perm("accounts.view_user") and not packer.has_perm("shop.view_payment")  # no email, money
    assert not packer.has_perm("staff.view_changerequest") and not packer.has_perm("staff.refund_order")  # nothing else
    assert reviewer.has_perms(["staff.publish_paper", "content.view_paper"]) and not reviewer.has_perm(
        "content.change_paper"
    )
    assert marketing.has_perms(["shop.add_coupon", "shop.change_review"]) and not marketing.has_perm(
        "staff.approve_discount"
    )
    assert rep.has_perms(["shop.add_order", "shop.change_quoterequest"])
    assert not rep.has_perm("shop.add_refund") and not rep.has_perm("staff.refund_order")  # no refunds, no shipping
    assert not rep.has_perm("shop.add_shipment")
    views = Permission.objects.filter(codename__startswith="view_").count()
    assert auditor.get_all_permissions() >= {"staff.view_auditlog", "staff.export_auditlog", "accounts.view_user"}
    writes = {perm for perm in auditor.get_all_permissions() if not perm.split(".")[1].startswith("view_")}
    assert writes == {"staff.export_auditlog"} and len(auditor.get_all_permissions()) == views + 1
    assert not auditor.has_perm("staff.reveal_contact")  # no personal data revealed
    for perm in roles.OWNER_ONLY:  # the owners' own, beyond ADMIN's everything
        assert member(roles.OWNER).has_perm(perm) and not member(roles.ADMIN).has_perm(perm), perm
    for perm in roles.MONEY_APPROVALS:  # FINANCE approves money (and the owners), not ADMIN
        assert finance.has_perm(perm) and member(roles.OWNER).has_perm(perm) and not member(roles.ADMIN).has_perm(perm)
    admin = member(roles.ADMIN)  # ADMIN approves roles and exports; REVIEWER content
    assert admin.has_perms(["staff.approve_role_change", "staff.approve_export", "staff.view_staff"])
    assert admin.has_perms(["staff.view_apikey", "staff.pack_order"]) and not admin.has_perm("staff.assign_role")
    assert member(roles.OWNER).is_owner and not member(roles.ADMIN).is_owner and not member(roles.OWNER).is_superuser
    assert UserFactory(is_superuser=True).is_owner  # a break-glass account passes for one


def test_the_old_roles_keep_their_permissions_and_gain_the_panels():
    support, sales, editor = member(roles.SUPPORT), member(roles.SALES), member(roles.CONTENT_EDITOR)
    assert support.has_perms(["staff.reveal_contact", "staff.unlock_user", "staff.handle_data_request"])
    assert support.has_perms(["staff.refund_order", "staff.view_inbox", "learn.add_entitlement"])
    assert not support.has_perm("staff.approve_refund") and not support.has_perm("accounts.change_user")
    assert sales.has_perms(["shop.add_payment", "staff.refund_order", "staff.record_offline_payment"])
    # SALES does not pack, ship or approve refunds (plan 4.1): PACKER packs, FINANCE approves, SALES asks in the panel
    assert not sales.has_perm("staff.pack_order") and not sales.has_perm("shop.change_shipment")
    assert not sales.has_perm("shop.add_refund") and not sales.has_perm("staff.approve_refund")
    assert editor.has_perms(["content.change_question", "staff.view_inbox"]) and not editor.has_perm(
        "staff.view_system"
    )


def test_shipping_and_the_insights_go_to_the_roles_that_do_them():
    grants = {  # plan 5.7 and 5.16
        roles.PACKER: {"staff.view_parcels", "staff.book_parcel"},
        roles.SALES: {"staff.view_parcels", "staff.act_on_exception", "staff.view_cod"},
        roles.SUPPORT: {"staff.view_parcels"},  # "where is my parcel?"
        roles.FINANCE: {"staff.view_cod", "staff.reconcile_cod", "staff.view_insights"},
        roles.MARKETING: {"staff.view_insights"},
        roles.AUDITOR: {"staff.view_parcels", "staff.view_cod", "staff.view_insights"},  # the views
    }
    every = {"view_parcels", "book_parcel", "act_on_exception", "view_cod", "reconcile_cod", "manage_pickup_locations"}
    every = {f"staff.{name}" for name in every | {"view_insights", "acknowledge_signal"}}
    for name in roles.STAFF_ROLES:
        held = member(name).get_all_permissions() & every
        assert held == (every if name in (roles.ADMIN, roles.OWNER) else grants.get(name, set())), name


def test_limits_take_the_highest_of_a_persons_roles():
    assert roles.limit({roles.SUPPORT}, "refund_inr") == 1_000
    assert roles.limit({roles.SUPPORT, roles.SALES}, "refund_inr") == 2_000
    assert roles.limit({roles.SALES, roles.OWNER}, "refund_inr") is None  # no limit
    assert roles.limit({roles.CONTENT_EDITOR}, "refund_inr") == 0 and roles.limit(set(), "export_rows") == 0
    assert set(roles.ROLE_LIMITS) <= roles.STAFF_ROLES
    assert all(set(limits) == set(roles.LIMITS) for limits in roles.ROLE_LIMITS.values())


def test_separation_of_duties_is_warned_about_at_sync(caplog):
    assert roles.conflicts({roles.FINANCE, roles.PACKER}) == [(roles.FINANCE, roles.PACKER)]
    assert roles.conflicts({roles.AUDITOR, roles.SUPPORT}) == [(roles.AUDITOR, roles.SUPPORT)]
    assert not roles.conflicts({roles.SALES, roles.PACKER, roles.SUPPORT})
    both = member(roles.FINANCE, roles.PACKER)
    with caplog.at_level("WARNING", logger="accounts.roles"):
        call_command("bootstrap_roles", stdout=open("/dev/null", "w"))
    assert f"user #{both.pk} holds both FINANCE and PACKER" in caplog.text


def test_the_admin_stays_closed_to_staff_with_only_the_panels_roles(client):
    for user, status in [
        (member(roles.PACKER, roles.FINANCE, is_staff=True), 302),  # the staff API only: its lists are scoped
        (member(roles.PACKER, roles.SALES, is_staff=True), 200),  # SALES opens it, as before
        (UserFactory(is_staff=True), 200),  # staff without a role see an empty admin, as before
    ]:
        client.force_login(user)
        assert client.get(reverse("admin:index")).status_code == status, user.role_names
