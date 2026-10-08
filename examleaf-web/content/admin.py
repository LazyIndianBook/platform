from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Board, Book, ClassLevel, Paper, Question, Solution, Subject

admin.site.register(Board, list_display=["short_name", "name", "state"])
admin.site.register(ClassLevel)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "board", "class_level"]
    list_filter = ["board", "class_level"]


@admin.register(Book)
class BookAdmin(SimpleHistoryAdmin):
    list_display = ["title", "subject", "edition", "slug"]
    list_filter = ["subject"]


@admin.register(Paper)
class PaperAdmin(SimpleHistoryAdmin):
    list_display = ["code", "book", "tier", "number", "full_marks", "is_published", "is_sample"]
    list_filter = ["book__subject", "tier", "is_published", "is_sample"]
    list_editable = ["is_published"]
    search_fields = ["code", "title"]


class SolutionInline(admin.StackedInline):
    model = Solution


@admin.register(Question)
class QuestionAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "marks_text", "is_alternative", "order"]
    list_filter = ["paper__book__subject", "paper__tier", "is_alternative"]
    list_select_related = ["paper"]
    search_fields = ["paper__code", "label", "text_md", "tags__name"]
    raw_id_fields = ["paper"]
    inlines = [SolutionInline]


@admin.register(Solution)
class SolutionAdmin(SimpleHistoryAdmin):
    list_filter = ["question__paper__book__subject", "question__paper__tier"]
    list_select_related = ["question__paper"]
    search_fields = ["question__paper__code", "question__label", "body_md"]
    raw_id_fields = ["question"]
