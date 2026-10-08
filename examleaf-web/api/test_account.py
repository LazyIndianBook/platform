"""API v1 for the Next.js account pages (Phase 8): My record in figures, what Download my data holds, the app's store
links, the signed-in devices (allauth.usersessions through allauth.headless), and Download my data and Delete my
account after a recent log-in instead of the password (accounts without one: Google)."""

import time
from datetime import timedelta

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.usersessions.models import UserSession
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import PASSWORD
from accounts.models import DeletionRequest
from accounts.views import DATA_PARTS, export_user_data
from api.tests import add_paper, sign_in, student
from content.tests import make_paper
from ops.tasks import clear_sessions
from practice.models import Attempt

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
BROWSER = "/_allauth/browser/v1"


def test_my_record_averages_tiers_and_subjects_and_keeps_each_papers_best_and_latest():
    api, easy = APIClient(), make_paper()
    medium = add_paper(easy.book, "PHY-M02", tier="M")
    user = sign_in(api, student())
    today = timezone.localdate()
    best = Attempt.objects.create(user=user, paper=easy, marks_obtained="52.5", date=today - timedelta(days=2))  # 75%
    latest = Attempt.objects.create(user=user, paper=easy, marks_obtained=35, date=today - timedelta(days=1))  # 50%
    Attempt.objects.create(user=user, paper=medium, marks_obtained=49)  # 70%
    record = api.get("/api/v1/me/record/").json()
    assert record["count"] == 3
    assert record["tiers"] == [
        {"tier": "E", "label": "Easy", "count": 2, "average": 62},  # 62.5 rounds as My record rounds it
        {"tier": "M", "label": "Medium", "count": 1, "average": 70},
    ]
    assert [(s["code"], s["count"], s["average"]) for s in record["subjects"]] == [("PHY", 3, 65)]
    [first, second] = record["papers"]
    assert (first["paper"], first["count"], first["best"]["id"], first["latest"]["id"]) == (
        "PHY-E01", 2, best.pk, latest.pk,
    )  # fmt: skip
    assert (first["best"]["marks_obtained"], first["best"]["percent"], second["paper"]) == ("52.5", 75, "PHY-M02")
    medium_only = api.get("/api/v1/me/record/", {"tier": "M"}).json()
    assert (medium_only["count"], [t["tier"] for t in medium_only["tiers"]]) == (1, ["M"])
    assert api.get("/api/v1/me/record/", {"tier": "X"}).status_code == 400
    sign_in(api, student(verified=False))
    assert api.get("/api/v1/me/record/").status_code == 403


def test_the_export_summary_names_each_part_with_its_count_without_the_password():
    api, paper = APIClient(), make_paper()
    assert api.get("/api/v1/me/export/summary/").status_code == 401
    user = sign_in(api, student())
    Attempt.objects.create(user=user, paper=paper, marks_obtained=40)
    parts = api.get("/api/v1/me/export/summary/").json()
    assert [part["key"] for part in parts] == list(DATA_PARTS)
    counts = {part["key"]: part["count"] for part in parts}
    assert (counts["attempts"], counts["orders"], counts["sessions"]) == (1, 0, 0) and counts["profile"]
    assert parts[0]["label"].startswith("Your details")


def test_the_configuration_gives_the_apps_store_pages(settings):
    api = APIClient()
    assert api.get("/api/v1/config/").json()["app_links"] == {"android": None, "ios": None}
    settings.APP_LINK_ANDROID = "https://play.google.com/store/apps/details?id=example"
    assert api.get("/api/v1/config/").json()["app_links"]["android"] == settings.APP_LINK_ANDROID


def log_in(client, user):
    response = client.post(BROWSER + "/auth/login", {"email": user.email, "password": PASSWORD}, "application/json")
    assert response.status_code == 200


def test_signed_in_devices_are_listed_and_the_others_signed_out_and_go_with_the_account():
    user = student()
    phone, laptop = Client(HTTP_USER_AGENT="Phone"), Client(HTTP_USER_AGENT="Laptop")
    log_in(phone, user)
    log_in(laptop, user)
    sessions = phone.get(BROWSER + "/auth/sessions").json()["data"]
    assert sorted((s["user_agent"], s["is_current"], s["ip"]) for s in sessions) == [
        ("Laptop", False, "127.0.0.1"),
        ("Phone", True, "127.0.0.1"),
    ]
    assert all(s["last_seen_at"] for s in sessions)  # USERSESSIONS_TRACK_ACTIVITY
    others = [s["id"] for s in sessions if not s["is_current"]]
    assert phone.delete(BROWSER + "/auth/sessions", {"sessions": others}, "application/json").status_code == 200
    assert (laptop.get("/api/v1/me/").status_code, phone.get("/api/v1/me/").status_code) == (401, 200)
    UserSession.objects.create(user=user, ip="10.0.0.1", session_key="ended-elsewhere", user_agent="Old phone")
    clear_sessions()  # nightly: the devices of ended sessions go
    assert [row["user_agent"] for row in export_user_data(user)["sessions"]] == ["Phone"]  # in Download my data
    DeletionRequest.objects.create(user=user).complete()
    assert not UserSession.objects.filter(user=user).exists()


def logged_in(client, user, seconds_ago=0):
    """A browser session that logged in with Google `seconds_ago`, as allauth records it."""
    client.force_login(user)
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {"method": "socialaccount", "at": time.time() - seconds_ago, "provider": "google", "uid": "1"}
    ]
    session.save()


def test_an_account_without_a_password_exports_and_deletes_within_5_minutes_of_a_log_in():
    user, client = student(email="rahul@example.com"), Client()
    user.set_unusable_password()
    user.save()
    logged_in(client, user, seconds_ago=301)
    refused = client.post("/api/v1/me/export/", {}, "application/json")
    assert (refused.status_code, refused.json()["code"]) == (403, "reauthentication_required")
    assert client.post("/api/v1/me/deletion/", {"password": ""}, "application/json").status_code == 403
    logged_in(client, user)  # Continue with Google again
    assert client.post("/api/v1/me/export/", {}, "application/json").json()["profile"]["email"] == "rahul@example.com"
    assert client.post("/api/v1/me/deletion/", {}, "application/json").status_code == 201
    api = APIClient()
    sign_in(api, user)  # the app's tokens have no session: only a password would do
    assert api.post("/api/v1/me/export/", {}).status_code == 403


def test_a_reauthentication_through_headless_stands_in_for_the_password():
    user, client = student(), Client()
    log_in(client, user)
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {**record, "at": record["at"] - 301} for record in session[AUTHENTICATION_METHODS_SESSION_KEY]
    ]  # the log-in, 5 minutes ago
    session.save()
    assert client.post("/api/v1/me/export/", {}, "application/json").status_code == 403
    wrong = client.post("/api/v1/me/export/", {"password": "wrong"}, "application/json")
    assert wrong.json() == {"password": ["Incorrect password."]}  # a password sent is checked, and counted (L6)
    again = client.post(BROWSER + "/auth/reauthenticate", {"password": PASSWORD}, "application/json")
    assert again.status_code == 200
    assert client.post("/api/v1/me/export/", {}, "application/json").status_code == 200
    assert client.post("/api/v1/me/export/", {"password": PASSWORD}, "application/json").status_code == 200
