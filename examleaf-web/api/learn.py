"""REST API v1 of the revision course (learn/; API.md "Revision course"). Chapters are public; a clip's links, the
quiz, flash cards, progress, the plan, book codes and settings need a signed-in student with a confirmed address."""

from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import exceptions, generics, mixins, permissions, serializers, status, throttling, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from content.templatetags.markdown import render
from learn import plan, services
from learn.models import (
    CardReview,
    Chapter,
    Clip,
    Device,
    Entitlement,
    FlashCard,
    Learner,
    Progress,
    QuizAttempt,
    QuizItem,
    Revision,
)
from learn.views import playback

from .views import VerifiedEmail

STUDENT = [permissions.IsAuthenticated, VerifiedEmail]
LOCKED = "Unlock this subject with the code printed in your book."
READY = Q(revision__clips__processing=Clip.Processing.READY)


@extend_schema_field(OpenApiTypes.STR)
class Html(serializers.Field):
    """A Markdown field rendered by the site ($…$ maths left for KaTeX)."""

    def __init__(self, source, **kwargs):
        super().__init__(source=source, read_only=True, **kwargs)

    def to_representation(self, value):
        return render(value or "")


class ChapterSerializer(serializers.ModelSerializer):
    must_do_html = Html("must_do")
    clips = serializers.IntegerField(source="clip_count", read_only=True, help_text="processed clips")
    minutes = serializers.SerializerMethodField()
    entitled = serializers.SerializerMethodField(help_text="every clip, card and quiz item is open to the user")
    free_cards = serializers.SerializerMethodField(help_text="its flash cards are a free preview")
    progress = serializers.SerializerMethodField(help_text="% of its clips watched to the end; null signed out")

    class Meta:
        model = Chapter
        fields = ["id", "subject", "number", "title", "weight", "frequency", "must_do", "must_do_html", "clips"]
        fields += ["minutes", "entitled", "free_cards", "progress"]

    def get_minutes(self, chapter) -> int:
        return round((chapter.seconds or 0) / 60)

    def get_entitled(self, chapter) -> bool:
        return chapter.subject_id in self.context["subjects"]

    def get_free_cards(self, chapter) -> bool:
        return services.is_free_chapter(chapter)

    def get_progress(self, chapter) -> int | None:
        if self.context["done"] is None:
            return None
        return round(100 * self.context["done"].get(chapter.pk, 0) / chapter.clip_count) if chapter.clip_count else 0


class ClipRowSerializer(serializers.ModelSerializer):
    free = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField(help_text="neither free nor entitled: the clip answers 403")
    completed = serializers.SerializerMethodField()

    class Meta:
        model = Clip
        fields = ["id", "order", "title", "kind", "duration", "free", "locked", "completed"]

    def get_free(self, clip) -> bool:
        return clip.free

    def get_locked(self, clip) -> bool:
        return not (clip.free or clip.revision.chapter.subject_id in self.context["subjects"])

    def get_completed(self, clip) -> bool:
        return clip.pk in self.context["watched"]


class RevisionSerializer(serializers.ModelSerializer):
    clips = serializers.SerializerMethodField()

    class Meta:
        model = Revision
        fields = ["title", "target_minutes", "clips"]

    @extend_schema_field(ClipRowSerializer(many=True))
    def get_clips(self, revision):
        clips = list(revision.clips.order_by("order", "pk").select_related("revision"))
        for clip in clips:
            clip.free = services.is_free_clip(clip)
        ready = [clip for clip in clips if clip.processing == Clip.Processing.READY]
        return ClipRowSerializer(ready, many=True, context=self.context).data


class ChapterDetailSerializer(ChapterSerializer):
    revision = RevisionSerializer(read_only=True)
    flash_cards = serializers.IntegerField(source="flash_cards.count", read_only=True)
    quiz_items = serializers.IntegerField(source="quiz_items.count", read_only=True)

    class Meta(ChapterSerializer.Meta):
        fields = [*ChapterSerializer.Meta.fields, "revision", "flash_cards", "quiz_items"]


def course_context(request):
    """What the chapter and clip answers need about the user: subjects open, clips watched, chapters' progress."""
    user = request.user
    signed_in = user.is_authenticated
    progress = Progress.objects.filter(user=user, completed=True) if signed_in else Progress.objects.none()
    done = progress.values("clip__revision__chapter").annotate(n=Count("pk"))
    return {
        "subjects": services.entitled_subjects(user),
        "watched": set(progress.values_list("clip_id", flat=True)),
        "done": {row["clip__revision__chapter"]: row["n"] for row in done} if signed_in else None,
    }


class ChapterViewSet(viewsets.ReadOnlyModelViewSet):
    """Chapters with a published revision, `?subject=<id>`; one chapter with its revision's clips."""

    permission_classes = [permissions.AllowAny]
    queryset = (
        Chapter.objects.filter(revision__status=Revision.Status.PUBLISHED)
        .select_related("revision", "subject")
        .annotate(
            clip_count=Count("revision__clips", filter=READY), seconds=Sum("revision__clips__duration", filter=READY)
        )
    )
    filterset_fields = ["subject"]
    ordering_fields = ["number", "weight", "frequency"]
    ordering = ["subject", "number"]

    def get_serializer_class(self):
        return ChapterDetailSerializer if self.action == "retrieve" else ChapterSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context if getattr(self, "swagger_fake_view", False) else {**context, **course_context(self.request)}


class ClipSerializer(serializers.ModelSerializer):
    chapter = serializers.IntegerField(source="revision.chapter_id")
    notes_html = Html("notes")
    questions = serializers.SerializerMethodField(help_text="the Board-style questions it prepares for")
    hls_url = serializers.URLField(help_text="HLS master playlist; works for 10 minutes (expires_at)")
    poster_url = serializers.URLField()
    expires_at = serializers.DateTimeField(allow_null=True)
    seconds_watched = serializers.IntegerField()
    completed = serializers.BooleanField()

    class Meta:
        model = Clip
        fields = ["id", "chapter", "order", "title", "kind", "duration", "notes", "notes_html", "questions"]
        fields += ["hls_url", "poster_url", "expires_at", "seconds_watched", "completed"]

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
    def get_questions(self, clip):
        questions = clip.questions.select_related("paper")
        return [{"paper": q.paper.code, "label": q.label, "web_url": q.paper.landing_url()} for q in questions]


class ProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Progress
        fields = ["seconds_watched", "completed"]


class ClipViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """A processed clip of a published revision, with its links (403 while it is locked); its progress."""

    permission_classes = STUDENT
    serializer_class = ClipSerializer
    queryset = Clip.objects.filter(
        processing=Clip.Processing.READY, revision__status=Revision.Status.PUBLISHED
    ).select_related("revision")

    def get_object(self):
        clip = super().get_object()
        if not (
            services.is_free_clip(clip)
            or clip.revision.chapter.subject_id in services.entitled_subjects(self.request.user)
        ):
            raise exceptions.PermissionDenied(LOCKED)
        return clip

    def retrieve(self, request, *args, **kwargs):
        clip = self.get_object()
        progress = Progress.objects.filter(user=request.user, clip=clip).first() or Progress()
        for name, value in [*playback(clip).items(), *ProgressSerializer(progress).data.items()]:
            setattr(clip, name, value)
        return Response(self.get_serializer(clip).data)

    @extend_schema(request=ProgressSerializer, responses=ProgressSerializer)
    @action(detail=True, methods=["post"], serializer_class=ProgressSerializer)
    def progress(self, request, *args, **kwargs):
        """How far the student watched; `completed` once true stays true."""
        clip = self.get_object()
        given = self.get_serializer(data=request.data)
        given.is_valid(raise_exception=True)
        progress, _ = Progress.objects.get_or_create(user=request.user, clip=clip)
        progress.seconds_watched = given.validated_data.get("seconds_watched", progress.seconds_watched)
        progress.completed = progress.completed or given.validated_data.get("completed", False)
        progress.save()
        return Response(ProgressSerializer(progress).data)


CHAPTER = OpenApiParameter("chapter", int, required=True, description="chapter id")


def open_chapter(user, pk, cards=False):
    """A published chapter the user may open: entitled, or (flash cards) the free first chapter; 400 or 403."""
    try:
        chapter = Chapter.objects.get(pk=int(pk), revision__status=Revision.Status.PUBLISHED)
    except TypeError, ValueError, Chapter.DoesNotExist:
        raise exceptions.ValidationError({"chapter": ["Give the id of a chapter (learn/chapters/)."]}) from None
    if not (chapter.subject_id in services.entitled_subjects(user) or cards and services.is_free_chapter(chapter)):
        raise exceptions.PermissionDenied(LOCKED)
    return chapter


class QuizItemSerializer(serializers.ModelSerializer):
    text_html = Html("text")

    class Meta:
        model = QuizItem
        fields = ["id", "chapter", "kind", "text", "text_html", "options"]


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField(max_length=200, help_text="the option's number from 1, true/false, or the word(s)")


class CheckedSerializer(serializers.Serializer):
    correct = serializers.BooleanField()
    right_answer = serializers.CharField()
    explanation = serializers.CharField()
    explanation_html = serializers.CharField()


class QuizViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """A chapter's one-mark quiz (no answers in the list); an answer is checked on the server and recorded."""

    permission_classes = STUDENT
    serializer_class = QuizItemSerializer
    queryset = QuizItem.objects.filter(chapter__revision__status=Revision.Status.PUBLISHED)
    filter_backends = []

    def get_queryset(self):
        if self.action == "list":
            return (
                super().get_queryset().filter(chapter=open_chapter(self.request.user, self.request.GET.get("chapter")))
            )
        return super().get_queryset()

    @extend_schema(parameters=[CHAPTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_throttles(self):
        self.throttle_scope = "learn_quiz" if self.action == "attempt" else None  # answers only (600 an hour)
        return super().get_throttles()

    @extend_schema(request=AnswerSerializer, responses=CheckedSerializer)
    @action(detail=True, methods=["post"], serializer_class=AnswerSerializer)
    def attempt(self, request, *args, **kwargs):
        item = self.get_object()
        if item.chapter.subject_id not in services.entitled_subjects(request.user):
            raise exceptions.PermissionDenied(LOCKED)
        given = self.get_serializer(data=request.data)
        given.is_valid(raise_exception=True)
        correct = item.is_right(given.validated_data["answer"])
        QuizAttempt.objects.create(user=request.user, item=item, correct=correct)
        if item.kind == QuizItem.Kind.MCQ:
            right = item.options[int(item.answer) - 1]
        else:
            right = item.answer.split("|")[0].capitalize()
        return Response(
            {"correct": correct, "right_answer": right, "explanation": item.explanation,
             "explanation_html": render(item.explanation)}
        )  # fmt: skip


class FlashCardSerializer(serializers.ModelSerializer):
    front_html = Html("front")
    back_html = Html("back")

    class Meta:
        model = FlashCard
        fields = ["id", "chapter", "order", "front", "front_html", "back", "back_html"]


class ReviewSerializer(serializers.Serializer):
    known = serializers.BooleanField(help_text="the student knew the back")


class FlashCardViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """A chapter's flash cards (the first chapter's are free); "I knew it" or not, for revise-again."""

    permission_classes = STUDENT
    serializer_class = FlashCardSerializer
    queryset = FlashCard.objects.filter(chapter__revision__status=Revision.Status.PUBLISHED)
    filter_backends = []

    def get_queryset(self):
        if self.action == "list":
            chapter = open_chapter(self.request.user, self.request.GET.get("chapter"), cards=True)
            return super().get_queryset().filter(chapter=chapter)
        return super().get_queryset()

    @extend_schema(parameters=[CHAPTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=ReviewSerializer, responses={201: None})
    @action(detail=True, methods=["post"], serializer_class=ReviewSerializer)
    def review(self, request, *args, **kwargs):
        card = self.get_object()
        open_chapter(request.user, card.chapter_id, cards=True)
        given = self.get_serializer(data=request.data)
        given.is_valid(raise_exception=True)
        CardReview.objects.create(user=request.user, card=card, known=given.validated_data["known"])
        return Response(status=status.HTTP_201_CREATED)


class PlanQuery(serializers.Serializer):
    exam_date = serializers.DateField(required=False)
    minutes = serializers.IntegerField(required=False, min_value=10, max_value=300)
    subject = serializers.ListField(child=serializers.IntegerField(), required=False)


def clip_row(clip):
    return {"id": clip.pk, "chapter": clip.revision.chapter_id, "title": clip.title, "kind": clip.kind,
            "duration": clip.duration}  # fmt: skip


class PlanView(views.APIView):
    """The pass plan: clips day by day until the exam, chapters by Board marks x previous-year questions x weakness,
    and the minimum to pass. The exam date and minutes a day come from the query or learn/settings/."""

    permission_classes = STUDENT

    @extend_schema(
        parameters=[
            OpenApiParameter("exam_date", OpenApiTypes.DATE, description="default: saved in learn/settings/"),
            OpenApiParameter("minutes", int, description="a day, 10 to 300; default: saved, or 30"),
            OpenApiParameter("subject", int, many=True, description="default: the subjects open to the user, or all"),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *args, **kwargs):
        query = PlanQuery(data={**request.query_params.dict(), "subject": request.query_params.getlist("subject")})
        query.is_valid(raise_exception=True)
        saved = Learner.objects.filter(user=request.user).first() or Learner()
        exam_date = query.validated_data.get("exam_date") or saved.exam_date
        if not exam_date or exam_date <= timezone.localdate():
            raise exceptions.ValidationError(
                {"exam_date": ["Give a date after today (or save it in learn/settings/)."]}
            )
        published = Chapter.objects.filter(revision__status=Revision.Status.PUBLISHED).values_list("subject", flat=True)
        subjects = set(query.validated_data.get("subject") or published)
        if not query.validated_data.get("subject"):
            subjects = {s for s in subjects if s in services.entitled_subjects(request.user)} or subjects
        made = plan.build(request.user, subjects, exam_date, query.validated_data.get("minutes", saved.minutes_per_day))
        return Response(
            {
                **{key: made[key] for key in ("exam_date", "days_left", "minutes_per_day")},
                "days": [
                    {"date": day["date"], "minutes": round(sum(c.duration for c in day["clips"]) / 60),
                     "clips": [clip_row(clip) for clip in day["clips"]]}
                    for day in made["days"]
                ],
                "not_scheduled": [chapter.pk for chapter in made["not_scheduled"]],
                "minimum_to_pass": [
                    {"subject": row["subject"].pk, "pass_marks": row["pass_marks"], "marks": row["marks"],
                     "chapters": [
                         {"id": pick["chapter"].pk, "number": pick["chapter"].number, "title": pick["chapter"].title,
                          "weight": pick["chapter"].weight, "minutes": pick["minutes"],
                          "marks_per_minute": round(pick["marks_per_minute"], 2),
                          "clips": [clip_row(clip) for clip in pick["clips"]]}
                         for pick in row["chapters"]
                     ]}
                    for row in made["minimum_to_pass"]
                ],
            }
        )  # fmt: skip


class ReviseAgainView(views.APIView):
    """Quiz items and flash cards answered wrong whose day has come (1, 3 and 7 days), the longest waiting first."""

    permission_classes = STUDENT

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, *args, **kwargs):
        due = plan.revise_again(request.user)
        return Response(
            {
                "quiz_items": [
                    {**QuizItemSerializer(row["item"]).data, "due": row["due"]} for row in due["quiz_items"]
                ],
                "flash_cards": [
                    {**FlashCardSerializer(row["item"]).data, "due": row["due"]} for row in due["flash_cards"]
                ],
            }
        )


class EntitlementSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", default=None, help_text="null: every subject")

    class Meta:
        model = Entitlement
        fields = ["id", "subject", "subject_name", "source", "valid_until", "created"]


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40, help_text="as printed: 7KQM-3XPA-9TRW (any case, spaces or dashes)")


class PerAddress(throttling.SimpleRateThrottle):
    """Book codes tried per client address (learn_redeem_address), beside the per-user limit (learn_redeem)."""

    scope = "learn_redeem_address"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RedeemView(generics.GenericAPIView):
    """A book code: opens its subject (or all) for a year; a code works once. 5 tries an hour per user and address."""

    permission_classes = STUDENT
    serializer_class = CodeSerializer
    throttle_classes = [throttling.UserRateThrottle, throttling.ScopedRateThrottle, PerAddress]
    throttle_scope = "learn_redeem"

    @extend_schema(responses=EntitlementSerializer)
    def post(self, request, *args, **kwargs):
        given = self.get_serializer(data=request.data)
        given.is_valid(raise_exception=True)
        try:
            entitlement = services.redeem(request.user, given.validated_data["code"])
        except services.CodeError as error:
            raise exceptions.ValidationError({"code": [str(error)]}) from None
        return Response(EntitlementSerializer(entitlement).data)


class EntitlementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """What the user may watch, newest first (expired ones included: `valid_until`)."""

    permission_classes = STUDENT
    serializer_class = EntitlementSerializer
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Entitlement.objects.none()
        return self.request.user.entitlements.select_related("subject")


class LearnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Learner
        fields = ["exam_date", "minutes_per_day", "reminders"]


class LearnerView(generics.RetrieveUpdateAPIView):
    """The student's course settings: exam date, minutes a day, the daily reminder (off until turned on)."""

    permission_classes = STUDENT
    serializer_class = LearnerSerializer

    def get_object(self):
        return Learner.objects.get_or_create(user=self.request.user)[0]


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["token", "platform"]
        extra_kwargs = {"token": {"validators": []}}  # a token seen before moves to this account


class DeviceView(generics.GenericAPIView):
    """The app's Firebase Cloud Messaging token, for the daily reminder: POST after log-in (and when Firebase gives a
    new one), DELETE at log-out. Deleted with the account."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DeviceSerializer

    @extend_schema(responses={201: DeviceSerializer})
    def post(self, request, *args, **kwargs):
        given = self.get_serializer(data=request.data)
        given.is_valid(raise_exception=True)
        Device.objects.update_or_create(
            token=given.validated_data["token"],
            defaults={"user": request.user, "platform": given.validated_data.get("platform", "")},
        )
        return Response(given.data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    def delete(self, request, *args, **kwargs):
        token = self.get_serializer(data=request.data)
        token.is_valid(raise_exception=True)
        request.user.devices.filter(token=token.validated_data["token"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
