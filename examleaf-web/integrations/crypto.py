"""The encryption of what IntegrationAccount keeps secret (credentials, the cached access token, the webhook tokens):
Fernet (AES-128-CBC with HMAC-SHA256, from `cryptography`) through MultiFernet over INTEGRATION_KEYS, newest first. A
value is encrypted with the first key and read with any of them, so a key is rotated by putting a new one first,
running `manage.py rotate_integration_keys` (which re-encrypts every row under it) and then removing the old one
(RUNBOOK.md "Integration keys")."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SecretUnreadable(ImproperlyConfigured):
    """A stored secret that none of INTEGRATION_KEYS opens: a key removed before the rows were rotated, or a copy of
    the database restored without its key."""


def keys():
    """INTEGRATION_KEYS, newest first. In development and in the tests, without them, one key made from SECRET_KEY, so
    that nothing needs setting up there; a server (DEBUG off) has none of its own (integrations.E001)."""
    if settings.INTEGRATION_KEYS:
        return list(settings.INTEGRATION_KEYS)
    if settings.DEBUG or settings.TESTING:
        digest = hashlib.sha256(f"integrations:{settings.SECRET_KEY}".encode()).digest()
        return [base64.urlsafe_b64encode(digest).decode()]
    raise ImproperlyConfigured("INTEGRATION_KEYS is empty: no integration secret can be kept or read (DEPLOYMENT.md).")


def fernet():
    return MultiFernet([Fernet(key) for key in keys()])


def encrypt(text):
    return fernet().encrypt(text.encode()).decode()


def decrypt(token):
    try:
        return fernet().decrypt(token.encode()).decode()
    except InvalidToken as error:
        raise SecretUnreadable("An integration secret cannot be read with INTEGRATION_KEYS (RUNBOOK.md).") from error


def rotate(token):
    """The token encrypted again under the first key, its timestamp kept (MultiFernet.rotate)."""
    try:
        return fernet().rotate(token.encode()).decode()
    except InvalidToken as error:
        raise SecretUnreadable("An integration secret cannot be read with INTEGRATION_KEYS (RUNBOOK.md).") from error
