"""The one audience function for marketing (accounts.audiences.marketable; plan 5.15 "Children's rules"): a minor
never, whatever any consent says; an unknown age only on a verified consent; an adult only on a consent for the
channel (or every channel) given and not withdrawn since."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from accounts.audiences import adult_born_by, marketable
from accounts.factories import UserFactory
from accounts.models import ConsentRecord, DeletionRequest, User
from accounts.tests import birthday

pytestmark = pytest.mark.django_db
MARKETING = ConsentRecord.Purpose.MARKETING


def consent(user, event=ConsentRecord.Event.GIVEN, channel="", verified=False, ago=0):
    row = ConsentRecord.objects.create(
        user=user,
        event=event,
        purpose=MARKETING,
        channel=channel,
        notice_version="1",
        verified_at=timezone.now() if verified else None,
    )
    ConsentRecord.objects.filter(pk=row.pk).update(created=timezone.now() - timedelta(minutes=ago))
    return row


def test_only_adults_with_a_consent_in_force_and_unknown_ages_with_a_verified_one_are_marketable():
    minor = UserFactory(date_of_birth=birthday(16))
    unknown = UserFactory(date_of_birth=None)
    verified_unknown = UserFactory(date_of_birth=None)
    adult_without = UserFactory(date_of_birth=birthday(30))
    adult_with = UserFactory(date_of_birth=birthday(30))
    adult_sms_only = UserFactory(date_of_birth=birthday(40))
    adult_withdrawn = UserFactory(date_of_birth=birthday(25))
    adult_leaving = UserFactory(date_of_birth=birthday(25))
    for user in (minor, unknown, adult_with, adult_leaving):
        consent(user, verified=True)  # a minor's consent, even verified, never makes them marketable
    consent(verified_unknown, channel="email", verified=True)
    consent(adult_sms_only, channel="sms")
    consent(adult_withdrawn, ago=10)
    consent(adult_withdrawn, event=ConsentRecord.Event.WITHDRAWN, channel="email", ago=5)
    DeletionRequest.objects.create(user=adult_leaving)
    ConsentRecord.objects.create(user=adult_without, notice_version="1")  # the account's consent: not marketing
    names = set(marketable(User.objects.all(), "email").values_list("pk", flat=True))
    assert names == {verified_unknown.pk, adult_with.pk, unknown.pk}  # unknown: its consent was verified too
    assert set(marketable(User.objects.all(), "sms").values_list("pk", flat=True)) == {
        unknown.pk, adult_with.pk, adult_sms_only.pk, adult_withdrawn.pk}  # fmt: skip
    consent(adult_withdrawn, ago=1)  # given again since: in force again
    assert adult_withdrawn.pk in set(marketable(User.objects.all(), "email").values_list("pk", flat=True))
    with pytest.raises(ValueError):
        marketable(User.objects.all(), "carrier pigeon")


def test_an_unknown_age_needs_a_verified_consent_and_the_eighteenth_birthday_counts_on_29_february():
    unknown = UserFactory(date_of_birth=None)
    consent(unknown)  # declared, not verified
    assert not marketable(User.objects.filter(pk=unknown.pk), "email").exists()
    assert adult_born_by(date(2028, 2, 29)) == date(2010, 2, 28)
    assert adult_born_by(date(2026, 3, 1)) == date(2008, 3, 1)  # born 29 February 2008: 18 from 1 March
