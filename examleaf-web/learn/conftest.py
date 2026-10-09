"""The course module's test helpers: a published course of a subject (learn.tests.make_course), members of staff with
their roles (narrowed to a subject where the role is), the staff API's sign-in (staff/tests/conftest.py), a key for
the book codes' hashes."""

import pytest

from accounts import roles
from content.conftest import narrowed
from staff.tests.conftest import STAFF, events, make_staff, signed_in  # noqa: F401  (the course tests' helpers)

COURSE = STAFF + "course/"


@pytest.fixture(autouse=True)
def quick_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # many users per test


@pytest.fixture(autouse=True)
def code_secret(settings):
    settings.LEARN_CODE_SECRET = "a-test-key-for-the-book-codes"


@pytest.fixture
def physics(db):
    from .tests import make_course

    return make_course(chapters=2, clips=3)


@pytest.fixture
def editor():
    return narrowed(roles.CONTENT_EDITOR, "PHY")


@pytest.fixture
def reviewer():
    return narrowed(roles.REVIEWER, "PHY")


@pytest.fixture
def support():
    return make_staff(roles.SUPPORT)


@pytest.fixture
def owner():
    return make_staff(roles.OWNER)
