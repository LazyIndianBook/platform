"""Three guards on every request and three watches on every response. The staff's endpoints (the staff API, the
shipping app's and the insights') and the Django admin answer only on the admin host (ADMIN_HOSTS): on any other they
are 404 to everyone, signed in or not (plan 9.1). A session in which a member of staff is logged in as a customer
(IMPERSONATING, set by the account API's account/impersonate/: staff.services.accept_impersonation) ends once it is
over (its time, its end by either side, the panel's session gone: 401 `impersonation_ended` under /api/ and
/_allauth/), is refused payments, passwords, email, second factors, consent, addresses, reviews and deletion (403
`impersonating`, research 2.7), and each of its requests is an audit event by the member of staff on behalf of the
customer. A 403 from the staff's endpoints to someone signed in is an `authz_fail` event (research 3.1: every
authorization failure; anonymous probes stay in Caddy's log). A Razorpay webhook refused for its signature counts on
the day's inbox item for the system's watchers."""

import logging
import re

from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404, JsonResponse
from django.http.request import split_domain_port, validate_host
from django.utils import timezone

logger = logging.getLogger(__name__)
# The staff's endpoints: the staff API's, the shipping app's (not the checkout's shipping/ and shipping/quote/), the
# insights'.
STAFF_APIS = re.compile(
    r"^/api/v1/(?:staff|insights|shipping/(?:shipments|exceptions|cod|charges|pickup-locations|orders|manifest))/"
)
ADMIN = "/admin/"
STEPS = {"reauthentication_required", "break_glass_reason_required", "passkey_required"}
WEBHOOKS = {"/shop/webhooks/razorpay/": "Razorpay"}
# A website session in which a member of staff is logged in as the customer: who, until when, why, the Impersonation
IMPERSONATING, IMPERSONATION_UNTIL = "impersonating_staff_id", "impersonation_until"
IMPERSONATION_REASON, IMPERSONATION_ID = "impersonation_reason", "impersonation_id"
WHILE_IMPERSONATING = re.compile(
    r"^/(?:api/v1/(?:orders/|auth/password/|me/(?:export|deletion|parent-consent|nominee|consent)/|addresses/"
    r"|products/[^/]+/reviews/)"
    r"|_allauth/[^/]+/v1/(?:account/|auth/(?:password|2fa|webauthn|reauthenticate)))"
)
SAFE = {"GET", "HEAD", "OPTIONS"}
JSON_PATHS = ("/api/", "/_allauth/")


def on_admin_host(request):
    """Whether the request came to an admin host (ADMIN_HOSTS, as ALLOWED_HOSTS writes them); with none set
    (development), every host is one."""
    hosts = settings.ADMIN_HOSTS
    return not hosts or validate_host(split_domain_port(request.get_host())[0], hosts)


class StaffAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if STAFF_APIS.match(request.path) and not on_admin_host(request):
            return JsonResponse({"detail": "Not found."}, status=404)
        if request.path.startswith(ADMIN) and not on_admin_host(request):  # the Django admin: the same rule
            raise Http404
        response, impersonated = None, bool(request.session.get(IMPERSONATING))
        if impersonated:
            from .services import website_impersonation_over  # (services imports this module)

            if why := website_impersonation_over(request):
                request._impersonation_over = why  # the log-out's receiver records the end (staff.signals)
                logout(request)
                if request.path.startswith(JSON_PATHS):
                    detail = "The member of staff's session as the customer is over."
                    return JsonResponse({"detail": detail, "code": "impersonation_ended"}, status=401)
                impersonated = False
            elif request.method not in SAFE and WHILE_IMPERSONATING.match(request.path):
                detail = "Not while a member of staff is logged in as the customer."
                response = JsonResponse({"detail": detail, "code": "impersonating"}, status=403)
        if response is None:
            response = self.get_response(request)
        try:
            if impersonated and request.session.get(IMPERSONATING):  # (not ended by this request)
                self.on_behalf(request, response)
            if response.status_code == 403 and STAFF_APIS.match(request.path):
                self.denied(request, response)
            elif response.status_code == 400 and request.path in WEBHOOKS:
                self.webhook_refused(request.path)
        except Exception:  # the answer goes out whatever the log does
            logger.exception("Audit of %s %s failed", request.method, request.path)
        return response

    @staticmethod
    def on_behalf(request, response):
        """A request of the member of staff logged in as the customer: by them (staff.audit's actor in such a
        session), on behalf of and about the customer."""
        from .audit import Outcome, record

        code = response.status_code
        outcome = Outcome.DENIED if code in (401, 403) else Outcome.FAILED if code >= 400 else Outcome.SUCCESS
        details = {"method": request.method, "path": request.path[:200], "status": code}
        record("impersonation.request", request=request, target=request.user, outcome=outcome, details=details)

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
        if data.get("code") in STEPS:  # a step-up or a break-glass session's reason asked for, not a refusal
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
