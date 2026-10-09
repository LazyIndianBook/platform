"""The content module's staff API, under /api/v1/staff/content/ (API.md "Content (staff)"; content/README.md), on the
staff app's rules (staff.api.StaffView): the panel's session with a second factor or an API key, each action's
catalogued permission, the person's subjects (StaffScope: a CONTENT_EDITOR narrowed to PHY reaches PHY's books,
papers, questions, solutions, reviews, reports and deposits, and 404 for the others), cursor pages, `no-store`, every
refusal an `authz_fail` (staff.middleware). Books and papers change at once; a question's or a solution's text goes to
its draft and through a review (content.review); reported mistakes are triaged (content.reports); imports are staff
jobs (content.imports); every change is an audit event. The serializers are explicit (never `__all__`)."""

import base64
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import exceptions, generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from staff import audit
from staff.api import Cursor, StaffView
from staff.backends import SUBJECT, scope_values, scoped
from staff.models import Job
from staff.privacy import mask_email
from staff.serializers import JobSerializer

from . import papers_parser, reports, review
from .isbn import changed_isbn
from .models import Book, ErrorReport, LegalDeposit, Paper, Question, ReviewTask, Solution, Subject
from .tasks import deposit_item

DRAFT_STATES = [Question.State.DRAFT, Question.State.IN_REVIEW]
PROOF_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
PROOF_MB = 5


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["content (staff)"]


class ContentView(StaffView):
    """Every queryset in the person's subjects, for the permission the action names."""

    schema = StaffSchema()

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return scoped(queryset, self.request.user, self.required_permission(self.request))


class Oldest(Cursor):
    ordering = "pk"


class ByCode(Cursor):
    ordering = "code"


def preview(text, length=140):
    """The first words of a text, on one line (the tree's rows)."""
    line = " ".join((text or "").split())
    return line if len(line) <= length else line[: length - 1].rstrip() + "…"


def in_scope(model, pk, user, perm):
    return scoped(model.objects.filter(pk=pk), user, perm).exists()


def django_errors(error):
    return serializers.ValidationError(getattr(error, "message_dict", None) or {"non_field_errors": error.messages})


class NotPublic(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The site's address is not a public https one: a printed code made with it would not work."
    default_code = "site_url_not_public"


# ---- History (every content model keeps one: simple-history) ----


class ContentLineSerializer(serializers.Serializer):
    op = serializers.ChoiceField(choices=review.LINE_OPS)
    text = serializers.CharField()


class ContentChangeSerializer(serializers.Serializer):
    field = serializers.CharField(help_text='a field, or "draft.<field>" for a draft\'s')
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
    lines = ContentLineSerializer(many=True, help_text="the two, line by line")


class ContentVersionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="history_id")
    at = serializers.DateTimeField(source="history_date")
    by = serializers.IntegerField(source="history_user_id", allow_null=True)
    reason = serializers.CharField(source="history_change_reason", allow_null=True)
    type = serializers.ChoiceField(source="history_type", choices=review.VERSION_TYPES)
    changes = ContentChangeSerializer(many=True, help_text="what this version changed from the one before it")


VERSION_PAGE = inline_serializer(
    "ContentVersionPage",
    {
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": ContentVersionSerializer(many=True),
    },
)


class HistoryMixin:
    """GET …/{id}/history/: the versions, newest first, each with what it changed (simple-history's diff_against);
    POST …/{id}/history/{version}/restore/: back to one (a question's or a solution's text into its draft)."""

    @extend_schema(
        responses=VERSION_PAGE, parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)]
    )
    @action(detail=True, filter_backends=[])
    def history(self, request, *args, **kwargs):
        obj = self.get_object()
        paginator = Cursor()
        page = paginator.paginate_queryset(obj.history.all(), request, view=self)
        older = obj.history.filter(history_id__lt=page[-1].history_id).order_by("-history_id").first() if page else None
        rows = []
        for index, version in enumerate(page):
            before = page[index + 1] if index + 1 < len(page) else older
            version.changes = review.version_changes(version, before)
            rows.append(version)
        return paginator.get_paginated_response(ContentVersionSerializer(rows, many=True).data)

    @extend_schema(
        request=None,
        responses=OpenApiTypes.OBJECT,
        parameters=[OpenApiParameter("history_id", int, OpenApiParameter.PATH, description="the version's id")],
    )
    @action(detail=True, methods=["post"], url_path=r"history/(?P<history_id>\d+)/restore", filter_backends=[])
    def restore(self, request, history_id=None, *args, **kwargs):
        """Back to a version: a book's or a paper's fields at once, a question's or a solution's text into its
        draft (to be reviewed)."""
        obj = review.restore(self.get_object(), int(history_id), self.human(), request)
        return Response(self.detail_serializer(obj, context=self.get_serializer_context()).data)


# ---- Books ----


class BookFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(field_name="subject__code", help_text="its code: PHY")
    board = django_filters.CharFilter(field_name="subject__board__short_name", help_text="ASSEB")
    class_level = django_filters.NumberFilter(field_name="subject__class_level__number")

    class Meta:
        model = Book
        fields = ["subject", "board", "class_level", "format"]


class ContentBookSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    papers = serializers.SerializerMethodField(help_text="its papers")
    deposit_due_on = serializers.DateField(read_only=True, allow_null=True, help_text="the legal deposit's last day")
    isbn = serializers.CharField(
        max_length=20, required=False, allow_blank=True, help_text="ISBN-13, hyphens allowed: kept as its 13 digits"
    )

    class Meta:
        model = Book
        fields = ["id", "title", "subject", "subject_code", "edition", "slug", "cover", "isbn", "format"]
        fields += ["published_on", "deposit_due_on", "papers"]

    def get_papers(self, book) -> int:
        count = getattr(book, "papers_count", None)
        return book.papers.count() if count is None else count

    def validate_isbn(self, value):
        try:
            digits = changed_isbn(value, self.instance.isbn if self.instance else None)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        if digits and Book.objects.filter(isbn=digits).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Another book has this ISBN: each format and edition has its own.")
        return digits

    def validate_subject(self, subject):
        if not in_scope(Subject, subject.pk, self.context["request"].user, "content.view_subject"):
            raise serializers.ValidationError("Not one of your subjects.")
        return subject


class ContentBookDetailSerializer(ContentBookSerializer):
    missing_deposits = serializers.SerializerMethodField(help_text="the libraries without this edition yet")

    class Meta(ContentBookSerializer.Meta):
        fields = [*ContentBookSerializer.Meta.fields, "missing_deposits"]

    def get_missing_deposits(self, book) -> list[str]:
        return LegalDeposit.missing([book])[book.pk]


EDITED = ["title", "subject", "edition", "slug", "cover", "isbn", "format", "published_on"]


class BookViewSet(HistoryMixin, ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Books (filters subject, board, class_level, format): their ISBN (checked when set or changed), format,
    edition and publication date (the legal deposit's clock); made and changed at once, audited."""

    queryset = Book.objects.select_related("subject").annotate(papers_count=Count("papers"))
    filterset_class = BookFilter
    detail_serializer = ContentBookDetailSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history"], "content.view_book"),
        "create": "content.add_book",
        **dict.fromkeys(["partial_update", "restore"], "content.change_book"),
    }

    def get_serializer_class(self):
        return ContentBookSerializer if self.action == "list" else ContentBookDetailSerializer

    @extend_schema(request=ContentBookSerializer, responses={201: ContentBookDetailSerializer})
    def create(self, request, *args, **kwargs):
        data = ContentBookSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            book = Book(**data.validated_data)
            try:
                book.full_clean()
            except DjangoValidationError as error:
                raise django_errors(error) from error
            book._change_reason = "made in the panel"
            book.save()
            audit.record("content.book_created", request=request, target=book, details={"slug": book.slug})
        return Response(ContentBookDetailSerializer(book, context=self.get_serializer_context()).data, status=201)

    @extend_schema(request=ContentBookSerializer(partial=True), responses=ContentBookDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        book = self.get_object()
        data = ContentBookSerializer(book, data=request.data, partial=True, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=book.pk)
            changes = {}
            for field, value in data.validated_data.items():
                if getattr(book, field) != value:
                    changes[field] = [getattr(book, field), value]
                    setattr(book, field, value)
            if changes:
                try:
                    book.full_clean()
                except DjangoValidationError as error:
                    raise django_errors(error) from error
                book._change_reason = "changed in the panel"
                book.save()
                audit.record("content.book_changed", request=request, target=book, changes=changes)
                if {"edition", "published_on"} & set(changes):  # the deposits it now needs, and their date
                    deposit_item(book, LegalDeposit.missing([book])[book.pk])
        return Response(ContentBookDetailSerializer(book, context=self.get_serializer_context()).data)


# ---- Papers ----


class PaperFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(field_name="book__subject__code", help_text="its code: PHY")
    board = django_filters.CharFilter(field_name="book__subject__board__short_name")
    class_level = django_filters.NumberFilter(field_name="book__subject__class_level__number")
    changed = django_filters.BooleanFilter(method="filter_changed", help_text="true: a draft waits in it")
    q = django_filters.CharFilter(method="filter_q", help_text="its code or title")

    class Meta:
        model = Paper
        fields = ["subject", "board", "class_level", "book", "tier", "is_published"]

    def filter_changed(self, queryset, name, value):
        drafted = Q(questions__state__in=DRAFT_STATES) | Q(questions__solution__state__in=DRAFT_STATES)
        return queryset.filter(drafted).distinct() if value else queryset.exclude(drafted)

    def filter_q(self, queryset, name, value):
        value = value.strip()[:50]
        return queryset.filter(Q(code__icontains=value) | Q(title__icontains=value)) if value else queryset


class ContentPaperSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    subject_code = serializers.CharField(source="book.subject.code", read_only=True)
    questions = serializers.SerializerMethodField(help_text="its questions on the site")
    drafts = serializers.SerializerMethodField(help_text="its questions and solutions with a draft")

    class Meta:
        model = Paper
        fields = ["id", "code", "title", "book", "book_title", "subject_code", "tier", "number", "full_marks"]
        fields += ["pass_marks", "time_text", "is_published", "is_sample", "questions", "drafts"]
        read_only_fields = ["code", "book"]

    def get_questions(self, paper) -> int:
        count = getattr(paper, "questions_count", None)
        return paper.questions.filter(is_published=True).count() if count is None else count

    def get_drafts(self, paper) -> int:
        count = getattr(paper, "drafts_count", None)
        if count is None:
            drafted = Q(state__in=DRAFT_STATES) | Q(solution__state__in=DRAFT_STATES)
            return paper.questions.filter(drafted).count()
        return count


class ContentTreeSolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Solution
        fields = ["id", "state"]
        read_only_fields = fields


class ContentTreeQuestionSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    preview = serializers.SerializerMethodField()
    solution = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ["id", "order", "label", "number", "group_label", "part_label", "is_alternative", "marks_text"]
        fields += ["is_published", "state", "preview", "solution"]
        read_only_fields = fields

    def get_preview(self, question) -> str:
        return preview(question.text_md)

    @extend_schema_field(ContentTreeSolutionSerializer(allow_null=True))
    def get_solution(self, question):
        solution = question.solution if hasattr(question, "solution") else None
        return ContentTreeSolutionSerializer(solution).data if solution else None


class ContentHeaderSerializer(serializers.Serializer):
    lines = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    allotment = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)


class ContentPaperDetailSerializer(ContentPaperSerializer):
    header_json = ContentHeaderSerializer(
        required=False, help_text="the paper's instruction lines and allotment tables"
    )
    tree = serializers.SerializerMethodField(help_text="its questions in order, each with its solution")

    class Meta(ContentPaperSerializer.Meta):
        fields = [*ContentPaperSerializer.Meta.fields, "header_json", "tree"]
        # on the site or not, the open sample or not: POST …/publish/ (staff.publish_paper), never the editor's PATCH
        read_only_fields = [*ContentPaperSerializer.Meta.read_only_fields, "is_published", "is_sample"]
        validators = []  # the one open sample per book is the publish action's to keep

    @extend_schema_field(ContentTreeQuestionSerializer(many=True))
    def get_tree(self, paper):
        rows = paper.questions.select_related("solution").order_by("order", "pk")
        return ContentTreeQuestionSerializer(rows, many=True).data


class PaperPublishSerializer(serializers.Serializer):
    is_published = serializers.BooleanField(required=False, help_text="on the site, or off it")
    is_sample = serializers.BooleanField(
        required=False, help_text="the book's open sample (its solutions need no account); the book's other one stops"
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": ["Say is_published, is_sample or both."]})
        return attrs


class PaperViewSet(
    HistoryMixin, ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Papers by code (filters subject, board, class_level, book, tier, is_published, changed, q); one with its
    questions and solutions as a tree; its QR code. Publishing or unpublishing a paper, or making it the book's open
    sample (which the book's other paper then is no longer), is publish/'s (staff.publish_paper), not the PATCH's. Its
    code is in its printed QR code: it never changes here."""

    queryset = Paper.objects.select_related("book__subject")
    filterset_class = PaperFilter
    pagination_class = ByCode
    detail_serializer = ContentPaperDetailSerializer
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history", "qr"], "content.view_paper"),
        **dict.fromkeys(["partial_update", "restore"], "content.change_paper"),
        "publish": "staff.publish_paper",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            drafted = Q(questions__state__in=DRAFT_STATES) | Q(questions__solution__state__in=DRAFT_STATES)
            queryset = queryset.annotate(
                questions_count=Count("questions", filter=Q(questions__is_published=True), distinct=True),
                drafts_count=Count("questions", filter=drafted, distinct=True),
            )
        return queryset

    def get_serializer_class(self):
        return ContentPaperSerializer if self.action == "list" else ContentPaperDetailSerializer

    @extend_schema(request=ContentPaperDetailSerializer(partial=True), responses=ContentPaperDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        paper = self.get_object()
        data = ContentPaperDetailSerializer(
            paper, data=request.data, partial=True, context=self.get_serializer_context()
        )
        data.is_valid(raise_exception=True)
        return self.change(request, paper, dict(data.validated_data), "changed in the panel")

    @extend_schema(request=PaperPublishSerializer, responses=ContentPaperDetailSerializer)
    @action(detail=True, methods=["post"], filter_backends=[])
    def publish(self, request, *args, **kwargs):
        """The paper on the site or off it (every solution behind its printed code with it), and the book's open
        sample or not: made the sample, it stops being the book's other paper's (one per book)."""
        paper = self.get_object()
        asked = PaperPublishSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.change(request, paper, dict(asked.validated_data), "published in the panel")

    def change(self, request, paper, values, reason):
        """The fields changed at once, under the paper's lock, as one audit event (published, unpublished or
        changed); the open sample moved from the book's other paper when this one becomes it."""
        with transaction.atomic():
            paper = Paper.objects.select_for_update().get(pk=paper.pk)
            changes = {field: [getattr(paper, field), value] for field, value in values.items()
                       if getattr(paper, field) != value}  # fmt: skip
            if changes.get("is_sample", [None, False])[1]:
                others = Paper.objects.select_for_update().filter(book_id=paper.book_id, is_sample=True)
                for other in others.exclude(pk=paper.pk):
                    other.is_sample = False
                    other._change_reason = f"the open sample moved to {paper.code}"
                    other.save(update_fields=["is_sample"])
                    audit.record("content.paper_changed", request=request, target=other,
                                 changes={"is_sample": [True, False]})  # fmt: skip
            for field, (_, value) in changes.items():
                setattr(paper, field, value)
            if changes:
                paper._change_reason = reason
                paper.save()
                published = changes.get("is_published")
                verb = "published" if published and published[1] else "unpublished" if published else "changed"
                audit.record(f"content.paper_{verb}", request=request, target=paper, changes=changes)
        return Response(ContentPaperDetailSerializer(paper, context=self.get_serializer_context()).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "printing",
                str,
                description="the print run the code goes into (PHY-2027-1): the address carries it, and a mistake "
                "reported from that page names it",
            )
        ],
        responses=inline_serializer(
            "PaperQr",
            {
                "url": serializers.URLField(help_text="what the code encodes: SITE_URL/s/<CODE>/ (?printing=<run>)"),
                "png": serializers.CharField(help_text="the code as a data: URL (PNG)"),
            },
        ),
    )
    @action(detail=True, filter_backends=[])
    def qr(self, request, *args, **kwargs):
        """The paper's QR code and the address it prints, which the site can redirect later, with the print run when
        one is named; refused while SITE_URL is not a public https address (a printed book cannot be corrected), as
        export_qr refuses."""
        paper = self.get_object()
        site = urlparse(settings.SITE_URL)
        if site.scheme != "https" or site.hostname in ("localhost", "127.0.0.1"):
            raise NotPublic()
        printing = request.query_params.get("printing", "").strip()
        if printing and not reports.PRINTING.fullmatch(printing):
            raise serializers.ValidationError(
                {"printing": ["A print run's label: letters, digits and hyphens, PHY-2027-1."]}
            )
        url = paper.landing_url() + (f"?printing={printing}" if printing else "")
        png = base64.b64encode(paper.qr_image("png", url=url)).decode()
        return Response({"url": url, "png": f"data:image/png;base64,{png}"})


# ---- Questions and solutions: the live text, its draft and its review ----


class ContentOpenReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewTask
        fields = ["id", "state", "stage", "assignee", "submitted_by", "created"]
        read_only_fields = fields


def open_review(obj):
    task = review.open_tasks(obj).first()
    return ContentOpenReviewSerializer(task).data if task else None


class QuestionFilter(django_filters.FilterSet):
    book = django_filters.NumberFilter(field_name="paper__book")
    subject = django_filters.CharFilter(field_name="paper__book__subject__code", help_text="its code: PHY")
    changed = django_filters.BooleanFilter(method="filter_changed", help_text="true: a draft waits")
    q = django_filters.CharFilter(field_name="label", lookup_expr="icontains", help_text="its label")

    class Meta:
        model = Question
        fields = ["paper", "book", "subject", "state", "is_published"]

    def filter_changed(self, queryset, name, value):
        return queryset.filter(state__in=DRAFT_STATES) if value else queryset.exclude(state__in=DRAFT_STATES)


class ContentQuestionSerializer(serializers.ModelSerializer):
    paper_code = serializers.CharField(source="paper.code", read_only=True)
    number = serializers.CharField(read_only=True)
    preview = serializers.SerializerMethodField()
    solution = serializers.SerializerMethodField(help_text="its solution's id, if it has one")

    class Meta:
        model = Question
        fields = ["id", "paper", "paper_code", "order", "label", "number", "marks_text", "is_published", "state"]
        fields += ["preview", "solution"]
        read_only_fields = fields

    def get_preview(self, question) -> str:
        return preview(question.text_md)

    def get_solution(self, question) -> int | None:
        return question.solution.pk if hasattr(question, "solution") else None


class ContentQuestionDetailSerializer(ContentQuestionSerializer):
    tags = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField(help_text="the review its draft waits in, if any")

    class Meta(ContentQuestionSerializer.Meta):
        fields = [
            *ContentQuestionSerializer.Meta.fields,
            "text_md",
            "table_md",
            "options_json",
            "group_label",
            "part_label",
        ]
        fields += ["is_alternative", "tags", "draft", "draft_by", "published_at", "published_by", "review"]
        read_only_fields = fields

    def get_tags(self, question) -> list[str]:
        return sorted(question.tags.names())

    def get_review(self, question) -> dict | None:
        return open_review(question)


class QuestionUpdateSerializer(serializers.Serializer):
    """What the panel changes: the text and what the site shows of it go to the draft (DRAFTED); the order, the
    label and the tags change at once (the import keys on the label: a renamed one is a new question there)."""

    text_md = serializers.CharField(max_length=10_000, required=False)
    table_md = serializers.CharField(max_length=10_000, required=False, allow_blank=True)
    options_json = serializers.ListField(
        child=serializers.CharField(max_length=500), max_length=10, required=False, help_text="the options, in order"
    )
    marks_text = serializers.CharField(max_length=40, required=False, allow_blank=True)
    group_label = serializers.CharField(max_length=300, required=False, allow_blank=True)
    part_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    is_alternative = serializers.BooleanField(required=False)
    order = serializers.IntegerField(min_value=1, max_value=32_767, required=False)
    label = serializers.CharField(max_length=20, required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=100), max_length=20, required=False)


class SolutionFilter(django_filters.FilterSet):
    paper = django_filters.NumberFilter(field_name="question__paper")
    book = django_filters.NumberFilter(field_name="question__paper__book")
    subject = django_filters.CharFilter(field_name="question__paper__book__subject__code", help_text="its code: PHY")
    changed = django_filters.BooleanFilter(method="filter_changed", help_text="true: a draft waits")

    class Meta:
        model = Solution
        fields = ["paper", "book", "subject", "state"]

    def filter_changed(self, queryset, name, value):
        return queryset.filter(state__in=DRAFT_STATES) if value else queryset.exclude(state__in=DRAFT_STATES)


class ContentSolutionSerializer(serializers.ModelSerializer):
    question_label = serializers.CharField(source="question.label", read_only=True)
    paper = serializers.IntegerField(source="question.paper_id", read_only=True)
    paper_code = serializers.CharField(source="question.paper.code", read_only=True)
    preview = serializers.SerializerMethodField()

    class Meta:
        model = Solution
        fields = ["id", "question", "question_label", "paper", "paper_code", "state", "preview"]
        read_only_fields = fields

    def get_preview(self, solution) -> str:
        return preview(solution.draft.get("body_md", solution.body_md))


class ContentSolutionDetailSerializer(ContentSolutionSerializer):
    review = serializers.SerializerMethodField(help_text="the review its draft waits in, if any")
    question_text = serializers.CharField(source="question.text_md", read_only=True)
    marks_text = serializers.CharField(source="question.marks_text", read_only=True)

    class Meta(ContentSolutionSerializer.Meta):
        fields = [*ContentSolutionSerializer.Meta.fields, "question_text", "marks_text", "body_md", "draft", "draft_by"]
        fields += ["published_at", "published_by", "review"]
        read_only_fields = fields

    def get_review(self, solution) -> dict | None:
        return open_review(solution)


class SolutionUpdateSerializer(serializers.Serializer):
    body_md = serializers.CharField(max_length=20_000, help_text="Markdown with $…$ maths: into the draft")


class ContentSubmitSerializer(serializers.Serializer):
    assignee = serializers.IntegerField(required=False, allow_null=True, help_text="a reviewer of the subject")


class DraftedViewSet(
    HistoryMixin, ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """A question's or a solution's live text and its draft: PATCH writes the draft (the structural check of
    content.latex first), submit/ sends it to a reviewer, discard/ drops it, rollback/ undoes the last publish
    (staff.publish_paper); history/ and restore (into the draft)."""

    pagination_class = Oldest
    model_name = ""

    @classmethod
    def perms(cls, name):
        return {
            **dict.fromkeys(["list", "retrieve", "history"], f"content.view_{name}"),
            **dict.fromkeys(["partial_update", "submit", "discard", "restore"], f"content.change_{name}"),
            "rollback": "staff.publish_paper",
        }

    def detail_response(self, obj):
        obj = type(obj).objects.select_related(*review.related(obj)).get(pk=obj.pk)
        return Response(self.detail_serializer(obj, context=self.get_serializer_context()).data)

    @extend_schema(request=ContentSubmitSerializer, responses={201: ContentOpenReviewSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request, *args, **kwargs):
        """The draft to a second person: a review task (201) and an inbox item for the subject's reviewers."""
        obj, user = self.get_object(), self.human()
        asked = ContentSubmitSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        assignee = None
        if (pk := asked.validated_data.get("assignee")) is not None:
            from accounts.models import User

            assignee = User.objects.filter(pk=pk, is_active=True, is_staff=True).first()
            if assignee is None:
                raise serializers.ValidationError({"assignee": ["A reviewer of this subject other than yourself."]})
        task = review.submit(obj, user, request, assignee)
        return Response(ContentOpenReviewSerializer(task).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def discard(self, request, *args, **kwargs):
        """The draft dropped (and its review withdrawn): the live text stays."""
        return self.detail_response(review.discard_draft(self.get_object(), self.human(), request))

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def rollback(self, request, *args, **kwargs):
        """The last publish undone: the text before it live again, the text it published back in the draft."""
        return self.detail_response(review.rollback(self.get_object(), self.human(), request))


class QuestionViewSet(DraftedViewSet):
    queryset = Question.objects.select_related("paper__book__subject", "solution")
    filterset_class = QuestionFilter
    detail_serializer = ContentQuestionDetailSerializer
    permissions = DraftedViewSet.perms("question")

    def get_serializer_class(self):
        return ContentQuestionSerializer if self.action == "list" else ContentQuestionDetailSerializer

    @extend_schema(request=QuestionUpdateSerializer, responses=ContentQuestionDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        question, user = self.get_object(), self.human()
        asked = QuestionUpdateSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        values = dict(asked.validated_data)
        drafted = {field: values.pop(field) for field in Question.DRAFTED if field in values}
        with transaction.atomic():
            question = review.locked(question)
            tags = values.pop("tags", None)
            changes = review.changed_fields(question, values)
            if tags is not None and set(tags) != set(question.tags.names()):
                changes["tags"] = [sorted(question.tags.names()), sorted(tags)]
                question.tags.set(tags)
            for field, value in changes.items():
                if field != "tags":
                    changes[field] = [getattr(question, field), value]
                    setattr(question, field, value)
            if set(changes) - {"tags"}:
                if (
                    "label" in changes
                    and question.paper.questions.filter(label=question.label).exclude(pk=question.pk).exists()
                ):
                    raise serializers.ValidationError({"label": ["Another question of this paper has this label."]})
                question._change_reason = "changed in the panel"
                question.save(update_fields=sorted(set(changes) - {"tags"}))
            if changes:
                audit.record("content.question_changed", request=request, target=review.target(question),
                             changes=changes)  # fmt: skip
            if drafted:
                question = review.save_draft(question, drafted, user, request)
        return self.detail_response(question)


class SolutionViewSet(DraftedViewSet):
    queryset = Solution.objects.select_related("question__paper__book__subject")
    filterset_class = SolutionFilter
    detail_serializer = ContentSolutionDetailSerializer
    permissions = DraftedViewSet.perms("solution")

    def get_serializer_class(self):
        return ContentSolutionSerializer if self.action == "list" else ContentSolutionDetailSerializer

    @extend_schema(request=SolutionUpdateSerializer, responses=ContentSolutionDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        solution, user = self.get_object(), self.human()
        asked = SolutionUpdateSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.detail_response(review.save_draft(solution, dict(asked.validated_data), user, request))


# ---- Reviews ----


class ReviewFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(field_name="subject__code", help_text="its code: PHY")
    mine = django_filters.BooleanFilter(
        method="filter_mine", help_text="true: waiting for me (open, for me or nobody, not my own edit)"
    )
    submitted = django_filters.BooleanFilter(method="filter_submitted", help_text="true: the ones I submitted")
    open = django_filters.BooleanFilter(method="filter_open", help_text="true: in progress, or approved and not live")

    class Meta:
        model = ReviewTask
        fields = ["subject", "paper", "state", "stage"]

    def filter_mine(self, queryset, name, value):
        user = self.request.user
        if not value:
            return queryset
        queryset = queryset.filter(ReviewTask.OPEN).filter(Q(assignee=None) | Q(assignee=user))
        return queryset.exclude(submitted_by=user).exclude(edited_by=user)

    def filter_submitted(self, queryset, name, value):
        return queryset.filter(submitted_by=self.request.user) if value else queryset

    def filter_open(self, queryset, name, value):
        return queryset.filter(ReviewTask.OPEN) if value else queryset.exclude(ReviewTask.OPEN)


class ContentReviewSerializer(serializers.ModelSerializer):
    kind = serializers.CharField(source="target_type.model", read_only=True, help_text="question or solution")
    subject = serializers.CharField(source="subject.code", read_only=True, allow_null=True)
    fields_changed = serializers.SerializerMethodField(help_text="the fields its draft changes")
    yours = serializers.SerializerMethodField(help_text="you edited or submitted it: another reviewer decides")

    class Meta:
        model = ReviewTask
        fields = ["id", "label", "kind", "target_id", "subject", "paper", "stage", "state", "assignee"]
        fields += ["submitted_by", "edited_by", "approved_by", "approved_at", "published_by", "published_at"]
        fields += ["rolled_back_by", "rolled_back_at", "created", "fields_changed", "yours"]
        read_only_fields = fields

    def get_fields_changed(self, task) -> list[str]:
        return sorted(task.draft)

    def get_yours(self, task) -> bool:
        user = self.context["request"].user
        return getattr(user, "pk", None) in (task.submitted_by_id, task.edited_by_id)


class ContentCommentSerializer(serializers.Serializer):
    author = serializers.IntegerField(allow_null=True)
    text = serializers.CharField()
    at = serializers.DateTimeField()
    field = serializers.CharField(allow_blank=True)


class ContentReviewDetailSerializer(ContentReviewSerializer):
    comments = ContentCommentSerializer(many=True, read_only=True)
    changes = serializers.SerializerMethodField(
        help_text="its draft against the live text now, field by field; once published, the text it replaced against it"
    )
    question = serializers.SerializerMethodField(help_text="the question's id (for a solution: its question's)")

    class Meta(ContentReviewSerializer.Meta):
        fields = [*ContentReviewSerializer.Meta.fields, "draft", "previous", "comments", "changes", "question"]
        read_only_fields = fields

    @extend_schema_field(ContentChangeSerializer(many=True))
    def get_changes(self, task):
        if task.published_at:  # the live text is the draft now: what the publish changed instead
            return [review.change(field, task.previous.get(field, ""), value) for field, value in task.draft.items()]
        target = task.target
        return review.draft_changes(target, task.draft) if target is not None else []

    def get_question(self, task) -> int | None:
        target = task.target
        if target is None:
            return None
        return target.pk if isinstance(target, Question) else target.question_id


class ContentDecisionSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class NeedsChangesSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000, help_text="what to change")
    field = serializers.CharField(max_length=40, required=False, allow_blank=True, help_text="the field it is about")


class ReviewViewSet(ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The review queue, oldest first (filters subject, paper, state, stage, mine, submitted, open): `mine` is
    "waiting for me". A reviewer (staff.publish_paper, in their subjects) approves, asks for changes (with a comment)
    or publishes (approving on the way); never their own edit (403 `own_edit`)."""

    queryset = ReviewTask.objects.select_related("subject", "target_type")
    filterset_class = ReviewFilter
    pagination_class = Oldest
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "content.view_reviewtask"),
        **dict.fromkeys(["approve", "needs_changes", "publish"], "staff.publish_paper"),
    }

    def get_serializer_class(self):
        return ContentReviewSerializer if self.action == "list" else ContentReviewDetailSerializer

    def answer(self, task):
        task = ReviewTask.objects.select_related("subject", "target_type").get(pk=task.pk)
        return Response(ContentReviewDetailSerializer(task, context=self.get_serializer_context()).data)

    @extend_schema(request=ContentDecisionSerializer, responses=ContentReviewDetailSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        asked = ContentDecisionSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.answer(
            review.approve(self.get_object(), self.human(), request, asked.validated_data.get("comment", ""))
        )

    @extend_schema(request=NeedsChangesSerializer, responses=ContentReviewDetailSerializer)
    @action(detail=True, methods=["post"], url_path="needs-changes")
    def needs_changes(self, request, *args, **kwargs):
        asked = NeedsChangesSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        return self.answer(
            review.needs_changes(self.get_object(), self.human(), data["comment"], request, data.get("field", ""))
        )

    @extend_schema(request=ContentDecisionSerializer, responses=ContentReviewDetailSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, *args, **kwargs):
        asked = ContentDecisionSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.answer(
            review.publish(self.get_object(), self.human(), request, asked.validated_data.get("comment", ""))
        )


# ---- Reported mistakes and the errata ----


class ReportFilter(django_filters.FilterSet):
    state = django_filters.ChoiceFilter(
        choices=ErrorReport.State.choices, method="filter_state", help_text="none: the open ones (reported, confirmed)"
    )
    subject = django_filters.CharFilter(field_name="subject__code", help_text="its code: PHY")
    printing = django_filters.CharFilter(field_name="printing", lookup_expr="iexact")
    teacher = django_filters.BooleanFilter(field_name="teacher_verified", help_text="true: from verified teachers")
    book = django_filters.NumberFilter(field_name="paper__book")

    class Meta:
        model = ErrorReport
        fields = ["state", "category", "subject", "printing", "teacher", "paper", "book"]

    def filter_state(self, queryset, name, value):
        return queryset.filter(state=value)

    def filter_queryset(self, queryset):
        data = self.form.cleaned_data if self.is_bound and self.form.is_valid() else {}
        if not data.get("state"):
            queryset = queryset.filter(state__in=ErrorReport.OPEN)
        return super().filter_queryset(queryset)


class ContentReportSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField(help_text="solution, question, quiz_item or clip")
    subject = serializers.CharField(source="subject.code", read_only=True, allow_null=True)
    paper_code = serializers.CharField(source="paper.code", read_only=True, allow_null=True)
    question_label = serializers.CharField(source="question.label", read_only=True, allow_null=True)
    email = serializers.SerializerMethodField(help_text="masked; only to tell them of the fix")
    can_tell = serializers.SerializerMethodField(help_text="fixed, an address left, not told yet")

    class Meta:
        model = ErrorReport
        fields = ["id", "kind", "target_id", "subject", "paper", "paper_code", "question", "question_label", "step"]
        fields += ["printing", "category", "note", "email", "reporter", "teacher_verified", "state", "fixed_in"]
        fields += ["fixed_at", "resolved_at", "staff_note", "reporter_told_at", "public", "created", "can_tell"]
        read_only_fields = fields

    def get_kind(self, report) -> str:
        return reports.kind_of(report)

    def get_email(self, report) -> str:
        return mask_email(report.email)

    def get_can_tell(self, report) -> bool:
        return bool(report.email) and report.state in ErrorReport.FIXED and not report.reporter_told_at


class ContentLinkedSerializer(serializers.Serializer):
    paper_id = serializers.IntegerField(allow_null=True)
    question_id = serializers.IntegerField(allow_null=True)
    solution_id = serializers.IntegerField(allow_null=True)
    question_text = serializers.CharField(required=False)
    solution_text = serializers.CharField(required=False)
    solution_state = serializers.CharField(required=False, allow_null=True)
    title = serializers.CharField(required=False, help_text="a quiz item's text, a clip's title")


class ContentReportDetailSerializer(ContentReportSerializer):
    linked = serializers.SerializerMethodField(help_text="what it is about, as the site shows it now")

    class Meta(ContentReportSerializer.Meta):
        fields = [*ContentReportSerializer.Meta.fields, "handled_by", "linked"]
        read_only_fields = fields

    @extend_schema_field(ContentLinkedSerializer)
    def get_linked(self, report):
        return reports.linked(report)


class ContentReportUpdateSerializer(serializers.Serializer):
    staff_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    public = serializers.BooleanField(required=False, help_text="on the errata of its book and printing")
    printing = serializers.RegexField(reports.PRINTING, max_length=40, required=False, allow_blank=True)
    step = serializers.IntegerField(min_value=1, max_value=50, required=False, allow_null=True)


class ContentTransitionSerializer(serializers.Serializer):
    staff_note = serializers.CharField(max_length=2000, required=False, allow_blank=True, help_text="why (a rejection)")
    fixed_in = serializers.CharField(
        max_length=40, required=False, allow_blank=True, help_text="the printing (fix-in-printing)"
    )


def transition_action(verb):
    """POST reports/{id}/<verb>/: one step of the triage (content.reports.TRANSITIONS)."""

    def step(self, request, *args, **kwargs):
        asked = ContentTransitionSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        report = reports.transition(
            self.get_object(), verb, self.human(), request, data.get("staff_note"), data.get("fixed_in", "")
        )
        return self.answer(report)

    step.__name__ = step.__qualname__ = verb.replace("-", "_")  # the router routes to the method by this name
    step.__doc__ = f"The triage's step `{verb}` (content.reports.TRANSITIONS)."
    routed = action(detail=True, methods=["post"], url_path=verb, url_name=verb)(step)
    return extend_schema(request=ContentTransitionSerializer, responses=ContentReportDetailSerializer)(routed)


class ReportViewSet(ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The triage queue, oldest first; the open ones unless `state` says (filters state, category, subject, printing,
    teacher, paper, book); spam never shows. Each step and the reporter told are staff.triage_report's."""

    queryset = ErrorReport.objects.filter(spam=False).select_related("subject", "paper", "question", "target_type")
    filterset_class = ReportFilter
    pagination_class = Oldest
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "content.view_errorreport"),
        **dict.fromkeys(
            ["partial_update", "tell", "confirm", "reject", "fix_online", "fix_in_printing", "reopen"],
            "staff.triage_report",
        ),
    }

    def get_serializer_class(self):
        return ContentReportSerializer if self.action == "list" else ContentReportDetailSerializer

    def filter_queryset(self, queryset):  # the list's filters (the open ones by default) never hide a report acted on
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    def answer(self, report):
        report = ErrorReport.objects.select_related("subject", "paper", "question", "target_type").get(pk=report.pk)
        return Response(ContentReportDetailSerializer(report, context=self.get_serializer_context()).data)

    @extend_schema(request=ContentReportUpdateSerializer, responses=ContentReportDetailSerializer)
    def partial_update(self, request, *args, **kwargs):
        report = self.get_object()
        asked = ContentReportUpdateSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        with transaction.atomic():
            report = reports.locked(report)
            changes = review.changed_fields(report, dict(asked.validated_data))
            changes = {field: [getattr(report, field), value] for field, value in changes.items()}
            for field, (_, value) in changes.items():
                setattr(report, field, value)
            if changes:
                report.save()
                shown = {field: value for field, value in changes.items() if field != "staff_note"}
                audit.record("content.report_changed", request=request, target=report, changes=shown,
                             details={"staff_note": "staff_note" in changes})  # fmt: skip
        return self.answer(report)

    confirm = transition_action("confirm")
    reject = transition_action("reject")
    fix_online = transition_action("fix-online")
    fix_in_printing = transition_action("fix-in-printing")
    reopen = transition_action("reopen")

    @extend_schema(request=None, responses=ContentReportDetailSerializer)
    @action(detail=True, methods=["post"])
    def tell(self, request, *args, **kwargs):
        """The reporter emailed that the fix is published: once, fixed, if they left an address (then cleared)."""
        return self.answer(reports.tell(self.get_object(), self.human(), request))


class ErrataFilter(django_filters.FilterSet):
    book = django_filters.CharFilter(method="filter_book", help_text="its slug or id")
    printing = django_filters.CharFilter(field_name="printing", lookup_expr="iexact")

    class Meta:
        model = ErrorReport
        fields = ["book", "printing", "public"]

    def filter_book(self, queryset, name, value):
        return queryset.filter(paper__book=value) if value.isdigit() else queryset.filter(paper__book__slug=value)


class ContentErratumSerializer(serializers.ModelSerializer):
    paper_code = serializers.CharField(source="paper.code", read_only=True, allow_null=True)
    question_label = serializers.CharField(source="question.label", read_only=True, allow_null=True)
    book = serializers.IntegerField(source="paper.book_id", read_only=True, allow_null=True)

    class Meta:
        model = ErrorReport
        fields = ["id", "book", "paper_code", "question_label", "step", "category", "printing", "state", "fixed_in"]
        fields += ["fixed_at", "public", "created"]
        read_only_fields = fields


class ErrataView(ContentView, generics.ListAPIView):
    """The errata per book and printing: confirmed and fixed mistakes (filters book, printing, public); those marked
    `public` are the website's (GET /api/v1/errata/?book=)."""

    serializer_class = ContentErratumSerializer
    filterset_class = ErrataFilter
    permissions = {"GET": "content.view_errorreport"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ErrorReport.objects.none()
        return reports.errata(scoped(ErrorReport.objects.all(), self.request.user, "content.view_errorreport"))


# ---- Imports from the books repository (staff jobs: content.imports) ----


def import_jobs(user):
    """The imports `user` may see: those of their subjects (a person narrowed to some), newest first."""
    jobs = Job.objects.filter(kind=Job.Kind.CONTENT_IMPORT)
    if user.is_superuser or getattr(user, "api_key", None) is not None:
        return jobs
    codes = scope_values(user, "content.view_paper", SUBJECT)
    if codes is not None:
        names = [name for name, meta in papers_parser.SUBJECTS.items() if meta["code"] in codes]
        jobs = jobs.filter(params__subject__in=names)
    return jobs


class ImportsView(ContentView, generics.ListAPIView):
    """The imports, newest first: dry runs and applies (each a staff job; POST /api/v1/staff/jobs/ with kind
    content_import starts one, staff.import_content), within the person's subjects."""

    serializer_class = JobSerializer
    permissions = {"GET": "content.view_paper"}
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Job.objects.none()
        return import_jobs(self.request.user)


# ---- Legal deposits ----


class DepositFilter(django_filters.FilterSet):
    class Meta:
        model = LegalDeposit
        fields = ["book", "library"]


class LegalDepositSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    edition = serializers.CharField(max_length=60, required=False, help_text="the book's edition when left out")
    proof_file = serializers.FileField(
        write_only=True, required=False, help_text=f"a scan: PDF or a picture, {PROOF_MB} MB at most"
    )
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = LegalDeposit
        fields = ["id", "book", "book_title", "edition", "library", "sent_on", "proof", "proof_file", "has_file"]
        fields += ["erp_delivery_note", "created_by", "created"]
        read_only_fields = ["created_by", "created"]
        validators = []  # one per book, edition and library: validate() says so in words (the edition may be left out)

    def get_has_file(self, deposit) -> bool:
        return bool(deposit.proof_file)

    def validate_book(self, book):
        if not in_scope(Book, book.pk, self.context["request"].user, "content.add_legaldeposit"):
            raise serializers.ValidationError("Not one of your subjects' books.")
        return book

    def validate_sent_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Not a day to come: the day it went.")
        return value

    def validate_proof_file(self, file):
        if file.size > PROOF_MB * 1024 * 1024 or getattr(file, "content_type", "") not in PROOF_TYPES:
            raise serializers.ValidationError(f"A PDF, JPEG, PNG or WebP of {PROOF_MB} MB at most.")
        return file

    def validate(self, attrs):
        attrs["edition"] = (attrs.get("edition") or attrs["book"].edition).strip()
        if not attrs["edition"]:
            raise serializers.ValidationError({"edition": ["Give the edition: the book has none."]})
        if LegalDeposit.objects.filter(book=attrs["book"], edition=attrs["edition"], library=attrs["library"]).exists():
            raise serializers.ValidationError({"library": ["This library has this edition already."]})
        return attrs


class MissingDepositSerializer(serializers.Serializer):
    book = serializers.IntegerField()
    title = serializers.CharField()
    edition = serializers.CharField()
    subject = serializers.CharField()
    published_on = serializers.DateField()
    due_on = serializers.DateField()
    overdue = serializers.BooleanField()
    missing = serializers.ListField(child=serializers.ChoiceField(choices=LegalDeposit.Library.choices))


def missing_deposits(user, perm):
    """The published books in reach whose edition some of the four libraries have not received, the latest first."""
    books = list(scoped(Book.objects.filter(published_on__isnull=False), user, perm).select_related("subject")
                 .order_by("-published_on", "pk"))  # fmt: skip
    missing, today = LegalDeposit.missing(books), timezone.localdate()
    return [
        {
            "book": book.pk,
            "title": book.title,
            "edition": book.edition,
            "subject": book.subject.code,
            "published_on": book.published_on,
            "due_on": book.deposit_due_on,
            "overdue": book.deposit_due_on < today,
            "missing": missing[book.pk],
        }
        for book in books
        if missing[book.pk]
    ]


class LegalDepositViewSet(ContentView, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                          viewsets.GenericViewSet):  # fmt: skip
    """The deposits made (filters book, library), one recorded (content.add_legaldeposit: JSON, or multipart with the
    proof's scan), its scan, and the published books still missing some of the four libraries."""

    queryset = LegalDeposit.objects.select_related("book")
    serializer_class = LegalDepositSerializer
    filterset_class = DepositFilter
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permissions = {
        **dict.fromkeys(["list", "retrieve", "proof", "missing"], "content.view_legaldeposit"),
        "create": "content.add_legaldeposit",
    }

    def perform_create(self, serializer):
        with transaction.atomic():
            try:
                deposit = serializer.save(created_by=self.human())
            except IntegrityError as error:  # the same library at the same moment
                raise serializers.ValidationError({"library": ["This library has this edition already."]}) from error
            book = deposit.book
            deposit_item(book, LegalDeposit.missing([book])[book.pk])
            audit.record(
                "content.legal_deposit_recorded",
                request=self.request,
                target=book,
                details={"deposit": deposit.pk, "library": deposit.library, "edition": deposit.edition},
            )

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 302: None})
    @action(detail=True, filter_backends=[])
    def proof(self, request, *args, **kwargs):
        """The proof's scan: the file, or 302 to the private bucket's own link (signed for 5 minutes)."""
        deposit = self.get_object()
        if not deposit.proof_file:
            raise exceptions.NotFound("No scan was kept with this deposit.")
        storage = deposit.proof_file.storage
        if not isinstance(storage, FileSystemStorage):
            return HttpResponseRedirect(storage.url(deposit.proof_file.name))
        name = deposit.proof_file.name.rsplit("/", 1)[-1]
        return FileResponse(storage.open(deposit.proof_file.name, "rb"), as_attachment=True, filename=name)

    @extend_schema(responses=MissingDepositSerializer(many=True))
    @action(detail=False, pagination_class=None, filter_backends=[])
    def missing(self, request, *args, **kwargs):
        return Response(
            MissingDepositSerializer(missing_deposits(request.user, "content.view_legaldeposit"), many=True).data
        )


# ---- The module's home ----


class ContentSummarySerializer(serializers.Serializer):
    reports_open = inline_serializer(
        "ReportsOpen",
        {"total": serializers.IntegerField(), "by_category": serializers.DictField(child=serializers.IntegerField())},
    )
    reviews_waiting = serializers.IntegerField(allow_null=True, help_text="open reviews; null: not yours to see")
    reviews_mine = serializers.IntegerField(allow_null=True, help_text="waiting for you")
    drafts = serializers.IntegerField(allow_null=True, help_text="questions and solutions changed since publish")
    legal_deposits_missing = MissingDepositSerializer(many=True, allow_null=True)
    last_import = JobSerializer(allow_null=True)


class SummaryView(ContentView, generics.GenericAPIView):
    """The content module's home: reports open by category, reviews waiting (and for me), drafts changed since
    publish, books missing legal deposits, the last import; each part null for whoever may not see it."""

    serializer_class = ContentSummarySerializer
    permissions = {"GET": "content.view_errorreport"}
    pagination_class = None
    filter_backends = []

    def get(self, request, *args, **kwargs):
        user = request.user
        reported = scoped(ErrorReport.objects.filter(spam=False, state__in=ErrorReport.OPEN), user,
                          "content.view_errorreport")  # fmt: skip
        by_category = dict(reported.values_list("category").annotate(n=Count("pk")).order_by())
        body = {
            "reports_open": {"total": sum(by_category.values()), "by_category": by_category},
            "reviews_waiting": None,
            "reviews_mine": None,
            "drafts": None,
            "legal_deposits_missing": None,
            "last_import": None,
        }
        if user.has_perm("content.view_reviewtask"):
            waiting = scoped(ReviewTask.objects.filter(ReviewTask.OPEN), user, "content.view_reviewtask")
            body["reviews_waiting"] = waiting.count()
            if user.has_perm("staff.publish_paper") and getattr(user, "pk", None):
                mine = waiting.filter(Q(assignee=None) | Q(assignee=user)).exclude(submitted_by=user)
                body["reviews_mine"] = mine.exclude(edited_by=user).count()
        if user.has_perm("content.view_solution") and user.has_perm("content.view_question"):
            questions = scoped(Question.objects.filter(state__in=DRAFT_STATES), user, "content.view_question")
            solutions = scoped(Solution.objects.filter(state__in=DRAFT_STATES), user, "content.view_solution")
            body["drafts"] = questions.count() + solutions.count()
        if user.has_perm("content.view_legaldeposit"):
            body["legal_deposits_missing"] = missing_deposits(user, "content.view_legaldeposit")
        if user.has_perm("content.view_paper"):
            body["last_import"] = import_jobs(user).first()
        return Response(ContentSummarySerializer(body, context={"request": request}).data)


router = SimpleRouter()
router.register("books", BookViewSet, basename="content-book")
router.register("papers", PaperViewSet, basename="content-paper")
router.register("questions", QuestionViewSet, basename="content-question")
router.register("solutions", SolutionViewSet, basename="content-solution")
router.register("reviews", ReviewViewSet, basename="content-review")
router.register("reports", ReportViewSet, basename="content-report")
router.register("legal-deposits", LegalDepositViewSet, basename="content-legal-deposit")
urlpatterns = [  # under /api/v1/staff/content/ (staff/urls.py)
    path("summary/", SummaryView.as_view(), name="content-summary"),
    path("errata/", ErrataView.as_view(), name="content-errata"),
    path("imports/", ImportsView.as_view(), name="content-imports"),
    *router.urls,
]
