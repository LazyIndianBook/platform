from django.contrib import admin
from import_export import resources
from import_export.admin import ExportMixin

from .models import AnswerSheetUpload, Attempt


class AttemptResource(resources.ModelResource):  # CSV export
    class Meta:
        model = Attempt
        fields = ("id", "user__email", "user__full_name", "paper__code", "date", "marks_obtained",
                  "time_taken_minutes", "notes", "created")


@admin.register(Attempt)
class AttemptAdmin(ExportMixin, admin.ModelAdmin):
    resource_classes = [AttemptResource]
    list_display = ["user", "paper", "date", "marks_obtained", "time_taken_minutes"]
    list_filter = ["paper__book__subject", "paper__tier", "date"]
    list_select_related = ["user", "paper"]
    search_fields = ["user__email", "paper__code"]
    raw_id_fields = ["user", "paper"]
    date_hierarchy = "date"


@admin.register(AnswerSheetUpload)
class AnswerSheetUploadAdmin(admin.ModelAdmin):
    list_display = ["user", "paper", "status", "created"]
    list_filter = ["status", "paper__book__subject"]
    raw_id_fields = ["user", "paper"]
    readonly_fields = ["status_changed", "created", "modified"]
