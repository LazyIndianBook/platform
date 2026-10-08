"""The revision course's API: chapters, locked and free clips with their signed links, progress, quiz, flash cards,
plan, revise-again, book codes and their limits, settings, devices, and the push reminders."""

import time
from datetime import timedelta
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from accounts.models import ConsentRecord
from api.learn import ParentConfirmed
from api.tests import sign_in, student

from .models import Chapter, Clip, Device, Entitlement, FlashCard, Learner, QuizAttempt, QuizItem, Revision
from .services import make_codes
from .tasks import send_reminders
from .tests import make_course

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def course():
    return make_course(chapters=2, clips=2)


def url(path):
    return f"/api/v1/learn/{path}"


def test_chapters_are_public_and_say_what_is_open(api, course):
    chapters = api.get(url("chapters/"), {"subject": course.pk}).json()["results"]
    assert [
        (c["number"], c["clips"], c["minutes"], c["entitled"], c["free_cards"], c["progress"]) for c in chapters
    ] == [
        (1, 2, 4, False, True, None),
        (2, 2, 4, False, False, None),
    ]
    one = api.get(url(f"chapters/{chapters[0]['id']}/")).json()
    assert [(c["title"], c["free"], c["locked"]) for c in one["revision"]["clips"]] == [
        ("Clip 1.1", True, False),
        ("Clip 1.2", False, True),
    ]
    assert [(c["has_revision"], c["revision_status"]) for c in chapters] == [(True, "published")] * 2
    assert chapters[0]["free_preview"] == Clip.objects.get(title="Clip 1.1").pk
    Revision.objects.filter(chapter__number=1).update(status="draft")  # back in draft: coming soon, nothing shown
    Chapter.objects.create(subject=course, number=3, title="Chapter 3", weight="4.5", frequency=6)  # none yet
    chapters = api.get(url("chapters/"), {"subject": course.pk}).json()["results"]
    assert [
        (c["number"], c["weight"], c["has_revision"], c["revision_status"], c["clips"], c["free_preview"],
         c["free_cards"]) for c in chapters
    ] == [
        (1, "7.0", False, "none", 0, None, False),
        (2, "7.0", True, "published", 2, Clip.objects.get(title="Clip 2.1").pk, False),
        (3, "4.5", False, "none", 0, None, False),
    ]  # fmt: skip
    assert api.get(url(f"chapters/{chapters[0]['id']}/")).status_code == 404  # a draft's clips stay unseen
    assert api.get(url("chapters/"), {"ordering": "-weight"}).json()["results"][2]["number"] == 3


def test_a_locked_clip_is_refused_a_free_one_plays_through_its_signed_link(api, course, client, monkeypatch):
    free, locked = Clip.objects.filter(revision__chapter__number=1)
    assert api.get(url(f"clips/{free.pk}/")).status_code == 401
    sign_in(api, student())
    assert api.get(url(f"clips/{locked.pk}/")).json() == {
        "detail": "Unlock this subject with the code printed in your book."
    }
    folder = free.hls_path.rsplit("/", 1)[0]
    default_storage.save(f"{folder}/master.m3u8", ContentFile(b"#EXTM3U\n480p/index.m3u8\n"))
    default_storage.save(f"{folder}/480p/seg_000.ts", ContentFile(b"ts"))
    clip = api.get(url(f"clips/{free.pk}/")).json()
    assert clip["completed"] is False and clip["expires_at"]
    master = client.get(clip["hls_url"].removeprefix("http://localhost:8000"))
    assert (master.status_code, master["Content-Type"], master.content) == (
        200,
        "application/vnd.apple.mpegurl",
        b"#EXTM3U\n480p/index.m3u8\n",
    )
    segment = clip["hls_url"].removeprefix("http://localhost:8000").replace("master.m3u8", "480p/seg_000.ts")
    assert b"".join(client.get(segment).streaming_content) == b"ts"
    assert client.get(segment.replace("seg_000.ts", "../../x")).status_code == 404
    later = time.time() + 601
    monkeypatch.setattr("django.core.signing.time.time", lambda: later)
    assert client.get(clip["hls_url"].removeprefix("http://localhost:8000")).status_code == 403  # 10 minutes later
    assert client.get(segment).status_code == 200  # a clip started in time plays to the end


def test_an_entitled_student_watches_everything_and_progress_is_kept(api, course):
    user = sign_in(api, student())
    Entitlement.objects.create(user=user, subject=course)
    clip = Clip.objects.get(title="Clip 2.2")
    assert api.get(url(f"clips/{clip.pk}/")).status_code == 200
    assert api.post(url(f"clips/{clip.pk}/progress/"), {"seconds_watched": 120, "completed": True}).json() == {
        "seconds_watched": 120,
        "completed": True,
    }
    api.post(url(f"clips/{clip.pk}/progress/"), {"seconds_watched": 10})  # watched again from the start
    assert api.get(url(f"clips/{clip.pk}/")).json()["completed"] is True
    progress = {c["number"]: c["progress"] for c in api.get(url("chapters/")).json()["results"]}
    assert progress == {1: 0, 2: 50}


def test_unconfirmed_addresses_cannot_use_the_course(api, course):
    sign_in(api, student(verified=False))
    assert api.get(url("settings/")).status_code == 403


def test_the_quiz_is_checked_on_the_server(api, course, monkeypatch):
    user = sign_in(api, student())
    chapter = Chapter.objects.get(number=1)
    item = QuizItem.objects.create(chapter=chapter, kind="mcq", text="Unit of flux?", options=["(i) T", "(ii) Wb"],
                                   answer="2", explanation="$\\Phi = BA$")  # fmt: skip
    assert api.get(url("quiz/")).status_code == 400
    assert api.get(url("quiz/"), {"chapter": chapter.pk}).status_code == 403
    Entitlement.objects.create(user=user, subject=None)
    listed = api.get(url("quiz/"), {"chapter": chapter.pk}).json()["results"]
    assert [i["options"] for i in listed] == [[], ["(i) T", "(ii) Wb"]] and "answer" not in listed[1]
    checked = api.post(url(f"quiz/{item.pk}/attempt/"), {"answer": "1"}).json()
    assert checked == {"correct": False, "right_answer": "(ii) Wb", "explanation": "$\\Phi = BA$",
                       "explanation_html": "<p>$\\Phi = BA$</p>\n"}  # fmt: skip
    assert api.post(url(f"quiz/{item.pk}/attempt/"), {"answer": "2"}).json()["correct"] is True
    assert list(QuizAttempt.objects.values_list("correct", flat=True)) == [False, True]
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "learn_quiz", "2/hour")
    assert api.post(url(f"quiz/{item.pk}/attempt/"), {"answer": "2"}).status_code == 429


def test_flash_cards_of_the_first_chapter_are_free(api, course):
    sign_in(api, student())
    one, two = Chapter.objects.all()
    cards = api.get(url("flash-cards/"), {"chapter": one.pk}).json()["results"]
    assert [c["front_html"] for c in cards] == ["<p>Front 1</p>\n"]
    assert api.get(url("flash-cards/"), {"chapter": two.pk}).status_code == 403
    assert api.post(url(f"flash-cards/{cards[0]['id']}/review/"), {"known": False}).status_code == 201
    card_two = FlashCard.objects.get(chapter=two)
    assert api.post(url(f"flash-cards/{card_two.pk}/review/"), {"known": True}).status_code == 403


def test_the_plan_and_what_to_revise_again(api, course):
    user = sign_in(api, student())
    assert "exam_date" in api.get(url("plan/")).json()
    exam = timezone.localdate() + timedelta(days=20)
    assert api.patch(url("settings/"), {"exam_date": exam.isoformat(), "minutes_per_day": 10}).status_code == 200
    Clip.objects.update(duration=300)
    plan = api.get(url("plan/")).json()
    assert (plan["days_left"], plan["minutes_per_day"], plan["minimum_to_pass"][0]["pass_marks"]) == (20, 10, 21)
    assert [[c["title"] for c in day["clips"]] for day in plan["days"]] == [
        ["Clip 1.1", "Clip 1.2"],
        ["Clip 2.1", "Clip 2.2"],
    ]
    assert len(api.get(url("plan/"), {"minutes": 20}).json()["days"]) == 1
    minimum = plan["minimum_to_pass"][0]  # decimals as strings, as everywhere in the API
    assert (minimum["marks"], minimum["chapters"][0]["weight"], minimum["chapters"][0]["marks_per_minute"]) == (
        "14.0",
        "7.0",
        "0.70",
    )
    assert api.get(url("plan/"), {"exam_date": timezone.localdate().isoformat()}).status_code == 400

    item = QuizItem.objects.get(chapter__number=1)
    Entitlement.objects.create(user=user)  # revise-again lists what the student may open (I5)
    QuizAttempt.objects.create(user=user, item=item, correct=False, created=timezone.now() - timedelta(days=2))
    again = api.get(url("revise-again/")).json()
    assert [i["id"] for i in again["quiz_items"]] == [item.pk] and again["flash_cards"] == []


def test_book_codes_are_redeemed_once_and_tries_are_limited(api, course):
    user = sign_in(api, student())
    code = make_codes(course, 1, "PHY-1")[0]
    answer = api.post(url("redeem/"), {"code": code})
    assert (answer.status_code, answer.json()["subject"], answer.json()["source"]) == (200, course.pk, "book_code")
    assert [e["subject_name"] for e in api.get(url("entitlements/")).json()["results"]] == ["Physics"]
    assert api.post(url("redeem/"), {"code": "ABCD-EFGH-JKLM"}).json() == {
        "code": ["This code is not valid. Check it against the one printed in your book."]
    }
    for _ in range(3):
        api.post(url("redeem/"), {"code": "ABCD-EFGH-JKLM"})
    assert api.post(url("redeem/"), {"code": code}).status_code == 429  # the sixth try within the hour
    assert user.entitlements.count() == 1

    sign_in(api, student())  # another student at the same address: the address has had its five
    assert api.post(url("redeem/"), {"code": code}).status_code == 429


def test_a_student_under_18_whose_parent_has_not_confirmed_reads_the_course_and_saves_nothing(api, course, settings):
    """PARENTAL_CONSENT_MODE "verified": read-only until the parent agrees (as for marks and orders)."""
    settings.PARENTAL_CONSENT_MODE = "verified"
    user = sign_in(api, student(date_of_birth=timezone.localdate() - timedelta(days=16 * 366)))
    Entitlement.objects.create(user=user, subject=course)
    clip, item, card = Clip.objects.first(), QuizItem.objects.first(), FlashCard.objects.first()
    assert api.get(url(f"clips/{clip.pk}/")).status_code == 200 and api.get(url("plan/")).status_code == 400
    writes = [
        (url(f"clips/{clip.pk}/progress/"), {"seconds_watched": 5}),
        (url(f"quiz/{item.pk}/attempt/"), {"answer": "true"}),
        (url(f"flash-cards/{card.pk}/review/"), {"known": True}),
        (url("redeem/"), {"code": "ABCD-EFGH-JKLM"}),
        ("/api/v1/devices/", {"token": "tok-1"}),
    ]
    for address, body in writes:
        answer = api.post(address, body)
        assert (answer.status_code, answer.json()["detail"]) == (403, ParentConfirmed.message), address
    assert api.patch(url("settings/"), {"minutes_per_day": 20}).status_code == 403
    assert api.get(url("settings/")).status_code == 200
    assert api.delete("/api/v1/devices/", {"token": "tok-1"}).status_code == 204  # at log-out
    ConsentRecord.objects.create(user=user, notice_version="1", by_parent=True, verified_at=timezone.now())
    assert api.post(url(f"quiz/{item.pk}/attempt/"), {"answer": "true"}).status_code == 200


def test_devices_and_the_daily_reminder(api, course, settings):
    user = sign_in(api, student())
    assert api.post("/api/v1/devices/", {"token": "tok-1", "platform": "android"}).status_code == 201
    sign_in(api, other := student())
    api.post("/api/v1/devices/", {"token": "tok-1"})  # the same phone, another account
    api.post("/api/v1/devices/", {"token": "tok-2"})
    assert list(Device.objects.values_list("token", "user")) == [("tok-1", other.pk), ("tok-2", other.pk)]
    assert api.delete("/api/v1/devices/", {"token": "tok-2"}).status_code == 204
    assert send_reminders() == 0  # no Firebase account set: nothing is sent

    settings.FCM_SERVICE_ACCOUNT_JSON = '{"type": "service_account"}'
    Learner.objects.create(user=other, reminders=True, exam_date=timezone.localdate() + timedelta(days=9))
    Learner.objects.create(user=user, reminders=False)
    Device.objects.create(user=other, token="tok-3")
    from firebase_admin import messaging

    gone = messaging.UnregisteredError("gone")
    answers = mock.Mock(responses=[mock.Mock(success=True, exception=None), mock.Mock(success=False, exception=gone)])
    with mock.patch("learn.tasks.firebase"), mock.patch.object(messaging, "send_each", return_value=answers) as send:
        assert send_reminders() == 1
    [notes] = send.call_args.args
    assert [n.fid for n in notes] == ["tok-1", "tok-3"] and notes[0].notification.body.startswith("9 days")
    assert list(Device.objects.values_list("token", flat=True)) == ["tok-1"]


def test_chapter_answers_take_as_many_queries_for_more_chapters_and_clips(api):
    subject = make_course(chapters=2, clips=2)
    sign_in(api, student())
    first = Chapter.objects.get(number=1)

    def queries(path):
        with CaptureQueriesContext(connection) as captured:
            assert api.get(path).status_code == 200
        return len(captured)

    before = queries(url("chapters/")), queries(url(f"chapters/{first.pk}/"))
    for number in (3, 4):
        chapter = Chapter.objects.create(subject=subject, number=number, title=f"Chapter {number}")
        Revision.objects.create(chapter=chapter, title="More", status="published")
    for order in range(3, 7):
        Clip.objects.create(
            revision=first.revision, order=order, title=f"More {order}", processing="ready", duration=60
        )
    assert (queries(url("chapters/")), queries(url(f"chapters/{first.pk}/"))) == before
