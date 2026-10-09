"""Two guards on every request and two watches on every response. The staff API answers only on the admin host
(ADMIN_HOSTS): on any other it is 404 to everyone, signed in or not (plan 9.1). A session that is a member of staff
logged in as a customer (`staff:impersonating`, set by the website's account area when it accepts a token) is refused
payments, passwords, email, second factors, consent, addresses and deletion (research 2.7). A 403 from the staff API
to someone signed in is an `authz_fail` event (research 3.1: every authorization failure; anonymous probes stay in
Caddy's log). A Razorpay webhook refused for its signature counts on the day's inbox item for the system's
watchers."""

import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.http.request import split_domain_port, validate_host
from django.utils import timezone

logger = logging.getLogger(__name__)
STAFF_API = "/api/v1/staff/"
WEBHOOKS = {"/shop/webhooks/razorpay/": "Razorpay"}
IMPERSONATING = "staff:impersonating"
WHILE_IMPERSONATING = re.compile(
    r"^/(?:api/v1/(?:orders/|auth/password/|me/(?:export|deletion|parent-consent)/|addresses/)"
    r"|_allauth/[^/]+/v1/(?:account/|auth/(?:password|2fa|webauthn|reauthenticate)))"
)
SAFE = {"GET", "HEAD", "OPTIONS"}


def on_admin_host(request):
    """Whether the request came to an admin host (ADMIN_HOSTS, as ALLOWED_HOSTS writes them); with none set
    (development), every host is one."""
    hosts = settings.ADMIN_HOSTS
    return not hosts or validate_host(split_domain_port(request.get_host())[0], hosts)


class StaffAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(STAFF_API) and not on_admin_host(request):
            return JsonResponse({"detail": "Not found."}, status=404)
        if request.method not in SAFE and WHILE_IMPERSONATING.match(request.path):
            if request.session.get(IMPERSONATING):
                detail = "Not while a member of staff is logged in as the customer."
                return JsonResponse({"detail": detail, "code": "impersonating"}, status=403)
        response = self.get_response(request)
        try:
            if response.status_code == 403 and request.path.startswith(STAFF_API):
                self.denied(request, response)
            elif response.status_code == 400 and request.path in WEBHOOKS:
                self.webhook_refused(request.path)
        except Exception:  # the answer goes out whatever the log does
            logger.exception("Audit of %s %s failed", request.method, request.path)
        return response

    @staticmethod
    def denied(request, response):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        data = getattr(response, "data", None)
        if not isinstance(data, dict):
            import json

            try:
                data = json.loads(response.content)
            except ValueError:
                data = {}
        if data.get("code") == "reauthentication_required":  # a step-up asked for, not a refusal
            return
        from .audit import Outcome, record

        record(
            "authz_fail",
            request=request,
            outcome=Outcome.DENIED,
            details={
                "method": request.method,
                "path": request.path[:200],
                "detail": str(data.get("detail", ""))[:200],
                "error": str(data.get("code", "")),  # ("code" is masked: verification codes)
            },
        )

    @staticmethod
    def webhook_refused(path):
        from .models import InboxItem

        day = timezone.localdate().isoformat()
        item, created = InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.FAILED_WEBHOOK,
            target_type="webhook",
            target_id=f"{WEBHOOKS[path]}:{day}",
            done_at=None,
            defaults={
                "title": f"{WEBHOOKS[path]} webhooks refused on {day} (wrong signature)",
                "permission": "staff.view_system",
                "data": {"count": 1},
            },
        )
        if not created:
            item.data = {**item.data, "count": item.data.get("count", 0) + 1}
            item.save(update_fields=["data"])
