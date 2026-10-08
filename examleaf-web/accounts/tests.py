import logging
import re
from datetime import date

from axes.models import AccessAttempt, AccessLog
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from content.models import Board
from content.tests import make_paper

from .models import User


def birthday(age):
    today = date.today()
    return today.replace(year=today.year - age, day=min(today.day, 28))


class SignupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_paper()
        cls.board = Board.objects.get()

    def setUp(self):
        cache.clear()  # allauth's rate limits (e.g. one confirmation email per address per 3 minutes) live in the cache

    def signup(self, age, **extra):
        data = {
            "full_name": "Rahul Das",
            "email": "rahul@example.com",
            "password1": "Brahmaputra-2027",
            "password2": "Brahmaputra-2027",
            "class_level": 12,
            "board": self.board.pk,
            "date_of_birth": birthday(age).isoformat(),
            **extra,
        }
        return self.client.post(reverse("account_signup"), data)

    def test_under_18_needs_parent_details_and_consent(self):
        response = self.signup(16)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["form"].errors), {"parent_name", "parent_contact", "consent"})
        self.assertIn("parent or guardian", response.context["form"].errors["consent"][0])
        self.assertFalse(User.objects.exists())

    def test_under_18_parent_contact_must_be_a_phone_or_email(self):
        response = self.signup(16, parent_name="Anita Das", parent_contact="12345", consent="on")
        self.assertEqual(set(response.context["form"].errors), {"parent_contact"})

    def test_under_18_with_consent_verifies_email_and_returns_to_the_paper(self):
        response = self.signup(
            16, parent_name="Anita Das", parent_contact="98640 12345", consent="on", next="/s/PHY-E01/"
        )
        user = User.objects.get()
        self.assertTrue(user.is_minor)
        self.assertEqual((user.parent_name, user.parent_contact), ("Anita Das", "+919864012345"))
        self.assertIsNotNone(user.consent_at)
        # allauth sends a code; the student types it on the page they are on and lands on the paper's solutions.
        code = re.search(r"^([A-Z0-9]{4}-[A-Z0-9]{4})$", mail.outbox[0].body, re.M).group(1)
        response = self.client.post(response.url, {"code": code})
        self.assertRedirects(response, "/s/PHY-E01/", fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get("/s/PHY-E01/"), "solutions.html")

    def test_adult_must_agree_to_the_privacy_notice_too(self):
        response = self.signup(19)
        self.assertEqual(set(response.context["form"].errors), {"consent"})
        self.assertIn("privacy notice", response.context["form"].errors["consent"][0])
        self.assertFalse(User.objects.exists())

    def test_adult_needs_no_parent_and_keeps_none(self):
        self.signup(19, consent="on", parent_name="Ignored", parent_contact="12345")  # not even validated
        user = User.objects.get()
        self.assertFalse(user.is_minor)
        self.assertEqual((user.parent_name, user.parent_contact), ("", ""))
        self.assertIsNotNone(user.consent_at)

    def test_signup_page_links_the_privacy_notice_next_to_the_box(self):
        self.assertContains(
            self.client.get(reverse("account_signup")), f'<a href="{reverse("privacy")}" target="_blank"'
        )

    def test_register_url_redirects_to_signup_keeping_next(self):
        response = self.client.get("/account/register/?next=/s/PHY-E01/")
        self.assertRedirects(response, reverse("account_signup") + "?next=/s/PHY-E01/")


# MD5 hashing is fast: these tests log in many times
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginSecurityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(logging.CRITICAL)  # axes logs every failure
        cls.addClassCleanup(logging.disable, logging.NOTSET)

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin@example.com", "Brahmaputra-2027", full_name="Admin")

    def admin_login(self, email, password):  # the admin's login form is allauth's (SECURITY_REVIEW.md H2)
        admin_form = self.client.get("/admin/login/?next=/admin/")
        self.assertRedirects(admin_form, "/account/login/?next=%2Fadmin%2F", fetch_redirect_response=False)
        return self.client.post(reverse("account_login"), {"login": email, "password": password, "next": "/admin/"})

    def test_good_logins_are_not_recorded_only_failed_ones_are(self):
        self.assertEqual(self.admin_login("admin@example.com", "Brahmaputra-2027").status_code, 302)
        self.assertEqual(AccessLog.objects.count(), 0)  # the privacy notice promises failed attempts only
        self.client.logout()  # (the log-in waits for the emailed code: a new one starts)
        self.admin_login("admin@example.com", "wrong")
        self.assertEqual(AccessAttempt.objects.count(), 1)

    def test_failures_lock_the_account_even_for_the_right_password(self):
        for _ in range(5):  # allauth: 5 per account in 5 minutes, from any address; axes: 10 per address
            self.admin_login("Admin@Example.com", "wrong")  # the e-mail is lowered: one account, one counter
        response = self.admin_login("admin@example.com", "Brahmaputra-2027")
        self.assertContains(response, "Too many failed login attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_students_logging_in_with_allauth_are_counted_per_email(self):
        cache.clear()
        self.client.post(reverse("account_login"), {"login": "Student@Example.com", "password": "wrong"})
        # the username is recorded (not None, which would lock by IP only)
        self.assertEqual(AccessAttempt.objects.get().username, "student@example.com")
