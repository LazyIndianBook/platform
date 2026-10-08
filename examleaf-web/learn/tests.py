"""The course content: quiz checking, the admin (publishing, ordering clips, every page). Helpers for the other test
modules of the app: make_course."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.factories import UserFactory
from content.tests import make_paper

from .models import Chapter, Clip, FlashCard, QuizItem, Revision

pytestmark = pytest.mark.django_db


def make_course(subject=None, chapters=2, clips=2, seconds=120):
    """Published revisions of `chapters` chapters, each with `clips` processed clips, a flash card and a quiz item."""
    subject = subject or make_paper().book.subject
    for number in range(1, chapters + 1):
        chapter = Chapter.objects.create(subject=subject, number=number, title=f"Chapter {number}", weight=7)
        revision = Revision.objects.create(chapter=chapter, title=f"Revise {number}", status="published", order=number)
        for order in range(1, clips + 1):
            Clip.objects.create(
                revision=revision, order=order, title=f"Clip {number}.{order}", processing="ready", duration=seconds,
                hls_path=f"learn/hls/{number}{order}/v1/master.m3u8", poster=f"learn/hls/{number}{order}/v1/poster.jpg",
            )  # fmt: skip
        FlashCard.objects.create(chapter=chapter, front=f"Front {number}", back=f"Back {number}")
        QuizItem.objects.create(chapter=chapter, kind="true_false", text=f"Statement {number}", answer="true")
    return subject


def test_answers_are_checked_by_kind():
    mcq = QuizItem(kind="mcq", options=["(i) a", "(ii) b"], answer="2")
    assert mcq.is_right(2) and mcq.is_right("2") and not mcq.is_right(1)
    true_false = QuizItem(kind="true_false", answer="false")
    assert true_false.is_right(False) and true_false.is_right("False") and not true_false.is_right(True)
    blank = QuizItem(kind="fill_blank", answer="dioptre|D")
    assert blank.is_right(" The Dioptre. ") and blank.is_right("d") and not blank.is_right("metre")


def test_a_multiple_choice_answer_names_an_option():
    with pytest.raises(ValidationError):
        QuizItem(kind="mcq", options=["(i) a", "(ii) b"], answer="3").clean()


def test_publish_needs_a_ready_clip_and_clips_move(client):
    subject = make_course(chapters=1, clips=3)
    empty = Revision.objects.create(chapter=Chapter.objects.create(subject=subject, number=2, title="Two"), title="E")
    Revision.objects.update(status="draft")
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    revisions = reverse("admin:learn_revision_changelist")
    client.post(revisions, {"action": "publish", "_selected_action": [r.pk for r in Revision.objects.all()]})
    assert list(Revision.objects.filter(status="published")) == [Revision.objects.exclude(pk=empty.pk).get()]

    last = Clip.objects.get(title="Clip 1.3")
    client.post(reverse("admin:learn_clip_changelist"), {"action": "move_up", "_selected_action": [last.pk]})
    assert list(Clip.objects.order_by("order").values_list("title", flat=True)) == ["Clip 1.1", "Clip 1.3", "Clip 1.2"]


def test_every_learn_admin_page_opens(client):
    make_course(chapters=1, clips=1)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    for model in [Chapter, Revision, Clip, FlashCard, QuizItem]:
        name = f"admin:learn_{model._meta.model_name}"
        for url in [
            reverse(f"{name}_changelist"),
            reverse(f"{name}_add"),
            reverse(f"{name}_change", args=[model.objects.first().pk]),
        ]:
            assert client.get(url).status_code == 200, url


