"""The words of the emails: no delivery promise outside the Shipping Policy, greetings from ExamLeaf (the website's
words are the frontend's)."""

import pytest
from django.core import mail

from shop import services
from shop.factories import ProductFactory, make_order

pytestmark = pytest.mark.django_db


def test_no_delivery_time_is_promised_outside_the_shipping_policy(client, django_capture_on_commit_callbacks, settings):
    settings.SHOP_COD_ENABLED = True
    order = make_order((ProductFactory(), 1), method="cod")
    with django_capture_on_commit_callbacks(execute=True):
        services.place_cod(order)
        services.deliver_order(services.ship_order(services.pack_order(order), "India Post", "EA1"))
    bodies = {m.subject.split("] ")[1]: m.body for m in mail.outbox}
    assert "/shipping/" in bodies[f"Order {order.number} confirmed"]
    assert all("working days" not in body for body in bodies.values())


def test_emails_greet_from_examleaf_not_from_the_host_name(client):
    reset = "/_allauth/browser/v1/auth/password/request"  # the website's "Forgot your password?"
    client.post(reset, {"email": "nobody@example.com"}, content_type="application/json", HTTP_HOST="localhost")
    assert mail.outbox and "Hello from ExamLeaf!" in mail.outbox[0].body
    assert "Thank you for using ExamLeaf." in mail.outbox[0].body and "testserver" not in mail.outbox[0].subject
