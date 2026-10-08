"""Parental consent by SMS (PARENTAL_CONSENT_MODE "verified"): a parent's Indian mobile number gets the short signed
link (/c/<token>/, a token that fits a 30-character DLT variable), recorded as confirmed through the texted link (the
website's page asks api/v1/parent-consent/<token>/)."""

import re

import pytest
from django.test import Client

from accounts.models import ConsentRecord, User
from accounts.test_security import confirm_own_address, sign_up
from content.tests import make_paper

pytestmark = pytest.mark.django_db


def texted_token(capsys):
    return re.findall(
        r"SMS parent_consent to \+919864012345: \{'var1': 'Rahul', 'var2': '([^']+)'\}", capsys.readouterr().out
    )


def test_a_parents_mobile_number_gets_the_link_by_sms(client, settings, capsys):
    settings.PARENTAL_CONSENT_MODE = "verified"
    make_paper()  # a board
    sign_up(client, parent_contact="98640 12345")
    student = User.objects.get()
    assert student.parent_contact == "+919864012345" and student.consent_pending
    assert texted_token(capsys) == []  # not before the student has confirmed their own address (M3)
    confirm_own_address(client)
    [token] = texted_token(capsys)
    assert len(token) <= 30 and re.fullmatch(r"[\w.-]+", token)
    parent, link = Client(), f"/api/v1/parent-consent/{token}/"
    assert parent.get(link).json()["contact"] == "phone"  # the page: "… gave your mobile number"
    assert parent.get(f"/api/v1/parent-consent/{token[:-1]}x/").status_code == 400  # a changed signature
    parent.post(link)
    record = ConsentRecord.objects.get(verified_at__isnull=False)
    assert record.method == ConsentRecord.Method.SMS_LINK and not User.objects.get().consent_pending


def test_a_corrected_number_voids_the_first_link_and_sms_off_means_email_only(client, settings, capsys):
    settings.PARENTAL_CONSENT_MODE = "verified"
    make_paper()
    sign_up(client, parent_contact="98640 12345")
    confirm_own_address(client)
    [first] = texted_token(capsys)
    client.post("/api/v1/me/parent-consent/", {"parent_contact": "98641 12345"}, content_type="application/json")
    assert "to +919864112345" in capsys.readouterr().out
    assert Client().get(f"/api/v1/parent-consent/{first}/").status_code == 400
    settings.SMS_ENABLED = False
    response = sign_up(Client(), email="other@example.com", parent_contact="98640 12345")
    [error] = response.json()["errors"]
    assert error["param"] == "parent_contact"
    assert error["message"] == "Enter your parent's or guardian's email address: we send them a link to confirm."
