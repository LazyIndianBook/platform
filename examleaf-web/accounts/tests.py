import re
from datetime import date

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
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
        data = {"full_name": "Rahul Das", "email": "rahul@example.com", "password1": "Brahmaputra-2027",
                "password2": "Brahmaputra-2027", "class_level": 12, "board": self.board.pk,
                "date_of_birth": birthday(age).isoformat(), **extra}
        return self.client.post(reverse("account_signup"), data)

    def test_under_18_needs_parent_details_and_consent(self):
        response = self.signup(16)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["form"].errors), {"parent_name", "parent_contact", "parent_consent"})
        self.assertFalse(User.objects.exists())

    def test_under_18_parent_contact_must_be_a_phone_or_email(self):
        response = self.signup(16, parent_name="Anita Das", parent_contact="12345", parent_consent="on")
        self.assertEqual(set(response.context["form"].errors), {"parent_contact"})

    def test_under_18_with_consent_verifies_email_and_returns_to_the_paper(self):
        response = self.signup(16, parent_name="Anita Das", parent_contact="98640 12345", parent_consent="on",
                               next="/s/PHY-E01/")
        user = User.objects.get()
        self.assertTrue(user.is_minor)
        self.assertEqual((user.parent_name, user.parent_contact), ("Anita Das", "+919864012345"))
        self.assertIsNotNone(user.consent_at)
        # allauth sends a code; the student types it on the page they are on and lands on the paper's solutions.
        code = re.search(r"^([A-Z0-9]{4}-[A-Z0-9]{4})$", mail.outbox[0].body, re.M).group(1)
        response = self.client.post(response.url, {"code": code})
        self.assertRedirects(response, "/s/PHY-E01/", fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get("/s/PHY-E01/"), "solutions.html")

    def test_adult_needs_no_parent_and_keeps_none(self):
        self.signup(19, parent_name="Ignored", parent_contact="ignored@example.com")
        user = User.objects.get()
        self.assertFalse(user.is_minor)
        self.assertEqual((user.parent_name, user.parent_contact), ("", ""))

    def test_register_url_redirects_to_signup_keeping_next(self):
        response = self.client.get("/account/register/?next=/s/PHY-E01/")
        self.assertRedirects(response, reverse("account_signup") + "?next=/s/PHY-E01/")
