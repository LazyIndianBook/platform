"""Who may watch: entitlements, free previews, book codes (made, kept hashed, redeemed once), the shop's hooks."""

import csv
import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from shop.factories import ProductFactory, make_order

from .models import BookCode, Chapter, Clip, Entitlement
from .services import (
    CodeError,
    entitled_subjects,
    grant_for_order,
    is_free_chapter,
    is_free_clip,
    redeem,
    revoke_for_order,
)
from .tests import make_course

pytestmark = pytest.mark.django_db


def test_entitlements_open_their_subject_until_their_last_day():
    physics = make_course(chapters=1)
    user, today = UserFactory(), timezone.localdate()
    assert physics.pk not in entitled_subjects(user)
    Entitlement.objects.create(user=user, subject=physics, valid_until=today)
    assert physics.pk in entitled_subjects(user) and 999 not in entitled_subjects(user)
    Entitlement.objects.update(valid_until=today - timedelta(days=1))
    assert physics.pk not in entitled_subjects(user)
    Entitlement.objects.create(user=user, subject=None)  # every subject, for good
    assert 999 in entitled_subjects(user) and 999 in entitled_subjects(UserFactory(is_staff=True))


def test_free_previews(settings):
    make_course(chapters=2, clips=2)
    first, second = Clip.objects.filter(revision__chapter__number=1)
    assert is_free_clip(first) and not is_free_clip(second)
    second.is_free_preview = True
    assert is_free_clip(second)
    one, two = Chapter.objects.all()
    assert is_free_chapter(one) and not is_free_chapter(two)
    settings.LEARN_FREE_PREVIEW = False
    assert not is_free_clip(first) and not is_free_chapter(one)


def test_book_codes_are_kept_hashed_and_redeemed_once(tmp_path):
    physics = make_course(chapters=1)
    out = tmp_path / "codes.csv"
    call_command("make_book_codes", "phy", 3, batch="PHY-2027-1", out=str(out), stderr=io.StringIO())
    rows = list(csv.DictReader(out.open()))
    assert [row["subject"] for row in rows] == ["PHY"] * 3 and BookCode.objects.count() == 3
    code = rows[0]["code"]
    assert len(code) == 14 and not BookCode.objects.filter(digest__contains=code.replace("-", "")).exists()

    student, other = UserFactory(), UserFactory()
    entitlement = redeem(student, code.lower().replace("-", " "))  # as typed
    assert (entitlement.subject, entitlement.source) == (physics, "book_code")
    assert entitlement.valid_until == timezone.localdate() + timedelta(days=365)
    assert redeem(student, code) == entitlement  # the same student again: the same, nothing new
    for bad, why in [(code, "used already"), ("7KQM-3XPA-9TRW", "not valid"), ("12345", "12 letters")]:
        with pytest.raises(CodeError, match=why):
            redeem(other, bad)
    assert not other.entitlements.exists()


def test_staff_find_a_code_in_the_admin_by_typing_it(client, tmp_path):
    make_course(chapters=1)
    out = tmp_path / "codes.csv"
    call_command("make_book_codes", "ALL", 2, batch="ALL-1", out=str(out), stderr=io.StringIO())
    code = next(csv.DictReader(out.open()))["code"]
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    found = client.get(reverse("admin:learn_bookcode_changelist"), {"q": code})
    assert found.context["cl"].result_count == 1 and BookCode.objects.filter(subject=None).count() == 2


def test_digital_products_open_the_course_once_paid_and_close_when_refunded():
    physics = make_course(chapters=1)
    user = UserFactory()
    order = make_order((ProductFactory(kind="digital", subject=physics), 1), (ProductFactory(), 1), user=user)
    assert [(e.subject, e.source, e.reference) for e in grant_for_order(order)] == [(physics, "purchase", order.number)]
    grant_for_order(order)  # a repeated webhook
    assert user.entitlements.count() == 1 and physics.pk in entitled_subjects(user)
    assert revoke_for_order(order) == 1 and not user.entitlements.exists()
    assert grant_for_order(make_order((ProductFactory(kind="digital"), 1))) == []  # a guest: no account
