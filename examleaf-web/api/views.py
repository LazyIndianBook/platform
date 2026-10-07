"""REST API v1: the public catalogue (cached), the solutions (signed in, email confirmed), the student's attempts, and
the DPDP self-service of the profile (Download my data, Delete my account) with the website's own functions."""

import django_filters
from allauth.account.utils import has_verified_email
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.formats import date_format
from django.views.decorators.cache import cache_page
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import ConsentRecord, DeletionRequest
from accounts.views import export_user_data
from content.models import Board, Book, Paper, Subject
from ops.tasks import queue_text_email
from practice.forms import AttemptFilter
from practice.models import Attempt

from .serializers import (
    AttemptSerializer,
    BoardSerializer,
    BookSerializer,
    PaperSerializer,
    QuestionSerializer,
    SubjectSerializer,
)

PUBLIC_CACHE = 15 * 60  # seconds; the catalogue changes only when papers are imported


class VerifiedEmail(permissions.BasePermission):
    """Signed in with a confirmed email address, as the website requires before it shows solutions."""

    message = "Confirm your email address first."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_verified_email(request.user))


def cached(viewset):
    """The catalogue is the same for everybody: list and detail pages are kept in the cache (Redis in production)."""
    for name in ("list", "retrieve"):
        viewset = method_decorator(cache_page(PUBLIC_CACHE), name=name)(viewset)
    return viewset


@cached
class BoardViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Board.objects.order_by("id")
    serializer_class = BoardSerializer


@cached
class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Subject.objects.select_related("board", "class_level").order_by("id")
    serializer_class = SubjectSerializer
    filterset_fields = ["board"]


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
    @action(
        detail=True,
        permission_classes=[permissions.IsAuthenticated, VerifiedEmail],
        pagination_class=None,
        filter_backends=[],
    )
    def solutions(self, request, *args, **kwargs):
        """The questions in paper order, each with its marking-scheme solution (Markdown and HTML)."""
        questions = self.get_object().questions.select_related("solution")
        return Response(QuestionSerializer(questions, many=True).data)


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
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
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


# The steps and emails are those of accounts.views.delete_account and cancel_deletion: keep them the same.
class DeletionView(generics.GenericAPIView):
    """Delete my account: POST (with the password) asks for it, due seven days later; DELETE cancels it."""

    serializer_class = PasswordSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={201: DeletionSerializer, 200: DeletionSerializer})
    def post(self, request, *args, **kwargs):
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        if deletion := request.user.pending_deletion:
            return Response(DeletionSerializer(deletion).data)
        with transaction.atomic():
            deletion = DeletionRequest.objects.create(user=request.user)
            ConsentRecord.record(request, request.user, event=ConsentRecord.Event.WITHDRAWN)
        day = date_format(timezone.localtime(deletion.due_at), "j F Y")
        queue_text_email(
            request.user.email,
            "Your account will be deleted",
            f"We have your request to delete your ExamLeaf account. It will be deleted on {day}.\n\n"
            f'Changed your mind, or did not ask for this? Log in before then and press "Keep my '
            f'account" on {settings.SITE_URL}{reverse("account")}',
        )
        return Response(DeletionSerializer(deletion).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, *args, **kwargs):
        deletion = request.user.pending_deletion
        if not deletion:
            raise exceptions.NotFound("No account deletion is waiting.")
        deletion.status, deletion.closed_at = DeletionRequest.Status.CANCELLED, timezone.now()
        deletion.save()
        ConsentRecord.record(request, request.user)  # staying on is consenting again
        queue_text_email(
            request.user.email,
            "Your account will not be deleted",
            "The deletion of your ExamLeaf account has been cancelled. Your account stays as it was.",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
