"""REST API v1: the public catalogue (cached), the solutions (signed in, email confirmed), the student's attempts, and
the DPDP self-service of the profile (Download my data, Delete my account) with the website's own functions."""

from functools import wraps

import django_filters
from allauth.account.utils import has_verified_email
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db.models import Prefetch
from django.http import QueryDict
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, permissions, serializers, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import DeletionRequest
from accounts.views import export_user_data, keep_account, request_deletion
from content.models import Board, Book, Paper, Subject
from content.views import cache_solutions
from practice.forms import AttemptFilter
from practice.models import Attempt

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
    """DRF's error format, also for a JSON body over DATA_UPLOAD_MAX_MEMORY_SIZE (Django would answer an HTML 400)."""
    return views.exception_handler(PayloadTooLarge() if isinstance(exc, RequestDataTooBig) else exc, context)


class VerifiedEmail(permissions.BasePermission):
    """Signed in with a confirmed email address (a website log-in needs one too)."""

    message = "Confirm your email address first."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_verified_email(request.user))


class CanReadSolutions(VerifiedEmail):
    """Everyone while the solutions are open (SOLUTIONS_REQUIRE_LOGIN=0), as on the website; otherwise VerifiedEmail."""

    def has_permission(self, request, view):
        return not settings.SOLUTIONS_REQUIRE_LOGIN or super().has_permission(request, view)


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
        questions = self.get_object().questions.select_related("solution")
        return cache_solutions(Response(QuestionSerializer(questions, many=True).data), request.user)


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


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_password(self, value):
        check_password(self.context["request"], value)  # counted: 429 after five wrong ones in an hour (L6)
        return value


class DataExportView(generics.GenericAPIView):
    """Download my data: everything kept about the user, as the website's JSON file. Asks for the password, as the
    website does."""

    serializer_class = PasswordSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def post(self, request, *args, **kwargs):
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        return Response(export_user_data(request.user))


class DeletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeletionRequest
        fields = ["status", "requested_at", "due_at"]


class DeletionView(generics.GenericAPIView):
    """Delete my account: POST (with the password) asks for it, due seven days later; DELETE cancels it. The steps and
    emails are the website's (accounts.views.request_deletion and keep_account)."""

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
