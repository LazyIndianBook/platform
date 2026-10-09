"""The staff tests' helpers: members of staff with roles (and the second factor staff must have), API clients signed
in with or without a recent re-authentication, and the shop's fixtures (Razorpay mocked, no network). The roles hold
their permissions from the test database's migrate on (staff.apps.sync_roles_after_migrate)."""

import time

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from shop.conftest import commit, no_network, quick_pdf, rzp, shop_settings  # noqa: F401  (fixtures)
from staff.models import AuditEvent

STAFF = "/api/v1/staff/"


@pytest.fixture(autouse=True)
def quick_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # many users per test


def make_staff(*role_names, **fields):
    """A member of staff with these roles and an authenticator app (UserFactory gives staff one)."""
    user = UserFactory(is_staff=True, **fields)
    user.groups.set(Group.objects.filter(name__in=role_names))
    return type(user).objects.get(pk=user.pk)  # without cached roles or permissions


def signed_in(user, reauth=True):
    """The panel: a browser session of `user`, re-authenticated a moment ago (or long ago)."""
    client = APIClient()
    client.force_login(user)
    session = client.session
    at = time.time() if reauth else time.time() - 3600
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": at, "email": user.email}]
    session.save()
    return client


@pytest.fixture
def staff():
    return make_staff


@pytest.fixture
def panel():
    return signed_in


def events(action=None, **filters):
    rows = AuditEvent.objects.order_by("id")
    return rows.filter(action=action, **filters) if action else rows.filter(**filters)
