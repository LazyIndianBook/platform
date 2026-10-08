"""Security review fixes in the API (SECURITY_REVIEW.md): log-in and reset limits per account, wrong passwords,
attempts, ordering."""

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import PASSWORD
from api.tests import sign_in, student
from content.models import Subject
from content.tests import make_paper
from practice.models import Attempt

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
    pytest.mark.filterwarnings("ignore:app_settings.AUTHENTICATION_METHOD is deprecated"),  # inside dj-rest-auth
]


@pytest.fixture
def api():
    return APIClient()


def test_failed_api_log_ins_are_counted_per_account_from_any_address(api):  # M7
    user = student()
    for n in range(5):
        api.post("/api/v1/auth/login/", {"email": user.email, "password": "wrong"}, REMOTE_ADDR=f"10.0.0.{n}")
    response = api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}, REMOTE_ADDR="10.0.0.9")
    assert response.status_code == 400 and "Too many failed login attempts" in str(response.json())


def test_api_password_resets_are_limited_per_email_address(api):  # L5
    user = student()
    for n in range(5):
        response = api.post("/api/v1/auth/password/reset/", {"email": user.email.upper()}, REMOTE_ADDR=f"10.0.1.{n}")
        assert response.status_code == 200
    response = api.post("/api/v1/auth/password/reset/", {"email": user.email}, REMOTE_ADDR="10.0.1.9")
    assert response.status_code == 429 and len(mail.outbox) == 5


def test_five_wrong_passwords_in_the_app_end_its_tokens(api):  # L6
    user = student()
    refresh = RefreshToken.for_user(user)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    for _ in range(4):
        assert api.post("/api/v1/me/export/", {"password": "wrong"}).status_code == 400
    assert api.post("/api/v1/me/deletion/", {"password": "wrong"}).status_code == 429  # the fifth
    assert api.post("/api/v1/me/export/", {"password": PASSWORD}).status_code == 429  # for an hour, even the right one
    change = {"old_password": PASSWORD, "new_password1": "Kaziranga-2028", "new_password2": "Kaziranga-2028"}
    assert api.post("/api/v1/auth/password/change/", change).status_code == 429
    api.credentials()
    assert api.post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)}).status_code == 401  # blacklisted


def test_notes_and_new_attempts_a_day_are_limited_on_the_api_and_the_site(api, client):  # L12
    paper, user = make_paper(), student()
    sign_in(api, user)
    too_long = {"paper": paper.code, "marks_obtained": "40", "notes": "x" * 2001}
    assert "notes" in api.post("/api/v1/attempts/", too_long).json()
    Attempt.objects.bulk_create([Attempt(user=user, paper=paper, marks_obtained=40) for _ in range(20)])
    response = api.post("/api/v1/attempts/", {"paper": paper.code, "marks_obtained": "40"})
    assert response.status_code == 400 and "At most 20 attempts" in str(response.json())
    first = Attempt.objects.filter(user=user).first()
    assert api.patch(f"/api/v1/attempts/{first.pk}/", {"marks_obtained": "41"}).status_code == 200  # edits go on
    client.force_login(user)
    page = client.post(reverse("attempt_add", args=[paper.code]), {"date": "2026-10-01", "marks_obtained": "40"})
    assert page.status_code == 200 and "At most 20 attempts" in page.text
    page = client.post(
        reverse("attempt_edit", args=[first.pk]), {"date": "2026-10-01", "marks_obtained": "40", **too_long}
    )
    assert "at most 2000 characters" in page.text


def test_boards_and_subjects_sort_only_by_their_listed_fields(api):  # I4
    physics = make_paper().book.subject
    Subject.objects.create(name="Biology", code="BIO", board=physics.board, class_level=physics.class_level)

    def names(ordering):
        return [s["name"] for s in api.get(f"/api/v1/subjects/?ordering={ordering}").json()["results"]]

    assert names("name") == ["Biology", "Physics"]
    assert names("code") == ["Physics", "Biology"]  # not listed: the default order (id)
    assert api.get("/api/v1/boards/?ordering=-state").status_code == 200


def test_unknown_query_parameters_share_the_cached_page(api, django_assert_num_queries):  # L8 (api part)
    make_paper()
    assert api.get("/api/v1/books/?x=1").status_code == 200
    with django_assert_num_queries(0):  # the same entry as /api/v1/books/
        assert api.get("/api/v1/books/?x=2&y=3").json() == api.get("/api/v1/books/").json()
    assert api.get("/api/v1/books/?search=nothing-like-it").json()["results"] == []  # known ones still count
    assert api.get("/api/v1/papers/?tier=H&x=1").json()["results"] == []  # and the filters
