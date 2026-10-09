"""The permission catalogue (research 1.4): every permission a role names is catalogued and exists, every staff
permission is listed by hand, OWNER holds exactly the catalogued ones, and the risk drives the same behaviour
everywhere."""

import pytest
from django.contrib.auth.models import Group, Permission

from accounts import roles
from staff import catalogue
from staff.models import StaffPermissions

pytestmark = pytest.mark.django_db


def named_permissions():
    for name, wanted in roles.ROLES.items():
        if isinstance(wanted, list):
            for perm in wanted:
                if perm != roles.VIEW_ALL:
                    yield name, perm
    for perm in [*roles.OWNER_ONLY, *roles.MONEY_APPROVALS]:
        yield "OWNER_ONLY or MONEY_APPROVALS", perm


def test_every_permission_a_role_names_is_catalogued_and_exists():
    existing = {f"{app}.{codename}" for app, codename in Permission.objects.values_list("content_type__app_label",
                                                                                         "codename")}  # fmt: skip
    for role, perm in named_permissions():
        assert catalogue.entry(perm) is not None, (role, perm)
        assert perm in existing, (role, perm)


def test_every_staff_permission_is_listed_by_hand_with_a_known_area_and_risk():
    staff = Permission.objects.filter(content_type__app_label="staff")
    assert staff.count() == len(catalogue.STAFF_ACTIONS) + len(catalogue.STAFF_MODELS)
    for perm in staff:
        entry = catalogue.EXPLICIT.get(f"staff.{perm.codename}")
        assert entry is not None, perm.codename
        assert entry.risk in catalogue.RISKS and entry.area and entry.label
    holder = {codename for codename, _ in StaffPermissions._meta.permissions}
    assert holder == {row[0] for row in catalogue.STAFF_ACTIONS}
    required = {"refund_order", "approve_refund", "record_offline_payment", "publish_paper", "reveal_contact"}
    required |= {"suspend_user", "reset_user_mfa", "impersonate_user", "export_personal_data", "assign_role"}
    required |= {"approve_role_change", "view_auditlog", "export_auditlog", "manage_api_keys", "replay_webhook"}
    required |= {"toggle_maintenance", "break_glass", "view_inbox", "manage_settings", "manage_flags"}
    required |= {"handle_data_request", "manage_incident", "view_system"}
    assert required <= holder, required - holder


def test_owner_holds_every_catalogued_permission_and_break_glass_accounts_alone_the_rest():
    owner = set(Group.objects.get(name=roles.OWNER).permissions.values_list("content_type__app_label", "codename"))
    for app, codename in Permission.objects.values_list("content_type__app_label", "codename"):
        assert ((app, codename) in owner) == (catalogue.entry(f"{app}.{codename}") is not None), (app, codename)
    assert ("django_celery_beat", "add_periodictask") not in owner  # periodic tasks stay superuser-only (plan 5.19)
    assert ("django_celery_beat", "view_periodictask") in owner


def test_a_custom_permission_nobody_catalogued_has_no_entry_and_counts_as_critical():
    assert catalogue.entry("shop.export_order").risk == catalogue.HIGH  # listed by hand
    assert catalogue.entry("shop.change_order").risk == catalogue.MEDIUM  # Django's verb: by rule
    assert catalogue.entry("shop.delete_order").risk == catalogue.HIGH
    assert catalogue.entry("shop.view_order").label == "View orders"
    assert catalogue.entry("shop.fly_order") is None and catalogue.entry("nope.view_thing") is None
    assert catalogue.risk("shop.fly_order") == catalogue.CRITICAL and catalogue.needs_reauth("shop.fly_order")


def test_the_risk_says_what_it_triggers():
    refund, impersonate, unlock = (catalogue.entry(f"staff.{name}") for name in
                                   ["refund_order", "impersonate_user", "unlock_user"])  # fmt: skip
    assert refund.reauth and refund.approval and not refund.alerts
    assert impersonate.reauth and impersonate.alerts  # critical: re-authenticate, and the owners are told
    assert not unlock.reauth and not unlock.alerts
    assert catalogue.entry("staff.manage_incident").alerts  # alerts by hand, without the re-authentication
    assert catalogue.entry("staff.change_price").approval  # a price may wait for an approver (Phase B: its own)
    assert catalogue.entry("shop.add_offer").approval and not catalogue.entry("shop.change_product").approval
