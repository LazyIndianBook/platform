"""The queue, a ticket and the agents read as many queries with one row as with many (shop/test_query_counts.py's
rule): no query per ticket, per message, per order, per line or per person."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts import roles
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order, verified_user
from shop.models import Cart, Shipment
from support import services

from .conftest import SUPPORT, make_staff, make_ticket, signed_in

pytestmark = pytest.mark.django_db
TICKETS = SUPPORT + "tickets/"


def queries(client, path):
    client.get(path)  # the session's and the switches' first reads
    with CaptureQueriesContext(connection) as captured_queries:
        assert client.get(path).status_code == 200
    return len(captured_queries)


def test_the_queue_costs_the_same_few_queries_however_long(commit):
    client = signed_in(make_staff(roles.SUPPORT))
    with commit():
        make_ticket(order=make_order((ProductFactory(), 1)))
    one = queries(client, TICKETS)
    with commit():
        for index in range(6):
            make_ticket(subject=f"Ticket {index}", order=make_order((ProductFactory(), 1)), category="order")
    assert queries(client, TICKETS) == one


def test_the_agents_cost_the_same_few_queries_however_many(commit):
    client = signed_in(make_staff(roles.SUPPORT))
    one = queries(client, SUPPORT + "agents/")
    for role in [roles.SUPPORT, roles.SALES, roles.CONTENT_EDITOR, roles.ADMIN]:
        make_staff(role)
    assert queries(client, SUPPORT + "agents/") == one


def order_of(user, lines):
    Cart.objects.filter(user=user).delete()
    order = make_order(*[(ProductFactory(price=Decimal("299.00")), 1) for _ in range(lines)], user=user)
    shop.record_capture(captured(order))
    Shipment.objects.create(order=order, tracking_number=f"EA{order.pk}IN")
    return order


def test_a_ticket_costs_the_same_few_queries_however_many_messages_and_orders(commit):
    staff = make_staff(roles.SUPPORT)
    client = signed_in(staff)
    customer = verified_user("rahul@example.com")
    with commit():
        ticket = make_ticket(user=customer, order=order_of(customer, 1))
    one = queries(client, f"{TICKETS}{ticket.number}/")
    for index in range(4):
        order_of(customer, 3)
        services.add_message(ticket, by=staff, direction="note", body=f"Note {index}")
    assert queries(client, f"{TICKETS}{ticket.number}/") == one
