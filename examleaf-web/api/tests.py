"""REST API v1: catalogue, solutions, sign-up rules, email codes, JWT, attempts, data rights, limits, schema."""

import re
import uuid

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import PASSWORD, UserFactory
from accounts.models import ConsentRecord, DeletionRequest, User
from accounts.tests import birthday
from content.models import Board, Book, Paper, Question, Solution
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


@pytest.fixture
def paper():
    return make_paper()


def student(verified=True, **fields):
    user = UserFactory(**fields)
    EmailAddress.objects.create(user=user, email=user.email, verified=verified, primary=True)
    return user


def sign_in(api, user):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user


def add_paper(book, code, tier="M", published=True, questions=1):
    paper = Paper.objects.create(
        book=book, code=code, tier=tier, number=int(code[-2:]), title=code, full_marks=70, pass_marks=21,
        time_text="3 hours", is_published=published,
    )  # fmt: skip
    for order in range(1, questions + 1):
        question = Question.objects.create(paper=paper, order=order, label=str(order), text_md=f"Question {order}")
        Solution.objects.create(question=question, body_md=f"**Final answer:** {order}")
    return paper


def test_catalogue_is_public_with_published_papers_only(api, paper):
    add_paper(paper.book, "PHY-M02", published=False)
    board = api.get("/api/v1/boards/").json()["results"][0]
    assert board["short_name"] == "ASSEB"
    subject = api.get(f"/api/v1/subjects/?board={board['id']}").json()["results"][0]
    assert (subject["code"], subject["board"], subject["class_level"]) == ("PHY", "ASSEB", 12)
    book = api.get("/api/v1/books/physics-2027/").json()
    assert book["subject"]["code"] == "PHY" and book["cover"] is None
    assert book["papers"] == [{"code": "PHY-E01", "tier": "E", "number": 1, "title": paper.title, "is_published": True}]
    data = api.get("/api/v1/papers/PHY-E01/").json()
    assert data["book"] == "physics-2027" and data["full_marks"] == 70 and data["web_url"].endswith("/s/PHY-E01/")
    assert data["solutions_url"] == "http://testserver/api/v1/papers/PHY-E01/solutions/"
    assert api.get("/api/v1/papers/PHY-M02/").status_code == 404  # unpublished, as on the website
    assert api.get("/api/v1/qr/phy-e01/").json()["solutions_url"] == data["solutions_url"]  # any case, as scanned
    assert api.get("/api/v1/qr/PHY-M02/").status_code == 404


def test_papers_filter_search_order_and_paginate(api, paper):
    for n in range(2, 6):
        add_paper(paper.book, f"PHY-M{n:02d}")
    page = api.get("/api/v1/papers/?tier=M&ordering=-number&page_size=3").json()
    assert page["count"] == 4 and [p["code"] for p in page["results"]] == ["PHY-M05", "PHY-M04", "PHY-M03"]
    assert "page=2" in page["next"]
    assert api.get("/api/v1/papers/?page_size=3&page=2&tier=M").json()["results"][0]["code"] == "PHY-M05"
    assert api.get("/api/v1/papers/?search=e01").json()["count"] == 1
    assert api.get("/api/v1/papers/?book=physics-2027&subject=99").json()["count"] == 0
    assert api.get("/api/v1/papers/?page_size=1000").json()["count"] == 5  # page_size capped at 200, not refused
    assert api.get("/api/v1/books/?search=chemistry").json()["count"] == 0


def test_catalogue_queries_do_not_grow_with_the_rows(api, paper, django_assert_num_queries):
    for n, slug in enumerate(["chemistry-2027", "mathematics-2027"], start=2):
        book = Book.objects.create(title=slug, subject=paper.book.subject, slug=slug)
        for m in range(1, 4):
            add_paper(book, f"X{n}-M{m:02d}")
    with django_assert_num_queries(3):  # count, books with subject/board/class, their papers
        assert len(api.get("/api/v1/books/").json()["results"]) == 3
    with django_assert_num_queries(2):  # count, papers with book and subject
        assert api.get("/api/v1/papers/").json()["count"] == 7


def test_solutions_need_a_signed_in_student_with_a_confirmed_email(api, paper, django_assert_num_queries):
    url = "/api/v1/papers/PHY-E01/solutions/"
    assert api.get(url).status_code == 401
    sign_in(api, student(verified=False))
    response = api.get(url)
    assert response.status_code == 403 and response.json() == {"detail": "Confirm your email address first."}
    sign_in(api, student())
    for order in range(2, 6):
        Question.objects.create(paper=paper, order=order, label=f"{order} OR", is_alternative=True, text_md="Or this")
    with django_assert_num_queries(4):  # user, email confirmed, paper, questions with solutions: not one per question
        questions = api.get(url).json()
    assert [q["order"] for q in questions] == [1, 2, 3, 4, 5]
    first = questions[0]
    assert first["label"] == "2(c)" and first["marks"] == "2" and not first["is_alternative"]
    assert first["solution"]["markdown"].startswith("| Step | Marks |")
    assert '<table class="steps">' in first["solution"]["html"] and "$I = 0.5$" in first["solution"]["html"]
    assert questions[1]["is_alternative"] and questions[1]["solution"] is None


def emailed_code():
    return re.search(r"^([A-Z0-9]{4}-[A-Z0-9]{4})$", mail.outbox[-1].body, re.M).group(1)


def register(api, age, **extra):
    data = {
        "full_name": "Rahul Das",
        "email": "rahul@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "class_level": 12,
        "board": Board.objects.get().pk,  # the paper fixture's board (ids differ between databases)
        "date_of_birth": birthday(age).isoformat(),
        **extra,
    }
    return api.post("/api/v1/auth/registration/", data)


def test_registration_keeps_the_website_rules(api, paper):
    response = register(api, 16, consent=True)
    assert response.status_code == 400
    assert set(response.json()) == {"parent_name", "parent_contact"}  # under 18 without a parent: refused
    assert set(register(api, 16, parent_name="Anita Das", parent_contact="98640 12345").json()) == {"consent"}
    assert "parent or guardian" in register(api, 16, consent=False).json()["consent"][0]
    assert set(register(api, 19, consent=True, password2="other-Pass-2027").json()) == {"password2"}
    assert not User.objects.exists() and not mail.outbox


def test_sign_up_then_the_emailed_code_logs_the_student_in(api, paper):
    response = register(api, 16, parent_name="Anita Das", parent_contact="98640 12345", consent=True)
    assert response.status_code == 201 and response.json()["detail"] == "Verification e-mail sent."
    assert "sessionid" not in response.cookies  # the app holds the token; no cookie
    token = response.json()["verification_token"]
    user = User.objects.get()
    assert user.is_student and user.parent_contact == "+919864012345" and user.consent_at
    assert ConsentRecord.objects.get(user=user).by_parent
    wrong = api.post("/api/v1/auth/registration/verify-email/", {"verification_token": token, "code": "AAAA-AAAA"})
    assert wrong.status_code == 400 and "code" in wrong.json()
    response = api.post(
        "/api/v1/auth/registration/verify-email/", {"verification_token": token, "code": emailed_code()}
    )
    assert response.status_code == 200 and set(response.json()) == {"access", "refresh", "user"}
    assert response.json()["user"]["roles"] == ["STUDENT"] and EmailAddress.objects.get(user=user).verified
    again = api.post("/api/v1/auth/registration/verify-email/", {"verification_token": token, "code": emailed_code()})
    assert again.status_code == 400  # the token is spent
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
    assert api.get("/api/v1/papers/PHY-E01/solutions/").status_code == 200


def test_signing_up_with_a_registered_address_looks_the_same_and_tells_its_owner(api, paper):
    student(email="rahul@example.com")
    response = register(api, 19, consent=True)
    assert response.status_code == 201 and response.json()["verification_token"]  # no way to tell who is registered
    assert User.objects.count() == 1 and "already" in mail.outbox[-1].body
    response = api.post(
        "/api/v1/auth/registration/verify-email/", {"verification_token": response.json()["verification_token"],
                                                    "code": "AAAA-AAAA"},
    )  # fmt: skip
    assert response.status_code == 400


def test_jwt_login_refresh_rotation_logout_blacklist(api):
    user = student(email="rahul@example.com")
    assert api.post("/api/v1/auth/login/", {"email": user.email, "password": "wrong"}).status_code == 400
    response = api.post("/api/v1/auth/login/", {"email": "Rahul@example.com", "password": PASSWORD})
    assert "sessionid" not in response.cookies  # no server session for the app
    tokens = response.json()
    assert tokens["user"]["email"] == "rahul@example.com"
    user.refresh_from_db()
    assert user.last_login
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api.get("/api/v1/me/").json()["email"] == "rahul@example.com"
    api.credentials()
    new = api.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}).json()
    assert new["access"] and new["refresh"] != tokens["refresh"]  # rotated
    assert api.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}).status_code == 401  # blacklisted
    api.credentials(HTTP_AUTHORIZATION="Bearer expired.or.stale")  # an app may still send its old access token
    assert api.post("/api/v1/auth/logout/", {"refresh": new["refresh"]}).status_code == 200
    assert api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}).status_code == 200
    assert api.post("/api/v1/auth/token/refresh/", {"refresh": new["refresh"]}).status_code == 401


def test_axes_locks_the_account_after_ten_failed_api_logins(api):
    user = student()
    for _ in range(10):
        api.post("/api/v1/auth/login/", {"email": user.email, "password": "wrong"})
    assert api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}).status_code == 400


def test_login_with_an_unconfirmed_address_sends_a_code(api):
    user = student(verified=False, email="rahul@example.com")
    response = api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD})
    assert response.status_code == 400 and response.json()["detail"] == "E-mail is not verified."
    token = response.json()["verification_token"]
    response = api.post(
        "/api/v1/auth/registration/verify-email/", {"verification_token": token, "code": emailed_code()}
    )
    assert response.status_code == 200 and response.json()["user"]["id"] == user.pk


def test_a_password_change_ends_the_old_tokens_and_tells_the_owner(api):
    user = sign_in(api, student(email="rahul@example.com"))
    data = {"old_password": PASSWORD, "new_password1": "Kaziranga-2028", "new_password2": "Kaziranga-2028"}
    assert api.post("/api/v1/auth/password/change/", data).status_code == 200
    assert "password" in mail.outbox[-1].subject.lower() and mail.outbox[-1].to == [user.email]
    assert api.get("/api/v1/me/").status_code == 401  # every token of the old password is revoked


def test_password_reset_mails_the_websites_link_which_the_api_also_accepts(api):
    user = student(email="rahul@example.com")
    assert api.post("/api/v1/auth/password/reset/", {"email": user.email}).status_code == 200
    uid, key = re.search(r"/account/password/reset/key/(\w+)-([\w-]+)/", mail.outbox[-1].body).groups()
    data = {"uid": uid, "token": key, "new_password1": "Kaziranga-2028", "new_password2": "Kaziranga-2028"}
    assert api.post("/api/v1/auth/password/reset/confirm/", data).status_code == 200
    user.refresh_from_db()
    assert user.check_password("Kaziranga-2028")


def test_attempts_are_the_students_own(api, paper, django_assert_num_queries):
    hard = add_paper(paper.book, "PHY-H01", tier="H")
    add_paper(paper.book, "PHY-H02", tier="H", published=False)
    other = Attempt.objects.create(user=student(), paper=paper, marks_obtained=30)
    user = sign_in(api, student())
    created = api.post("/api/v1/attempts/", {"paper": "PHY-E01", "marks_obtained": "52.5", "notes": "optics"})
    assert created.status_code == 201
    attempt = created.json()
    assert (attempt["subject"], attempt["tier"], attempt["full_marks"], attempt["percent"]) == ("PHY", "E", 70, 75)
    hard_attempt = {"paper": "PHY-H01", "marks_obtained": 40, "time_taken_minutes": 170}
    assert api.post("/api/v1/attempts/", hard_attempt).status_code == 201
    for bad in [{"paper": "PHY-H01", "marks_obtained": 71}, {"paper": "PHY-H02", "marks_obtained": 10}]:
        assert api.post("/api/v1/attempts/", bad).status_code == 400  # over full marks; an unpublished paper
    with django_assert_num_queries(4):  # user, email confirmed, count, attempts with paper and subject
        listed = api.get("/api/v1/attempts/").json()
    assert listed["count"] == 2 and Attempt.objects.filter(user=user).count() == 2
    filtered = api.get(f"/api/v1/attempts/?tier=H&subject={hard.book.subject_id}").json()["results"]
    assert [a["paper"] for a in filtered] == ["PHY-H01"]
    url = f"/api/v1/attempts/{attempt['id']}/"
    assert api.patch(url, {"marks_obtained": 60}).json()["marks_obtained"] == "60.0"
    assert api.patch(url, {"paper": "PHY-H01"}).json() == {"paper": ["An attempt stays with its paper."]}
    assert api.get(f"/api/v1/attempts/{other.pk}/").status_code == 404  # someone else's
    assert api.delete(f"/api/v1/attempts/{other.pk}/").status_code == 404 and Attempt.objects.filter(pk=other.pk)
    assert api.delete(url).status_code == 204 and api.get("/api/v1/attempts/").json()["count"] == 1
    api.credentials()
    assert api.get("/api/v1/attempts/").status_code == 401


def test_profile_reads_and_updates_what_the_student_may_change(api, paper):
    user = sign_in(api, student(email="rahul@example.com", date_of_birth=birthday(16), parent_name="Anita Das"))
    me = api.get("/api/v1/me/").json()
    assert me["email"] == "rahul@example.com" and me["parent_name"] == "Anita Das" and me["deletion_due_at"] is None
    changes = {
        "full_name": "Rahul Kumar Das",
        "district": "Kamrup",
        "phone": "98640 12345",
        "board": paper.book.subject.board_id,
    }
    response = api.patch("/api/v1/me/", {**changes, "email": "x@example.com", "date_of_birth": "2000-01-01"})
    assert response.status_code == 200 and response.json()["phone"] == "+919864012345"
    user.refresh_from_db()
    assert (user.full_name, user.district, user.email, user.date_of_birth) == (
        "Rahul Kumar Das", "Kamrup", "rahul@example.com", birthday(16),
    )  # fmt: skip
    assert api.patch("/api/v1/me/", {"phone": "12345"}).status_code == 400


def test_download_my_data_asks_for_the_password(api, paper):
    user = sign_in(api, student(email="rahul@example.com"))
    Attempt.objects.create(user=user, paper=paper, marks_obtained=52, notes="revise optics")
    assert api.post("/api/v1/me/export/", {"password": "wrong"}).json() == {"password": ["Incorrect password."]}
    data = api.post("/api/v1/me/export/", {"password": PASSWORD}).json()
    assert data["profile"]["email"] == "rahul@example.com" and data["attempts"][0]["notes"] == "revise optics"
    assert data["email_addresses"] == [{"email": "rahul@example.com", "verified": True, "primary": True}]
    assert data["addresses"] == [] and data["orders"] == []  # the website's export, shop included


def test_account_deletion_waits_seven_days_and_can_be_cancelled(api):
    user = sign_in(api, student(email="rahul@example.com"))
    assert api.post("/api/v1/me/deletion/", {"password": "wrong"}).status_code == 400
    response = api.post("/api/v1/me/deletion/", {"password": PASSWORD})
    assert response.status_code == 201 and response.json()["status"] == "pending"
    deletion = DeletionRequest.objects.get(user=user)
    assert (deletion.due_at - deletion.requested_at).days == 7 and user.consents.first().event == "withdrawn"
    assert mail.outbox[-1].subject == "[ExamLeaf] Your account will be deleted"
    assert api.post("/api/v1/me/deletion/", {"password": PASSWORD}).status_code == 200  # the same request again
    assert api.get("/api/v1/me/").json()["deletion_due_at"]
    assert api.delete("/api/v1/me/deletion/").status_code == 204
    deletion.refresh_from_db()
    assert deletion.status == "cancelled" and user.consents.first().event == "given"
    assert mail.outbox[-1].subject == "[ExamLeaf] Your account will not be deleted"
    assert api.delete("/api/v1/me/deletion/").status_code == 404
    DeletionRequest.objects.create(user=user).complete()  # what the daily purge does seven days later
    assert api.get("/api/v1/me/").status_code == 401  # and the app's tokens end with it


def test_throttles_count_per_address_and_per_scope(api, paper, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "anon", "3/minute")
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "dj_rest_auth", "2/minute")
    assert [api.get("/api/v1/qr/PHY-E01/").status_code for _ in range(4)] == [200, 200, 200, 429]
    other = APIClient(REMOTE_ADDR="10.0.0.2")
    logins = [other.post("/api/v1/auth/login/", {"email": "a@example.com", "password": "x"}) for _ in range(3)]
    assert [r.status_code for r in logins] == [400, 400, 429] and int(logins[-1]["Retry-After"]) > 0


def test_request_bodies_are_limited_on_the_api_and_the_site(api, client, settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1000
    response = api.post("/api/v1/auth/login/", {"email": "a@example.com", "password": "x" * 2000})
    assert response.status_code == 413 and response.json() == {"detail": "The request body is too large."}
    assert client.post("/account/login/", {"login": "a@example.com", "password": "x" * 2000}).status_code == 400
    assert api.post("/api/v1/auth/login/", {"email": "a@example.com", "password": "x"}).status_code == 400  # parsed


def test_cors_only_for_listed_origins_and_only_on_the_api(api, paper, settings):
    settings.CORS_ALLOWED_ORIGINS = ["https://app.examleaf.in"]
    preflight = {"HTTP_ACCESS_CONTROL_REQUEST_METHOD": "GET", "HTTP_ACCESS_CONTROL_REQUEST_HEADERS": "authorization"}
    response = api.options("/api/v1/papers/", HTTP_ORIGIN="https://app.examleaf.in", **preflight)
    assert response["Access-Control-Allow-Origin"] == "https://app.examleaf.in"
    assert "authorization" in response["Access-Control-Allow-Headers"]
    assert "Access-Control-Allow-Origin" not in api.get("/api/v1/papers/", HTTP_ORIGIN="https://evil.example")
    assert "Access-Control-Allow-Origin" not in api.get("/books/physics-2027/", HTTP_ORIGIN="https://app.examleaf.in")


def test_json_only_request_ids_json_404_and_health(api):
    request_id = uuid.uuid4().hex
    response = api.get("/api/v1/boards/", HTTP_X_REQUEST_ID=request_id)
    assert response["Content-Type"] == "application/json" and response["X-Request-ID"] == request_id
    assert api.post("/api/v1/auth/login/", {"email": "a@example.com"}, format="multipart").status_code == 415
    for url in ["/api/v1/nothing/", "/api/v2/boards/", "/api/v1/boards"]:
        assert api.get(url).json() == {"detail": "Not found."}
    response = api.get("/api/v1/health/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200 and response.json()["Database(alias='default')"] == "OK"
    assert PeriodicTask.objects.filter(task="api.tasks.flush_expired_tokens", enabled=True).exists()  # daily clean-up


def test_openapi_schema_is_valid_and_the_docs_pages_load(api, tmp_path):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", tmp_path / "schema.yml")
    schema = (tmp_path / "schema.yml").read_text()
    assert "/api/v1/papers/{code}/solutions/" in schema and "AStudentUnder18" in schema
    for path in ["/api/v1/cart/items/{product}/", "/api/v1/orders/{number}/payment/confirm/", "/api/v1/orders/lookup/"]:
        assert path in schema  # the shop
    assert "application/pdf" in schema  # invoices and credit notes are files, not JSON
    for url in ["/api/schema/", "/api/docs/", "/api/docs/?script", "/api/redoc/"]:
        assert api.get(url).status_code == 200, url
