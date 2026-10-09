"""Secrets: MultiFernet over INTEGRATION_KEYS (encrypt, decrypt with any key, rotate under the first), the rotation
command, what is shown of a secret, and the refusals without keys on a server."""

import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command

from integrations import checks, crypto
from integrations.models import IntegrationAccount

pytestmark = pytest.mark.django_db
BASE_DIR = Path(__file__).resolve().parents[2]


def test_a_secret_is_encrypted_with_the_first_key_and_read_with_any(settings, fernet_keys):
    old, new = fernet_keys
    token = crypto.encrypt("s3cret")
    assert "s3cret" not in token and crypto.decrypt(token) == "s3cret"
    settings.INTEGRATION_KEYS = [new, old]  # a new key put first: old tokens still read
    assert crypto.decrypt(token) == "s3cret"
    rotated = crypto.rotate(token)
    settings.INTEGRATION_KEYS = [new]  # the old key removed: only the rotated token reads
    assert crypto.decrypt(rotated) == "s3cret"
    with pytest.raises(crypto.SecretUnreadable):
        crypto.decrypt(token)


def test_without_keys_development_and_tests_use_one_made_from_the_secret_key_and_a_server_none(settings):
    settings.INTEGRATION_KEYS = []
    assert crypto.decrypt(crypto.encrypt("x")) == "x"  # TESTING
    settings.TESTING = settings.DEBUG = False
    with pytest.raises(ImproperlyConfigured, match="INTEGRATION_KEYS is empty"):
        crypto.encrypt("x")


def test_rotate_integration_keys_re_encrypts_every_secret_of_every_account(settings, fernet_keys):
    old, new = fernet_keys
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="live")
    account.set_credentials({"email": "api@examleaf.in", "password": "pass-word-1234"})
    account.save()
    account.set_token("jwt-token", None)
    webhook = account.rotate_webhook_token()
    IntegrationAccount.objects.create(provider="erpnext", mode="test")  # nothing secret: left alone
    settings.INTEGRATION_KEYS = [new, old]
    out = StringIO()
    call_command("rotate_integration_keys", stdout=out)
    assert "1 account(s)" in out.getvalue()
    settings.INTEGRATION_KEYS = [new]
    account.refresh_from_db()
    assert account.get_credentials() == {"email": "api@examleaf.in", "password": "pass-word-1234"}
    assert account.get_token() == "jwt-token" and account.webhook_token_matches(webhook)


def test_rotation_stops_at_a_secret_no_key_reads(settings, fernet_keys):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="live")
    account.set_credentials({"password": "x" * 12})
    account.save()
    settings.INTEGRATION_KEYS = [Fernet.generate_key().decode()]  # the old key gone too soon
    with pytest.raises(CommandError, match=f"Account #{account.pk}"):
        call_command("rotate_integration_keys", stdout=StringIO())


def test_only_the_last_four_characters_are_shown_and_new_credentials_drop_the_token(account):
    account.set_credentials({"email": "api-user@examleaf.in", "password": "correct-horse-battery"})
    account.save()
    account.set_token("cached", None)
    account.rotate_webhook_token()
    shown = account.masked()
    assert shown["credentials"] == {"email": "…f.in", "password": "…tery"}
    assert shown["webhook_token"].startswith("…") and len(shown["webhook_token"]) == 5
    assert "correct-horse" not in account.credentials  # encrypted at rest
    account.set_credentials({"email": "new@examleaf.in", "password": "another-password"})
    assert account.token == "" and account.token_expires_at is None and account.rotate_by is not None


def test_a_server_with_accounts_and_no_keys_refuses_to_start(settings, account):
    settings.INTEGRATION_KEYS, settings.DEBUG, settings.TESTING = [], False, False
    assert [error.id for error in checks.integration_keys(None, databases=["default"])] == ["integrations.E001"]
    assert checks.integration_keys(None, databases=None) == []  # check --deploy, no database: not asked
    settings.INTEGRATION_KEYS = [Fernet.generate_key().decode()]
    assert checks.integration_keys(None, databases=["default"]) == []
    settings.INTEGRATION_KEYS = []
    IntegrationAccount.objects.all().delete()
    assert checks.integration_keys(None, databases=["default"]) == []  # nothing to read yet


def test_a_value_that_is_not_a_fernet_key_stops_the_settings():
    env = {
        **os.environ,
        "SECRET_KEY": "ci-only-not-secret-but-fifty-characters-long-as-settings-ask",
        "INTEGRATION_KEYS": f"{Fernet.generate_key().decode()},not-a-key",
        "DEBUG": "0",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import examleaf.settings"], cwd=BASE_DIR, env=env, capture_output=True, text=True
    )
    assert result.returncode != 0 and "INTEGRATION_KEYS holds a value that is not a Fernet key" in result.stderr
