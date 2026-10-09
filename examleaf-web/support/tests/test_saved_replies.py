"""Saved replies (plan 5.14): SUPPORT reads them, their changes are ADMIN's; variables with fallbacks ({name|there},
{order}, {refund_days}, {number}), unknown ones refused; one title per language; a delete goes to the bin for 30 days
and can be restored; each ticket gets them filled for itself, its language first, the refund's days by its payment's
method."""

import pytest
from django.utils import timezone

from accounts import roles
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Payment
from support import services
from support.models import SavedReply

from .conftest import SUPPORT, events, make_staff, make_ticket, signed_in

pytestmark = pytest.mark.django_db
REPLIES = SUPPORT + "saved-replies/"
REFUND = {
    "title": "Refund started",
    "language": "en",
    "body": "Hello {name|there}, the refund of {order|your order} reaches you in {refund_days|5 to 10} working days.",
}


def test_support_reads_and_admin_keeps_the_saved_replies():
    support, admin = signed_in(make_staff(roles.SUPPORT)), signed_in(make_staff(roles.ADMIN))
    assert support.post(REPLIES, REFUND).status_code == 403
    made = admin.post(REPLIES, REFUND)
    assert made.status_code == 201 and made.json()["variables"] == ["name", "order", "refund_days"]
    assert [row["title"] for row in support.get(REPLIES).json()["results"]] == ["Refund started"]
    unknown = admin.post(REPLIES, {**REFUND, "title": "Bad", "body": "Hi {customer}"})
    assert unknown.status_code == 400 and "{refund_days}" in unknown.json()["body"][0]
    assert admin.post(REPLIES, REFUND).status_code == 400  # the same title in the same language
    assert admin.post(REPLIES, {**REFUND, "language": "as"}).status_code == 201  # in Assamese: another reply
    url = f"{REPLIES}{made.json()['id']}/"
    assert admin.patch(url, {"title": "Refund on its way"}, format="json").json()["title"] == "Refund on its way"
    assert support.delete(url).status_code == 403
    assert admin.delete(url).status_code == 204
    assert made.json()["id"] not in [row["id"] for row in admin.get(REPLIES).json()["results"]]
    assert [row["id"] for row in admin.get(REPLIES, {"bin": "true"}).json()["results"]] == [made.json()["id"]]
    assert admin.post(f"{url}restore/").json()["deleted_at"] is None
    trail = list(events(action__startswith="support.saved_reply_").values_list("action", flat=True))
    assert trail == [
        "support.saved_reply_created",
        "support.saved_reply_created",
        "support.saved_reply_changed",
        "support.saved_reply_deleted",
        "support.saved_reply_restored",
    ]


def test_a_ticket_gets_the_replies_filled_for_it_in_its_language_first(commit):
    SavedReply.objects.create(**REFUND)
    SavedReply.objects.create(title="নমস্কাৰ", language="as", body="নমস্কাৰ {name|বন্ধু}, {number}")
    order = make_order((ProductFactory(), 1), email="rahul@example.com")
    shop.record_capture(captured(order))
    Payment.objects.filter(order=order).update(raw_payload={"method": "upi"})
    with commit():
        english = make_ticket(order=order)
        assamese = make_ticket(name="", body="মোৰ কিতাপখন অহা নাই")  # ৰ: Assamese
    assert (english.language, assamese.language) == ("en", "as")
    client = signed_in(make_staff(roles.SUPPORT))
    filled = client.get(f"{SUPPORT}tickets/{english.number}/").json()["saved_replies"]
    assert filled[0]["title"] == "Refund started"
    assert filled[0]["text"] == f"Hello Rahul, the refund of {order.number} reaches you in 2 to 7 working days."
    other = client.get(f"{SUPPORT}tickets/{assamese.number}/").json()["saved_replies"]
    assert [reply["language"] for reply in other] == ["as", "en"]
    assert other[0]["text"] == f"নমস্কাৰ বন্ধু, {assamese.number}"  # no name: the fallback
    assert other[1]["text"].startswith("Hello there, the refund of your order reaches you in 5 to 10")
    assert signed_in(make_staff(roles.CONTENT_EDITOR)).get(f"{SUPPORT}tickets/{english.number}/").status_code == 404


def test_rendering_fills_variables_and_falls_back():
    values = {"name": "", "order": "EL-2026-000001", "refund_days": "", "number": "SR-2026-000001"}
    assert services.render_reply("{name|there} {order} {refund_days|5 to 10} {number}", values) == (
        "there EL-2026-000001 5 to 10 SR-2026-000001"
    )
    assert services.unknown_variables("{name} {nope|x}") == ["nope"]
    assert timezone.now()
