"""Legal and privacy (plan 5.15; staff/privacy_api.py, staff/privacy.py, staff/compliance.py, examleaf/retention.py,
pages/versions.py): the erasure's holds with their "kept until" lines, the erasure obeying them, the ledger re-applied
after a restore, the retention clean-up, the cockpit, legal holds, nominees, policy versions, the disclosures, the
dark-pattern self-audit and its certificate, the processors' tasks."""

import json
from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.http import int_to_base36
from rest_framework.test import APIClient

from accounts import roles
from accounts.models import ConsentRecord, DeletionRequest, LegalHold, Nominee, User
from accounts.tasks import copy_erasure_ledger, purge_due_deletions
from accounts.tests import birthday
from accounts.views import parent_signer
from api.tests import student
from examleaf import retention
from ops.models import SmsLog
from ops.tasks import purge_books, purge_expired, trim_expired
from pages.models import Page
from pages.versions import publish, publish_due, versions
from shop.factories import ProductFactory, make_order
from shop.models import Cart, CreditNote, Invoice, Order, Refund, WebhookEvent
from staff import privacy
from staff.compliance import cockpit
from staff.models import DarkPatternAudit, DataRequest, InboxItem, Incident, ProcessorRecord, SiteSetting
from staff.tasks import remind_dark_pattern_audit

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
PRIVACY = STAFF + "privacy/"


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()  # the site settings are read through the cache


def live_order(user, year="2025-26", notes=0):
    """An order of the books (live mode) with its invoice of that financial year, and credit notes."""
    Cart.objects.filter(user=user).delete()  # one cart per account: each order is made from a new one
    order = make_order((ProductFactory(), 1), user=user, email=user.email)
    Order.objects.filter(pk=order.pk).update(livemode=True)
    serial = Invoice.objects.count() + 1
    invoice = Invoice.objects.create(order=order, number=f"EL/{year}/{serial:05d}", financial_year=year, serial=serial)
    for index in range(notes):
        refund = Refund.objects.create(order=order, payment=order.payments.get(), amount=10, reason="Damaged")
        CreditNote.objects.create(
            refund=refund,
            invoice=invoice,
            number=f"CN/{year}/{serial}{index}",
            financial_year=year,
            serial=serial * 10 + index,
        )
    return order


def keep_of(report, part):
    return next(row for row in report["keep"] if row["part"] == part)


# The retention schedule


def test_the_books_are_kept_8_financial_years_or_72_months_after_the_annual_return_whichever_is_later():
    assert retention.books_until("2026-27") == date(2035, 3, 31)  # the Companies Act's 8 years outlast GST's 72 months
    assert retention.books_until("T2025-26") == date(2034, 3, 31)  # the test series: the same rule
    assert retention.books_cutoff(date(2035, 3, 31)) == date(2026, 4, 1)  # 2026-27 still kept on its last day
    assert retention.books_cutoff(date(2035, 4, 1)) == date(2027, 4, 1)  # and gone the day after


def test_every_period_kept_is_at_least_the_laws_minimum_now_and_once_the_dpdp_rules_apply():
    for rule in retention.SCHEDULE:
        for minimum in rule.minimums:
            if rule.keep_days is not None and minimum.days is not None:
                assert rule.keep_days >= minimum.days, (rule.key, minimum)
    assert retention.minimum("sms_log", date(2027, 5, 12)).days == 180
    assert retention.minimum("sms_log", date(2027, 5, 13)).days == 365
    assert retention.next_minimum("security_logs", date(2026, 10, 9)).since == date(2027, 5, 13)
    from django.conf import settings

    from shop import payments

    assert retention.rule("webhook_events").keep_days >= payments.WEBHOOK_MAX_AGE.days  # replays stay refused
    assert retention.rule("celery_results").keep_days == settings.CELERY_RESULT_EXPIRES.days


def test_the_sms_log_is_trimmed_at_90_days_and_kept_a_year_webhooks_go_at_7_days_and_silent_phones_go(settings):
    from learn.models import Device

    now = timezone.now()

    def sms(days):
        row = SmsLog.objects.create(kind="otp", phone_hash="h", phone_last4="2345", status=SmsLog.Status.SENT)
        SmsLog.objects.filter(pk=row.pk).update(created=now - timedelta(days=days))
        return row.pk

    fresh, trimmed, gone = sms(10), sms(100), sms(400)
    WebhookEvent.objects.create(event_id="evt_new", digest="1" * 64, name="payment.captured")
    WebhookEvent.objects.create(event_id="evt_old", digest="2" * 64, name="payment.captured")
    WebhookEvent.objects.filter(event_id="evt_old").update(received_at=now - timedelta(days=8))
    quiet, heard = (Device.objects.create(user=student(), token=token) for token in ("quiet", "heard"))
    Device.objects.filter(pk=quiet.pk).update(last_seen=now - timedelta(days=91))
    assert trim_expired() == {"sms_log": 2}  # the 100 and the 400 days old (the latter then deleted)
    counts = purge_expired()
    assert counts["sms_log"] == 1 and counts["webhook_events"] == 1 and counts["devices"] == 1
    assert dict(SmsLog.objects.values_list("pk", "phone_last4")) == {fresh: "2345", trimmed: ""}
    assert gone not in SmsLog.objects.values_list("pk", flat=True)
    assert list(WebhookEvent.objects.values_list("event_id", flat=True)) == ["evt_new"]
    assert list(Device.objects.values_list("token", flat=True)) == ["heard"]
    assert events("retention.purged").get().details["rows"]["sms_log"] == 1
    # a second night: nothing left to do, and no event for it
    assert trim_expired() == {"sms_log": 0} and not any(purge_expired().values())
    assert events("retention.purged").count() == 1 and events("retention.trimmed").count() == 1
    assert heard.pk  # (kept)


def test_orders_past_their_books_lose_the_customers_details_but_a_held_one_stays(commit):
    customer = student(email="rahul@example.com")
    old, held = live_order(customer, "2025-26"), live_order(customer, "2025-26")
    Order.objects.filter(pk__in=[old.pk, held.pk]).update(created=timezone.now().replace(year=2025, month=6))
    Invoice.objects.update(created=timezone.now().replace(year=2025, month=6))
    Invoice.objects.filter(order=old).update(pdf="invoices/old.pdf")
    LegalHold.objects.create(
        target_type=ContentType.objects.get_for_model(Order), target_id=str(held.pk), reason="chargeback"
    )
    assert purge_books(today=date(2034, 3, 31)) == 0  # its last day: still kept
    with commit():
        assert purge_books(today=date(2034, 4, 1)) == 1
    old.refresh_from_db()
    held.refresh_from_db()
    assert old.email == "deleted" and old.shipping_address["name"] == "deleted" and not old.invoice.pdf
    assert held.email == "rahul@example.com"
    assert purge_books(today=date(2034, 4, 1)) == 0  # again: nothing more


def test_the_retention_page_says_each_minimum_and_when_it_changes(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args: date(2026, 10, 9))
    rows = {row["key"]: row for row in signed_in(make_staff(roles.AUDITOR)).get(PRIVACY + "retention/").json()}
    sms, processing = rows["sms_log"], rows["processing_records"]
    assert sms["keep_days"] == 365 and sms["trim_days"] == 90
    assert (sms["minimum"], sms["changes_on"], sms["next_minimum"]) == ("180 days", "2027-05-13", "one year")
    assert (processing["minimum_days"], processing["changes_on"]) == (None, "2027-05-13")  # nothing before the Rules
    monkeypatch.setattr(timezone, "localdate", lambda *args: date(2027, 5, 13))
    rows = {row["key"]: row for row in signed_in(make_staff(roles.AUDITOR)).get(PRIVACY + "retention/").json()}
    assert (rows["sms_log"]["minimum"], rows["sms_log"]["changes_on"]) == ("one year", None)
    assert rows["processing_records"]["minimum_days"] == 365
    assert signed_in(make_staff(roles.PACKER)).get(PRIVACY + "retention/").status_code == 403


# The erasure: its holds, its dry run, and the erasure obeying them


def test_the_dry_run_keeps_the_books_by_financial_year_with_their_kept_until_line():
    customer = student(email="rahul@example.com")
    live_order(customer, "2025-26", notes=1)
    live_order(customer, "2026-27")
    report = privacy.erasure_report(customer)
    old, new = keep_of(report, "books:2025-26"), keep_of(report, "books:2026-27")
    assert old["until"] == date(2034, 3, 31) and new["until"] == date(2035, 3, 31)
    assert old["line"] == (
        "kept until 31 March 2034: 1 invoice and 1 credit note of 2025-26 with the orders behind them, for GST and "
        "the Companies Act (8 financial years, or 72 months after the year's annual return)"
    )
    assert new["line"].startswith("kept until 31 March 2035: 1 invoice of 2026-27 with the order behind it")


def test_the_dry_run_keeps_a_year_of_processing_logs_by_the_accounts_number_only():
    from staff.audit import record

    customer = student(email="rahul@example.com")
    record("sensitive_read", target=customer)
    log = SmsLog.objects.create(kind="otp", phone_hash="h", phone_last4="2345", user=customer, status="sent")
    report = privacy.erasure_report(customer)
    audit, sms = keep_of(report, "audit:general"), keep_of(report, "sms")
    assert audit["count"] == 1 and audit["until"] == timezone.localdate() + timedelta(days=730)
    assert "naming the account by its number only" in audit["line"]
    assert sms["until"] == timezone.localdate(log.created) + timedelta(days=365) and sms["kind"] == "processing_logs"
    assert not any(row["part"] == "sms" for row in report["erase"])


def test_a_legal_hold_on_the_person_stops_the_erasure_and_one_on_an_order_is_kept_until_its_day():
    customer = student(email="rahul@example.com")
    order = live_order(customer)
    LegalHold.objects.create(user=customer, reason="dispute", until=date(2027, 1, 31))
    LegalHold.objects.create(
        target_type=ContentType.objects.get_for_model(Order), target_id=str(order.pk), reason="chargeback"
    )
    report = privacy.erasure_report(customer)
    assert not report["can_erase"]
    assert any("A legal hold (a dispute" in block and "until 31 January 2027" in block for block in report["blocks"])
    held = [row["line"] for row in report["keep"] if row["kind"] == "legal_hold"]
    assert held[0] == "kept until 31 January 2027: the account, under a legal hold (a dispute)"
    assert held[1] == f"kept: Order {order.number}, under a legal hold (a chargeback), until released"
    deletion = DeletionRequest.objects.create(user=customer, due_at=timezone.now())
    with pytest.raises(DeletionRequest.Held):
        deletion.complete()
    assert User.objects.get(pk=customer.pk).email == "rahul@example.com"


def test_a_childs_deletion_waits_for_the_parents_link_then_the_purge_erases_it(client, commit):
    child = student(email="rahul@example.com", date_of_birth=birthday(15), parent_name="Anita Das",
                    parent_contact="anita@example.com")  # fmt: skip
    client.force_login(child)
    with commit():
        assert (
            client.post("/api/v1/me/deletion/", {"password": "Brahmaputra-2027"}, "application/json").status_code == 201
        )
    [link] = [m for m in mail.outbox if m.to == ["anita@example.com"]]
    assert "confirm the deletion" in link.subject and "/c/" in link.body
    deletion = DeletionRequest.objects.get()
    DeletionRequest.objects.filter(pk=deletion.pk).update(due_at=timezone.now())
    assert any("parent or guardian" in block for block in privacy.erasure_report(child)["blocks"])
    assert purge_due_deletions() == 0  # it waits, and the inbox says why
    assert InboxItem.objects.get(kind="compliance", done_at=None).title.startswith(
        f"Account deletion {deletion.pk} waits"
    )
    token = parent_signer(child.parent_contact).sign(int_to_base36(child.pk))
    parent = APIClient()
    page = parent.get(f"/api/v1/parent-consent/{token}/").json()
    assert page["deletion"]["confirmed"] is False
    confirmed = parent.post(f"/api/v1/parent-consent/{token}/", {"confirm": "deletion"}, format="json").json()
    assert confirmed["deletion"]["confirmed"] is True
    assert ConsentRecord.objects.filter(event="withdrawn", by_parent=True, verified_at__isnull=False).exists()
    assert events("account.deletion_parent_confirmed").get().actor_type == "anonymous"
    with commit():
        assert purge_due_deletions() == 1
    assert User.objects.get(pk=child.pk).email == f"deleted-{child.pk}@deleted.invalid"
    assert not InboxItem.objects.filter(kind="compliance", done_at=None).exists()  # closed with the deletion


def test_staff_record_a_parents_confirmation_with_its_evidence():
    child = student(email="rahul@example.com", date_of_birth=birthday(15), parent_contact="+919864012345")
    deletion = DeletionRequest.objects.create(user=child)
    url = f"{PRIVACY}deletions/{deletion.pk}/parent-confirmation/"
    support = make_staff(roles.SUPPORT)
    assert signed_in(support).post(url, {}, format="json").status_code == 400  # the evidence's reference first
    done = signed_in(support).post(url, {"evidence_ref": "Call of 9 Oct, ticket SR-2026-000041"}, format="json")
    assert done.status_code == 200 and DeletionRequest.objects.get().parent_confirmed_by == support
    record = ConsentRecord.objects.get(method=ConsentRecord.Method.STAFF_MANUAL)
    assert record.verified_by == support and record.evidence_ref.startswith("Call of 9 Oct") and not record.ip_hash
    assert signed_in(support).post(url, {"evidence_ref": "Again"}, format="json").status_code == 400
    assert not privacy.erasure_holds(child)


def test_the_erasure_keeps_the_sms_log_anonymised_drops_the_nominee_and_tells_each_processor(commit):
    customer = student(email="rahul@example.com")
    Nominee.objects.create(user=customer, name="Anita Das", contact="anita@example.com", relation="mother")
    SmsLog.objects.create(kind="otp", phone_hash="h", phone_last4="2345", user=customer, status="sent")
    ProcessorRecord.objects.create(name="Amazon SES", purpose="email", data_categories="email", country="India",
                                   holds_personal_data=True, erasure_action="ask SES to purge the address")  # fmt: skip
    ProcessorRecord.objects.create(name="Razorpay", purpose="payments", data_categories="orders", country="India")
    with commit():
        DeletionRequest.objects.create(user=customer, due_at=timezone.now()).complete()
    assert list(SmsLog.objects.values_list("user", "phone_last4")) == [(None, "")] and not Nominee.objects.exists()
    [task] = InboxItem.objects.filter(kind="processor_task")
    assert task.title == f"Erasure of account #{customer.pk} (deletion {DeletionRequest.objects.get().pk}): ask SES " \
        "to purge the address (Amazon SES)"  # fmt: skip
    assert task.permission == "staff.manage_compliance" and "rahul" not in task.title
    deletion = DeletionRequest.objects.get()
    assert deletion.subject_hash == privacy.ledger_hash("rahul@example.com")
    assert events("account.erased").get().details["deletion_request"] == deletion.pk


def test_with_the_intermediary_rule_the_registration_details_stay_180_days_then_go(settings, commit):
    settings.SUPPORT_INTERMEDIARY_RULES = True
    customer = student(email="rahul@example.com", full_name="Rahul Das")
    assert keep_of(privacy.erasure_report(customer), "registration")["kind"] == "intermediary"
    with commit():
        DeletionRequest.objects.create(user=customer, due_at=timezone.now()).complete()
    kept = User.objects.get(pk=customer.pk)
    assert kept.email == "rahul@example.com" and not kept.is_active and kept.full_name == "Rahul Das"
    deletion = DeletionRequest.objects.get()
    assert deletion.registration_until.date() == (timezone.now() + timedelta(days=180)).date()
    DeletionRequest.objects.filter(pk=deletion.pk).update(registration_until=timezone.now())
    purge_due_deletions()
    assert User.objects.get(pk=customer.pk).email == f"deleted-{customer.pk}@deleted.invalid"
    settings.SUPPORT_INTERMEDIARY_RULES = False
    assert not any(row["kind"] == "intermediary" for row in privacy.erasure_report(student())["keep"])


def test_an_erased_account_restored_from_a_backup_is_erased_again(tmp_path, settings, commit):
    settings.STORAGES = {**settings.STORAGES, "backups": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                                          "OPTIONS": {"location": str(tmp_path)}}}  # fmt: skip
    customer = student(email="rahul@example.com", full_name="Rahul Das")
    other = student(email="someone@example.com")
    restored_fields = {"email": "rahul@example.com", "full_name": "Rahul Das", "is_active": True}
    with commit():
        DeletionRequest.objects.create(user=customer, due_at=timezone.now()).complete()
    assert (tmp_path / "erasures" / f"{DeletionRequest.objects.get().pk}.json").exists()  # copied off the server
    assert DeletionRequest.objects.get().ledger_copied_at and copy_erasure_ledger() == 0  # the nightly sweep: none
    # the restore: an older backup brings the account back, and the deletion request did not exist then
    DeletionRequest.objects.all().delete()
    User.objects.filter(pk=customer.pk).update(**restored_fields)
    call_command("reapply_erasures", "--dry-run")
    assert User.objects.get(pk=customer.pk).email == "rahul@example.com"  # a dry run changes nothing
    call_command("reapply_erasures")
    assert User.objects.get(pk=customer.pk).email == f"deleted-{customer.pk}@deleted.invalid"
    assert events("account.erased").last().details["reapplied"] is True
    # an id taken by someone else since is never touched
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"user": other.pk, "subject_hash": privacy.ledger_hash("gone@example.com")}) + "\n")
    call_command("reapply_erasures", "--ledger", str(ledger), "--no-bucket")
    assert User.objects.get(pk=other.pk).email == "someone@example.com"
    exported = tmp_path / "export.jsonl"
    call_command("reapply_erasures", "--export", str(exported))
    assert json.loads(exported.read_text().splitlines()[0])["user"] == customer.pk


def test_a_staff_erasure_answers_with_what_stays_and_the_contact_block(settings, commit):
    SiteSetting.objects.create(key="DATA_PROTECTION_OFFICER", value="Priya Kalita, privacy@examleaf.in", reason="Set")
    customer = student(email="rahul@example.com")
    live_order(customer, "2025-26")
    Order.objects.update(status="delivered")
    request = DataRequest.objects.create(kind="erasure", channel="email", user=customer, requester=customer.email,
                                         summary="Erase it", identity_verified=True)  # fmt: skip
    text = signed_in(make_staff(roles.SUPPORT)).get(f"{STAFF}data-requests/{request.pk}/response/").json()["body"]
    assert "- Kept until 31 March 2034: 1 invoice of 2025-26" in text
    assert "Questions about your personal data: Priya Kalita" in text
    subject, body = privacy.erasure_confirmation(customer, request)
    assert "Kept until 31 March 2034" in body and "Priya Kalita" in body and "[not set" not in body


# The cockpit


def test_the_cockpit_has_every_clock_with_the_record_behind_it(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    now = timezone.now()
    late = DataRequest.objects.create(kind="access", channel="email", requester="a@example.com", summary="A copy",
                                      received_at=now - timedelta(days=3))  # fmt: skip
    Incident.objects.create(title="A lost laptop", kind="data_leak", detected_at=now - timedelta(hours=7))
    child = student(date_of_birth=birthday(15), parent_contact="anita@example.com")
    DeletionRequest.objects.create(user=child)
    ConsentRecord.objects.create(user=student(), notice_version=Page.objects.get(slug="privacy").version)
    answer = signed_in(make_staff(roles.SUPPORT)).get(PRIVACY + "cockpit/").json()
    kinds = {row["kind"]: row for row in answer["clocks"]}
    assert kinds["data_request_ack"]["overdue"] and kinds["data_request_ack"]["target_id"] == str(late.pk)
    assert kinds["incident_cert_in"]["overdue"] and not kinds["incident_board"]["overdue"]
    assert kinds["parent_consent"]["account"] == child.pk and kinds["parent_consent"]["due_at"] is None
    assert kinds["deletion_parent"]["target_type"] == "accounts.deletionrequest"
    assert kinds["dark_pattern_audit"]["target_label"].startswith("Self-audit 202")
    assert answer["clocks"][0]["overdue"]  # the overdue first
    assert answer["counts"]["data_request_ack"] == {"open": 1, "overdue": 1}
    assert answer["support"] == {"installed": True, "error": ""}  # the support app is there and its fields match
    assert answer["consents"][0]["given"] == 1 and answer["consents"][0]["number"] == 1
    assert answer["consents"][0]["in_force"] is True
    titles = [item["title"] for item in answer["calendar"]]
    assert "The quarterly access review" in titles and "The quarterly restore drill" in titles
    assert signed_in(make_staff(roles.FINANCE)).get(PRIVACY + "cockpit/").status_code == 403


def test_the_cockpit_reads_the_support_apps_tickets_when_it_is_installed():
    pytest.importorskip("support.models")  # the support app (P7): run at the merge
    answer = signed_in(make_staff(roles.ADMIN)).get(PRIVACY + "cockpit/").json()
    assert answer["support"] == {"installed": True, "error": ""}


# Legal holds


def test_legal_holds_are_put_on_a_person_or_an_order_listed_and_released():
    customer = student(email="rahul@example.com")
    order = live_order(customer)
    finance, support = make_staff(roles.FINANCE), make_staff(roles.SUPPORT)
    url = PRIVACY + "holds/"
    on_person = signed_in(finance).post(url, {"user": customer.pk, "reason": "dispute", "note": "Case 41"},
                                        format="json")  # fmt: skip
    assert on_person.status_code == 201 and on_person.json()["target_label"] == f"Account #{customer.pk}"
    on_order = signed_in(finance).post(url, {"target_type": "shop.order", "target_id": order.number,
                                             "reason": "chargeback", "until": "2030-01-31"}, format="json")  # fmt: skip
    assert on_order.status_code == 201 and on_order.json()["target_label"] == f"Order {order.number}"
    assert on_order.json()["target_id"] == str(order.pk)
    for bad in [{"reason": "dispute"}, {"user": customer.pk, "target_type": "shop.order", "target_id": "1",
                "reason": "dispute"}, {"target_type": "shop.order", "target_id": "EL-NOPE", "reason": "claim"},
                {"user": customer.pk, "reason": "dispute", "until": "2020-01-01"}]:  # fmt: skip
        assert signed_in(finance).post(url, bad, format="json").status_code == 400, bad
    assert signed_in(support).post(url, {"user": customer.pk, "reason": "claim"}, format="json").status_code == 403
    listed = signed_in(support).get(url + "?active=true").json()["results"]
    assert [row["reason"] for row in listed] == ["chargeback", "dispute"]
    hold = on_person.json()["id"]
    assert signed_in(finance).post(f"{url}{hold}/release/", {}, format="json").status_code == 400  # say why
    released = signed_in(finance).post(f"{url}{hold}/release/", {"reason": "Settled"}, format="json").json()
    assert released["active"] is False and released["released_by"] == finance.pk
    assert signed_in(finance).post(f"{url}{hold}/release/", {"reason": "Again"}, format="json").status_code == 400
    assert signed_in(support).get(url + "?active=false").json()["results"][0]["id"] == hold
    assert [event.action for event in events(target_type="accounts.legalhold")] == [
        "legal_hold.created", "legal_hold.created", "legal_hold.released"]  # fmt: skip
    assert "Case 41" not in json.dumps(list(events("legal_hold.created").values("details")))


def test_the_holds_list_reads_its_labels_at_once():
    customer = student(email="rahul@example.com")
    admin = signed_in(make_staff(roles.ADMIN))

    def hold_an_order():
        order = live_order(customer)
        LegalHold.objects.create(target_type=ContentType.objects.get_for_model(Order), target_id=str(order.pk),
                                 reason="claim")  # fmt: skip

    hold_an_order()
    admin.get(PRIVACY + "holds/")
    with CaptureQueriesContext(connection) as one:
        assert admin.get(PRIVACY + "holds/").status_code == 200
    for _ in range(3):
        hold_an_order()
    with CaptureQueriesContext(connection) as four:
        assert len(admin.get(PRIVACY + "holds/").json()["results"]) == 4
    assert len(four) == len(one)


# A customer's nominee, and withdrawing a marketing consent


def test_a_customer_nominates_someone_and_staff_read_it_masked_then_reveal_it_with_a_reason():
    customer = student(email="rahul@example.com")
    api = APIClient()
    api.force_authenticate(customer)
    assert api.get("/api/v1/me/nominee/").status_code == 404
    given = {"name": "Anita  Das", "contact": "98640 12345", "relation": "mother"}
    assert api.put("/api/v1/me/nominee/", given, format="json").status_code == 201
    assert api.get("/api/v1/me/nominee/").json()["contact"] == "+919864012345"
    mine = {**given, "contact": "rahul@example.com"}
    assert api.put("/api/v1/me/nominee/", mine, format="json").json()["contact"] == ["The nominee's own address or "
                                                                                   "number, not yours."]  # fmt: skip
    assert api.put("/api/v1/me/nominee/", {**given, "relation": "aunt"}, format="json").status_code == 200
    support = make_staff(roles.SUPPORT)
    seen = signed_in(support).get(f"{PRIVACY}nominees/{customer.pk}/").json()
    assert seen["nominee"]["contact"] == "••••••2345" and seen["nominee"]["name"] == "Anita Das"
    assert events("sensitive_read").get().details == {"what": "nominee", "child": False}
    url = f"{PRIVACY}nominees/{customer.pk}/reveal/"
    assert signed_in(support, reauth=False).post(url, {"reason": "Ticket 41"}, format="json").status_code == 403
    assert signed_in(support).post(url, {"reason": "Ticket 41: the claim"}, format="json").json() == {
        "contact": "+919864012345"
    }
    assert signed_in(make_staff(roles.PACKER)).get(f"{PRIVACY}nominees/{customer.pk}/").status_code == 403
    assert signed_in(support).get(f"{PRIVACY}nominees/{make_staff(roles.SALES).pk}/").status_code == 404
    assert api.delete("/api/v1/me/nominee/").status_code == 204 and not Nominee.objects.exists()


def test_a_marketing_consent_is_withdrawn_as_easily_and_its_processors_are_told_to_stop(commit):
    customer = student(email="rahul@example.com")
    ProcessorRecord.objects.create(name="Amazon SES", purpose="email", data_categories="email", country="India",
                                   holds_marketing_data=True)  # fmt: skip
    api = APIClient()
    api.force_authenticate(customer)
    with commit():
        first = api.post("/api/v1/me/consent/withdraw/", {"purpose": "marketing", "channel": "email"}, format="json")
    assert first.status_code == 201 and first.json()["detail"].endswith("on email.")
    again = api.post("/api/v1/me/consent/withdraw/", {"purpose": "marketing", "channel": "email"}, format="json")
    assert again.status_code == 200 and ConsentRecord.objects.filter(event="withdrawn").count() == 1
    [task] = InboxItem.objects.filter(kind="processor_task")
    assert task.title == f"Marketing consent withdrawn by account #{customer.pk} (email): tell Amazon SES to stop"
    assert api.post("/api/v1/me/consent/withdraw/", {"purpose": "account"}, format="json").status_code == 400


def test_the_customers_privacy_endpoints_are_throttled(monkeypatch):
    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "dj_rest_auth", "2/minute")
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "anon", "2/minute")
    api = APIClient()
    api.force_authenticate(student())
    assert [api.get("/api/v1/me/nominee/").status_code for _ in range(3)] == [404, 404, 429]
    public = APIClient()
    assert [public.get("/api/v1/pages/privacy/versions/").status_code for _ in range(3)] == [200, 200, 429]


# Policy versions


def test_a_policy_version_is_published_now_or_for_a_later_day_with_its_number_and_diff():
    page = Page.objects.get(slug="privacy")
    owner = make_staff(roles.OWNER)
    text = page.body_md + "\n\n## Nominees\n\nYou may nominate a person to act for you."
    url = f"{PRIVACY}policies/privacy/"
    editor = make_staff(roles.CONTENT_EDITOR)
    sent = {"markdown": text, "summary": "Nominees added"}
    published = signed_in(editor).post(url + "publish/", sent, format="json").json()
    assert (published["number"], published["version"], published["summary"]) == (2, "2", "Nominees added")
    assert published["effective_from"] == timezone.localdate().isoformat()
    assert ConsentRecord.record(None, student()).notice_version == "2"
    diff = signed_in(owner).get(url + "versions/2/diff/").json()
    assert diff["previous"] == 1 and diff["added"] == 4 and diff["removed"] == 0
    assert {"kind": "added", "text": "## Nominees"} in diff["lines"]
    assert signed_in(owner).get(url + "versions/9/diff/").status_code == 404
    assert signed_in(editor).post(url + "publish/", sent, format="json").status_code == 400  # the same text
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert signed_in(editor).post(url + "publish/", {**sent, "markdown": "x", "effective_from": yesterday},
                                  format="json").status_code == 400  # fmt: skip
    # a version for a later day: the page stays as it is until then
    later = timezone.localdate() + timedelta(days=10)
    scheduled = signed_in(editor).post(url + "publish/", {"markdown": "New terms.", "summary": "Shorter",
                                       "effective_from": later.isoformat()}, format="json").json()  # fmt: skip
    assert scheduled["scheduled"]["number"] == 3 and scheduled["number"] == 2
    public = APIClient().get("/api/v1/pages/privacy/versions/").json()
    assert [(row["number"], row["upcoming"], row["in_force"]) for row in public] == [
        (3, True, False), (2, False, True), (1, False, False)]  # fmt: skip
    assert publish_due(later - timedelta(days=1)) == [] and publish_due(later) == ["privacy"]
    page.refresh_from_db()
    assert (page.body_md, page.version, page.effective_from) == ("New terms.", "3", later)
    assert [event.action for event in events(target_type="pages.page")] == [
        "policy.published", "policy.scheduled", "policy.in_force"]  # fmt: skip
    assert signed_in(make_staff(roles.SUPPORT)).post(url + "publish/", sent, format="json").status_code == 403


def test_a_scheduled_version_can_be_withdrawn_before_its_day_and_the_website_sees_the_number():
    page = Page.objects.get(slug="terms")
    publish(page, markdown="Later terms.", title="", summary="Later", by=make_staff(roles.ADMIN),
            effective_from=timezone.localdate() + timedelta(days=3))  # fmt: skip
    url = f"{PRIVACY}policies/terms/cancel-scheduled/"
    admin = make_staff(roles.ADMIN)
    assert (
        signed_in(admin).post(url, {"reason": "Counsel asked for changes"}, format="json").json()["scheduled"] is None
    )
    assert signed_in(admin).post(url, {"reason": "Again"}, format="json").status_code == 400
    shown = APIClient().get("/api/v1/pages/terms/").json()
    assert shown["number"] == 1 and shown["effective_from"] and "summary" in shown
    assert [version.number for version in versions(Page.objects.get(slug="terms"))] == [1]


# The disclosures


def test_the_disclosures_are_saved_together_with_a_reason_and_shown_by_config_without_cert_in(settings):
    url = PRIVACY + "disclosures/"
    owner = make_staff(roles.OWNER)
    before = signed_in(owner).get(url).json()
    assert {row["key"] for row in before["settings"]} >= {"DISCLOSURE_LEGAL_NAME", "CERT_IN_POINT_OF_CONTACT"}
    assert next(row for row in before["settings"] if row["key"] == "CERT_IN_POINT_OF_CONTACT")["public"] is False
    values = {
        "DISCLOSURE_GRIEVANCE_OFFICER": "Priya Kalita",
        "DISCLOSURE_GRIEVANCE_DESIGNATION": "Grievance Officer",
        "CERT_IN_POINT_OF_CONTACT": "Bikash Deka, security@examleaf.in",
        "NCH_STATUS": "applied",
        "NCH_SINCE": "2026-10-01",
    }
    assert signed_in(owner).put(url, {"values": values}, format="json").status_code == 400  # a reason
    saved = signed_in(owner).put(url, {"values": values, "reason": "The rules of 1 January"}, format="json").json()
    assert {row["key"] for row in saved["history"]} == set(values)
    assert events("setting.changed").count() == 5
    assert signed_in(owner).put(url, {"values": values, "reason": "Again"}, format="json").json() == {
        "non_field_errors": ["Nothing changed."]
    }
    bad = {"NCH_SINCE": "2026-02-30", "NCH_STATUS": "joined", "NOPE": "x"}
    assert set(signed_in(owner).put(url, {"values": bad, "reason": "Typo"}, format="json").json()) == set(bad)
    assert signed_in(make_staff(roles.SUPPORT)).put(url, {"values": values, "reason": "x"},
                                                    format="json").status_code == 403  # fmt: skip
    config = APIClient().get("/api/v1/config/").json()
    assert config["disclosures"]["grievance_officer"] == "Priya Kalita"
    assert config["disclosures"]["nch_status"] == "applied" and config["disclosures"]["registered_address"] is None
    assert "Bikash" not in json.dumps(config) and "cert_in" not in json.dumps(config["disclosures"])


# The dark-pattern self-audit


def test_the_dark_pattern_self_audit_is_completed_once_and_its_certificate_shown_from_its_day():
    url = PRIVACY + "dark-pattern-audits/"
    owner = make_staff(roles.OWNER)
    made = signed_in(owner).post(url, {"year": 2027}, format="json").json()
    assert len(made["rows"]) == 13 and made["rows"][0] == {"pattern": "false_urgency", "label": "False urgency",
                                                           "finding": "", "fix": ""}  # fmt: skip
    assert signed_in(owner).post(url, {"year": 2027}, format="json").status_code == 400  # one a year
    one = f"{url}{made['id']}/"
    assert signed_in(owner).post(one + "complete/", {}, format="json").status_code == 400  # every row first
    rows = [{**row, "finding": "None found on the checkout", "fix": "Nothing to change"} for row in made["rows"]]
    assert signed_in(owner).patch(one, {"rows": rows[:12]}, format="json").status_code == 400  # all 13
    signed_in(owner).patch(one, {"rows": rows, "certificate_text": "We certify the audit of 2027."}, format="json")
    tomorrow = timezone.localdate() + timedelta(days=1)
    done = signed_in(owner).post(one + "complete/", {"effective_from": tomorrow.isoformat()}, format="json").json()
    assert done["completed_by"] == owner.pk
    assert signed_in(owner).patch(one, {"certificate_text": "Changed"}, format="json").status_code == 400
    assert APIClient().get("/api/v1/config/").json()["dark_pattern_certificate"] is None  # not before its day
    DarkPatternAudit.objects.update(effective_from=timezone.localdate())
    cache.clear()
    shown = APIClient().get("/api/v1/config/").json()["dark_pattern_certificate"]
    assert shown == {"year": 2027, "text": "We certify the audit of 2027.",
                     "effective_from": timezone.localdate().isoformat()}  # fmt: skip
    assert signed_in(make_staff(roles.SUPPORT)).post(url, {"year": 2028}, format="json").status_code == 403
    assert signed_in(make_staff(roles.AUDITOR)).get(url).status_code == 200


def test_the_certificates_signed_copy_is_kept_in_the_private_storage(tmp_path, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                                          "OPTIONS": {"location": str(tmp_path)}}}  # fmt: skip
    audit_row = DarkPatternAudit.objects.create(year=2027)
    owner = signed_in(make_staff(roles.OWNER))
    url = f"{PRIVACY}dark-pattern-audits/{audit_row.pk}/file/"
    assert owner.get(url).status_code == 404
    bad = SimpleUploadedFile("certificate.exe", b"MZ", content_type="application/octet-stream")
    assert owner.post(url, {"file": bad}, format="multipart").status_code == 400
    pdf = SimpleUploadedFile("certificate.pdf", b"%PDF-1.7", content_type="application/pdf")
    assert owner.post(url, {"file": pdf}, format="multipart").json()["has_file"] is True
    assert b"".join(owner.get(url).streaming_content) == b"%PDF-1.7"


def test_the_self_audits_reminder_opens_once_a_year_from_1_december(monkeypatch):
    def on(day):
        monkeypatch.setattr(timezone, "localdate", lambda *args: day)

    on(date(2026, 11, 30))
    assert remind_dark_pattern_audit() is False
    on(date(2026, 12, 1))
    assert remind_dark_pattern_audit() is True
    item = InboxItem.objects.get(kind="compliance")
    assert item.title.startswith("The dark-pattern self-audit and its certificate for 2027")
    InboxItem.objects.update(done_at=timezone.now())
    on(date(2026, 12, 2))
    assert remind_dark_pattern_audit() is False and InboxItem.objects.count() == 1  # once a year, even when done
    on(date(2027, 12, 1))
    assert remind_dark_pattern_audit() is True and InboxItem.objects.count() == 2  # the next year's


def test_the_cockpit_counts_and_the_inbox_for_the_compliance_duties():
    InboxItem.objects.create(kind="processor_task", title="x", permission="staff.manage_compliance",
                             target_type="staff.processorrecord", target_id="1:erasure:1")  # fmt: skip
    assert cockpit()["inbox"] == 1


def test_processors_say_what_they_keep_and_how_to_make_them_erase():
    admin = signed_in(make_staff(roles.ADMIN))
    made = admin.post(STAFF + "processors/", {"name": "Cloudflare R2", "purpose": "media", "data_categories":
                      "answer-sheet photos", "country": "Asia-Pacific", "holds_personal_data": True,
                      "erasure_action": "delete the media in R2"}, format="json").json()  # fmt: skip
    assert made["holds_personal_data"] is True and made["erasure_action"] == "delete the media in R2"
    answer = privacy.erasure_report(student())
    assert answer["notes"] == ["Once it is done, the inbox asks to tell: Cloudflare R2."]
