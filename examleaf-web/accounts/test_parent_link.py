"""The parent's consent link with hostile input (SECURITY_REVIEW_PHASE5_6.md M3): nothing goes from an anonymous
sign-up, the messages are fixed text with at most an allowed name, and one address or number gets a few links a day."""

import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.test_security import confirm_own_address, sign_up
from accounts.views import A_STUDENT, shown_name
from api.tests import emailed_code, register
from content.tests import make_paper

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
HOSTILE = "Your parcel is held: pay Rs 49 at examleaf-help.com"


@pytest.fixture
def verified(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    make_paper()  # a board


@pytest.mark.parametrize(
    "typed, shown",
    [
        ("Rahul Das", "Rahul Das"),
        ("  A.  K. Das ", "A. K. Das"),
        ("Mary-Ann Saikia", "Mary-Ann Saikia"),
        ("রাহুল দাস", "রাহুল দাস"),  # Assamese, with its vowel signs
        (HOSTILE, A_STUDENT),
        ("visit examleaf-help.com now", A_STUDENT),  # a dot inside a word: a web address
        ("Rahul 2010", A_STUDENT),
        ("Rahul‮Das", A_STUDENT),  # a right-to-left override
        ("<b>Rahul</b>", A_STUDENT),
        ("Rahul" * 13, A_STUDENT),  # 65 characters
        ("", A_STUDENT),
    ],
)
def test_only_a_plain_name_reaches_the_parent(typed, shown):
    assert shown_name(typed) == shown


def test_an_anonymous_sign_up_in_the_app_writes_to_nobody_until_its_address_is_confirmed(verified):
    api = APIClient()
    response = register(api, 16, full_name=HOSTILE, parent_name="X", parent_contact="victim@example.com", consent=True)
    assert response.status_code == 201 and not [m for m in mail.outbox if m.to == ["victim@example.com"]]
    token = response.json()["verification_token"]
    assert api.post("/api/v1/auth/registration/verify-email/", {"verification_token": token, "code": emailed_code()})
    [message] = [m for m in mail.outbox if m.to == ["victim@example.com"]]
    assert message.body.startswith("A student has registered at ExamLeaf") and "examleaf-help" not in message.body
    html = message.alternatives[0][0]
    assert "examleaf-help" not in html and set(re.findall(r'href="(https?://[^/"]+)', html)) <= {
        "http://localhost:8000"
    }


def test_the_sms_carries_a_student_for_a_name_that_is_not_one(verified, client, capsys):
    sign_up(client, full_name=HOSTILE, parent_contact="98640 12345")
    confirm_own_address(client)
    assert "SMS parent_consent to +919864012345: {'var1': 'a student'," in capsys.readouterr().out


def test_one_parent_address_gets_three_links_a_day_and_the_page_says_when_none_went(verified, client):
    sign_up(client, parent_contact="anita@example.com")
    confirm_own_address(client)  # the first link
    student = User.objects.get()
    for _ in range(2):
        page = client.post(reverse("parent_consent_resend"), {"parent_contact": "anita@example.com"}, follow=True)
        assert "We have sent anita@example.com a link" in page.text
        cache.delete(f"accounts:parent-link:{student.pk}")  # past the ten minutes between two links
    page = client.post(reverse("parent_consent_resend"), {"parent_contact": "anita@example.com"}, follow=True)
    assert "The link was not sent" in page.text and "We have sent anita@example.com" not in page.text
    assert len([m for m in mail.outbox if m.to == ["anita@example.com"]]) == 3
