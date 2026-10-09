import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import razorpay
import requests

from shop import invoices, payments
from shop.factories import KEY, SECRET, WEBHOOK_SECRET

RECORDED_SETTLEMENTS = json.loads((Path(__file__).parent / "fixtures" / "razorpay_settlements.json").read_text())


def pytest_configure(config):
    config.addinivalue_line("markers", "real_pdf: render invoices with WeasyPrint instead of a stand-in")


@pytest.fixture(autouse=True)
def shop_settings(settings):
    settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET = KEY, SECRET  # test keys: test mode
    settings.RAZORPAY_WEBHOOK_SECRET_TEST, settings.RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET, "live-webhook-secret"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture(autouse=True)
def quick_pdf(request, monkeypatch):
    if "real_pdf" not in request.keywords:  # WeasyPrint takes about a second per invoice
        monkeypatch.setattr(invoices, "render_pdf", lambda invoice: b"%PDF-1.7 stand-in")


@pytest.fixture
def rzp(monkeypatch):
    """Razorpay's client with its network calls replaced; signatures are still checked by the SDK (local HMAC)."""
    client = MagicMock()
    client.utility = razorpay.Client(auth=(KEY, SECRET)).utility
    client.order.create.side_effect = lambda data, **kw: {"id": f"order_{data['receipt']}", **data}
    client.payment.fetch_multiple_refund.return_value = {"entity": "collection", "count": 0, "items": []}
    client.payment.refund.side_effect = lambda payment_id, data, **kw: {
        "id": f"rfnd_{data['notes']['refund_id']}",
        "status": "processed",
        "amount": data["amount"],
    }
    monkeypatch.setattr(payments, "client", lambda: client)
    return client


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """`with commit():` runs what the code queues for after the commit (emails, tasks), as production would."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


def in_paise(rupees):
    return int(Decimal(str(rupees)) * 100)


class FakeSettlements:
    """Razorpay's settlement API (the recon by day, a settlement by id) answering from the recorded shapes
    (fixtures/razorpay_settlements.json) with each test's settlements; `fail` makes every call answer that status."""

    def __init__(self):
        self.days, self.settlements, self.calls, self.fail = {}, {}, [], None

    def add(self, day, settlement_id, *items, net=None, utr="UTR20261009001"):
        """A settlement of `day` with these items ({type, entity_id, amount, fee, tax, order_receipt} in rupees: a
        payment's credit is its amount less its fee, its GST included; a refund's debit its amount and fee; an
        adjustment's `credit` or `debit` given): Razorpay's own net is its items' unless `net` says otherwise."""
        rows = []
        for item in items:
            row = copy.deepcopy(RECORDED_SETTLEMENTS[f"{item['type']}_item"])
            amount, fee, tax = (in_paise(item.get(name, 0)) for name in ("amount", "fee", "tax"))
            credit = {"payment": amount - fee}.get(item["type"], in_paise(item.get("credit", 0)))
            debit = {"refund": amount + fee}.get(item["type"], in_paise(item.get("debit", 0)))
            row.update(entity_id=item["entity_id"], amount=amount, fee=fee, tax=tax, credit=credit, debit=debit)
            row.update(settlement_id=settlement_id, settlement_utr=utr, order_receipt=item.get("order_receipt"))
            rows.append(row)
        self.days.setdefault(day, []).extend(rows)
        own = in_paise(net) if net is not None else sum(row["credit"] - row["debit"] for row in rows)
        self.settlements[settlement_id] = {**RECORDED_SETTLEMENTS["settlement"], "id": settlement_id, "amount": own,
                                           "utr": utr}  # fmt: skip

    def handle(self, request):
        self.calls.append((request.method, request.url.path))
        if self.fail:
            return httpx.Response(self.fail, json={"error": {"code": "SERVER_ERROR", "description": "down"}})
        path, query = request.url.path, request.url.params
        if path == "/v1/settlements/recon/combined":
            rows = self.days.get(date(int(query["year"]), int(query["month"]), int(query["day"])), [])
            skip, count = int(query.get("skip", 0)), int(query.get("count", 10))
            page = rows[skip : skip + count]
            return httpx.Response(200, json={**RECORDED_SETTLEMENTS["recon_page"], "count": len(page), "items": page})
        if path.startswith("/v1/settlements/") and (found := self.settlements.get(path.rsplit("/", 1)[-1])):
            return httpx.Response(200, json=found)
        return httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "No such id"}})

    def transport(self):
        return httpx.MockTransport(self.handle)


@pytest.fixture
def razorpay_settlements(monkeypatch):
    """Razorpay's settlement API answered by FakeSettlements (shop.settlements' calls)."""
    from shop import settlements

    fake = FakeSettlements()
    monkeypatch.setattr(settlements, "transport", fake.transport)
    return fake


@pytest.fixture
def real_seller(settings):
    """The seller's details as .env gives them once filled in (the defaults hold [placeholders])."""
    settings.SHOP_SELLER = {
        **settings.SHOP_SELLER,
        "address": "House 1, Zoo Road, Guwahati, Assam 781001",
        "email": "orders@examleaf.in",
        "phone": "+91 98640 00000",
    }
