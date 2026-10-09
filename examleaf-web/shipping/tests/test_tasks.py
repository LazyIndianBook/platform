"""The tasks and commands: the Shiprocket token (renewed from day 9, and once after a 401), the connection test, a
booking that gives up into the dead-letter list, an open circuit, the PIN survey, the beat entries and the commands."""

from datetime import timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command
from django.utils import timezone

from integrations.client import CircuitOpen, IntegrationRejected
from integrations.models import IntegrationAccount, IntegrationCall, IntegrationFailure
from integrations.services import test_connection
from shipping import services, tasks
from shipping.carriers import carrier_for
from shipping.carriers.fake import FAKE
from shipping.models import PickupLocation, PinServiceability, ShipmentDetail
from shop.models import PinCode

pytestmark = pytest.mark.django_db


def test_the_token_is_renewed_from_day_nine_and_after_a_401(account, pickup, prepaid):
    carrier = carrier_for(account)
    carrier.wallet_balance()
    assert FAKE.logins == 1 and account.token_expires_at - timezone.now() > timedelta(days=9, hours=23)
    IntegrationAccount.objects.filter(pk=account.pk).update(token_expires_at=timezone.now() + timedelta(days=2))
    assert tasks.renew_token() == 0  # day 8: still good
    IntegrationAccount.objects.filter(pk=account.pk).update(token_expires_at=timezone.now() + timedelta(hours=23))
    assert tasks.renew_token() == 1 and FAKE.logins == 2  # day 9
    FAKE.revoke_token()  # revoked early, or Shiprocket lost it
    assert carrier_for(IntegrationAccount.objects.get(pk=account.pk)).wallet_balance() == 1250
    assert FAKE.logins == 3 and IntegrationCall.objects.filter(status_code=401).count() == 1


def test_the_log_in_s_password_and_token_are_never_logged(account):
    carrier_for(account).wallet_balance()
    login = IntegrationCall.objects.get(operation="login")
    assert "a-long-api-password" not in login.excerpt and FAKE.token not in login.excerpt
    assert '"password":"[secret]"' in login.excerpt


def test_a_trial_call_that_needs_a_new_token_logs_in_as_part_of_the_trial(account):
    from integrations.models import COOL_OFF

    past = timezone.now() - COOL_OFF - timedelta(minutes=1)
    IntegrationAccount.objects.filter(pk=account.pk).update(
        circuit_state="open", opened_at=past, token="", token_expires_at=None
    )
    assert carrier_for(IntegrationAccount.objects.get(pk=account.pk)).wallet_balance() == 1250
    account.refresh_from_db()
    assert account.circuit_state == "closed" and FAKE.logins == 1


def test_credentials_that_do_not_log_in_are_a_refusal(account):
    account.set_credentials({"email": "api-user@example.com", "password": ""})
    account.save()
    with pytest.raises(IntegrationRejected, match="login: HTTP 400"):
        carrier_for(account).wallet_balance()


def test_the_connection_test_reads_the_wallet_balance(account):
    IntegrationAccount.objects.filter(pk=account.pk).update(enabled=False)  # tested before it is switched on
    account.refresh_from_db()
    assert test_connection(account) == (True, "Connected: wallet balance ₹1,250.00.")
    account.refresh_from_db()
    assert account.last_test_ok and account.last_test_at
    FAKE.fail("/account/details/wallet-balance", status=500)
    ok, message = test_connection(account)
    assert not ok and "HTTP 500" in message


def test_a_refused_booking_gives_up_into_the_dead_letter_list(account, pickup, prepaid):
    PickupLocation.objects.filter(pk=pickup.pk).update(nickname="Warehouse")  # not a nickname Shiprocket knows
    shipment = services.prepare(prepaid, account=account, courier_company_id=51)
    result = tasks.book_shipment.apply(args=(shipment.pk, 51), throw=False)
    assert result.state == "FAILURE"
    failure = IntegrationFailure.objects.get()
    assert failure.task_name == "shipping.tasks.book_shipment" and failure.args == {
        "args": [shipment.pk, 51],
        "kwargs": {},
    }
    assert "Wrong Pickup location" in failure.last_error and failure.account == account
    PickupLocation.objects.filter(pk=pickup.pk).update(nickname="Primary")  # fixed, then replayed
    assert failure.replay() and not failure.replay()


def test_an_open_circuit_stops_the_booking_before_it_calls(account, pickup, prepaid):
    shipment = services.prepare(prepaid, account=account, courier_company_id=51)
    account.force_open()
    calls = len(FAKE.calls)
    with pytest.raises(CircuitOpen):
        tasks.book_shipment.delay(shipment.pk, 51)
    assert len(FAKE.calls) == calls and ShipmentDetail.objects.get(shipment=shipment).locked_until is None


def test_the_survey_of_the_north_east_s_pins(account, pickup):
    PinCode.objects.bulk_create(
        [
            PinCode(pin="781024", states=["AS"], districts=["Kamrup Metro"]),
            PinCode(pin="793001", states=["ML"], districts=["East Khasi Hills"]),
            PinCode(pin="737101", states=["SK"], districts=["Gangtok"]),  # Sikkim, inside West Bengal's range
            PinCode(pin="110001", states=["DL"], districts=["New Delhi"]),
        ]
    )
    FAKE.unserviceable = {"793001"}
    assert services.survey_pins(account) == (3, 1, 1)
    assert set(PinServiceability.objects.values_list("pin", flat=True)) == {"781024", "793001", "737101"}
    assert PinServiceability.objects.get(pin="793001").courier_company_id == 0  # India Post's
    amazon = PinServiceability.objects.get(pin="781024", courier_name="Amazon Shipping 1kg")
    assert amazon.prepaid and not amazon.cod and amazon.etd_days == 7
    out = StringIO()
    call_command("shipping_survey_pins", "781024", stdout=out)
    assert "1 PIN(s) surveyed" in out.getvalue()
    assert services.survey_pins(account, limit=1) == (1, 0, 0)  # the one surveyed longest ago


def test_the_beat_runs_the_shipping_tasks():
    tasks_ = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    for name in [
        "poll_tracking",
        "sync_statement",
        "check_cod_remittances",
        "check_weight_discrepancies",
        "renew_token",
        "survey_pins",
        "send_held_messages",
    ]:
        assert f"shipping.tasks.{name}" in tasks_
    assert "integrations.tasks.purge_old_records" in tasks_


def test_the_smoke_test_is_for_the_live_account_and_asks_first(account):
    with pytest.raises(CommandError, match="test mode"):
        call_command("shipping_smoke_test", "--yes")
    IntegrationAccount.objects.filter(pk=account.pk).update(mode="live")
    with pytest.raises(CommandError, match="--yes"):
        call_command("shipping_smoke_test")
    IntegrationAccount.objects.filter(pk=account.pk).update(enabled=False)
    with pytest.raises(CommandError, match="No Shiprocket account"):
        call_command("shipping_smoke_test", "--yes")


def test_the_commands_report(account, pickup, prepaid):
    out = StringIO()
    for command in [
        "shipping_poll_tracking",
        "shipping_sync_statement",
        "shipping_check_cod",
        "shipping_check_discrepancies",
    ]:
        call_command(command, stdout=out)
    text = out.getvalue()
    assert "Tracking read for 0 parcel(s)." in text and "0 new line(s)." in text and "None awaited." in text
    assert "0 weight dispute(s)." in text
