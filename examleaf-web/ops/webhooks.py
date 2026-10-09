"""POST /api/hooks/sms-events/: MSG91's delivery reports (research-integrations 4.1). MSG91 signs nothing: it sends the
token we generated (the connections page, MSG91's webhook) in the X-Webhook-Token header, compared here in constant time
with the token of MSG91's account and, for 24 hours after a rotation, the previous one. No token, a wrong one, or none
set at all: 403 (kept as a rejected event, without its body). A body that holds no report: 400. Otherwise the raw body
is kept (InboundEvent: once per body, and once per report, its id being MSG91's request ids, numbers' last digits and
statuses hashed), answered 200 at once and processed by a task (ops.tasks.process_sms_event: each SmsLog row of the
request told whether it was delivered, and why not). Throttled per client address."""

import hashlib
import json
import re
from urllib.parse import parse_qs

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from integrations.connections import SMS_TOKEN_HEADER, webhook_account
from integrations.services import receive_event

from .models import SmsLog

FINAL = {SmsLog.Delivery.DELIVERED, SmsLog.Delivery.FAILED, SmsLog.Delivery.REJECTED}
CODES = {  # MSG91's delivery report codes, where its words say nothing plainer
    "1": SmsLog.Delivery.DELIVERED,
    "2": SmsLog.Delivery.FAILED,
    "5": SmsLog.Delivery.PENDING,
    "6": SmsLog.Delivery.PENDING,
    "8": SmsLog.Delivery.PENDING,
    "9": SmsLog.Delivery.REJECTED,  # NDNC: the number is on the do-not-disturb register
    "16": SmsLog.Delivery.REJECTED,
    "17": SmsLog.Delivery.REJECTED,  # a blocked number
    "25": SmsLog.Delivery.REJECTED,
    "26": SmsLog.Delivery.REJECTED,
}
WORDS = [  # the report's own words, first match wins: "not delivered" before "delivered"
    (re.compile(r"undeliv|not deliv|fail|expire", re.I), SmsLog.Delivery.FAILED),
    (re.compile(r"reject|ndnc|\bdnd\b|block|dlt|template", re.I), SmsLog.Delivery.REJECTED),
    (re.compile(r"deliver", re.I), SmsLog.Delivery.DELIVERED),
    (re.compile(r"pending|submit|sent|accept|enroute|queue", re.I), SmsLog.Delivery.PENDING),
]


def decode(body, content_type=""):
    """The reports' JSON from a body: JSON (a list, one report, or {"data": …}), or a form with a `data` field."""
    text = body.decode("utf-8", "replace")
    if "x-www-form-urlencoded" in (content_type or ""):
        text = (parse_qs(text).get("data") or [""])[0]
    payload = json.loads(text)
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload if isinstance(payload, list) else [payload]


def reports_of(payload):
    """Each report as {request_id, last4, status, description, date}: MSG91's request (`requestId`) and its reports
    (`report`: [{number, status, desc, date}]), or one report flat; a row without a request id is no report of ours."""
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        request_id = str(item.get("requestId") or item.get("request_id") or item.get("requestID") or "").strip()
        reports = item["report"] if isinstance(item.get("report"), list) else [item]
        for report in reports:
            if not isinstance(report, dict) or not request_id:
                continue
            number = re.sub(r"\D", "", str(report.get("number") or report.get("mobile") or report.get("telNum") or ""))
            words = report.get("desc") or report.get("description") or report.get("failureReason") or ""
            rows.append(
                {
                    "request_id": request_id[:100],
                    "last4": number[-4:],
                    "status": str(report.get("status") or "").strip()[:20],
                    "description": str(words or report.get("reason") or "").strip()[:200],
                    "date": str(report.get("date") or "").strip()[:40],
                }
            )
    return rows


def delivery_of(report):
    """delivered, pending, failed or rejected: the report's words first, its code next; pending when neither says."""
    for pattern, state in WORDS:
        if pattern.search(report["description"]) or pattern.search(report["status"]):
            return state
    return CODES.get(report["status"], SmsLog.Delivery.PENDING)


def event_id(reports):
    """The reports' own id: their requests, numbers' last digits and statuses, hashed (a report sent again is a
    duplicate whatever else its body says)."""
    parts = sorted(f"{row['request_id']}:{row['last4']}:{row['status']}:{row['description']}" for row in reports)
    return "dlr:" + hashlib.sha256("|".join(parts).encode()).hexdigest()


class SmsEventsView(APIView):
    authentication_classes = []  # the token is the authentication
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sms_events"

    @extend_schema(exclude=True)  # MSG91's, not the API's
    def post(self, request, *args, **kwargs):
        token, body = request.headers.get(SMS_TOKEN_HEADER, ""), request.body
        account = webhook_account("msg91")
        if account is None or not account.webhook_token_matches(token):
            receive_event("msg91", body, request.headers, rejected=True)
            return Response({"detail": "Unknown or missing token."}, status=status.HTTP_403_FORBIDDEN)
        try:
            reports = reports_of(decode(body, request.content_type))
        except ValueError, TypeError:
            reports = []
        if not reports:
            return Response({"detail": "No delivery report in it."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            receive_event("msg91", body, request.headers, account=account, event_id=event_id(reports))
        return Response({"detail": "Received."})


def apply_reports(body, content_type="application/json"):
    """The delivery reports of a stored event written on their SmsLog rows: the state, MSG91's words when it failed,
    the report's time. A final report (delivered, failed, rejected) is never replaced by a later one, a pending one
    only fills an empty state (reports arrive out of order). Returns how many rows changed."""
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    changed = 0
    for report in reports_of(decode(body.encode() if isinstance(body, str) else body, content_type)):
        state = delivery_of(report)
        rows = SmsLog.objects.filter(provider_id=report["request_id"])
        if report["last4"]:
            rows = rows.filter(phone_last4=report["last4"])  # one request to several numbers: each its own report
        rows = rows.filter(delivery="") if state == SmsLog.Delivery.PENDING else rows.exclude(delivery__in=FINAL)
        try:
            when = parse_datetime(report["date"].replace(" ", "T")) if report["date"] else None
        except ValueError:  # a date that is no date: the report's arrival stands for it
            when = None
        if when is not None and timezone.is_naive(when):
            when = timezone.make_aware(when)  # MSG91 reports India's time
        reason = report["description"] if state in (SmsLog.Delivery.FAILED, SmsLog.Delivery.REJECTED) else ""
        changed += rows.update(delivery=state, delivery_reason=reason, delivered_at=when or timezone.now())
    return changed
