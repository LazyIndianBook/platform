"""Course data is personal data: in Download my data (export_learning), and gone with the account (with the app's
devices); book codes stay used."""

import pytest

from accounts.factories import UserFactory
from accounts.models import DeletionRequest

from .models import BookCode, CardReview, Clip, Device, Entitlement, FlashCard, Learner, Progress, QuizAttempt, QuizItem
from .services import export_learning, make_codes, redeem
from .tests import make_course

pytestmark = pytest.mark.django_db


def everything(user, subject):
    redeem(user, make_codes(subject, 1, "PHY-1")[0])
    Learner.objects.create(user=user, reminders=True)
    Progress.objects.create(user=user, clip=Clip.objects.first(), seconds_watched=30)
    QuizAttempt.objects.create(user=user, item=QuizItem.objects.first(), correct=False)
    CardReview.objects.create(user=user, card=FlashCard.objects.first(), known=True)
    Device.objects.create(user=user, token=f"fid-{user.pk}", platform="android")


def test_download_my_data_has_the_course_data():
    subject = make_course(chapters=1)
    user, other = UserFactory(), UserFactory()
    everything(user, subject)
    everything(other, subject)
    data = export_learning(user)
    assert data["settings"] == {"exam_date": None, "minutes_per_day": 30, "reminders": True}
    assert [(e["subject__name"], e["source"]) for e in data["entitlements"]] == [("Physics", "book_code")]
    assert [b["batch"] for b in data["book_codes_redeemed"]] == ["PHY-1"]
    assert [(p["clip__title"], p["seconds_watched"]) for p in data["progress"]] == [("Clip 1.1", 30)]
    assert [(q["item__text"], q["correct"]) for q in data["quiz_answers"]] == [("Statement 1", False)]
    assert [c["known"] for c in data["flash_card_reviews"]] == [True]
    assert [d["platform"] for d in data["devices"]] == ["android"] and "fid-" not in str(data)


def test_account_deletion_removes_it_and_the_devices():
    subject = make_course(chapters=1)
    user, other = UserFactory(), UserFactory()
    everything(user, subject)
    everything(other, subject)
    DeletionRequest.objects.create(user=user).complete()
    for model in (Progress, QuizAttempt, CardReview, Learner, Device, Entitlement):
        assert list(model.objects.values_list("user", flat=True)) == [other.pk], model
    assert BookCode.objects.filter(redeemed_by=user).count() == 1  # still used: it cannot be redeemed again
