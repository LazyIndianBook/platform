"""The Course module's staff API, under /api/v1/staff/course/ (API.md "Course (staff)"; learn/README.md "The Course
module"), on the staff app's rules (staff.api.StaffView): the panel's session with a second factor or an API key,
each action's catalogued permission, the person's subjects (StaffScope: an editor narrowed to PHY reaches PHY's
chapters, revisions, clips, cards and quiz items, and 404 for the others), cursor pages, `no-store`, every refusal an
`authz_fail` (staff.middleware). The rules are learn.course's (the outline's order, review and publish, the bin, the
bank, entitlements) and learn.codes' (book codes); every change is an audit event; explicit serializers, each named
Course… (the schema's component names are global). No endpoint lists learners or ranks them: a learner's page is
opened one at a time, by its account, and logged."""

from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Least
from django.urls import path, reverse
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import exceptions, generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from accounts.models import User
from api.schema import AutoSchema
from content.models import ErrorReport, Subject
from insights.cells import minimum
from insights.models import FraudSignal, ItemStat
from staff import audit
from staff.api import Cursor, StaffView
from staff.backends import scoped
from staff.privacy import mask_email
from staff.serializers import JobSerializer

from . import codes, course, dashboard, media, services
from .approvals import subject_of
from .models import (
    BATCH_LABEL,
    BookCode,
    CardReview,
    Chapter,
    Clip,
    CodeBatch,
    Device,
    Entitlement,
    FlashCard,
    Progress,
    QuizAttempt,
    QuizItem,
    Revision,
)
from .views import playback

STUCK = 3600  # seconds in "processing" before a clip counts as stuck (its task lost): reprocess_clips' rule
PREVIEW = 140  # characters of a card's or an item's text in a row


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["course (staff)"]


class CourseView(StaffView):
    """Every queryset in the person's subjects, for the permission the action names."""

    schema = StaffSchema()

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return scoped(queryset, self.request.user, self.required_permission(self.request))


def preview(text, length=PREVIEW):
    line = " ".join((text or "").split())
    return line if len(line) <= length else line[: length - 1].rstrip() + "…"


def person(user):
    """A member of staff by id and name (their own colleagues: not masked)."""
    return {"id": user.pk, "name": user.full_name or user.email} if user else None


PERSON = inline_serializer(
    "CoursePerson", {"id": serializers.IntegerField(), "name": serializers.CharField()}, allow_null=True
)


def django_errors(error):
    return serializers.ValidationError(getattr(error, "message_dict", None) or {"non_field_errors": error.messages})


def changed(obj, values):
    """{field: [before, after]} of the values that differ, set on `obj`."""
    changes = {}
    for field, value in values.items():
        if getattr(obj, field) != value:
            changes[field] = [getattr(obj, field), value]
            setattr(obj, field, value)
    return changes


@extend_schema_field(serializers.ListField(child=serializers.CharField(max_length=100), max_length=20))
class CourseTags(serializers.Field):
    """A row's tags (taggit's names): read as a sorted list, written as a list of at most 20, each a word or a few."""

    def to_representation(self, value):
        return sorted(tag.name for tag in value.all())  # (the prefetched tags: no query per row)

    def to_internal_value(self, data):
        try:
            return course.clean_tags(data, "tags")
        except serializers.ValidationError as error:
            raise serializers.ValidationError(error.detail["tags"]) from error


def set_tags(obj, tags):
    """The row's tags replaced by `tags`; {"tags": [before, after]} when they changed."""
    before = sorted(obj.tags.names())
    after = sorted({" ".join(tag.split()) for tag in tags if tag.strip()})
    if before == after:
        return {}
    obj.tags.set(after, clear=True)
    return {"tags": [before, after]}


# ---- Clips' words: the processing state as a reason a person reads ----

REASONS = [  # (what ffmpeg's or the storage's message holds, what the editor reads)
    (media.NOT_A_CLIP[:40], "The file is not a video we take (mp4, mov, m4v, webm or mkv, with H.264, HEVC, VP9 or "
     "AV1 video and AAC, Opus or MP3 sound): export it as an H.264 mp4 and upload it again."),
    ("The file has no video", "The file has sound but no picture: upload the video itself."),
    ("Larger than LEARN_MAX_UPLOAD_MB", "The video is larger than the site takes: export it smaller, or split it."),
    ("took more than", "Making it took too long: split the video into shorter clips and upload each."),
    ("is not installed", "The media worker cannot run ffmpeg: tell whoever runs the servers."),
    ("failed (", "The video could not be read (cut short or damaged): export it again and upload it."),
]  # fmt: skip
STORAGE = "The video could not be fetched or its files saved (the storage did not answer): retry."


def stuck(clip):
    return clip.processing == Clip.Processing.PROCESSING and (timezone.now() - clip.modified).total_seconds() > STUCK


def reason(clip):
    """Why a clip is not ready, in words ("" when ready, or processing in time)."""
    if clip.processing == Clip.Processing.FAILED:
        return next((words for found, words in REASONS if found in clip.processing_error), STORAGE)
    if stuck(clip):
        return "It has been processing for over an hour: its task was probably lost when a worker stopped. Retry it."
    if clip.processing == Clip.Processing.UPLOADED and not clip.source:
        return "No video yet: upload it on the clip's page in the admin."
    return ""


def can_retry(clip):
    return bool(clip.source) and clip.deleted_at is None and (clip.processing == Clip.Processing.FAILED or stuck(clip))


# ---- Subjects and the outline ----


class CourseSubjectSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    chapters = serializers.IntegerField()
    published = serializers.IntegerField(help_text="revisions published")
    in_review = serializers.IntegerField(help_text="revisions waiting for a reviewer")
    scheduled = serializers.IntegerField(help_text="revisions approved, to be published at their time")
    clips = serializers.IntegerField(help_text="outside the bin")
    failed = serializers.IntegerField(help_text="clips whose video failed")
    cards = serializers.IntegerField()
    items = serializers.IntegerField()
    bin = serializers.IntegerField(help_text="clips, cards and quiz items in the bin")


def per_subject(rows):
    return {row[0]: row[1] for row in rows}


class SubjectsView(CourseView, generics.GenericAPIView):
    """The subjects whose chapters the person reaches, each with its course's counts (the module's first page)."""

    serializer_class = CourseSubjectSerializer
    permissions = {"GET": "learn.view_chapter"}
    pagination_class = None
    filter_backends = []
    queryset = Chapter.objects.all()

    @extend_schema(responses=CourseSubjectSerializer(many=True))
    def get(self, request, *args, **kwargs):
        user = request.user
        chapters = self.get_queryset()
        ids = sorted(set(chapters.values_list("subject", flat=True)))
        revisions = scoped(Revision.objects.filter(chapter__subject__in=ids), user, "learn.view_revision")
        statuses = {}
        for subject, state, n in revisions.values_list("chapter__subject", "status").annotate(n=Count("pk")):
            statuses[subject, state] = n
        clips = scoped(Clip.all_objects.filter(revision__chapter__subject__in=ids), user, "learn.view_clip")
        cards = scoped(FlashCard.all_objects.filter(chapter__subject__in=ids), user, "learn.view_flashcard")
        items = scoped(QuizItem.all_objects.filter(chapter__subject__in=ids), user, "learn.view_quizitem")
        live, binned = Q(deleted_at__isnull=True), Q(deleted_at__isnull=False)
        clip_rows = {
            row["revision__chapter__subject"]: row
            for row in clips.values("revision__chapter__subject").annotate(
                live=Count("pk", filter=live),
                failed=Count("pk", filter=live & Q(processing=Clip.Processing.FAILED)),
                binned=Count("pk", filter=binned),
            )
        }
        card_rows = {row["chapter__subject"]: row for row in cards.values("chapter__subject").annotate(
            live=Count("pk", filter=live), binned=Count("pk", filter=binned))}  # fmt: skip
        item_rows = {row["chapter__subject"]: row for row in items.values("chapter__subject").annotate(
            live=Count("pk", filter=live), binned=Count("pk", filter=binned))}  # fmt: skip
        counted = per_subject(chapters.values_list("subject").annotate(n=Count("pk")))
        empty = {"live": 0, "failed": 0, "binned": 0}
        rows = []
        for subject in Subject.objects.filter(pk__in=ids).order_by("code"):
            clip, card, item = (rows_.get(subject.pk, empty) for rows_ in (clip_rows, card_rows, item_rows))
            rows.append(
                {
                    "id": subject.pk,
                    "code": subject.code,
                    "name": subject.name,
                    "chapters": counted.get(subject.pk, 0),
                    "published": statuses.get((subject.pk, Revision.Status.PUBLISHED), 0),
                    "in_review": statuses.get((subject.pk, Revision.Status.REVIEW), 0),
                    "scheduled": statuses.get((subject.pk, Revision.Status.APPROVED), 0),
                    "clips": clip["live"],
                    "failed": clip.get("failed", 0),
                    "cards": card["live"],
                    "items": item["live"],
                    "bin": clip["binned"] + card["binned"] + item["binned"],
                }
            )
        return Response(CourseSubjectSerializer(rows, many=True).data)


class CourseOutlineClipSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    title = serializers.CharField()
    kind = serializers.ChoiceField(choices=Clip.Kind.choices)
    duration = serializers.IntegerField(help_text="seconds (once ready)")
    processing = serializers.ChoiceField(choices=Clip.Processing.choices)
    reason = serializers.CharField(help_text="why it is not ready, in words; empty when ready")
    is_free_preview = serializers.BooleanField(help_text="marked a free preview by an editor")
    free = serializers.BooleanField(help_text="free to anyone signed in: the revision's first clip, or marked")


class CourseOutlineCardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    front = serializers.CharField(help_text="its first words")


class CourseOutlineItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=QuizItem.Kind.choices)
    text = serializers.CharField(help_text="its first words")
    difficulty = serializers.CharField(allow_blank=True)
    flagged = serializers.IntegerField(allow_null=True, help_text="its open report in the content triage, if any")


class CourseOutlineRevisionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    status = serializers.ChoiceField(choices=Revision.Status.choices)
    target_minutes = serializers.IntegerField()
    minutes = serializers.IntegerField(help_text="of its ready clips")
    publish_at = serializers.DateTimeField(allow_null=True)
    clips = CourseOutlineClipSerializer(many=True)


class CourseOutlineChapterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.IntegerField()
    title = serializers.CharField()
    weight = serializers.DecimalField(max_digits=4, decimal_places=1, help_text="the Board's marks")
    frequency = serializers.IntegerField(help_text="previous-year questions")
    must_do = serializers.CharField(allow_blank=True)
    revision = CourseOutlineRevisionSerializer(allow_null=True)
    cards = CourseOutlineCardSerializer(many=True)
    items = CourseOutlineItemSerializer(many=True)


class CourseOutlineSerializer(serializers.Serializer):
    subject = inline_serializer(
        "CourseOutlineSubject",
        {"id": serializers.IntegerField(), "code": serializers.CharField(), "name": serializers.CharField()},
    )
    chapters = CourseOutlineChapterSerializer(many=True)
    completion_rule = serializers.CharField(help_text="what counts as a clip completed")
    free_preview = serializers.BooleanField(help_text="LEARN_FREE_PREVIEW: the first clip of each revision is free")


def open_flags(item_ids):
    """{quiz item id: its open report's id} (the content triage's item_analysis reports)."""
    kind = ContentType.objects.get_for_model(QuizItem)
    rows = ErrorReport.objects.filter(
        target_type=kind, target_id__in=list(item_ids), state__in=ErrorReport.OPEN, spam=False
    ).values_list("target_id", "pk")
    return {target: pk for target, pk in rows}


class OutlineView(CourseView, generics.GenericAPIView):
    """A subject's outline: its chapters by number, each with its revision (status, schedule) and clips, its flash
    cards and quiz items in their order, with the clips' processing and free previews. Bounded by the subject's
    content; a few queries whatever its size."""

    serializer_class = CourseOutlineSerializer
    permissions = {"GET": "learn.view_chapter"}
    pagination_class = None
    filter_backends = []
    queryset = Chapter.objects.all()

    @extend_schema(responses=CourseOutlineSerializer)
    def get(self, request, subject, *args, **kwargs):
        user = request.user
        chapters = list(
            self.get_queryset().filter(subject_id=subject).select_related("subject", "revision").order_by("number")
        )
        if not chapters:
            raise exceptions.NotFound("No chapter of this subject (or not one of your subjects).")
        ids = [chapter.pk for chapter in chapters]
        clips = scoped(Clip.objects.filter(revision__chapter__in=ids), user, "learn.view_clip").order_by("order", "pk")
        cards = scoped(FlashCard.objects.filter(chapter__in=ids), user, "learn.view_flashcard").order_by("order", "pk")
        items = scoped(QuizItem.objects.filter(chapter__in=ids), user, "learn.view_quizitem").order_by("order", "pk")
        by_revision, by_chapter_cards, by_chapter_items = {}, {}, {}
        for clip in clips:
            by_revision.setdefault(clip.revision_id, []).append(clip)
        for card in cards.only("pk", "order", "front", "chapter"):
            by_chapter_cards.setdefault(card.chapter_id, []).append(card)
        item_rows = list(items.only("pk", "order", "kind", "text", "difficulty", "chapter"))
        flags = open_flags(item.pk for item in item_rows)
        for item in item_rows:
            by_chapter_items.setdefault(item.chapter_id, []).append(item)
        out = []
        for chapter in chapters:
            revision = getattr(chapter, "revision", None)
            if revision is not None and not user.has_perm("learn.view_revision"):
                revision = None
            row = {
                "id": chapter.pk,
                "number": chapter.number,
                "title": chapter.title,
                "weight": chapter.weight,
                "frequency": chapter.frequency,
                "must_do": chapter.must_do,
                "revision": None,
                "cards": [{"id": c.pk, "order": c.order, "front": preview(c.front)} for c in
                          by_chapter_cards.get(chapter.pk, [])],
                "items": [{"id": i.pk, "order": i.order, "kind": i.kind, "text": preview(i.text),
                           "difficulty": i.difficulty, "flagged": flags.get(i.pk)} for i in
                          by_chapter_items.get(chapter.pk, [])],
            }  # fmt: skip
            if revision is not None:
                rows = by_revision.get(revision.pk, [])
                first = rows[0].pk if rows else None
                row["revision"] = {
                    "id": revision.pk,
                    "title": revision.title,
                    "status": revision.status,
                    "target_minutes": revision.target_minutes,
                    "minutes": round(sum(c.duration for c in rows if c.processing == Clip.Processing.READY) / 60),
                    "publish_at": revision.publish_at,
                    "clips": [
                        {
                            "id": clip.pk,
                            "order": clip.order,
                            "title": clip.title,
                            "kind": clip.kind,
                            "duration": clip.duration,
                            "processing": clip.processing,
                            "reason": reason(clip),
                            "is_free_preview": clip.is_free_preview,
                            "free": bool(services.is_free_clip(clip, first=first)),
                        }
                        for clip in rows
                    ],
                }
            out.append(row)
        answer = {
            "subject": {
                "id": chapters[0].subject.pk,
                "code": chapters[0].subject.code,
                "name": chapters[0].subject.name,
            },
            "chapters": out,
            "completion_rule": course.COMPLETION_RULE,
            "free_preview": settings.LEARN_FREE_PREVIEW,
        }
        return Response(CourseOutlineSerializer(answer).data)


# ---- Chapters and revisions ----


class CourseChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ["id", "subject", "number", "title", "weight", "frequency", "must_do"]
        read_only_fields = ["id", "subject", "number", "title", "weight", "frequency"]


class ChapterViewSet(CourseView, viewsets.GenericViewSet):
    """A chapter's must-do note (its number, title and the Board's figures come from the syllabus' import)."""

    queryset = Chapter.objects.all()
    serializer_class = CourseChapterSerializer
    permissions = {"partial_update": "learn.change_chapter"}

    @extend_schema(request=CourseChapterSerializer(partial=True), responses=CourseChapterSerializer)
    def partial_update(self, request, *args, **kwargs):
        chapter = self.get_object()
        data = CourseChapterSerializer(chapter, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            chapter = Chapter.objects.select_for_update().get(pk=chapter.pk)
            if changes := changed(chapter, data.validated_data):
                chapter.save(update_fields=list(changes))
                audit.record("course.chapter_changed", request=request, target=chapter, changes=changes)
        return Response(CourseChapterSerializer(chapter).data)


TRANSITIONS = ["submit", "approve", "needs_changes", "publish", "unpublish"]


def transitions(revision, user):
    """The moves of the revision's review the reader may make now (the record draws a button for each)."""
    edit = user.has_perm("learn.change_revision", revision)
    review = user.has_perm("staff.publish_course", revision)
    own = revision.submitted_by_id is not None and revision.submitted_by_id == getattr(user, "pk", None)
    state, moves = revision.status, []
    if state == Revision.Status.DRAFT and edit:
        moves.append("submit")
    if state == Revision.Status.REVIEW and review and not own:
        moves += ["approve", "needs_changes", "publish"]
    if state == Revision.Status.APPROVED and review and not own:
        moves.append("publish")
    if state != Revision.Status.DRAFT and review:
        moves.append("unpublish")
    return moves


class CourseRevisionSerializer(serializers.ModelSerializer):
    chapter = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    submitted_by = serializers.SerializerMethodField()
    reviewer = serializers.SerializerMethodField()
    minutes = serializers.SerializerMethodField(help_text="of its ready clips")
    clips = serializers.SerializerMethodField()
    cards = serializers.SerializerMethodField(help_text="its chapter's flash cards (live with it)")
    items = serializers.SerializerMethodField(help_text="its chapter's quiz items (live with it)")
    transitions = serializers.SerializerMethodField(help_text="the moves the reader may make now")

    class Meta:
        model = Revision
        fields = ["id", "chapter", "title", "target_minutes", "status", "status_label", "submitted_by"]
        fields += ["submitted_at", "reviewer", "publish_at", "minutes", "clips", "cards", "items", "transitions"]
        fields += ["created", "modified"]
        read_only_fields = [name for name in fields if name not in ("title", "target_minutes")]

    @extend_schema_field(
        inline_serializer(
            "CourseRevisionChapter",
            {
                "id": serializers.IntegerField(),
                "number": serializers.IntegerField(),
                "title": serializers.CharField(),
                "subject": serializers.IntegerField(),
                "subject_code": serializers.CharField(),
            },
        )
    )
    def get_chapter(self, revision):
        chapter = revision.chapter
        return {"id": chapter.pk, "number": chapter.number, "title": chapter.title, "subject": chapter.subject_id,
                "subject_code": chapter.subject.code}  # fmt: skip

    @extend_schema_field(PERSON)
    def get_submitted_by(self, revision):
        return person(revision.submitted_by)

    @extend_schema_field(PERSON)
    def get_reviewer(self, revision):
        return person(revision.reviewer)

    def live_clips(self, revision):
        if not hasattr(revision, "_live_clips"):
            revision._live_clips = list(revision.clips.order_by("order", "pk"))
        return revision._live_clips

    def get_minutes(self, revision) -> int:
        return round(sum(c.duration for c in self.live_clips(revision) if c.processing == Clip.Processing.READY) / 60)

    @extend_schema_field(CourseOutlineClipSerializer(many=True))
    def get_clips(self, revision):
        clips = self.live_clips(revision)
        first = clips[0].pk if clips else None
        return [
            {"id": c.pk, "order": c.order, "title": c.title, "kind": c.kind, "duration": c.duration,
             "processing": c.processing, "reason": reason(c), "is_free_preview": c.is_free_preview,
             "free": bool(services.is_free_clip(c, first=first))}
            for c in clips
        ]  # fmt: skip

    def get_cards(self, revision) -> int:
        return FlashCard.objects.filter(chapter=revision.chapter_id).count()

    def get_items(self, revision) -> int:
        return QuizItem.objects.filter(chapter=revision.chapter_id).count()

    @extend_schema_field(serializers.ListField(child=serializers.ChoiceField(choices=TRANSITIONS)))
    def get_transitions(self, revision):
        return transitions(revision, self.context["request"].user)


class CourseCommentSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CoursePublishSerializer(serializers.Serializer):
    publish_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None, help_text="a time to come; empty or null: now"
    )


class RevisionViewSet(CourseView, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """A revision's record and its review: submit (an editor), approve, send back with what to change, publish now
    or at a time, back to draft (a reviewer: staff.publish_course, never who submitted it: 403 own_edit)."""

    queryset = Revision.objects.select_related("chapter__subject", "submitted_by", "reviewer")
    serializer_class = CourseRevisionSerializer
    permissions = {
        "retrieve": "learn.view_revision",
        "partial_update": "learn.change_revision",
        "submit": "learn.change_revision",
        **dict.fromkeys(["approve", "needs_changes", "publish", "unpublish"], "staff.publish_course"),
    }

    def answer(self, revision):
        fresh = self.get_queryset().get(pk=revision.pk)
        return Response(self.get_serializer(fresh).data)

    @extend_schema(request=CourseRevisionSerializer(partial=True), responses=CourseRevisionSerializer)
    def partial_update(self, request, *args, **kwargs):
        revision = self.get_object()
        data = CourseRevisionSerializer(
            revision, data=request.data, partial=True, context=self.get_serializer_context()
        )
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            revision = Revision.objects.select_for_update().get(pk=revision.pk)
            if changes := changed(revision, data.validated_data):
                try:
                    revision.full_clean()
                except DjangoValidationError as error:
                    raise django_errors(error) from error
                revision.save(update_fields=[*changes, "modified"])
                audit.record("course.revision_changed", request=request, target=revision, changes=changes)
        return self.answer(revision)

    @extend_schema(request=None, responses=CourseRevisionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, *args, **kwargs):
        return self.answer(course.submit(self.get_object(), self.human(), request))

    @extend_schema(request=CourseCommentSerializer, responses=CourseRevisionSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        data = CourseCommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.answer(course.approve(self.get_object(), self.human(), data.validated_data["comment"], request))

    @extend_schema(request=CourseCommentSerializer, responses=CourseRevisionSerializer)
    @action(detail=True, methods=["post"], url_path="needs-changes")
    def needs_changes(self, request, *args, **kwargs):
        data = CourseCommentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        revision = course.needs_changes(self.get_object(), self.human(), data.validated_data["comment"], request)
        return self.answer(revision)

    @extend_schema(request=CoursePublishSerializer, responses=CourseRevisionSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, *args, **kwargs):
        data = CoursePublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        revision = course.publish(self.get_object(), self.human(), data.validated_data["publish_at"], request)
        return self.answer(revision)

    @extend_schema(request=None, responses=CourseRevisionSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, *args, **kwargs):
        return self.answer(course.unpublish(self.get_object(), self.human(), request))


# ---- A row's moves, its bin and its restore (clips, cards, quiz items) ----


class CourseMoveSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=course.MOVES, help_text="first, last, or before or after `target`")
    target = serializers.IntegerField(required=False, allow_null=True, help_text="a sibling's id (before, after)")


class CourseBinRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=course.ROW_KINDS)
    title = serializers.CharField(help_text="a clip's title, a card's front, an item's text: its first words")
    chapter = inline_serializer(
        "CourseBinChapter",
        {
            "id": serializers.IntegerField(),
            "number": serializers.IntegerField(),
            "title": serializers.CharField(),
            "subject": serializers.CharField(),
        },
    )
    revision = serializers.IntegerField(allow_null=True, help_text="a clip's revision")
    deleted_at = serializers.DateTimeField()
    bin_until = serializers.DateTimeField(help_text="restored until then; purged the night after")


def bin_row(obj):
    kind = next(name for name, model in course.KINDS.items() if isinstance(obj, model))
    chapter = obj.revision.chapter if isinstance(obj, Clip) else obj.chapter
    title = obj.title if isinstance(obj, Clip) else preview(obj.front if isinstance(obj, FlashCard) else obj.text)
    return {
        "id": obj.pk,
        "kind": kind,
        "title": title,
        "chapter": {
            "id": chapter.pk,
            "number": chapter.number,
            "title": chapter.title,
            "subject": chapter.subject.code,
        },  # fmt: skip
        "revision": obj.revision_id if isinstance(obj, Clip) else None,
        "deleted_at": obj.deleted_at,
        "bin_until": course.bin_until(obj),
    }


class RowActions:
    """move/, DELETE (into the bin), restore/ (out of it within 30 days) for a clip, a card or a quiz item. A
    binned row is read and restored (retrieve, restore: every row), not changed (the others: outside the bin)."""

    def get_queryset(self):
        model = self.queryset.model
        if self.action in ("retrieve", "restore"):
            self.queryset = model.all_objects.select_related(*self.related)
        return super().get_queryset()

    @extend_schema(request=CourseMoveSerializer)
    @action(detail=True, methods=["post"])
    def move(self, request, *args, **kwargs):
        data = CourseMoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        moved = course.move(self.get_object(), data.validated_data["to"], data.validated_data.get("target"), request)
        return Response(self.get_serializer(self.get_queryset().get(pk=moved.pk)).data)

    @extend_schema(responses={200: CourseBinRowSerializer})
    def destroy(self, request, *args, **kwargs):
        return Response(CourseBinRowSerializer(bin_row(course.delete(self.get_object(), request))).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def restore(self, request, *args, **kwargs):
        restored = course.restore(self.get_object(), request)
        return Response(self.get_serializer(restored).data)


# ---- Clips ----


class CourseClipSerializer(serializers.ModelSerializer):
    revision = serializers.SerializerMethodField()
    tags = CourseTags(required=False)
    processing_label = serializers.CharField(source="get_processing_display", read_only=True)
    reason = serializers.SerializerMethodField(help_text="why it is not ready, in words")
    error_detail = serializers.CharField(source="processing_error", read_only=True, help_text="ffmpeg's last words")
    processing_since = serializers.DateTimeField(source="modified", read_only=True)
    stuck = serializers.SerializerMethodField(help_text="processing for over an hour: its task was lost")
    can_retry = serializers.SerializerMethodField()
    free = serializers.SerializerMethodField(help_text="free to anyone signed in (the first clip, or marked)")
    has_video = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField(help_text="its poster once ready, a link signed for 10 minutes")
    player_url = serializers.SerializerMethodField(help_text="the staff player (opened on this host) once ready")
    questions = serializers.SerializerMethodField(help_text="the Board questions it prepares for")
    bin_until = serializers.SerializerMethodField()
    completion_rule = serializers.SerializerMethodField()

    class Meta:
        model = Clip
        fields = ["id", "revision", "order", "title", "kind", "notes", "is_free_preview", "free", "tags"]
        fields += ["processing", "processing_label", "reason", "error_detail", "processing_since", "stuck"]
        fields += ["can_retry", "has_video", "duration", "poster_url", "player_url", "questions", "deleted_at"]
        fields += ["bin_until", "completion_rule", "created", "modified"]
        editable = ["title", "kind", "notes", "is_free_preview", "tags"]
        read_only_fields = sorted(set(fields) - set(editable))

    @extend_schema_field(
        inline_serializer(
            "CourseClipRevision",
            {
                "id": serializers.IntegerField(),
                "title": serializers.CharField(),
                "status": serializers.ChoiceField(choices=Revision.Status.choices),
                "chapter": serializers.IntegerField(),
                "chapter_number": serializers.IntegerField(),
                "chapter_title": serializers.CharField(),
                "subject": serializers.IntegerField(),
                "subject_code": serializers.CharField(),
            },
        )
    )
    def get_revision(self, clip):
        revision, chapter = clip.revision, clip.revision.chapter
        return {"id": revision.pk, "title": revision.title, "status": revision.status, "chapter": chapter.pk,
                "chapter_number": chapter.number, "chapter_title": chapter.title, "subject": chapter.subject_id,
                "subject_code": chapter.subject.code}  # fmt: skip

    def get_reason(self, clip) -> str:
        return reason(clip)

    def get_stuck(self, clip) -> bool:
        return stuck(clip)

    def get_can_retry(self, clip) -> bool:
        return can_retry(clip)

    def get_free(self, clip) -> bool:
        return clip.deleted_at is None and bool(services.is_free_clip(clip))

    def get_has_video(self, clip) -> bool:
        return bool(clip.source)

    def ready(self, clip):
        return clip.processing == Clip.Processing.READY and clip.deleted_at is None

    def get_poster_url(self, clip) -> str | None:
        return playback(clip, site="")["poster_url"] if self.ready(clip) else None

    def get_player_url(self, clip) -> str | None:
        return reverse("learn:preview", args=[clip.pk]) if self.ready(clip) else None

    @extend_schema_field(
        inline_serializer(
            "CourseClipQuestion",
            {"id": serializers.IntegerField(), "paper": serializers.CharField(), "label": serializers.CharField()},
            many=True,
        )
    )
    def get_questions(self, clip):
        return [{"id": q.pk, "paper": q.paper.code, "label": q.label} for q in clip.questions.select_related("paper")]

    def get_bin_until(self, clip) -> str | None:
        until = course.bin_until(clip)
        return serializers.DateTimeField().to_representation(until) if until else None

    def get_completion_rule(self, clip) -> str:
        return course.COMPLETION_RULE


class ClipViewSet(RowActions, CourseView, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """A clip: its processing in words with Retry, its poster and duration once ready, the staff player's link, its
    free preview; changed (title, kind, notes, free preview, tags), moved, put in the bin (its files kept 30 days)
    and restored. Its video is uploaded on its admin page (straight to the bucket)."""

    queryset = Clip.objects.select_related("revision__chapter__subject")
    related = ["revision__chapter__subject"]
    serializer_class = CourseClipSerializer
    permissions = {
        "retrieve": "learn.view_clip",
        **dict.fromkeys(["partial_update", "move", "retry", "restore"], "learn.change_clip"),
        "destroy": "learn.delete_clip",
    }

    @extend_schema(request=CourseClipSerializer(partial=True), responses=CourseClipSerializer)
    def partial_update(self, request, *args, **kwargs):
        clip = self.get_object()
        data = CourseClipSerializer(clip, data=request.data, partial=True, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        tags = values.pop("tags", None)
        with transaction.atomic():
            clip = Clip.objects.select_for_update().get(pk=clip.pk)
            changes = changed(clip, values)
            if changes:
                clip.save(update_fields=[*changes, "modified"])
            if tags is not None:
                changes |= set_tags(clip, tags)
            if changes:
                audit.record("course.clip_changed", request=request, target=clip, changes=changes)
        return Response(self.get_serializer(self.get_queryset().get(pk=clip.pk)).data)

    @extend_schema(request=None, responses=CourseClipSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, *args, **kwargs):
        """Its video processed again (reprocess_clips' function): a failed clip, or one stuck in processing."""
        from .tasks import queue_processing

        with transaction.atomic():
            clip = Clip.objects.select_for_update().get(pk=self.get_object().pk)
            if not clip.source:
                raise course.refused("No video was uploaded: upload it on the clip's page in the admin.")
            if not can_retry(clip):
                state = "ready" if clip.processing == Clip.Processing.READY else "being processed"
                raise course.refused(f"It is {state}: nothing to retry.")
            queue_processing(clip)
            audit.record("course.clip_retried", request=request, target=clip)
        return Response(self.get_serializer(self.get_queryset().get(pk=clip.pk)).data)


# ---- Flash cards ----


class CourseCardSerializer(serializers.ModelSerializer):
    chapter = serializers.PrimaryKeyRelatedField(read_only=True)
    tags = CourseTags(required=False)
    bin_until = serializers.SerializerMethodField()

    class Meta:
        model = FlashCard
        fields = ["id", "chapter", "order", "front", "back", "tags", "deleted_at", "bin_until"]
        read_only_fields = ["id", "chapter", "order", "deleted_at", "bin_until"]

    def get_bin_until(self, card) -> str | None:
        until = course.bin_until(card)
        return serializers.DateTimeField().to_representation(until) if until else None


class CardViewSet(RowActions, CourseView, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """A flash card: changed (front, back, tags), moved, put in the bin and restored."""

    queryset = FlashCard.objects.select_related("chapter__subject")
    related = ["chapter__subject"]
    serializer_class = CourseCardSerializer
    permissions = {
        "retrieve": "learn.view_flashcard",
        **dict.fromkeys(["partial_update", "move", "restore"], "learn.change_flashcard"),
        "destroy": "learn.delete_flashcard",
    }

    @extend_schema(request=CourseCardSerializer(partial=True), responses=CourseCardSerializer)
    def partial_update(self, request, *args, **kwargs):
        card = self.get_object()
        data = CourseCardSerializer(card, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        tags = values.pop("tags", None)
        with transaction.atomic():
            card = FlashCard.objects.select_for_update().get(pk=card.pk)
            changes = changed(card, values)
            if changes:
                card.save(update_fields=list(changes))
            if tags is not None:
                changes |= set_tags(card, tags)
            if changes:
                audit.record("course.card_changed", request=request, target=card, changes=changes)
        return Response(self.get_serializer(card).data)


# ---- The quiz bank ----


def latest_stat(field):
    stats = ItemStat.objects.filter(item=OuterRef("pk")).order_by("-run_date", "-pk")
    return Subquery(stats.values(field)[:1])


def with_stats(items):
    """Each item with its newest item analysis (insights.ItemStat): a subquery a field, no query per row."""
    return items.annotate(
        stat_n=latest_stat("n"),
        stat_p=latest_stat("p"),
        stat_discrimination=latest_stat("discrimination"),
        stat_flags=latest_stat("flags"),
        stat_at=latest_stat("computed_at"),
    )


class CourseItemStatsSerializer(serializers.Serializer):
    n = serializers.IntegerField(allow_null=True, help_text="learners who answered it (first attempts)")
    p = serializers.FloatField(allow_null=True, help_text="share right; null (N/A) under 30 learners")
    discrimination = serializers.FloatField(allow_null=True, help_text="corrected item-total point-biserial")
    flags = serializers.ListField(child=serializers.CharField())
    computed_at = serializers.DateTimeField(allow_null=True, help_text="last calculated (nightly)")
    n_too_small = serializers.BooleanField(help_text="fewer than 30 learners: p and discrimination are N/A")


def stats_of(item):
    """The item's statistics as the bank shows them (the annotations of with_stats)."""
    from insights.jobs.learning import MIN_ANSWERS

    n = getattr(item, "stat_n", None)
    small = n is None or n < MIN_ANSWERS
    flags = getattr(item, "stat_flags", None) or []
    if isinstance(flags, str):  # SQLite gives a subquery's JSON back as text
        import json

        flags = json.loads(flags)
    return {
        "n": n,
        "p": None if small else getattr(item, "stat_p", None),
        "discrimination": None if small else getattr(item, "stat_discrimination", None),
        "flags": flags,
        "computed_at": getattr(item, "stat_at", None),
        "n_too_small": small,
    }


class CourseItemSerializer(serializers.ModelSerializer):
    chapter = serializers.SerializerMethodField()
    tags = CourseTags(required=False)
    source = serializers.SerializerMethodField(help_text="the book question it came from; null: written for the app")
    stats = serializers.SerializerMethodField()
    flagged = serializers.SerializerMethodField(help_text="its open report in the content triage")
    bin_until = serializers.SerializerMethodField()

    class Meta:
        model = QuizItem
        fields = ["id", "chapter", "order", "kind", "text", "options", "answer", "explanation", "topic", "marks"]
        fields += ["difficulty", "bloom", "tags", "source", "stats", "flagged", "deleted_at", "bin_until"]
        editable = ["kind", "text", "options", "answer", "explanation", "topic", "marks", "difficulty", "bloom", "tags"]
        read_only_fields = sorted(set(fields) - set(editable))

    @extend_schema_field(
        inline_serializer(
            "CourseItemChapter",
            {
                "id": serializers.IntegerField(),
                "number": serializers.IntegerField(),
                "title": serializers.CharField(),
                "subject": serializers.CharField(),
            },
        )
    )
    def get_chapter(self, item):
        chapter = item.chapter
        return {"id": chapter.pk, "number": chapter.number, "title": chapter.title, "subject": chapter.subject.code}

    @extend_schema_field(
        inline_serializer(
            "CourseItemSource",
            {
                "question": serializers.IntegerField(),
                "paper": serializers.CharField(),
                "label": serializers.CharField(),
            },
            allow_null=True,
        )
    )
    def get_source(self, item):
        question = item.source
        return {"question": question.pk, "paper": question.paper.code, "label": question.label} if question else None

    @extend_schema_field(CourseItemStatsSerializer)
    def get_stats(self, item):
        if not hasattr(item, "stat_n"):
            item = with_stats(QuizItem.all_objects.filter(pk=item.pk)).get()
        return stats_of(item)

    def get_flagged(self, item) -> int | None:
        flags = self.context.get("flags")
        return flags.get(item.pk) if flags is not None else open_flags([item.pk]).get(item.pk)

    def get_bin_until(self, item) -> str | None:
        until = course.bin_until(item)
        return serializers.DateTimeField().to_representation(until) if until else None

    def validate_options(self, options):
        if not isinstance(options, list) or len(options) > 8 or not all(isinstance(o, str) for o in options):
            raise serializers.ValidationError("A list of at most 8 options, each a text.")
        return [" ".join(option.split()) for option in options]


class CourseItemRowSerializer(CourseItemSerializer):
    """A row of the bank: the item's first words, without its key and explanation."""

    difficulty = serializers.ChoiceField(QuizItem.Difficulty.choices, allow_blank=True, read_only=True)
    bloom = serializers.ChoiceField(QuizItem.Bloom.choices, allow_blank=True, read_only=True)

    class Meta(CourseItemSerializer.Meta):
        fields = ["id", "chapter", "order", "kind", "text", "topic", "marks", "difficulty", "bloom", "tags", "source"]
        fields += ["stats", "flagged"]
        read_only_fields = fields

    def to_representation(self, item):
        data = super().to_representation(item)
        data["text"] = preview(item.text)
        return data


class ItemFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(field_name="chapter__subject__code", help_text="its code: PHY")
    chapter = django_filters.NumberFilter(field_name="chapter")
    topic = django_filters.CharFilter(field_name="topic", lookup_expr="icontains")
    tag = django_filters.CharFilter(field_name="tags__name", help_text="one tag's name, exactly")
    source = django_filters.ChoiceFilter(
        choices=[("book", "from a book question"), ("app", "written for the app")], method="filter_source"
    )
    difficulty = django_filters.CharFilter(method="filter_unset", help_text="easy, medium, hard, or none (not set)")
    bloom = django_filters.CharFilter(method="filter_unset", help_text="a Bloom level, or none (not set)")
    flags = django_filters.CharFilter(
        method="filter_flags", help_text="any, or a flag: low_discrimination, too_easy, too_hard, distractor"
    )
    n_too_small = django_filters.BooleanFilter(method="filter_small", help_text="true: under 30 learners (N/A)")
    flagged = django_filters.BooleanFilter(method="filter_flagged", help_text="true: an open report in the triage")
    q = django_filters.CharFilter(method="filter_q", help_text="words of its text")

    class Meta:
        model = QuizItem
        fields = ["subject", "chapter", "kind", "marks", "topic", "tag", "source", "difficulty", "bloom"]

    def filter_source(self, queryset, name, value):
        return queryset.filter(source__isnull=value == "app")

    def filter_unset(self, queryset, name, value):
        return queryset.filter(**{name: "" if value == "none" else value})

    def filter_flags(self, queryset, name, value):
        from insights.jobs.learning import MIN_ANSWERS

        queryset = queryset.filter(stat_n__gte=MIN_ANSWERS)
        if value == "any":
            return queryset.exclude(Q(stat_flags=[]) | Q(stat_flags__isnull=True))
        # ponytail: flags matched as text in the newest stat's JSON, portable across SQLite and PostgreSQL
        return queryset.filter(stat_flags__icontains=f'"{value}')

    def filter_small(self, queryset, name, value):
        from insights.jobs.learning import MIN_ANSWERS

        small = Q(stat_n__isnull=True) | Q(stat_n__lt=MIN_ANSWERS)
        return queryset.filter(small) if value else queryset.exclude(small)

    def filter_flagged(self, queryset, name, value):
        kind = ContentType.objects.get_for_model(QuizItem)
        reported = ErrorReport.objects.filter(target_type=kind, state__in=ErrorReport.OPEN, spam=False)
        ids = reported.values_list("target_id", flat=True)
        return queryset.filter(pk__in=ids) if value else queryset.exclude(pk__in=ids)

    def filter_q(self, queryset, name, value):
        words = " ".join(value.split())[:50]
        return queryset.filter(text__icontains=words) if words else queryset


class BankOrder(Cursor):
    ordering = ("chapter__subject__code", "chapter__number", "order", "pk")


class CourseFlagSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="",
                                 help_text="what looks wrong (optional)")  # fmt: skip


class CourseFlagAnswerSerializer(serializers.Serializer):
    report = serializers.IntegerField(help_text="the report in the content triage")
    created = serializers.BooleanField(help_text="false: one was open already")


class CourseVersionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="history_id")
    at = serializers.DateTimeField(source="history_date")
    by = serializers.IntegerField(source="history_user_id", allow_null=True)
    type = serializers.ChoiceField(source="history_type", choices=["+", "~", "-"])
    reason = serializers.CharField(source="history_change_reason", allow_null=True)
    changes = serializers.ListField(child=serializers.DictField(), help_text="field, before, after")


def versions(history, limit=50):
    """The newest versions, each with what it changed from the one before it (simple-history's diff_against)."""
    rows = list(history.order_by("-history_id")[: limit + 1])
    out = []
    for index, version in enumerate(rows[:limit]):
        before = rows[index + 1] if index + 1 < len(rows) else None
        version.changes = (
            [{"field": c.field, "before": c.old, "after": c.new} for c in version.diff_against(before).changes]
            if before is not None
            else []
        )
        out.append(version)
    return out


class ItemViewSet(RowActions, CourseView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The quiz bank: every item with its chapter, topic, marks, difficulty, Bloom level, source, tags and its item
    analysis (N/A under 30 learners), all filters; one changed (validated as the admin's form), moved, put in the
    bin, restored, flagged "needs checking" into the content triage (once while one is open), its history. Bulk edits
    of the metadata are a job: POST jobs/ {"kind": "bulk_action", "params": {"action": "item_metadata", …}}."""

    queryset = QuizItem.objects.select_related("chapter__subject", "source__paper")
    related = ["chapter__subject", "source__paper"]
    filterset_class = ItemFilter
    pagination_class = BankOrder
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history"], "learn.view_quizitem"),
        **dict.fromkeys(["partial_update", "move", "restore"], "learn.change_quizitem"),
        "destroy": "learn.delete_quizitem",
        "flag": "staff.triage_report",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        return with_stats(queryset.prefetch_related("tags")) if self.action in ("list", "retrieve") else queryset

    def get_serializer_class(self):
        return CourseItemRowSerializer if self.action == "list" else CourseItemSerializer

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        flags = open_flags(item.pk for item in page)
        return self.get_paginated_response(
            CourseItemRowSerializer(page, many=True, context={**self.get_serializer_context(), "flags": flags}).data
        )

    @extend_schema(request=CourseItemSerializer(partial=True), responses=CourseItemSerializer)
    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        data = CourseItemSerializer(item, data=request.data, partial=True, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        tags = values.pop("tags", None)
        with transaction.atomic():
            item = QuizItem.objects.select_for_update().get(pk=item.pk)
            changes = changed(item, values)
            if changes:
                try:
                    item.full_clean(exclude=["source", "chapter"])
                except DjangoValidationError as error:
                    raise django_errors(error) from error
                item._change_reason = "changed in the panel"
                item.save(update_fields=list(changes))
            if tags is not None:
                changes |= set_tags(item, tags)
            if changes:
                audit.record("course.item_changed", request=request, target=item, changes=changes)
        return Response(
            CourseItemSerializer(self.get_queryset().get(pk=item.pk), context=self.get_serializer_context()).data
        )

    @extend_schema(
        request=CourseFlagSerializer, responses={200: CourseFlagAnswerSerializer, 201: CourseFlagAnswerSerializer}
    )
    @action(detail=True, methods=["post"])
    def flag(self, request, *args, **kwargs):
        data = CourseFlagSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        report, made = course.flag_item(self.get_object(), data.validated_data["note"], request)
        return Response({"report": report.pk, "created": made}, status=status.HTTP_201_CREATED if made else 200)

    @extend_schema(responses=CourseVersionSerializer(many=True))
    @action(detail=True, filter_backends=[], pagination_class=None)
    def history(self, request, *args, **kwargs):
        """Its versions, newest first (50), each with what it changed."""
        item = self.get_object()
        return Response(CourseVersionSerializer(versions(item.history.all()), many=True).data)


# ---- The bin ----


BIN_KIND = OpenApiParameter("kind", str, enum=course.ROW_KINDS, description="clips (default), cards or items")


def bin_permission(view, request):
    """GET bin/: the view permission of the kind asked for (clips by default)."""
    params = getattr(request, "query_params", None) or getattr(request, "GET", {})  # (DRF's request, or Django's)
    model = course.KINDS.get(params.get("kind", "clips"), Clip)
    return f"learn.view_{model._meta.model_name}"


class Newest(Cursor):
    ordering = ("-deleted_at", "-pk")


class BinView(CourseView, generics.GenericAPIView):
    """What is in the bin, newest first, by kind: each restorable until `bin_until`, then purged with a clip's files."""

    permissions = {"GET": bin_permission}
    pagination_class = Newest
    filter_backends = []
    serializer_class = CourseBinRowSerializer

    def get_queryset(self):
        model = course.KINDS.get(self.request.query_params.get("kind", "clips"))
        if model is None:
            raise serializers.ValidationError({"kind": ["clips, cards or items."]})
        related = "revision__chapter__subject" if model is Clip else "chapter__subject"
        self.queryset = model.all_objects.filter(deleted_at__isnull=False).select_related(related)
        return super().get_queryset()

    @extend_schema(parameters=[BIN_KIND], responses=CourseBinRowSerializer(many=True))
    def get(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(CourseBinRowSerializer([bin_row(obj) for obj in page], many=True).data)


# ---- Entitlements ----

STATES = [("active", "open today"), ("ended", "ended"), ("revoked", "revoked by staff")]


def entitlement_state(entitlement, today=None):
    if entitlement.revoked_at:
        return "revoked"
    return "active" if course.is_active(entitlement, today) else "ended"


class CourseEntitlementSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField(help_text="its code; null: every subject")
    subject_name = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    can_extend = serializers.SerializerMethodField()
    can_revoke = serializers.SerializerMethodField()

    class Meta:
        model = Entitlement
        fields = ["id", "user", "subject", "subject_name", "source", "reference", "valid_until", "note", "state"]
        fields += ["revoked_at", "created", "modified", "can_extend", "can_revoke"]
        read_only_fields = fields

    @extend_schema_field(
        inline_serializer(
            "CourseLearnerRef",
            {
                "id": serializers.IntegerField(),
                "name": serializers.CharField(),
                "email": serializers.CharField(help_text="masked"),
                "is_minor": serializers.BooleanField(),
            },
        )
    )
    def get_user(self, entitlement):
        user = entitlement.user
        return {"id": user.pk, "name": user.full_name, "email": mask_email(user.email), "is_minor": user.is_minor}

    def get_subject(self, entitlement) -> str | None:
        return entitlement.subject.code if entitlement.subject_id else None

    def get_subject_name(self, entitlement) -> str:
        return entitlement.subject.name if entitlement.subject_id else "every subject"

    @extend_schema_field(serializers.ChoiceField(choices=STATES))
    def get_state(self, entitlement):
        return entitlement_state(entitlement)

    def get_can_extend(self, entitlement) -> bool:
        return entitlement.revoked_at is None and entitlement.valid_until is not None

    def get_can_revoke(self, entitlement) -> bool:
        return course.is_active(entitlement)


class EntitlementFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(method="filter_subject", help_text="its code, or ALL: every subject")
    state = django_filters.ChoiceFilter(choices=STATES, method="filter_state")
    user = django_filters.NumberFilter(field_name="user")

    class Meta:
        model = Entitlement
        fields = ["subject", "source", "state", "user"]

    def filter_subject(self, queryset, name, value):
        code = value.strip().upper()
        return queryset.filter(subject__isnull=True) if code == "ALL" else queryset.filter(subject__code=code)

    def filter_state(self, queryset, name, value):
        if value == "revoked":
            return queryset.filter(revoked_at__isnull=False)
        active = course.active_q()
        return (
            queryset.filter(active) if value == "active" else queryset.exclude(active).filter(revoked_at__isnull=True)
        )


class CourseGrantSerializer(serializers.Serializer):
    user = serializers.IntegerField(help_text="the account's id")
    subject = serializers.CharField(max_length=10, help_text="a subject's code (PHY), or ALL")
    valid_until = serializers.DateField(required=False, allow_null=True, default=None, help_text="null: no end")
    reason = serializers.CharField(max_length=200)
    reference = serializers.CharField(max_length=40, required=False, allow_blank=True, default="",
                                      help_text="a ticket's number, a school order's (optional)")  # fmt: skip


class CourseExtendSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=365)
    reason = serializers.CharField(max_length=200)


class CourseReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class CourseEntitlementDetailSerializer(CourseEntitlementSerializer):
    history = serializers.SerializerMethodField()

    class Meta(CourseEntitlementSerializer.Meta):
        fields = [*CourseEntitlementSerializer.Meta.fields, "history"]
        read_only_fields = fields

    @extend_schema_field(CourseVersionSerializer(many=True))
    def get_history(self, entitlement):
        return CourseVersionSerializer(versions(entitlement.history.all()), many=True).data


class Created(Cursor):
    ordering = ("-created", "-pk")


class EntitlementViewSet(CourseView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Who may watch what: filters subject, source, state, user, and `q`, an account's email address (exactly): a
    person looked up, so a `customer.lookup` event with its keyed hash. Granted (a reason), extended (days, a reason),
    revoked (a reason): the student's progress stays whatever happens. Bulk: POST jobs/ with a bulk_action of
    entitlement.grant (targets: account ids), entitlement.extend or entitlement.revoke (targets: entitlement ids),
    a dry run first."""

    queryset = Entitlement.objects.select_related("user", "subject")
    filterset_class = EntitlementFilter
    pagination_class = Created
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "learn.view_entitlement"),
        "create": "learn.add_entitlement",
        **dict.fromkeys(["extend", "revoke"], "learn.change_entitlement"),
    }

    def get_throttles(self):
        """A search for a person (`q`) at the searches' own rate (staff_search)."""
        throttles = super().get_throttles()
        if self.action == "list" and self.request.query_params.get("q", "").strip():
            self.throttle_scope = "staff_search"
        return throttles

    def get_serializer_class(self):
        return CourseEntitlementDetailSerializer if self.action == "retrieve" else CourseEntitlementSerializer

    @extend_schema(parameters=[OpenApiParameter("q", str, description="an account's email address, exactly")])
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if query := request.query_params.get("q", "").strip()[:254]:
            queryset = queryset.filter(user__email__iexact=query)
            details = {"kind": "email", "query": audit.mask(query.lower(), "contact"), "list": "entitlements"}
            audit.record("customer.lookup", request=request, details={**details, "found": queryset.count()})
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CourseEntitlementSerializer(page, many=True).data)

    @extend_schema(request=CourseGrantSerializer, responses={201: CourseEntitlementSerializer})
    def create(self, request, *args, **kwargs):
        by = self.human()
        data = CourseGrantSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        account = scoped(User.objects.filter(pk=values["user"]), by, "accounts.view_user").first()
        if account is None:
            raise course.refused("No such account (or not one you may see).", "user")
        subject = subject_of(values["subject"])
        course.check_subject_scope(by, "learn.add_entitlement", subject)
        entitlement = course.grant(account, subject, values["valid_until"], values["reason"], by=by,
                                   reference=values["reference"], request=request)  # fmt: skip
        return Response(CourseEntitlementSerializer(entitlement).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CourseExtendSerializer, responses=CourseEntitlementSerializer)
    @action(detail=True, methods=["post"])
    def extend(self, request, *args, **kwargs):
        data = CourseExtendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = course.extend(self.get_object(), data.validated_data["days"], data.validated_data["reason"],
                             by=self.human(), request=request)  # fmt: skip
        return Response(CourseEntitlementSerializer(self.get_queryset().get(pk=done.pk)).data)

    @extend_schema(request=CourseReasonSerializer, responses=CourseEntitlementSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, *args, **kwargs):
        data = CourseReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = course.revoke(self.get_object(), data.validated_data["reason"], by=self.human(), request=request)
        return Response(CourseEntitlementSerializer(self.get_queryset().get(pk=done.pk)).data)


# ---- Book codes: batches, voids, the lookup, the report ----

BATCH_STATES = ["generating", "failed", "ready", "dispatched", "void"]


def batch_key(batch):
    """How the batch's page is addressed: its label when a path can carry it (letters, digits, hyphens), else ~ and
    its id (a label made before the panel's rule; no label holds ~)."""
    return batch.label if BATCH_LABEL.regex.match(batch.label) else f"~{batch.pk}"


class CourseBatchJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    state = serializers.CharField()
    done = serializers.IntegerField()
    total = serializers.IntegerField()


class CourseBatchSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField(help_text="its page's address: course/codes/batches/{key}/")
    subject = serializers.SerializerMethodField(help_text="its code; null: every subject")
    product = serializers.SerializerMethodField()
    codes = serializers.IntegerField(read_only=True, help_text="made")
    redeemed = serializers.IntegerField(read_only=True)
    void = serializers.IntegerField(read_only=True, help_text="codes voided")
    state = serializers.SerializerMethodField()
    generated_by = serializers.SerializerMethodField()
    job = serializers.SerializerMethodField()

    class Meta:
        model = CodeBatch
        fields = ["id", "key", "label", "subject", "product", "printed", "codes", "redeemed", "void", "state"]
        fields += ["note", "created", "generated_at", "generated_by", "dispatched_at", "voided_at", "void_reason"]
        fields += ["job"]
        read_only_fields = fields

    def get_key(self, batch) -> str:
        return batch_key(batch)

    def get_subject(self, batch) -> str | None:
        return batch.subject.code if batch.subject_id else None

    @extend_schema_field(
        inline_serializer(
            "CourseBatchProduct",
            {"id": serializers.IntegerField(), "slug": serializers.CharField(), "title": serializers.CharField()},
            allow_null=True,
        )
    )
    def get_product(self, batch):
        book = batch.product
        return {"id": book.pk, "slug": book.slug, "title": book.title} if batch.product_id else None

    @extend_schema_field(serializers.ChoiceField(choices=BATCH_STATES))
    def get_state(self, batch):
        return codes.state(batch)

    @extend_schema_field(PERSON)
    def get_generated_by(self, batch):
        return person(batch.generated_by)

    @extend_schema_field(CourseBatchJobSerializer(allow_null=True))
    def get_job(self, batch):
        job = batch.job
        return {"id": job.pk, "state": job.state, "done": job.done, "total": job.total} if job else None


class CourseWeekSerializer(serializers.Serializer):
    week = serializers.DateField(help_text="its Monday")
    redeemed = serializers.IntegerField()


class CourseBatchSignalSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = FraudSignal
        fields = ["id", "kind", "label", "count", "window_start", "window_end", "created", "acknowledged_at"]
        read_only_fields = fields


class CourseBatchDetailSerializer(CourseBatchSerializer):
    redeemed_by_week = serializers.SerializerMethodField()
    signals = serializers.SerializerMethodField(help_text="the fraud signals that name it, newest first")
    activation_rate = serializers.SerializerMethodField(help_text="redeemed ÷ codes made")
    file_until = serializers.SerializerMethodField(help_text="the printer's file, downloadable by its maker until")
    generation = serializers.SerializerMethodField(help_text="the job that made the codes (its file: result_url)")

    class Meta(CourseBatchSerializer.Meta):
        fields = [*CourseBatchSerializer.Meta.fields, "redeemed_by_week", "signals", "activation_rate", "file_until"]
        fields += ["generation"]
        read_only_fields = fields

    @extend_schema_field(CourseWeekSerializer(many=True))
    def get_redeemed_by_week(self, batch):
        return CourseWeekSerializer(codes.redeemed_by_week(batch), many=True).data

    @extend_schema_field(CourseBatchSignalSerializer(many=True))
    def get_signals(self, batch):
        return CourseBatchSignalSerializer(codes.signals_for(batch), many=True).data

    def get_activation_rate(self, batch) -> float | None:
        made = batch.codes or batch.printed
        return round(batch.redeemed / made, 4) if made else None

    def get_file_until(self, batch) -> str | None:
        until = codes.file_until(batch)
        return serializers.DateTimeField().to_representation(until) if until else None

    @extend_schema_field(JobSerializer(allow_null=True))
    def get_generation(self, batch):
        return JobSerializer(batch.job, context=self.context).data if batch.job else None


class CourseBatchCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=40, help_text="the print run's: PHY-2027-1")
    subject = serializers.CharField(max_length=10, help_text="a subject's code (PHY), or ALL: a set of the four books")
    count = serializers.IntegerField(min_value=1, max_value=codes.MAX_CODES)
    product = serializers.CharField(max_length=200, help_text="the book the codes are printed in: its slug")
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000,
                                 help_text="the printer, the run, the delivery")  # fmt: skip

    def validate_label(self, label):
        label = label.strip()
        try:
            CodeBatch._meta.get_field("label").run_validators(label)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return label


class CourseBatchStartedSerializer(serializers.Serializer):
    batch = CourseBatchSerializer()
    job = JobSerializer()


class CourseDispatchedSerializer(serializers.Serializer):
    at = serializers.DateTimeField(required=False, allow_null=True, default=None,
                                   help_text="when the books left; empty: now")  # fmt: skip


class CourseVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class CourseCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40, help_text="typed or scanned: 7KQM-3XPA-9TRW (any case, spaces, dashes)")


class CourseCodeVoidSerializer(CourseCodeSerializer):
    reason = serializers.CharField(max_length=300)


class CourseCodeVoidedSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    batch = serializers.CharField()
    voided_at = serializers.DateTimeField()


CODE_STATES = ["unknown", "unused", "redeemed", "void"]


class CourseCodeLookupSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=CODE_STATES)
    line = serializers.CharField(help_text="the answer in one line")
    batch = serializers.CharField(allow_null=True)
    batch_state = serializers.ChoiceField(choices=BATCH_STATES, allow_null=True)
    subject = serializers.CharField(allow_null=True)
    redeemed_at = serializers.DateTimeField(allow_null=True)
    voided_at = serializers.DateTimeField(allow_null=True)
    redeemed_by = inline_serializer(
        "CourseCodeRedeemer",
        {
            "id": serializers.IntegerField(help_text="the account: its learner page and customer record"),
            "email": serializers.CharField(help_text="masked"),
            "is_minor": serializers.BooleanField(),
        },
        allow_null=True,
    )


class BatchFilter(django_filters.FilterSet):
    subject = django_filters.CharFilter(method="filter_subject", help_text="its code, or ALL")
    state = django_filters.ChoiceFilter(choices=[(s, s) for s in BATCH_STATES], method="filter_state")
    q = django_filters.CharFilter(field_name="label", lookup_expr="icontains", help_text="its label")

    class Meta:
        model = CodeBatch
        fields = ["subject", "state", "q"]

    def filter_subject(self, queryset, name, value):
        code = value.strip().upper()
        return queryset.filter(subject__isnull=True) if code == "ALL" else queryset.filter(subject__code=code)

    def filter_state(self, queryset, name, value):
        made, running = Q(generated_at__isnull=False), Q(job__state__in=["queued", "running"])
        states = {
            "void": Q(voided_at__isnull=False),
            "dispatched": Q(voided_at__isnull=True, dispatched_at__isnull=False),
            "ready": Q(voided_at__isnull=True, dispatched_at__isnull=True) & made,
            "generating": Q(voided_at__isnull=True, generated_at__isnull=True) & running,
            "failed": Q(voided_at__isnull=True, generated_at__isnull=True) & ~running,
        }
        return queryset.filter(states[value])


class BatchViewSet(CourseView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The print runs' book codes: made by a job (the printer's file, its maker's for 24 hours), marked dispatched,
    voided (every unused code: a typed confirmation in the panel), each with its redemptions by week and the fraud
    signals that name it. Addressed by its label (or `key`)."""

    queryset = codes.with_counts(CodeBatch.objects.select_related("subject", "product", "generated_by", "job"))
    filterset_class = BatchFilter
    pagination_class = Created
    lookup_field, lookup_value_regex = "label", "[^/]+"
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "learn.view_codebatch"),
        "create": "staff.make_book_codes",
        "dispatched": "learn.change_codebatch",
        "void": "staff.void_book_codes",
    }
    throttle_scopes = {"create": "staff_export"}  # a print run's codes, made as a file: an export's rate

    def get_serializer_class(self):
        return CourseBatchDetailSerializer if self.action == "retrieve" else CourseBatchSerializer

    def get_object(self):
        """By its `key`: its label, or ~ and its id (a label a path cannot carry)."""
        value, queryset = self.kwargs["label"], self.get_queryset()
        if value.startswith("~"):
            found = queryset.filter(pk=value[1:]).first() if value[1:].isdigit() else None
        else:
            found = queryset.filter(label=value).first()
        if found is None:
            raise exceptions.NotFound("No such batch (or not one you may see).")
        self.check_object_permissions(self.request, found)
        return found

    def answer(self, batch, serializer=CourseBatchSerializer, code=200):
        fresh = self.get_queryset().get(pk=batch.pk)
        return Response(serializer(fresh, context=self.get_serializer_context()).data, status=code)

    @extend_schema(request=CourseBatchCreateSerializer, responses={202: CourseBatchStartedSerializer})
    def create(self, request, *args, **kwargs):
        """A new print run's codes, made by a job (202): its file is yours to download once it is done, for 24 hours
        (then deleted); the owners are told."""
        user = self.human()
        data = CourseBatchCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        from shop.models import Product

        product = Product.objects.filter(slug=values["product"]).first()
        if product is None or product.kind == Product.Kind.DIGITAL:
            raise course.refused("A book (printed) the codes go into.", "product")
        subject = subject_of(values["subject"])
        course.check_subject_scope(user, "staff.make_book_codes", subject)
        batch = codes.start(label=values["label"], subject=subject, count=values["count"], product=product,
                            note=values["note"], user=user, request=request)  # fmt: skip
        fresh = self.get_queryset().get(pk=batch.pk)
        body = {
            "batch": CourseBatchSerializer(fresh).data,
            "job": JobSerializer(fresh.job, context={"request": request}).data,
        }
        return Response(body, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=CourseDispatchedSerializer, responses=CourseBatchSerializer)
    @action(detail=True, methods=["post"])
    def dispatched(self, request, *args, **kwargs):
        data = CourseDispatchedSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        batch = codes.dispatched(self.get_object(), data.validated_data["at"], by=self.human(), request=request)
        return self.answer(batch)

    @extend_schema(
        request=CourseVoidSerializer,
        responses=inline_serializer(
            "CourseBatchVoided", {"batch": CourseBatchSerializer(), "voided": serializers.IntegerField()}
        ),
    )
    @action(detail=True, methods=["post"])
    def void(self, request, *args, **kwargs):
        data = CourseVoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        batch, voided = codes.void_batch(self.get_object(), data.validated_data["reason"], by=self.human(),
                                         request=request)  # fmt: skip
        fresh = self.get_queryset().get(pk=batch.pk)
        return Response({"batch": CourseBatchSerializer(fresh).data, "voided": voided})


class CodeVoidView(CourseView, generics.GenericAPIView):
    """One code voided by its digest (a leaked one): its redemption refused from now; one redeemed already is
    refused here (revoke the access it opened instead)."""

    permissions = {"POST": "staff.void_book_codes"}
    serializer_class = CourseCodeVoidSerializer
    pagination_class = None

    @extend_schema(request=CourseCodeVoidSerializer, responses=CourseCodeVoidedSerializer)
    def post(self, request, *args, **kwargs):
        data = CourseCodeVoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        code = codes.void_code(data.validated_data["code"], data.validated_data["reason"], by=self.human(),
                               request=request)  # fmt: skip
        return Response({"id": code.pk, "batch": code.batch, "voided_at": code.voided_at})


class CodeLookupView(CourseView, generics.GenericAPIView):
    """A typed or scanned code, answered in one line: unused, redeemed (when, by which account: masked, linked),
    void, or unknown. The code is hashed, never kept; each lookup is audited and throttled."""

    permissions = {"POST": "learn.view_bookcode"}
    serializer_class = CourseCodeSerializer
    pagination_class = None
    throttle_scope = "staff_code_lookup"

    @extend_schema(request=CourseCodeSerializer, responses=CourseCodeLookupSerializer)
    def post(self, request, *args, **kwargs):
        data = CourseCodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            CourseCodeLookupSerializer(codes.lookup(data.validated_data["code"], request.user, request)).data
        )


class CourseReportCellSerializer(serializers.Serializer):
    district = serializers.CharField()
    activated = serializers.IntegerField(
        allow_null=True, help_text="null: fewer than the minimum, INSIGHTS_MIN_CELL (hidden)"
    )
    hidden = serializers.BooleanField()


class CourseReportRowSerializer(serializers.Serializer):
    batch = CourseBatchSerializer()
    printed = serializers.IntegerField()
    sold = serializers.IntegerField(allow_null=True, help_text="copies of its book sold online; null: no book named")
    activated = serializers.IntegerField(help_text="codes redeemed")
    revoked = serializers.IntegerField(help_text="access its codes opened, revoked by staff")
    void = serializers.IntegerField()
    activation_rate = serializers.FloatField(allow_null=True, help_text="activated ÷ printed")
    districts = CourseReportCellSerializer(many=True)


class CourseReportSerializer(serializers.Serializer):
    computed_at = serializers.DateTimeField()
    min_cell = serializers.IntegerField(help_text="a district's cell under it is hidden")
    definitions = serializers.DictField(child=serializers.CharField(), help_text="how each number is made")
    totals = inline_serializer(
        "CourseReportTotals",
        {
            "printed": serializers.IntegerField(),
            "sold": serializers.IntegerField(),
            "activated": serializers.IntegerField(),
            "revoked": serializers.IntegerField(),
            "void": serializers.IntegerField(),
            "activation_rate": serializers.FloatField(allow_null=True),
        },
    )
    rows = CourseReportRowSerializer(many=True)


DEFINITIONS = {
    "printed": "Codes made for the print run.",
    "sold": "Copies of its book sold on the website (and in bundles) from the day its codes were made until the next "
    "print run of the book, in orders that count: placed or paid, not cancelled or refunded, test orders left out. "
    "School and distributor copies sold through ERPNext are not counted yet.",
    "activated": "Codes redeemed in the app.",
    "revoked": "Access a code opened that staff took back.",
    "void": "Codes voided: they open nothing.",
    "activation_rate": "Activated ÷ printed.",
    "districts": "Where codes were redeemed: the redeemer's last order of the subject before the code, by its PIN "
    "code; a code from a book bought in a shop has none (unknown). A district with fewer than INSIGHTS_MIN_CELL is "
    "counted in other districts, itself hidden while fewer than that.",
}


class CodesReportView(CourseView, generics.GenericAPIView):
    """The codes report (plan 5.16): printed, sold, activated, revoked and void by batch, the activation rate, by
    district with the cells under
    INSIGHTS_MIN_CELL hidden (insights.cells.minimum). Computed when asked; the newest 200 print runs."""

    permissions = {"GET": "learn.view_codebatch"}
    serializer_class = CourseReportSerializer
    pagination_class = None
    filter_backends = []

    @extend_schema(responses=CourseReportSerializer)
    def get(self, request, *args, **kwargs):
        rows = codes.report(request.user)
        body = {"computed_at": timezone.now(), "min_cell": minimum(), "definitions": DEFINITIONS,
                "totals": codes.totals(rows), "rows": rows}  # fmt: skip
        return Response(CourseReportSerializer(body).data)


# ---- A learner's page (support): one account at a time, every view logged ----


class CourseLearnerSerializer(serializers.Serializer):
    logged = serializers.BooleanField(help_text="true: this view is in the access log")
    user = inline_serializer(
        "CourseLearnerUser",
        {
            "id": serializers.IntegerField(),
            "name": serializers.CharField(),
            "email": serializers.CharField(help_text="masked"),
            "is_minor": serializers.BooleanField(),
            "is_active": serializers.BooleanField(),
        },
    )
    summary_only = serializers.BooleanField(
        help_text="under 18 or of unknown age: a usage summary (counts and the week last active), no times"
    )
    summary = inline_serializer(
        "CourseLearnerSummary",
        {
            "clips_watched": serializers.IntegerField(),
            "minutes_watched": serializers.IntegerField(),
            "quiz_answers": serializers.IntegerField(),
            "quiz_accuracy": serializers.IntegerField(allow_null=True),
            "card_reviews": serializers.IntegerField(),
            "last_active": serializers.DateTimeField(allow_null=True, help_text="null for a summary"),
            "last_active_week": serializers.DateField(allow_null=True, help_text="its Monday"),
        },
    )
    entitlements = CourseEntitlementSerializer(many=True)
    codes = inline_serializer(
        "CourseLearnerCode",
        {
            "id": serializers.IntegerField(),
            "batch": serializers.CharField(),
            "subject": serializers.CharField(),
            "redeemed_at": serializers.DateTimeField(),
        },
        many=True,
        allow_null=True,
    )
    devices = inline_serializer(
        "CourseLearnerDevice",
        {
            "id": serializers.IntegerField(),
            "platform": serializers.CharField(allow_blank=True),
            "added": serializers.DateTimeField(allow_null=True, help_text="null for a summary"),
            "last_seen": serializers.DateTimeField(allow_null=True, help_text="null for a summary"),
            "last_seen_week": serializers.DateField(allow_null=True),
        },
        many=True,
    )
    chapters = inline_serializer(
        "CourseLearnerChapter",
        {
            "id": serializers.IntegerField(),
            "subject": serializers.CharField(),
            "number": serializers.IntegerField(),
            "title": serializers.CharField(),
            "clips_watched": serializers.IntegerField(),
            "clips_total": serializers.IntegerField(),
            "minutes_watched": serializers.IntegerField(),
            "quiz_answers": serializers.IntegerField(),
            "quiz_accuracy": serializers.IntegerField(allow_null=True),
            "card_reviews": serializers.IntegerField(),
            "cards_known": serializers.IntegerField(),
        },
        many=True,
    )
    tickets = inline_serializer(
        "CourseLearnerTicket",
        {
            "number": serializers.CharField(),
            "subject": serializers.CharField(),
            "category": serializers.CharField(),
            "status": serializers.CharField(),
            "received_at": serializers.DateTimeField(),
        },
        many=True,
        allow_null=True,
    )


def monday(moment):
    """The Monday (India) of the week of `moment`, or None."""
    day = timezone.localdate(moment) if moment else None
    return day - timedelta(days=day.weekday()) if day else None


def learner_page(user, reader):
    """Everything support reads about one learner's course, in counts: a child's (or an unknown age's) as a summary
    without times (DPDP Act s.9(3): no behavioural trail of a child, plan 10.1)."""
    adult = user.date_of_birth is not None and not user.is_minor
    entitled = services.entitled_subjects(user)
    subjects = dashboard.subjects(user, entitled)  # what the student's own Learning page counts
    cards = {
        row["card__chapter"]: row
        for row in CardReview.objects.filter(user=user, card__deleted_at__isnull=True)
        .values("card__chapter")
        .annotate(n=Count("pk"), known=Count("pk", filter=Q(known=True)))
    }
    chapters, last = [], None
    for subject in subjects:
        for chapter in subject["chapters"]:
            card = cards.get(chapter["id"], {})
            chapters.append(
                {"id": chapter["id"], "subject": subject["code"], "number": chapter["number"],
                 "title": chapter["title"], "clips_watched": chapter["clips_watched"],
                 "clips_total": chapter["clips_total"], "minutes_watched": chapter["minutes_watched"],
                 "quiz_answers": chapter["quiz_answers"], "quiz_accuracy": chapter["quiz_accuracy"],
                 "card_reviews": card.get("n", 0), "cards_known": card.get("known", 0)}
            )  # fmt: skip
    watched = Progress.objects.filter(user=user, clip__deleted_at__isnull=True, clip__processing="ready").aggregate(
        done=Count("pk", filter=Q(completed=True)), seconds=Sum(Least("seconds_watched", "clip__duration"))
    )
    answers = QuizAttempt.objects.filter(user=user, item__deleted_at__isnull=True).aggregate(
        n=Count("pk"), right=Count("pk", filter=Q(correct=True))
    )
    for rows, field in ((Progress.objects.filter(user=user), "updated"), (QuizAttempt.objects.filter(user=user),
                        "created"), (CardReview.objects.filter(user=user), "created")):  # fmt: skip
        newest = rows.aggregate(newest=Max(field))["newest"]
        last = max(filter(None, [last, newest]), default=None)
    entitlements = scoped(Entitlement.objects.filter(user=user).select_related("user", "subject"), reader,
                          "learn.view_entitlement").order_by("-created")  # fmt: skip
    redeemed = None
    if reader.has_perm("learn.view_bookcode"):
        rows = scoped(BookCode.objects.filter(redeemed_by=user).select_related("subject"), reader,
                      "learn.view_bookcode").order_by("-redeemed_at")[:50]  # fmt: skip
        redeemed = [{"id": code.pk, "batch": code.batch, "subject": code.subject.code if code.subject_id else "ALL",
                     "redeemed_at": code.redeemed_at} for code in rows]  # fmt: skip
    devices = [
        {"id": device.pk, "platform": device.platform, "added": device.created if adult else None,
         "last_seen": device.last_seen if adult else None, "last_seen_week": monday(device.last_seen)}
        for device in Device.objects.filter(user=user).order_by("-last_seen", "-pk")
    ]  # fmt: skip
    return {
        "logged": True,
        "user": {
            "id": user.pk,
            "name": user.full_name,
            "email": mask_email(user.email),
            "is_minor": user.is_minor,
            "is_active": user.is_active,
        },  # fmt: skip
        "summary_only": not adult,
        "summary": {
            "clips_watched": watched["done"] or 0,
            "minutes_watched": round((watched["seconds"] or 0) / 60),
            "quiz_answers": answers["n"],
            "quiz_accuracy": round(100 * answers["right"] / answers["n"]) if answers["n"] else None,
            "card_reviews": sum(row["n"] for row in cards.values()),
            "last_active": last if adult else None,
            "last_active_week": monday(last),
        },
        "entitlements": list(entitlements),
        "codes": redeemed,
        "devices": devices,
        "chapters": chapters,
        "tickets": tickets_of(user, reader),
    }


def tickets_of(user, reader):
    """The account's support tickets (support.Ticket, read lazily: null without the app or the permission)."""
    if not apps.is_installed("support") or not reader.has_perm("support.view_ticket"):
        return None
    from support.models import Ticket

    rows = scoped(Ticket.objects.filter(user=user).exclude(status=Ticket.Status.SPAM), reader, "support.view_ticket")
    return list(
        rows.order_by("-received_at", "-pk").values("number", "subject", "category", "status", "received_at")[:10]
    )


class LearnerAccount:
    """The learner the path names: an account that is not staff's, which the reader may see (accounts.view_user)."""

    def account(self):
        users = scoped(get_user_model().objects.filter(is_staff=False), self.request.user, "accounts.view_user")
        found = users.filter(pk=self.kwargs["user"]).first()
        if found is None:
            raise exceptions.NotFound("No such learner (or not one you may see).")
        return found


class LearnerView(LearnerAccount, CourseView, generics.GenericAPIView):
    """A learner's course for support, opened from a ticket's sidebar: entitlements, codes redeemed, devices (each
    signed out here), chapter progress, quiz accuracy and card reviews per chapter, the account's tickets. Every view
    is a `sensitive_read` (a child's marked so) and says so (`logged`); a child's is a usage summary, no times."""

    permissions = {"GET": "learn.view_entitlement"}
    serializer_class = CourseLearnerSerializer
    pagination_class = None
    filter_backends = []
    throttle_scope = "staff_search"

    @extend_schema(responses=CourseLearnerSerializer)
    def get(self, request, *args, **kwargs):
        user = self.account()
        audit.record("sensitive_read", request=request, target=user,
                     details={"what": "learner", "child": user.is_minor})  # fmt: skip
        return Response(CourseLearnerSerializer(learner_page(user, request.user)).data)


class DeviceSignOutView(LearnerAccount, CourseView, generics.GenericAPIView):
    """One of the learner's phones taken off the account: no more reminders to it until the app registers it again
    (at its next log-in). Ending the app's sign-in everywhere is the customer's page's (users/{id}/end-sessions/)."""

    permissions = {"POST": "staff.end_user_sessions"}
    pagination_class = None
    filter_backends = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request, *args, **kwargs):
        user = self.account()
        with transaction.atomic():
            device = Device.objects.select_for_update().filter(user=user, pk=self.kwargs["device"]).first()
            if device is None:
                raise exceptions.NotFound("No such device on this account.")
            details = {"device": device.pk, "platform": device.platform}
            device.delete()
            audit.record("course.device_signed_out", request=request, target=user, details=details)
        return Response(status=status.HTTP_204_NO_CONTENT)


router = SimpleRouter()
router.register("chapters", ChapterViewSet, basename="course-chapter")
router.register("revisions", RevisionViewSet, basename="course-revision")
router.register("clips", ClipViewSet, basename="course-clip")
router.register("cards", CardViewSet, basename="course-card")
router.register("items", ItemViewSet, basename="course-item")
router.register("entitlements", EntitlementViewSet, basename="course-entitlement")
router.register("codes/batches", BatchViewSet, basename="course-batch")
urlpatterns = [  # under /api/v1/staff/course/ (staff/urls.py)
    path("subjects/", SubjectsView.as_view(), name="course-subjects"),
    path("subjects/<int:subject>/outline/", OutlineView.as_view(), name="course-outline"),
    path("bin/", BinView.as_view(), name="course-bin"),
    path("codes/void/", CodeVoidView.as_view(), name="course-code-void"),
    path("codes/lookup/", CodeLookupView.as_view(), name="course-code-lookup"),
    path("codes/report/", CodesReportView.as_view(), name="course-codes-report"),
    path("learners/<int:user>/", LearnerView.as_view(), name="course-learner"),
    path("learners/<int:user>/devices/<int:device>/sign-out/", DeviceSignOutView.as_view(), name="course-device"),
    *router.urls,
]
