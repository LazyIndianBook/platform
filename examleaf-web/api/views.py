"""REST API v1: the public catalogue (cached), the solutions (signed in, email confirmed), the student's attempts, and
the DPDP self-service of the profile (Download my data, Delete my account) with the website's own functions."""

import time
from collections import defaultdict
from functools import wraps

import django_filters
from allauth.account import app_settings as account_settings
from allauth.account.authentication import get_authentication_records
from allauth.account.utils import has_verified_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import QueryDict
from django.utils.cache import patch_cache_control
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_serializer,
    inline_serializer,
)
from rest_framework import exceptions, generics, permissions, serializers, status, views, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.forms import TurnstileField
from accounts.models import DeletionRequest, TeacherProfile
from accounts.views import DATA_PARTS, export_user_data, how_many, keep_account, request_deletion, resend_parent_link
from content.models import Board, Book, Paper, Subject
from content.views import cache_solutions
from pages.models import Page
from pages.templatetags.pages import page_html
from pages.views import CONTACT_SENT, support_email
from practice.forms import AttemptFilter
from practice.models import Attempt
from shop.models import INR, ShippingRate
from shop.views import over_limit
from staff.config import site_setting

from .auth import check_password
from .serializers import (
    AttemptSerializer,
    BoardSerializer,
    BookSerializer,
    PaperSerializer,
    QuestionSerializer,
    SubjectSerializer,
)

PUBLIC_CACHE = 15 * 60  # seconds; the catalogue changes only when papers are imported


class PayloadTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The request body is too large."
    default_code = "too_large"


def exception_handler(exc, context):
    """DRF's error format, also for a JSON body over DATA_UPLOAD_MAX_MEMORY_SIZE (Django would answer an HTML 400) and
    for allauth's 429 (an HTML page): a code or SMS refused by its limits (accounts.adapter.TooManyCodes, M1, M2)."""
    if isinstance(exc, RequestDataTooBig):
        exc = PayloadTooLarge()
    elif isinstance(exc, ImmediateHttpResponse) and exc.response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        exc = exceptions.Throttled(detail=getattr(exc, "detail", None) or "Too many requests: try again later.")
    return views.exception_handler(exc, context)


class VerifiedEmail(permissions.BasePermission):
    """Signed in with a confirmed email address (a website log-in needs one too)."""

    message = "Confirm your email address first."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_verified_email(request.user))


def check_turnstile(attrs):
    """The website's bot check (Cloudflare Turnstile) while it is on: the token sent as `turnstile`."""
    if settings.TURNSTILE:
        try:
            TurnstileField().clean(attrs.get("turnstile", ""))
        except DjangoValidationError as error:
            raise serializers.ValidationError({"turnstile": error.messages}) from error


class CanReadSolutions(VerifiedEmail):
    """Everyone while the solutions are open (SOLUTIONS_REQUIRE_LOGIN=0) and on a book's open sample (Paper.is_sample),
    as on the website; otherwise VerifiedEmail."""

    def has_permission(self, request, view):
        if not settings.SOLUTIONS_REQUIRE_LOGIN or super().has_permission(request, view):
            return True
        return Paper.objects.filter(code=view.kwargs.get("code"), is_sample=True, is_published=True).exists()


def canonical_query(known):
    """Keep only the query parameters in `known`, sorted, before cache_page makes its key from the address: `?x=1` …
    `?x=n` then share the canonical address's entry instead of filling the cache with copies (L8)."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            django_request = request._request  # DRF's request wraps Django's
            query = QueryDict(mutable=True)
            for name in sorted(set(django_request.GET) & known):
                query.setlist(name, django_request.GET.getlist(name))
            django_request.GET, django_request.META["QUERY_STRING"] = query, query.urlencode()
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def cached(viewset):
    """The catalogue is the same for everybody: list and detail pages are kept in the cache (Redis in production),
    one entry per address made of the parameters the viewset reads (pages, search, ordering, its filters)."""
    filterset = getattr(viewset, "filterset_class", None)
    filters = filterset.base_filters if filterset else getattr(viewset, "filterset_fields", [])
    known = {"page", "page_size", "search", "ordering", "format", *filters}
    for name in ("list", "retrieve"):
        viewset = method_decorator([canonical_query(known), cache_page(PUBLIC_CACHE)], name=name)(viewset)
    return viewset


@cached
class BoardViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Board.objects.order_by("id")
    serializer_class = BoardSerializer
    ordering_fields = ["id", "name"]  # only these (I4): DRF would otherwise take any of the serializer's fields


@cached
class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Subject.objects.select_related("board", "class_level").order_by("id")
    serializer_class = SubjectSerializer
    filterset_fields = ["board"]
    ordering_fields = ["id", "name"]


@cached
class BookViewSet(viewsets.ReadOnlyModelViewSet):
    """Books with their published papers (only published papers are public, as on the website)."""

    permission_classes = [permissions.AllowAny]
    queryset = Book.objects.select_related("subject__board", "subject__class_level").prefetch_related(
        Prefetch("papers", queryset=Paper.objects.filter(is_published=True))
    )
    serializer_class = BookSerializer
    lookup_field = "slug"
    filterset_fields = ["subject"]
    search_fields = ["title", "subject__name"]
    ordering_fields = ["id", "title"]
    ordering = ["id"]


class PaperFilter(django_filters.FilterSet):
    book = django_filters.CharFilter(field_name="book__slug", help_text="book slug, e.g. physics-2027")
    subject = django_filters.NumberFilter(field_name="book__subject", help_text="subject id")

    class Meta:
        model = Paper
        fields = ["book", "subject", "tier"]


@cached
class PaperViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Paper.objects.filter(is_published=True).select_related("book__subject")
    serializer_class = PaperSerializer
    lookup_field = "code"
    filterset_class = PaperFilter
    search_fields = ["code", "title"]
    ordering_fields = ["code", "number", "tier"]
    ordering = ["code"]

    @extend_schema(responses=QuestionSerializer(many=True))
    @action(detail=True, permission_classes=[CanReadSolutions], pagination_class=None, filter_backends=[])
    def solutions(self, request, *args, **kwargs):
        """The questions in paper order, each with its marking-scheme solution (Markdown and HTML)."""
        paper = self.get_object()
        questions = paper.questions.select_related("solution")
        return cache_solutions(Response(QuestionSerializer(questions, many=True).data), request.user, paper.is_sample)


class QrView(generics.RetrieveAPIView):
    """What a scanned code (PHY-E01, any case) points to: the paper, with its solutions_url."""

    permission_classes = [permissions.AllowAny]
    queryset = Paper.objects.filter(is_published=True).select_related("book__subject")
    serializer_class = PaperSerializer

    def get_object(self):
        return generics.get_object_or_404(self.get_queryset(), code__iexact=self.kwargs["code"])


# TODO(teachers): nothing links a student to a teacher yet (TeacherProfile has no students). Once a link model exists,
# let verified teachers (user.is_teacher) list the attempts of the students linked to them, read-only.
class AttemptViewSet(viewsets.ModelViewSet):
    """The signed-in student's own attempts (My record), filterable by subject id and tier."""

    serializer_class = AttemptSerializer
    permission_classes = [permissions.IsAuthenticated, VerifiedEmail]
    filterset_class = AttemptFilter
    ordering_fields = ["date", "marks_obtained", "created"]
    ordering = ["-date", "-id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return Attempt.objects.none()
        return self.request.user.attempts.select_related("paper__book__subject")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TierAverageSerializer(serializers.Serializer):
    tier = serializers.ChoiceField(choices=Paper.Tier.choices)
    label = serializers.CharField()
    count = serializers.IntegerField(help_text="attempts")
    average = serializers.IntegerField(help_text="% of the full marks, rounded as My record rounds it")


class SubjectAverageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    count = serializers.IntegerField(help_text="attempts")
    average = serializers.IntegerField(help_text="% of the full marks")


class PaperRecordSerializer(serializers.Serializer):
    paper = serializers.CharField(help_text="its code")
    title = serializers.CharField()
    count = serializers.IntegerField(help_text="attempts")
    best = AttemptSerializer(help_text="the most marks (the latest of equals)")
    latest = AttemptSerializer()


class RecordSerializer(serializers.Serializer):
    count = serializers.IntegerField(help_text="attempts")
    tiers = TierAverageSerializer(many=True, help_text="the tiers attempted, Easy to Hard")
    subjects = SubjectAverageSerializer(many=True, help_text="by name")
    papers = PaperRecordSerializer(many=True, help_text="by code")


def average(attempts):
    """Their percentages' mean, rounded as My record rounds it (the record's averages per tier)."""
    return round(sum(attempt.percent for attempt in attempts) / len(attempts))


class RecordView(generics.GenericAPIView):
    """My record in figures: the average per tier (as My record shows it) and per subject, and per paper the best and
    the latest attempt; `?subject=<id>&tier=` as attempts/."""

    serializer_class = RecordSerializer
    permission_classes = [permissions.IsAuthenticated, VerifiedEmail]
    filterset_class = AttemptFilter
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Attempt.objects.none()
        return self.request.user.attempts.select_related("paper__book__subject")

    @extend_schema(
        parameters=[
            OpenApiParameter("subject", int, description="subject id"),
            OpenApiParameter("tier", str, enum=Paper.Tier.values),
        ]
    )
    def get(self, request, *args, **kwargs):
        attempts = self.filter_queryset(self.get_queryset())  # newest first
        tiers, subjects, papers = defaultdict(list), defaultdict(list), defaultdict(list)
        for attempt in attempts:
            tiers[attempt.paper.tier].append(attempt)
            subjects[attempt.paper.book.subject].append(attempt)
            papers[attempt.paper].append(attempt)
        record = {
            "count": len(attempts),
            "tiers": [
                {"tier": tier, "label": label, "count": len(tiers[tier]), "average": average(tiers[tier])}
                for tier, label in Paper.Tier.choices
                if tiers[tier]
            ],
            "subjects": [
                {"id": subject.pk, "code": subject.code, "name": subject.name, "count": len(rows),
                 "average": average(rows)}
                for subject, rows in sorted(subjects.items(), key=lambda item: item[0].name)
            ],
            "papers": [
                {"paper": paper.code, "title": paper.title, "count": len(rows), "latest": rows[0],
                 "best": max(rows, key=lambda attempt: attempt.marks_obtained)}
                for paper, rows in sorted(papers.items(), key=lambda item: item[0].code)
            ],
        }  # fmt: skip
        return Response(self.get_serializer(record).data)


class ReauthenticationRequired(exceptions.PermissionDenied):
    default_detail = {"detail": "Confirm it is you: enter your password, or log in again.",
                      "code": "reauthentication_required"}  # fmt: skip


def recently_authenticated(request):
    """Logged in or re-authenticated in this session within ACCOUNT_REAUTHENTICATION_TIMEOUT (5 minutes), by allauth's
    records of the session: the website's log-in and re-authentication, allauth.headless's (auth/reauthenticate,
    auth/2fa/reauthenticate, a new log-in, Google's included). Not allauth's did_recently_authenticate, which lets an
    account with neither a password nor a second step through at any time. The app's tokens have no session."""
    if not isinstance(request.successful_authenticator, SessionAuthentication):
        return False
    records = get_authentication_records(request)
    return bool(records) and time.time() - records[-1]["at"] < account_settings.REAUTHENTICATION_TIMEOUT


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
        help_text="not needed within 5 minutes of a log-in or re-authentication in this browser session",
    )

    def validate_password(self, value):
        if value:
            check_password(self.context["request"], value)  # counted: 429 after five wrong ones in an hour (L6)
        return value

    def validate(self, attrs):
        if not attrs.get("password") and not recently_authenticated(self.context["request"]):
            raise ReauthenticationRequired()  # 403: an account without a password logs in again (Google)
        return attrs


class DataExportView(generics.GenericAPIView):
    """Download my data: everything kept about the user, as the website's JSON file. Asks for the password, or a log-in
    or re-authentication in the last 5 minutes, as the website does."""

    serializer_class = PasswordSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def post(self, request, *args, **kwargs):
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        return Response(export_user_data(request.user))


class ExportPartSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="the part's name in the file")
    label = serializers.CharField()
    count = serializers.IntegerField(help_text="its records (a part that is one record: 1, or 0 when empty)")


class DataExportSummaryView(generics.GenericAPIView):
    """What Download my data holds, part by part, as the website's page shows it before the file; without the file,
    so without the password (the profile, the orders and My record show as much)."""

    serializer_class = ExportPartSerializer
    pagination_class = None
    filter_backends = []
    throttle_scope = "dj_rest_auth"  # the whole export is read: as often as the file

    @extend_schema(responses=ExportPartSerializer(many=True))
    def get(self, request, *args, **kwargs):
        data = export_user_data(request.user)
        parts = [{"key": key, "label": label, "count": how_many(data.get(key))} for key, label in DATA_PARTS.items()]
        return Response(self.get_serializer(parts, many=True).data)


class DeletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeletionRequest
        fields = ["status", "requested_at", "due_at"]


class DeletionView(generics.GenericAPIView):
    """Delete my account: POST (with the password, or within 5 minutes of a log-in or re-authentication) asks for it,
    due seven days later; DELETE cancels it. The steps and emails are the website's (accounts.views.request_deletion and
    keep_account)."""

    serializer_class = PasswordSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={201: DeletionSerializer, 200: DeletionSerializer})
    def post(self, request, *args, **kwargs):
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        deletion, created = request_deletion(request)
        return Response(
            DeletionSerializer(deletion).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, *args, **kwargs):
        if not keep_account(request):
            raise exceptions.NotFound("No account deletion is waiting.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Asked",
            value={"school_name": "Cotton Collegiate H.S. School", "district": "Kamrup Metro", "subject": "Physics"},
            request_only=True,
        )
    ]
)
class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ["school_name", "district", "subject", "verified", "verified_at", "created"]
        read_only_fields = ["verified", "verified_at", "created"]


class TeacherView(generics.GenericAPIView):
    """Teacher access, as on My account: GET the request and whether staff have verified it (404 until there is one);
    POST asks for it, once per account. Staff check with the school; a verified teacher gets the TEACHER role (roles
    in me/)."""

    serializer_class = TeacherSerializer
    permission_classes = [permissions.IsAuthenticated, VerifiedEmail]

    def get(self, request, *args, **kwargs):
        profile = generics.get_object_or_404(TeacherProfile, user=request.user)
        return Response(self.get_serializer(profile).data)

    @extend_schema(responses={201: TeacherSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save(user=request.user)
        except IntegrityError as error:  # one request per account (a double tap included): its status is in GET
            raise serializers.ValidationError({"non_field_errors": ["You have asked for teacher access."]}) from error
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_serializer(
    examples=[OpenApiExample("A corrected number", value={"parent_contact": "98640 12345"}, request_only=True)]
)
class ParentContactSerializer(serializers.Serializer):
    parent_contact = serializers.CharField(
        max_length=120, help_text="the parent's or guardian's email address or mobile number: the one on record, or new"
    )


class ParentConsentView(generics.GenericAPIView):
    """PARENTAL_CONSENT_MODE "verified", while a parent has not confirmed (`consent_pending` in me/): the link to
    confirm, again, to the contact on record or a corrected one, as on My account. 404 when no consent is awaited; 429
    within ten minutes of the last link."""

    serializer_class = ParentContactSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={200: DetailSerializer})
    def post(self, request, *args, **kwargs):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        if not user.consent_pending:
            raise exceptions.NotFound("No parent's consent is awaited.")
        try:
            resend_parent_link(user, data.validated_data["parent_contact"])
        except DjangoValidationError as error:
            if error.code == "too_soon":
                raise exceptions.Throttled(wait=600, detail=error.message) from error
            raise serializers.ValidationError({"parent_contact": [error.message]}) from error
        return Response({"detail": f"We have sent {user.parent_contact} a link to confirm."})


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A question",
            request_only=True,
            value={
                "name": "Rahul Das",
                "email": "rahul@example.com",
                "message": "Order EL-2026-000123 has not come yet.",
                "turnstile": "0.Zx…",
            },
        )
    ]
)
class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    email = serializers.EmailField(help_text="we reply to this address")
    message = serializers.CharField(max_length=2000)
    website = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="the honeypot: a field people never see; send none"
    )
    turnstile = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="Turnstile's token while the bot check is on"
    )

    def validate_name(self, value):
        return " ".join(value.split())  # one line: it is the email's subject

    def validate(self, attrs):
        check_turnstile(attrs)
        return attrs


class ContactUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The contact form is not set up yet: please write to us by email."


class ContactView(generics.GenericAPIView):
    """The contact form, as on the website's /contact/: the message becomes a support ticket (support.services
    .from_contact_form: a number, the legal clocks, the acknowledgement with the number to the sender's address; with
    SUPPORT_COPY_TO_EMAIL a copy to the support address, SUPPORT_EMAIL else SELLER_EMAIL). Turnstile's token while the
    bot check is on; 5 an hour per client address, the website's form included; a filled-in `website` (the honeypot)
    is thanked and dropped. 503 while the support address is still a [placeholder]: the acknowledgement's replies go
    there."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = ContactSerializer

    @extend_schema(responses={200: DetailSerializer})
    def post(self, request, *args, **kwargs):
        if not support_email():
            raise ContactUnavailable()
        if over_limit(request, "contact", 5, 3600):  # counted with the website's form
            raise exceptions.Throttled(wait=3600)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not data.validated_data.get("website"):
            from support.services import from_contact_form

            from_contact_form(*(data.validated_data[name] for name in ("name", "email", "message")), request=request)
        return Response({"detail": CONTACT_SENT})


CONFIG = inline_serializer(
    "Config",
    {
        "auth": inline_serializer(
            "AuthConfig",
            {
                "login_methods": serializers.ListField(child=serializers.CharField(), help_text='"email", "phone"'),
                "login_by_code": serializers.BooleanField(help_text="a code by email (or SMS) instead of a password"),
                "sms": serializers.BooleanField(help_text="SMS on: log-in by phone, a mobile number on the account"),
                "google": serializers.BooleanField(help_text="Continue with Google"),
                "passkeys": serializers.BooleanField(help_text="log-in with a passkey"),
                "turnstile_site_key": serializers.CharField(
                    allow_null=True, help_text="Cloudflare Turnstile's, while the bot check is on; send its token"
                ),
            },
        ),
        "shop": inline_serializer(
            "ShopConfig",
            {
                "open": serializers.BooleanField(help_text="off: only staff change carts, check out and pay"),
                "cod": serializers.BooleanField(help_text="cash on delivery offered"),
                "cod_max_value": serializers.DecimalField(
                    max_digits=10, decimal_places=2, help_text="the most an order may be worth, shipping included"
                ),
                "currency": serializers.CharField(),
            },
        ),
        "shipping": inline_serializer(
            "ShippingConfig",
            {
                "fee_from": serializers.DecimalField(
                    max_digits=10, decimal_places=2, allow_null=True, help_text='the lowest delivery fee: "from ₹40"'
                ),
                "free_above": serializers.DecimalField(
                    max_digits=10, decimal_places=2, allow_null=True, help_text="the lowest value that ships free"
                ),
            },
        ),
        "solutions_require_login": serializers.BooleanField(),
        "parental_consent": serializers.ChoiceField(choices=["declared", "verified"]),
        "support": inline_serializer(
            "SupportConfig",
            {
                "email": serializers.EmailField(allow_null=True, help_text="null until the real one is set"),
                "phone": serializers.CharField(allow_null=True, help_text="null until the real one is set"),
            },
        ),
        "app_links": inline_serializer(
            "AppLinksConfig",
            {
                "android": serializers.URLField(allow_null=True, help_text="Google Play's page; null until out"),
                "ios": serializers.URLField(allow_null=True, help_text="the App Store's page; null until out"),
            },
        ),
        "web_course": serializers.BooleanField(
            help_text="the revision course's chapter, flash-card and quiz pages on the website; off: the app only"
        ),
        "maintenance": inline_serializer(
            "MaintenanceConfig",
            {
                "on": serializers.BooleanField(help_text="show the banner; staff may still work"),
                "banner": serializers.CharField(allow_null=True, help_text="its text; null: none"),
            },
        ),
    },
)


class ConfigView(generics.GenericAPIView):
    """What this server has switched on, so that a frontend never hard-codes a feature flag: the ways to log in
    (allauth.headless's /_allauth/<client>/v1/config has allauth's own view of them), the bot check, the shop, whether
    the solutions need an account, the parent's consent mode, the support contacts (null while the seller's details
    still hold a [placeholder]), the app's store pages (null until set) and whether the revision course has pages on
    the website (WEB_COURSE, off by default), and maintenance mode with its banner. SHOP_OPEN, SHOP_COD_ENABLED,
    PARENTAL_CONSENT_MODE, WEB_COURSE and maintenance are the panel's when it has set them (staff.config), the
    environment's otherwise. Public, cacheable for 5 minutes."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        responses=CONFIG,
        examples=[
            OpenApiExample(
                "Production",
                response_only=True,
                value={
                    "auth": {
                        "login_methods": ["email", "phone"],
                        "login_by_code": True,
                        "sms": True,
                        "google": True,
                        "passkeys": True,
                        "turnstile_site_key": "0x4AAAAAAA…",
                    },
                    "shop": {"open": True, "cod": True, "cod_max_value": "1500.00", "currency": "INR"},
                    "shipping": {"fee_from": "40.00", "free_above": "499.00"},
                    "solutions_require_login": True,
                    "parental_consent": "verified",
                    "support": {"email": "help@examleaf.in", "phone": None},
                    "app_links": {"android": "https://play.google.com/store/apps/details?id=…", "ios": None},
                    "web_course": False,
                    "maintenance": {"on": False, "banner": None},
                },
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        seller, providers = settings.SHOP_SELLER, get_social_adapter().list_providers(request._request)
        response = Response(
            {
                "auth": {
                    "login_methods": sorted(account_settings.LOGIN_METHODS),
                    "login_by_code": account_settings.LOGIN_BY_CODE_ENABLED,
                    "sms": settings.SMS_ENABLED,
                    "google": any(provider.id == "google" for provider in providers),
                    "passkeys": settings.MFA_PASSKEY_LOGIN_ENABLED,
                    "turnstile_site_key": settings.TURNSTILE_SITE_KEY if settings.TURNSTILE else None,
                },
                "shop": {
                    "open": site_setting("SHOP_OPEN"),
                    "cod": site_setting("SHOP_COD_ENABLED"),
                    "cod_max_value": f"{settings.SHOP_COD_MAX_VALUE:.2f}",
                    "currency": INR,
                },
                "shipping": ShippingRate.summary(),  # the rates: shipping/
                "solutions_require_login": settings.SOLUTIONS_REQUIRE_LOGIN,
                "parental_consent": site_setting("PARENTAL_CONSENT_MODE"),
                "support": {
                    "email": support_email() or None,  # SUPPORT_EMAIL, else SELLER_EMAIL
                    "phone": None if "[" in seller["phone"] else seller["phone"] or None,
                },
                "app_links": {"android": settings.APP_LINK_ANDROID or None, "ios": settings.APP_LINK_IOS or None},
                "web_course": site_setting("WEB_COURSE"),
                "maintenance": {
                    "on": site_setting("MAINTENANCE_MODE"),
                    "banner": site_setting("MAINTENANCE_BANNER") or None,
                },
            }
        )
        patch_cache_control(response, public=True, max_age=300)
        return response


class PageSerializer(serializers.ModelSerializer):
    markdown = serializers.CharField(source="body_md")
    html = serializers.SerializerMethodField(help_text='as the website shows it; a [placeholder] is <mark class="…">')
    updated = serializers.DateTimeField(read_only=True, help_text="when the text last changed (its latest history)")
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ["slug", "title", "version", "updated", "markdown", "html", "web_url"]

    def get_html(self, page) -> str:
        return page_html(page.body_md)

    def get_web_url(self, page) -> str:
        return self.context["request"].build_absolute_uri(page.get_absolute_url())


@cached
class PageViewSet(viewsets.ReadOnlyModelViewSet):
    """The legal and policy pages (privacy, terms, refunds, shipping, contact) as the website shows them: Markdown and
    HTML, the version (consent records keep the privacy notice's) and when the text last changed. Cached 15 minutes."""

    permission_classes = [permissions.AllowAny]
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    lookup_field = "slug"
    ordering_fields = ["slug", "title"]
