"""The site's switches from the panel (SiteSetting) over the environment's, in config/ and where the code reads them,
from now or from a time to come, with their history; maintenance needs its own permission; the feature flags."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.tests import birthday
from api.tests import student
from shop.factories import ProductFactory
from staff.config import KNOWN_FLAGS
from staff.models import FeatureFlag, SiteSetting

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
CONFIG = "/api/v1/config/"


def put(user, key, value, **body):
    return signed_in(user).put(f"{STAFF}settings/{key}/", {"value": value, "reason": "Launch day", **body},
                               format="json")  # fmt: skip


def test_the_panels_value_overrides_the_environments_in_config_and_null_goes_back(settings):
    settings.SHOP_OPEN, settings.SHOP_COD_ENABLED = True, False
    admin = make_staff(roles.ADMIN)
    response = put(admin, "SHOP_OPEN", False)
    assert response.status_code == 200 and response.json()["source"] == "database"
    put(admin, "SHOP_COD_ENABLED", True)
    put(admin, "PARENTAL_CONSENT_MODE", "verified")
    put(admin, "WEB_COURSE", True)
    data = APIClient().get(CONFIG).json()
    assert (data["shop"]["open"], data["shop"]["cod"], data["parental_consent"], data["web_course"]) == (
        False, True, "verified", True)  # fmt: skip
    put(admin, "SHOP_OPEN", None)  # back to the environment's
    assert APIClient().get(CONFIG).json()["shop"]["open"] is True
    rows = signed_in(admin).get(f"{STAFF}settings/SHOP_OPEN/").json()
    assert [row["value"] for row in rows] == [None, False]  # the history, newest first
    change = events("setting.changed").first()
    assert change.changes == {"SHOP_OPEN": [True, False]} and change.reason == "Launch day"


def test_the_code_follows_the_panel_shop_open_cash_on_delivery_and_the_consent_mode(settings):
    settings.SHOP_OPEN, settings.PARENTAL_CONSENT_MODE, settings.SHOP_COD_ENABLED = True, "declared", True
    admin = make_staff(roles.ADMIN)
    customer = APIClient()
    customer.force_authenticate(student())
    product = ProductFactory()
    assert customer.post("/api/v1/cart/items/", {"product": product.slug, "quantity": 1}).status_code in (200, 201)
    put(admin, "SHOP_OPEN", False)
    closed = customer.post("/api/v1/cart/items/", {"product": product.slug, "quantity": 1})
    assert (closed.status_code, closed.json()["detail"]) == (403, "The shop opens soon.")
    child = student(date_of_birth=birthday(15), parent_name="A", parent_contact="anita@example.com")
    assert not child.consent_pending
    put(admin, "PARENTAL_CONSENT_MODE", "verified")
    assert type(child).objects.get(pk=child.pk).consent_pending  # a parent must confirm now
    from shop.services import ShopError, create_order

    put(admin, "SHOP_COD_ENABLED", False)  # the environment says on
    with pytest.raises(ShopError, match="Cash on delivery is not available"):
        create_order(None, user=None, email="a@example.com", address={"state": "AS"}, method="cod")


def test_a_change_from_a_time_to_come_waits_for_it(settings):
    settings.SHOP_OPEN = True
    admin = make_staff(roles.ADMIN)
    later = timezone.now() + timedelta(hours=2)
    described = put(admin, "SHOP_OPEN", False, effective_from=later.isoformat()).json()
    assert described["value"] is True and described["scheduled"][0]["value"] is False
    assert APIClient().get(CONFIG).json()["shop"]["open"] is True
    SiteSetting.objects.filter(key="SHOP_OPEN").update(effective_from=timezone.now() - timedelta(seconds=1))
    from staff.config import changed

    changed(SiteSetting)  # (what the cache would do by itself within a minute, or at the change's time)
    assert APIClient().get(CONFIG).json()["shop"]["open"] is False


def test_maintenance_needs_its_own_permission_and_tells_the_owners(settings, django_capture_on_commit_callbacks):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    admin, sales = make_staff(roles.ADMIN), make_staff(roles.SALES)
    assert put(sales, "MAINTENANCE_MODE", True).status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        assert put(admin, "MAINTENANCE_MODE", True).status_code == 200
    put(admin, "MAINTENANCE_BANNER", "Back at 6 pm")
    assert APIClient().get(CONFIG).json()["maintenance"] == {"on": True, "banner": "Back at 6 pm"}
    assert any("Maintenance mode" in message.subject for message in mail.outbox)
    assert put(admin, "MAINTENANCE_MODE", "yes").status_code == 400  # true or false
    assert put(admin, "PARENTAL_CONSENT_MODE", "maybe").status_code == 400
    assert signed_in(admin).put(f"{STAFF}settings/NO_SUCH/", {"value": 1, "reason": "x"}).status_code == 404
    assert put(admin, "SHOP_OPEN", False, reason="").status_code == 400  # say why


def test_settings_list_what_is_in_effect_and_where_it_comes_from(settings):
    settings.SHOP_COD_ENABLED = False
    rows = {row["key"]: row for row in signed_in(make_staff(roles.ADMIN)).get(STAFF + "settings/").json()}
    assert rows["SHOP_COD_ENABLED"] == {
        **rows["SHOP_COD_ENABLED"], "value": False, "environment": False, "source": "environment", "kind": "bool",
        "permission": "staff.manage_settings"}  # fmt: skip
    assert rows["PARENTAL_CONSENT_MODE"]["kind"] == ["declared", "verified"]


def test_feature_flags_are_switched_with_a_reason_and_listed_in_the_manifest():
    admin = make_staff(roles.ADMIN)
    response = signed_in(admin).put(f"{STAFF}flags/ERP_SYNC_ORDERS/", {"value": True, "reason": "Cut over"},
                                    format="json")  # fmt: skip
    assert response.status_code == 200 and FeatureFlag.objects.get().changed_by == admin
    flags = {flag["key"]: flag for flag in signed_in(admin).get(STAFF + "flags/").json()}
    flag = flags.pop("ERP_SYNC_ORDERS")
    assert (flag["key"], flag["value"], flag["reason"], flag["source"]) == (
        "ERP_SYNC_ORDERS",
        True,
        "Cut over",
        "database",
    )
    assert set(flags) == set(
        KNOWN_FLAGS
    )  # the ERP switches, never set: the environment's value (test_settings_history)
    assert signed_in(make_staff(roles.SUPPORT)).get(STAFF + "session/").json()["flags"] == {"ERP_SYNC_ORDERS": True}
    assert signed_in(admin).put(f"{STAFF}flags/lower_case/", {"value": True, "reason": "x"}).status_code == 404
    assert (
        signed_in(make_staff(roles.SALES))
        .put(f"{STAFF}flags/ERP_SYNC_ORDERS/", {"value": False, "reason": "x"})
        .status_code
        == 403
    )
    assert events("flag.changed").get().changes == {"ERP_SYNC_ORDERS": [None, True]}


def test_each_setting_and_flag_has_its_history_and_the_page_its_groups(settings):
    settings.ERP_ENABLED = True
    admin = make_staff(roles.ADMIN)
    put(admin, "SHOP_OPEN", False)
    put(admin, "SHOP_OPEN", True, reason="Open again")
    history = signed_in(admin).get(f"{STAFF}settings/SHOP_OPEN/history/").json()
    assert [(row["value"], row["reason"], row["changed_by"]) for row in history] == [
        (True, "Open again", admin.pk),
        (False, "Launch day", admin.pk),
    ]
    assert signed_in(admin).get(f"{STAFF}settings/NOT_A_SETTING/history/").status_code == 404
    groups = {row["key"]: row["group"] for row in signed_in(admin).get(f"{STAFF}settings/").json()}
    assert (groups["SHOP_OPEN"], groups["PARENTAL_CONSENT_MODE"], groups["MAINTENANCE_MODE"]) == (
        "shop",
        "consent",
        "maintenance",
    )
    flags = {flag["key"]: flag for flag in signed_in(admin).get(f"{STAFF}flags/").json()}
    erp = flags["ERP_ENABLED"]
    assert (erp["value"], erp["environment"], erp["source"], erp["group"]) == (True, True, "environment", "erp")
    url = f"{STAFF}flags/ERP_ENABLED/"
    assert signed_in(admin).put(url, {"value": "yes", "reason": "x"}, format="json").status_code == 400
    assert signed_in(admin).put(url, {"value": False, "reason": "Pause the sync"}, format="json").status_code == 200
    flags = {flag["key"]: flag for flag in signed_in(admin).get(f"{STAFF}flags/").json()}
    assert (flags["ERP_ENABLED"]["value"], flags["ERP_ENABLED"]["source"]) == (False, "database")
    [row] = signed_in(admin).get(f"{STAFF}flags/ERP_ENABLED/history/").json()
    assert (row["value"], row["reason"]) == (False, "Pause the sync")
    assert signed_in(make_staff(roles.SUPPORT)).get(f"{STAFF}flags/ERP_ENABLED/history/").status_code == 403
