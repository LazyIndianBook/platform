"""Smaller findings of SECURITY_REVIEW_PHASE5_6.md in the course: the book codes' key (L7), rows one account can add
and the reminder's batches (L8), revise-again within what the student may open (I5)."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.checks import run_checks
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from api.tests import sign_in, student

from .models import CardReview, Device, Entitlement, FlashCard, Learner, QuizAttempt, QuizItem, Revision
from .plan import revise_again
from .tasks import send_reminders
from .tests import make_course

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def test_a_server_does_not_start_without_the_book_codes_key(settings):
    settings.DEBUG, settings.TESTING, settings.LEARN_CODE_SECRET = False, False, ""
    assert "learn.E001" in [message.id for message in run_checks()]
    settings.LEARN_CODE_SECRET = "a-key-of-its-own"
    assert "learn.E001" not in [message.id for message in run_checks()]


def test_an_account_keeps_five_devices_and_a_days_worth_of_answers(monkeypatch):
    make_course(chapters=1)
    api = APIClient()
    user = sign_in(api, student())
    Entitlement.objects.create(user=user)
    for number in range(7):
        assert api.post("/api/v1/devices/", {"token": f"tok-{number}"}).status_code == 201
    assert sorted(Device.objects.values_list("token", flat=True)) == [f"tok-{n}" for n in range(2, 7)]
    monkeypatch.setattr("api.learn.ANSWERS_PER_DAY", 2)
    item, card = QuizItem.objects.get(), FlashCard.objects.get()
    answers = [api.post(f"/api/v1/learn/quiz/{item.pk}/attempt/", {"answer": "true"}).status_code for _ in range(3)]
    reviews = [api.post(f"/api/v1/learn/flash-cards/{card.pk}/review/", {"known": True}).status_code for _ in range(3)]
    assert answers == [200, 200, 429] and reviews == [201, 201, 429]
    QuizAttempt.objects.update(created=timezone.now() - timedelta(days=2))
    assert api.post(f"/api/v1/learn/quiz/{item.pk}/attempt/", {"answer": "true"}).status_code == 200


def test_the_reminder_deletes_what_firebase_refuses_as_a_token(settings):
    from firebase_admin import exceptions, messaging

    settings.FCM_SERVICE_ACCOUNT_JSON = '{"type": "service_account"}'
    user = UserFactory()
    Learner.objects.create(user=user, reminders=True)
    for token in ["junk", "gone", "fine"]:
        Device.objects.create(user=user, token=token)
    refused = [exceptions.InvalidArgumentError("not a token"), messaging.UnregisteredError("gone"), None]
    answers = mock.Mock(responses=[mock.Mock(success=error is None, exception=error) for error in refused])
    with mock.patch("learn.tasks.firebase"), mock.patch.object(messaging, "send_each", return_value=answers):
        assert send_reminders() == 1
    assert list(Device.objects.values_list("token", flat=True)) == ["fine"]


def test_revise_again_lists_only_what_the_student_may_still_open():
    make_course(chapters=1)
    user, item, card = UserFactory(), QuizItem.objects.get(), FlashCard.objects.get()
    access = Entitlement.objects.create(user=user)
    start = timezone.now() - timedelta(days=2)
    QuizAttempt.objects.create(user=user, item=item, correct=False, created=start)
    CardReview.objects.create(user=user, card=card, known=False, created=start)

    def listed():
        due = revise_again(user)
        return [row["item"] for row in due["quiz_items"]], [row["item"] for row in due["flash_cards"]]

    assert listed() == ([item], [card])
    access.valid_until = timezone.localdate() - timedelta(days=1)  # the year of access is over
    access.save()
    assert listed() == ([], [card])  # the first chapter's cards are free
    Revision.objects.update(status=Revision.Status.DRAFT)
    assert listed() == ([], [])
