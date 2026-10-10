"""Throttles (research 2.5; OWASP API4 and API6): what a person may repeat to harvest personal data, secrets or money
has a rate of its own per member of staff (or key): reveals, exports, bulk actions, searches for a person, book code
lookups, money; and the public report, ticket and contact endpoints per account or client address. Each row answers
429 (`throttled`, with Retry-After) once past its limit, set to 2 for the test; the configured rates stay under sane
ceilings (examleaf/api_settings.py and settings.py, DEPLOYMENT.md's table)."""

import pytest
from rest_framework.throttling import SimpleRateThrottle

from accounts import roles
from shop.factories import verified_user

from .conftest import STAFF, make_staff, signed_in
from .test_matrix import objects

pytestmark = pytest.mark.django_db
REASON = "Calling them back about it"
ROWS = [  # (the scope, method, path, body)
    ("staff_reveal", "post", "users/{customer}/reveal/", {"show": ["email"], "reason": REASON}),
    ("staff_reveal", "post", "privacy/nominees/{customer}/reveal/", {"reason": REASON}),
    ("staff_reveal", "post", "support/tickets/{ticket}/reveal/", {"show": ["email"], "reason": REASON}),
    ("staff_reveal", "post", "data-requests/{request}/reveal/", {"reason": REASON}),
    ("staff_reveal", "post", "orders/refunds/{refund}/payee/", {"reason": REASON}),
    ("staff_reveal", "post", "users/{customer}/impersonate/", {"reason": REASON, "ticket": "SR-2026-000001"}),
    ("staff_export", "post", "audit/export/", {}),
    ("staff_export", "post", "jobs/", {"kind": "audit_export", "params": {"filters": {}}}),
    ("staff_export", "post", "tax/gstr1/", {"month": "2026-09"}),
    ("staff_export", "post", "data-requests/{request}/export/", {}),
    ("staff_export", "post", "course/codes/batches/", {}),
    ("staff_bulk", "post", "jobs/", {"kind": "bulk_action", "params": {"action": "user.end_sessions"}}),
    ("staff_bulk", "post", "catalogue/import/", {}),
    ("staff_search", "get", "users/?q=riya@example.com", None),
    ("staff_search", "get", "orders/?q=riya@example.com", None),
    ("staff_search", "get", "support/tickets/?q=riya@example.com", None),
    ("staff_search", "get", "course/entitlements/?q=riya@example.com", None),
    ("staff_search", "get", "finance/payments/?q=EL-2026-000001", None),
    ("staff_search", "get", "course/learners/{learner}/", None),
    ("staff_code_lookup", "post", "course/codes/lookup/", {"code": "ABCD-EFGH-JKLM"}),
    ("staff_code_lookup", "post", "support/tickets/{ticket}/book-code/", {"code": "ABCD-EFGH-JKLM"}),
    ("staff_money", "post", "orders/{order}/refunds/", {}),
    ("staff_money", "post", "change-requests/", {}),
    ("staff_test_send", "post", "templates/{template}/test/", {}),
    ("staff_reports", "get", "reports/sales/", None),
]


def throttled(response):
    """429 with its wait; the staff API's says `throttled` beside its detail (the public API's has the detail)."""
    code = response.json().get("code", "throttled") if response.status_code == 429 else None
    return code == "throttled" and int(response["Retry-After"]) > 0


@pytest.mark.parametrize(("scope", "method", "path", "body"), ROWS, ids=[f"{s} {m} {p}" for s, m, p, _ in ROWS])
def test_each_rate_answers_429_past_its_limit(monkeypatch, scope, method, path, body):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, "2/hour")
    url = STAFF + path.format(**objects())
    client = signed_in(make_staff(roles.OWNER))  # every permission, re-authenticated: only the rate refuses
    answers = [getattr(client, method)(url, body, format="json") for _ in range(3)]
    assert [throttled(answer) for answer in answers[:2]] == [False, False], [a.status_code for a in answers]
    assert throttled(answers[2]), (answers[2].status_code, answers[2].content[:200])


def test_the_scopes_rows_cover_every_rate_the_staff_api_names():
    """Every throttle scope a staff view names (its throttle_scopes, its own scope) has a row here."""
    from .test_matrix import staff_endpoints

    named = set()
    for view, _ in staff_endpoints():
        named |= set(view.cls.throttle_scopes.values()) | {view.cls.throttle_scope}
    named |= {"staff_bulk"}  # jobs/'s bulk actions (JobViewSet.get_throttles)
    assert named - {"staff"} <= {scope for scope, *_ in ROWS}, sorted(named - {scope for scope, *_ in ROWS})


CEILINGS = {  # the most each rate may be configured to, in its own period
    "staff_reveal": (30, "hour"),
    "staff_export": (10, "hour"),
    "staff_bulk": (20, "hour"),
    "staff_code_lookup": (120, "hour"),
    "staff_search": (60, "minute"),
    "staff_money": (120, "hour"),
    "staff_test_send": (10, "hour"),
    "support_request": (10, "hour"),
}


def test_the_configured_rates_are_sensible():
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope, (most, period) in CEILINGS.items():
        number, _, unit = rates[scope].partition("/")
        assert unit == period and 0 < int(number) <= most, (scope, rates[scope])


def test_the_public_report_ticket_and_contact_endpoints_answer_429_past_their_limits(monkeypatch, settings):
    monkeypatch.setattr("api.reports.LIMITS", [("report", 2, 3600)])
    reports = [signed_in(verified_user("a@example.com")).post("/api/v1/reports/", {}, format="json") for _ in range(3)]
    assert [throttled(r) for r in reports] == [False, False, True], [r.status_code for r in reports]
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "support_request", "2/hour")
    me = signed_in(verified_user("b@example.com"))
    tickets = [me.post("/api/v1/me/tickets/", {}, format="json") for _ in range(3)]
    assert [throttled(t) for t in tickets] == [False, False, True], [t.status_code for t in tickets]
    settings.SUPPORT_EMAIL = "support@examleaf.in"
    from rest_framework.test import APIClient

    contact = [APIClient().post("/api/v1/contact/", {}, format="json") for _ in range(6)]
    assert [throttled(c) for c in contact] == [False] * 5 + [True], [c.status_code for c in contact]
