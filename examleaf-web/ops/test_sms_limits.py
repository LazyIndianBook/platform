"""The SMS limits (SECURITY_REVIEW_PHASE5_6.md M2): per number, per account and per purpose before the daily cap, and
a refused SMS is never reported as sent."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from api.tests import student
from ops import sms
from ops.models import SmsLog

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
PHONE = "+919864012345"


def earlier(user=None, phone=PHONE, kind="otp", hours=0, count=1):
    """SmsLog rows of SMS sent `hours` ago."""
    for _ in range(count):
        row = SmsLog.objects.create(
            kind=kind, phone_hash=sms.phone_hash(phone), phone_last4=phone[-4:], user=user, status=SmsLog.Status.SENT
        )
        SmsLog.objects.filter(pk=row.pk).update(created=timezone.now() - timedelta(hours=hours))


def test_one_number_gets_five_sms_an_hour_and_ten_a_day(capsys):
    earlier(count=5)
    assert not sms.queue_sms("otp", PHONE, {"otp": "111111"})  # the sixth within the hour
    assert "111111" not in capsys.readouterr().out
    SmsLog.objects.update(created=timezone.now() - timedelta(hours=2))
    assert sms.queue_sms("otp", PHONE, {"otp": "222222"})  # the hour has passed
    earlier(hours=3, count=4)
    assert not sms.queue_sms("otp", PHONE, {"otp": "333333"})  # the eleventh within the day
    assert sms.queue_sms("otp", "+919864099999", {"otp": "444444"})  # another number
    out = capsys.readouterr().out
    assert "222222" in out and "333333" not in out and "444444" in out
    assert SmsLog.objects.filter(status=SmsLog.Status.CAPPED).count() == 2


def test_one_account_gets_twenty_sms_a_day(capsys):
    user = UserFactory()
    for number in range(20):
        earlier(user, phone=f"+91986401{number:04d}", hours=5)
    assert not sms.queue_sms("order_placed", "+919864077777", {"var1": "EL-2026-000001"}, user=user)
    assert sms.queue_sms("order_placed", "+919864077777", {"var1": "EL-2026-000001"}, user=UserFactory())


def test_each_purpose_keeps_to_its_share_of_the_day_so_codes_still_go(settings):
    settings.SMS_DAILY_CAP = 10  # orders 3, parents' links 1, codes 7
    earlier(kind="order_shipped", phone="+919864000001", count=3)
    assert not sms.queue_sms("order_delivered", "+919864000002", {"var1": "EL-2026-000002"})
    earlier(kind="parent_consent", phone="+919864000003")
    assert not sms.queue_sms("parent_consent", "+919864000004", {"var1": "a student", "var2": "x"})
    assert sms.queue_sms("otp", "+919864000005", {"otp": "555555"})  # the codes' share is untouched


def test_the_app_is_told_when_a_code_was_not_sent():
    """M2: a code a limit stops is not reported as sent ("Code sent by SMS."): 429 with the reason, and no token."""
    student(login_phone=PHONE, login_phone_verified=True)
    earlier(count=5)
    response = APIClient().post("/api/v1/auth/phone/code/", {"phone": "98640 12345"}, format="json")
    assert response.status_code == 429 and response.json()["detail"].startswith("Too many messages have gone")
    assert SmsLog.objects.filter(status=SmsLog.Status.CAPPED).count() == 1
