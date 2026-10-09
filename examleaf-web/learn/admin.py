from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.urls import path, reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from . import uploads
from .models import (
    CODE_LENGTH,
    BookCode,
    Chapter,
    Clip,
    CodeBatch,
    Entitlement,
    FlashCard,
    QuizItem,
    Revision,
    clean_code,
    code_digest,
)


class IntoTheBin:
    """Phase B: a clip, card or quiz item deleted here goes into the panel's 30-day bin (learn.course), as there; its
    list shows the rows outside it (the default manager). The panel's Course module restores and purges."""

    def delete_model(self, request, obj):
        from .course import delete

        delete(obj, request=request)

    def delete_queryset(self, request, queryset):
        from .course import delete

        for obj in queryset:
            delete(obj, request=request)


def publishes(request):
    """Publishing a revision is a reviewer's (staff.publish_course), as in the panel."""
    return request.user.has_perm("staff.publish_course")


def move(clips, step):
    """Swap each clip with its neighbour in the revision (step -1: up, 1: down) and number the clips 1, 2, 3 …"""
    for clip in clips:
        siblings = list(clip.revision.clips.order_by("order", "pk"))
        here = next(i for i, sibling in enumerate(siblings) if sibling.pk == clip.pk)
        if 0 <= here + step < len(siblings):
            siblings[here], siblings[here + step] = siblings[here + step], siblings[here]
        for number, sibling in enumerate(siblings, 1):
            if sibling.order != number:
                sibling.order = number
                sibling.save(update_fields=["order"])


@admin.display(description="preview")
def preview(clip):
    """The staff player (learn.views.preview), once the clip has been saved."""
    return format_html('<a href="{}">Preview</a>', reverse("learn:preview", args=[clip.pk])) if clip.pk else "—"


class FlashCardInline(admin.TabularInline):
    model = FlashCard
    fields = ["order", "front", "back"]
    extra = 0
    can_delete = False  # a card's deletion: its own page, or the panel (the bin)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ["__str__", "subject", "weight", "frequency", "revision_status"]
    list_filter = ["subject"]
    search_fields = ["title"]
    inlines = [FlashCardInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("subject", "revision")

    @admin.display(description="revision")
    def revision_status(self, chapter):
        revision = getattr(chapter, "revision", None)
        return revision.get_status_display() if revision else "—"


class ClipInline(admin.TabularInline):
    model = Clip
    form = uploads.ClipForm
    fields = ["order", "title", "kind", "source", "source_key", "is_free_preview", "processing", "duration", preview]
    readonly_fields = ["processing", "duration", preview]
    extra = 0
    show_change_link = True
    can_delete = False  # a clip's deletion: its own page, or the panel (the bin keeps its files 30 days)


class UploadsToStorage:
    """The clip pages send videos straight to the bucket (uploads.py, H1): its origin joins their CSP's connect-src."""

    def changeform_view(self, request, *args, **kwargs):
        return uploads.allow_storage(
            super().changeform_view(request, *args, **kwargs), uploads.private(), "connect-src"
        )


@admin.register(Revision)
class RevisionAdmin(UploadsToStorage, admin.ModelAdmin):
    list_display = ["title", "chapter", "status", "clip_count", "order"]
    list_editable = ["order"]
    list_filter = ["status", "chapter__subject"]
    search_fields = ["title", "chapter__title"]
    inlines = [ClipInline]
    actions = ["publish", "unpublish"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("chapter").annotate(clip_count=Count("clips"))

    @admin.display(description="clips", ordering="clip_count")
    def clip_count(self, revision):
        return revision.clip_count

    @admin.action(description="Publish the selected revisions", permissions=["publish"])
    def publish(self, request, queryset):
        live = Q(clips__processing=Clip.Processing.READY, clips__deleted_at__isnull=True)
        not_ready = queryset.exclude(live).count()
        ready = queryset.filter(live).distinct()
        done = ready.update(status=Revision.Status.PUBLISHED, publish_at=None)
        self.message_user(request, f"{done} published.")
        if not_ready:
            self.message_user(request, f"{not_ready} left as they are: no clip is ready yet.", messages.WARNING)

    @admin.action(description="Back to draft", permissions=["publish"])
    def unpublish(self, request, queryset):
        done = queryset.update(status=Revision.Status.DRAFT, publish_at=None, reviewer=None)
        self.message_user(request, f"{done} back to draft.")

    def has_publish_permission(self, request):
        return publishes(request)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is Clip:
            from .tasks import queue_processing

            for clip_form in formset.forms:
                if uploads.video_changed(clip_form):
                    queue_processing(clip_form.instance)


@admin.register(Clip)
class ClipAdmin(IntoTheBin, UploadsToStorage, admin.ModelAdmin):
    form = uploads.ClipForm
    list_display = ["title", "revision", "order", "kind", "processing", "duration", "is_free_preview", preview]
    list_filter = ["processing", "kind", "revision__chapter__subject"]
    search_fields = ["title", "revision__title"]
    readonly_fields = ["processing", "processing_error", "hls_path", "duration", preview]
    raw_id_fields = ["questions"]
    actions = ["move_up", "move_down", "process_again"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("revision")

    def get_urls(self):
        upload = path("upload-url/", self.admin_site.admin_view(self.upload_url), name="learn_clip_upload_url")
        return [upload, *super().get_urls()]

    def upload_url(self, request):
        """The signed PUT link for a video sent straight to the bucket (uploads.upload_url)."""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            raise PermissionDenied
        return uploads.upload_url(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if uploads.video_changed(form):
            from .tasks import queue_processing

            queue_processing(obj)

    @admin.action(description="Move up", permissions=["change"])
    def move_up(self, request, queryset):
        move(queryset, -1)

    @admin.action(description="Move down", permissions=["change"])
    def move_down(self, request, queryset):
        move(queryset, 1)

    @admin.action(description="Process the video again", permissions=["change"])
    def process_again(self, request, queryset):
        from .tasks import queue_processing

        clips = [clip for clip in queryset if clip.source]
        for clip in clips:
            queue_processing(clip)
        self.message_user(request, f"{len(clips)} queued for processing.")


@admin.register(FlashCard)
class FlashCardAdmin(IntoTheBin, admin.ModelAdmin):
    list_display = ["__str__", "chapter", "order"]
    list_filter = ["chapter__subject"]
    search_fields = ["front", "back"]


@admin.register(QuizItem)
class QuizItemAdmin(IntoTheBin, SimpleHistoryAdmin):
    list_display = ["__str__", "chapter", "kind", "difficulty", "source"]
    list_filter = ["kind", "difficulty", "bloom", "chapter__subject"]
    search_fields = ["text", "chapter__title"]
    raw_id_fields = ["chapter"]


@admin.register(CodeBatch)
class CodeBatchAdmin(admin.ModelAdmin):
    """The panel makes, dispatches and voids batches (Course, Book codes): read-only here."""

    list_display = ["label", "subject", "product", "printed", "generated_at", "dispatched_at", "voided_at"]
    list_filter = ["subject", ("dispatched_at", admin.EmptyFieldListFilter), ("voided_at", admin.EmptyFieldListFilter)]
    search_fields = ["label"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    """Staff grants: added here (source "staff grant"); book codes and purchases make their own."""

    list_display = ["__str__", "user", "subject", "source", "reference", "valid_until", "created"]
    list_filter = ["source", "subject"]
    search_fields = ["user__email", "reference"]
    raw_id_fields = ["user"]
    readonly_fields = ["source", "reference"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "subject")


@admin.register(BookCode)
class BookCodeAdmin(admin.ModelAdmin):
    """Codes are made by manage.py make_book_codes and only their hashes kept: search with a whole code to find it."""

    list_display = ["__str__", "subject", "batch", "created", "redeemed_at", "redeemed_by"]
    list_filter = ["batch", "subject", ("redeemed_at", admin.EmptyFieldListFilter)]
    search_fields = ["batch"]
    readonly_fields = ["subject", "batch", "created", "redeemed_by", "redeemed_at"]

    def has_add_permission(self, request):
        return False

    def get_search_results(self, request, queryset, search_term):
        if len(clean_code(search_term)) == CODE_LENGTH:
            return queryset.filter(digest=code_digest(search_term)), False
        return super().get_search_results(request, queryset, search_term)
