"""Support outside the staff API: "My requests" for the signed-in customer (GET and POST /api/v1/me/tickets/: API.md
"My requests") and the support mailbox's hook (POST /api/hooks/support-mail/: the forwarder's, not the API's)."""

import base64

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.views import VerifiedEmail
from integrations.models import IntegrationAccount
from integrations.services import receive_event

from . import services
from .models import Ticket, contact_hash
from .serializers import MyTicketCreateSerializer, MyTicketSerializer

PROVIDER = "support_mail"
TOKEN_HEADER = "X-Support-Mail-Token"


class MyTicketsView(generics.ListCreateAPIView):
    """My requests: the signed-in customer's tickets (their account's, and those sent from one of its confirmed email
    addresses before it had them), newest first, 50 a page: the number, what it is about, its status and dates, never
    staff's notes nor who works on it. POST makes one (a confirmed email address; 10 an hour): it is acknowledged by
    email with its number at once."""

    serializer_class = MyTicketSerializer
    filter_backends = []

    def get_permissions(self):
        return [permissions.IsAuthenticated(), *([VerifiedEmail()] if self.request.method == "POST" else [])]

    def get_throttles(self):
        self.throttle_scope = "support_request" if self.request.method == "POST" else None
        return super().get_throttles()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Ticket.objects.none()
        user = self.request.user
        confirmed = EmailAddress.objects.filter(user=user, verified=True).values_list("email", flat=True)
        hashes = [contact_hash("email", address.lower()) for address in confirmed]
        mine = Q(user=user) | Q(user=None, requester_email_hash__in=hashes)
        tickets = Ticket.objects.filter(mine).exclude(status=Ticket.Status.SPAM).select_related("order")
        return tickets.order_by("-received_at", "-pk")

    @extend_schema(request=MyTicketCreateSerializer, responses={201: MyTicketSerializer})
    def post(self, request, *args, **kwargs):
        data = MyTicketCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        ticket = services.from_account(
            request.user,
            category=values["category"],
            subject=values["subject"],
            text=values["message"],
            order_number=values["order"],
            request=request,
        )
        return Response(MyTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class SupportMailView(APIView):
    """POST /api/hooks/support-mail/: an email sent to the support address, from the forwarder (an SES receipt rule's
    Lambda, or Cloudflare's Email Routing worker): the raw message (message/rfc822) or SES's receipt notification, with
    the support mailbox account's webhook token in X-Support-Mail-Token (integrations.IntegrationAccount "support_mail":
    compared in constant time, the previous one too for 24 hours after a rotation). A missing or wrong token, or no
    enabled account: 403, kept without its body. Otherwise 200 at once: the raw body kept once per SHA-256
    (InboundEvent), read by a task (support.tasks.process_inbound_mail). At most SUPPORT_MAIL_MAX_BYTES (413 above),
    API_THROTTLE_SUPPORT_MAIL per client address."""

    authentication_classes = []  # the token is the authentication
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support_mail"

    @extend_schema(exclude=True)  # the forwarder's, not the API's
    def post(self, request, *args, **kwargs):
        given = request.headers.get(TOKEN_HEADER, "")
        accounts = IntegrationAccount.objects.filter(provider=PROVIDER, enabled=True)
        account = next((account for account in accounts if account.webhook_token_matches(given)), None)
        if account is None:
            receive_event(PROVIDER, b"", request.headers, rejected=True)
            return Response({"detail": "Unknown or missing token."}, status=status.HTTP_403_FORBIDDEN)
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > settings.SUPPORT_MAIL_MAX_BYTES:
            return Response({"detail": "The message is too large."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        # the stream, not request.body: Django caps a body at DATA_UPLOAD_MAX_MEMORY_SIZE (1 MB), and mail with a
        # photo is larger; read up to our own cap
        raw = request._request.read(settings.SUPPORT_MAIL_MAX_BYTES + 1)
        if not raw.strip():
            return Response({"detail": "No message."}, status=status.HTTP_400_BAD_REQUEST)
        if len(raw) > settings.SUPPORT_MAIL_MAX_BYTES:
            return Response({"detail": "The message is too large."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:  # 8-bit mail that is not UTF-8: kept whole, as base64 (mail.raw_message reads it)
            raw = b"base64:" + base64.b64encode(raw)
        receive_event(PROVIDER, raw, request.headers, account=account)
        return Response({"detail": "Received."})
