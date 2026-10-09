"""POST /api/hooks/parcel-events/: Shiprocket's tracking webhook (research-integrations.md 1.7 and 3.6). Its address
avoids the words Shiprocket refuses in a webhook URL ("shiprocket", "kartrocket", "sr", "kr"). Shiprocket signs
nothing and sends no event id: it sends the static token we generated as `x-api-key`, compared here in constant time
with each enabled account's current token, or its previous one for 24 hours after a rotation. No token, a wrong one,
or none set at all: 403 (kept as a rejected event, without its body). Otherwise the raw body is kept (InboundEvent,
once per SHA-256), answered 200 at once and processed by a task. Throttled per client address."""

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from integrations.models import IntegrationAccount
from integrations.services import receive_event


class ParcelEventsView(APIView):
    authentication_classes = []  # the token is the authentication
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "parcel_events"

    @extend_schema(exclude=True)  # the carrier's, not the API's
    def post(self, request, *args, **kwargs):
        token, body = request.headers.get("x-api-key", ""), request.body
        accounts = IntegrationAccount.objects.filter(provider="shiprocket", enabled=True)
        account = next((account for account in accounts if account.webhook_token_matches(token)), None)
        if account is None:
            receive_event("shiprocket", body, request.headers, rejected=True)
            return Response({"detail": "Unknown or missing token."}, status=status.HTTP_403_FORBIDDEN)
        receive_event("shiprocket", body, request.headers, account=account)
        return Response({"detail": "Received."})
