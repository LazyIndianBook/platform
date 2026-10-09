"""The ERPNext sync in the admin: every page opens with rows behind it, nothing is added there, and the actions
replay, discard (with a reason) and resolve (with a note)."""

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserFactory
from erp import inbound, reconcile
from erp.client import client
from erp.fake import FAKE
from erp.models import ErpOutbox, ErpReconciliationDifference

from .helpers import ordered, pay_offline, relay, stock_in

pytestmark = pytest.mark.django_db
CONFLICT = {"message": {"ok": False, "error": {"code": "conflict", "message": "Taken.", "field": "invoice_number"}}}


@pytest.fixture
def superuser_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


@pytest.fixture
def rows_of_everything(on, book, customer):
    relay()
    stock_in(book, 10)
    inbound.refresh_stock(client())
    pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    relay()
    FAKE.add_b2b("Quotation", party_name="St. Mary's School", grand_total=1200)
    inbound.pull(["Quotation"])
    reconcile.run(timezone.localdate())


def test_every_page_opens_and_nothing_is_added(superuser_client, rows_of_everything):
    for model in admin.site._registry:
        if model._meta.app_label != "erp":
            continue
        base = f"admin:erp_{model._meta.model_name}"
        assert superuser_client.get(reverse(f"{base}_changelist")).status_code == 200, model
        assert superuser_client.get(reverse(f"{base}_changelist") + "?q=a&o=1").status_code == 200, model
        assert superuser_client.get(reverse(f"{base}_add")).status_code == 403, model
        row = model._default_manager.first()
        assert row is not None, model
        assert superuser_client.get(reverse(f"{base}_change", args=[row.pk])).status_code == 200, model


def test_the_actions(superuser_client, rows_of_everything):
    dead = ErpOutbox.objects.get(state="dead")
    url = reverse("admin:erp_erpoutbox_changelist")
    superuser_client.post(url, {"action": "replay", "_selected_action": [dead.pk]})
    dead.refresh_from_db()
    assert dead.state == "pending"
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    relay()
    form = superuser_client.post(url, {"action": "discard", "_selected_action": [dead.pk]})
    assert b"Why it is given up" in form.content  # the reason first
    superuser_client.post(url, {"action": "discard", "_selected_action": [dead.pk], "apply": "1", "reason": "By hand."})
    dead.refresh_from_db()
    assert dead.state == "discarded" and dead.failure.discard_reason == "By hand."
    difference = ErpReconciliationDifference.objects.first()
    url = reverse("admin:erp_erpreconciliationdifference_changelist")
    body = {"action": "resolve", "_selected_action": [difference.pk], "apply": "1", "note": "Checked."}
    superuser_client.post(url, body)
    difference.refresh_from_db()
    assert difference.note == "Checked." and difference.resolved_at
