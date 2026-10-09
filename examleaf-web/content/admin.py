from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Board, Book, ClassLevel, ErrorReport, LegalDeposit, Paper, Question, ReviewTask, Solution, Subject

admin.site.register(Board, list_display=["short_name", "name", "state"])
admin.site.register(ClassLevel)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "board", "class_level"]
    list_filter = ["board", "class_level"]


@admin.register(Book)
class BookAdmin(SimpleHistoryAdmin):
    list_display = ["title", "subject", "edition", "slug", "isbn", "format", "published_on"]
    list_filter = ["subject", "format"]


@admin.register(Paper)
class PaperAdmin(SimpleHistoryAdmin):
    list_display = ["code", "book", "tier", "number", "full_marks", "is_published", "is_sample"]
    list_filter = ["book__subject", "tier", "is_published", "is_sample"]
    search_fields = ["code", "title"]

    def get_readonly_fields(self, request, obj=None):
        """On the site or not, the open sample or not: a publisher's (staff.publish_paper), as in the panel."""
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("staff.publish_paper"):
            fields += ["is_published", "is_sample"]
        return fields


class PanelOwned:
    """A question's or a solution's text goes through the panel's draft and review (content.review): here it is read
    only, but for the break-glass accounts (superusers), who pass every check anyway."""

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class SolutionInline(PanelOwned, admin.StackedInline):
    model = Solution


@admin.register(Question)
class QuestionAdmin(PanelOwned, SimpleHistoryAdmin):
    list_display = ["__str__", "marks_text", "is_alternative", "order", "is_published", "state"]
    list_filter = ["paper__book__subject", "paper__tier", "is_alternative", "is_published", "state"]
    list_select_related = ["paper"]
    search_fields = ["paper__code", "label", "text_md", "tags__name"]
    raw_id_fields = ["paper"]
    inlines = [SolutionInline]


@admin.register(Solution)
class SolutionAdmin(PanelOwned, SimpleHistoryAdmin):
    list_display = ["__str__", "state"]
    list_filter = ["question__paper__book__subject", "question__paper__tier", "state"]
    list_select_related = ["question__paper"]
    search_fields = ["question__paper__code", "question__label", "body_md"]
    raw_id_fields = ["question"]


class ReadOnly(admin.ModelAdmin):
    """The panel's records (its content module): for reading here."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ReviewTask)
class ReviewTaskAdmin(ReadOnly):
    list_display = ["label", "stage", "state", "submitted_by", "published_at", "created"]
    list_filter = ["state", "stage", "subject"]


@admin.register(ErrorReport)
class ErrorReportAdmin(ReadOnly):
    list_display = ["__str__", "category", "state", "subject", "printing", "spam", "created"]
    list_filter = ["state", "category", "spam", "subject"]
    exclude = ["email"]  # the reporter's address: the panel shows it masked


@admin.register(LegalDeposit)
class LegalDepositAdmin(ReadOnly):
    list_display = ["book", "edition", "library", "sent_on"]
    list_filter = ["library"]
