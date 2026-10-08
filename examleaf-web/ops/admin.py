from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from import_export.admin import ExportMixin

admin.site.index_template = "admin/dashboard.html"  # the app list with today's and the month's numbers above it
admin.site.site_header = admin.site.site_title = "ExamLeaf admin"


class LoggedExportMixin(ExportMixin):
    """django-import-export's admin export (only with the model's "export_…" permission: settings.py), and each export
    written to the admin log: who exported how many rows of which model, and when (M5)."""

    def get_data_for_export(self, request, queryset, **kwargs):
        data = super().get_data_for_export(request, queryset, **kwargs)
        LogEntry.objects.create(
            user=request.user,
            content_type=ContentType.objects.get_for_model(self.model),
            object_repr=f"Export of {len(data)} {self.opts.verbose_name_plural}",
            action_flag=CHANGE,
            change_message=f"Exported {len(data)} rows.",
        )
        return data
