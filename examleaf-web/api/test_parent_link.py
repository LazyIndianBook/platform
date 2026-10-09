"""/api/v1/parent-consent/<token>/ (api/parent_link.py): the parent's link through the API, as on the website."""

import time
from datetime import date

import pytest
from django.utils.http import int_to_base36
from rest_framework.test import APIClient

from accounts.models import ConsentRecord, User
from accounts.views import parent_signer
from content.tests import make_paper

pytestmark = pytest.mark.django_db


def test_the_parent_sees_who_registered_then_agrees_once(settings, monkeypatch):
    settings.PARENTAL_CONSENT_MODE = "verified"
    board = make_paper().book.subject.board
    student = User.objects.create_user(
        "rahul@example.com",
        "x",
        full_name="Rahul Das",
        date_of_birth=date(2010, 5, 1),
        board=board,
        parent_contact="anita@example.com",
    )
    token = parent_signer(student.parent_contact).sign(int_to_base36(student.pk))
    url, api = f"/api/v1/parent-consent/{token}/", APIClient()
    page = api.get(url)
    assert page.status_code == 200 and page.json()["status"] == "pending" and page.json()["student_name"] == "Rahul Das"
    assert "no-store" in page["Cache-Control"] and page.json()["contact"] == "email"
    assert api.post(url).json()["status"] == "confirmed" and api.post(url).json()["status"] == "confirmed"
    record = ConsentRecord.objects.get(by_parent=True)  # recorded once, verified by the emailed link
    assert record.method == ConsentRecord.Method.EMAIL_LINK and record.verified_at
    later = time.time() + 8 * 86400
    monkeypatch.setattr(time, "time", lambda: later)
    expired = api.get(url)
    assert expired.status_code == 400 and expired.json() == {
        "status": "expired",
        "student_name": None,
        "student_email": None,
        "contact": None,
        "first_name": "Rahul",
        "days": 7,
        "deletion": None,  # no deletion waits (one does: staff/tests/test_legal.py)
    }
    assert api.post("/api/v1/parent-consent/zz.bad/").json()["first_name"] is None
