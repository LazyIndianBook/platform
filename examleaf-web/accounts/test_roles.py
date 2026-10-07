"""Roles (groups and their permissions), sign-up as a student, and teacher access."""

import pytest
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
    assert sales.get_all_permissions() == {"content.view_book"}  # orders and shipments come with the shop
    assert not member(roles.STUDENT).get_all_permissions() and not member(roles.TEACHER).get_all_permissions()


def test_admin_gets_every_permission_once_bootstrap_roles_has_run():
    # The migration can only give the permissions of the apps migrated before it; deploys run bootstrap_roles.
    call_command("bootstrap_roles", stdout=open("/dev/null", "w"))
    assert Group.objects.get(name=roles.ADMIN).permissions.count() == Permission.objects.count()


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
        reverse("account_signup"),
        {
            "full_name": "Rahul Das",
            "email": "rahul@example.com",
            "password1": "Brahmaputra-2027",
            "password2": "Brahmaputra-2027",
            "class_level": 12,
            "board": board.pk,
            "date_of_birth": "2010-05-01",
            "parent_name": "Anita Das",
            "parent_contact": "98640 12345",
            "consent": "on",
        },
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
    client.force_login(teacher)
    response = client.post(
        reverse("teacher_request"),
        {"school_name": "Cotton Collegiate HS School", "district": "Kamrup Metro", "subject": "Physics"},
    )
    assert response.url == reverse("account")
    assert "We are checking your request" in client.get(reverse("account")).text
    assert client.get(reverse("teacher_request")).url == reverse("account")  # one request per account
    profile = TeacherProfile.objects.get(user=teacher)
    assert not profile.verified and not teacher.is_teacher

    staff = member(roles.SUPPORT, is_staff=True)
    client.force_login(staff)
    run_action(client, "verify", [profile.pk], reverse("admin:accounts_teacherprofile_changelist"))
    profile.refresh_from_db()
    assert profile.verified and profile.verified_by == staff
    client.force_login(teacher)
    assert "You are a verified teacher" in client.get(reverse("account")).text
    assert teacher.__class__.objects.get(pk=teacher.pk).is_teacher
