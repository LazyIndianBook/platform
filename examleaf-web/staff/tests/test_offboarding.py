"""Offboarding's checklist (research 2.9): each step a row, those the panel did at once done with their counts, those
done by hand ticked by an owner only (audited), the inbox item open until the last one; the ERPNext user each role
calls for, applied by hand (people/<id>/erp/)."""

import pytest

from accounts import roles
from integrations.models import IntegrationAccount
from staff.models import AuditEvent, InboxItem, OffboardingStep, StaffOffboarding
from staff.services import OFFBOARDING_STEPS

from .conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
PEOPLE = STAFF + "people/"
MANUAL = [key for key, kind, _ in OFFBOARDING_STEPS if kind == "manual"]


def offboarded(owner, *role_names):
    person = make_staff(*role_names)
    response = signed_in(owner).post(f"{PEOPLE}{person.pk}/offboard/", {"reason": "Left the company"})
    assert response.status_code == 200, response.content
    return person, StaffOffboarding.objects.get(pk=response.json()["offboarding"])


def test_each_step_is_recorded_what_the_panel_did_with_its_counts_the_rest_to_tick():
    owner = make_staff(roles.OWNER)
    person, offboarding = offboarded(owner, roles.SALES)
    steps = {step.key: step for step in offboarding.steps.all()}
    assert list(steps) == [key for key, _, _ in OFFBOARDING_STEPS]
    assert all(steps[key].state == "done" and steps[key].done_by == owner for key, kind, _ in OFFBOARDING_STEPS
               if kind == "auto")  # fmt: skip
    assert steps["roles_removed"].detail == "SALES; 0 scopes" and steps["sessions_ended"].detail == "0 ended"
    assert steps["erpnext_user"].state == "not_needed" and "not in use" in steps["erpnext_user"].detail
    assert all(steps[key].state == "todo" for key in MANUAL if key != "erpnext_user")
    [item] = InboxItem.objects.filter(kind="offboarding", done_at=None)
    assert item.permission == "staff.assign_role" and "12 steps to do by hand" in item.title
    checklist = signed_in(owner).get(f"{PEOPLE}{person.pk}/offboarding/").json()
    assert checklist["reason"] == "Left the company" and checklist["steps"][0]["label"].startswith("Deactivated")
    assert signed_in(owner).get(f"{PEOPLE}{person.pk}/").status_code == 200  # still in reach, as one who was staff


def test_only_an_owner_ticks_the_steps_done_by_hand_and_the_last_one_finishes_it():
    owner = make_staff(roles.OWNER)
    person, offboarding = offboarded(owner, roles.SUPPORT)
    url = f"{PEOPLE}{person.pk}/offboarding/tick/"
    assert signed_in(make_staff(roles.ADMIN)).post(url, {"step": "github", "state": "done"}).status_code == 403
    client = signed_in(owner)
    assert client.post(url, {"step": "deactivated", "state": "todo"}).status_code == 400  # the panel's own
    assert client.post(url, {"step": "nothing", "state": "done"}).status_code == 404
    todo = [step for step in MANUAL if step != "erpnext_user"]
    for step in todo[:-1]:
        assert client.post(url, {"step": step, "state": "done", "note": "Removed"}).status_code == 200
    assert InboxItem.objects.filter(kind="offboarding", done_at=None).exists()
    finished = client.post(url, {"step": todo[-1], "state": "not_needed", "note": "Never had one"}).json()
    assert finished["finished_at"] and not InboxItem.objects.filter(kind="offboarding", done_at=None).exists()
    step = OffboardingStep.objects.get(offboarding=offboarding, key=todo[-1])
    assert (step.state, step.detail, step.done_by) == ("not_needed", "Never had one", owner)
    again = client.post(url, {"step": "github", "state": "todo"}).json()  # a step put back opens it again
    assert again["finished_at"] is None and InboxItem.objects.filter(kind="offboarding", done_at=None).exists()
    ticked = AuditEvent.objects.filter(action="offboarding.ticked").order_by("id")
    assert ticked.count() == len(todo) + 1 and ticked.last().details["step"] == "github"


def test_the_erpnext_user_is_a_step_while_erpnext_is_in_use_and_the_mirror_says_what_it_should_be():
    IntegrationAccount.objects.create(provider="erpnext", mode="live")
    owner = make_staff(roles.OWNER)
    finance = make_staff(roles.FINANCE)
    mirror = signed_in(owner).get(f"{PEOPLE}{finance.pk}/erp/").json()
    assert mirror["role_profiles"] == ["EL Finance"] and mirror["enabled"] and mirror["erp_in_use"]
    assert mirror["by_role"] == [{"role": roles.FINANCE, "profiles": ["EL Finance"]}]
    support = make_staff(roles.SUPPORT)
    assert signed_in(owner).get(f"{PEOPLE}{support.pk}/erp/").json()["enabled"] is False  # no ERPNext role
    _, offboarding = offboarded(owner, roles.FINANCE)
    step = offboarding.steps.get(key="erpnext_user")
    assert (step.state, step.detail) == ("todo", "Role profiles: EL Finance.")
