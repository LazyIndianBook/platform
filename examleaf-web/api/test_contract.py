"""API v1 for what the website's account and site pages do (phase 7): the frontends' configuration, the legal pages,
teacher access, the parent's link again and SMS updates, with the website's rules."""

import pytest
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import TeacherProfile
from accounts.tests import birthday
from api.tests import sign_in, student
from pages.models import Page

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]


@pytest.fixture
def api():
    return APIClient()


def test_the_configuration_tells_frontends_what_is_switched_on(api, settings):
    data = api.get("/api/v1/config/").json()
    assert data["auth"] == {
        "login_methods": ["email", "phone"], "login_by_code": True, "sms": True, "google": False, "passkeys": True,
        "turnstile_site_key": None,
    }  # fmt: skip
    assert data["shop"] == {"open": True, "cod": False, "cod_max_value": "1500.00", "currency": "INR"}
    assert (data["solutions_require_login"], data["parental_consent"]) == (True, "declared")
    assert data["support"] == {"email": None, "phone": None}  # the seller's details still hold [placeholders]
    settings.TURNSTILE, settings.TURNSTILE_SITE_KEY, settings.SHOP_OPEN = True, "0x4AAAAAAA", False
    settings.SHOP_SELLER = {**settings.SHOP_SELLER, "email": "help@examleaf.in", "phone": ""}
    response = api.get("/api/v1/config/", HTTP_AUTHORIZATION="Bearer expired.or.stale")  # ignored
    data = response.json()
    assert (data["auth"]["turnstile_site_key"], data["shop"]["open"]) == ("0x4AAAAAAA", False)
    assert data["support"] == {"email": "help@examleaf.in", "phone": None}
    assert response["Cache-Control"] == "public, max-age=300"


def test_legal_pages_come_as_markdown_and_the_websites_html_with_the_last_change(api):
    privacy = Page.objects.get(slug="privacy")
    data = api.get("/api/v1/pages/privacy/").json()
    assert (data["title"], data["version"], data["markdown"]) == (privacy.title, privacy.version, privacy.body_md)
    assert data["html"].startswith("<") and data["web_url"] == "http://testserver/privacy/" and data["updated"]
    assert '<mark class="placeholder">' in api.get("/api/v1/pages/contact/").json()["html"]  # still to fill in
    slugs = [page["slug"] for page in api.get("/api/v1/pages/").json()["results"]]
    assert slugs == ["privacy", "terms", "refunds", "shipping", "contact"]
    assert api.get("/api/v1/pages/about/").status_code == 404


def test_teacher_access_is_asked_once_and_its_status_read(api):
    assert api.get("/api/v1/me/teacher/").status_code == 401
    sign_in(api, student(verified=False))
    assert api.get("/api/v1/me/teacher/").status_code == 403  # email address not confirmed
    sign_in(api, student())
    assert api.get("/api/v1/me/teacher/").status_code == 404  # not asked yet
    asked = {"school_name": "Cotton Collegiate H.S. School", "district": "Kamrup Metro", "subject": "Physics"}
    assert api.post("/api/v1/me/teacher/", {**asked, "subject": ""}, format="json").json() == {
        "subject": ["This field may not be blank."]
    }
    response = api.post("/api/v1/me/teacher/", {**asked, "verified": True}, format="json")
    assert response.status_code == 201 and response.json()["verified"] is False  # staff verify it
    assert api.get("/api/v1/me/teacher/").json()["school_name"] == asked["school_name"]
    again = api.post("/api/v1/me/teacher/", asked, format="json")
    assert again.status_code == 400 and TeacherProfile.objects.count() == 1


def test_a_student_waiting_for_the_parent_can_send_the_link_again(api, settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    adult = APIClient()
    sign_in(adult, student(date_of_birth=birthday(20)))
    assert adult.post("/api/v1/me/parent-consent/", {"parent_contact": "anita@example.com"}).status_code == 404
    user = sign_in(api, student(date_of_birth=birthday(15), parent_name="Anita Das", parent_contact="old@example.com"))
    assert api.get("/api/v1/me/").json()["consent_pending"] is True
    own = api.post("/api/v1/me/parent-consent/", {"parent_contact": user.email}, format="json")
    assert own.status_code == 400 and "not your own" in own.json()["parent_contact"][0]
    response = api.post("/api/v1/me/parent-consent/", {"parent_contact": "Anita@Example.com"}, format="json")
    assert response.json() == {"detail": "We have sent anita@example.com a link to confirm."}
    assert mail.outbox[-1].to == ["anita@example.com"] and "/c/" in mail.outbox[-1].body
    again = api.post("/api/v1/me/parent-consent/", {"parent_contact": "anita@example.com"}, format="json")
    assert again.status_code == 429 and "ten minutes" in again.json()["detail"]


def test_sms_updates_need_a_confirmed_number(api):
    sign_in(api, student())
    response = api.patch("/api/v1/me/", {"sms_updates": True}, format="json")
    assert response.json() == {"sms_updates": ["Confirm a mobile number first: the updates go to it."]}
    sign_in(api, student(login_phone="+919864012345", login_phone_verified=True))
    data = api.patch("/api/v1/me/", {"sms_updates": True, "login_phone": "+919000000000"}, format="json").json()
    assert (data["sms_updates"], data["login_phone"], data["login_phone_verified"]) == (True, "+919864012345", True)
