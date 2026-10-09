from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from import_export.admin import ExportMixin

from .models import EmailSuppression, SmsLog
from .sms import phone_hash

admin.site.index_template = "admin/dashboard.html"  # the app list with today's and the month's numbers above it
admin.site.site_header = admin.site.site_title = "ExamLeaf admin"
_has_permission = admin.site.has_permission


def has_permission(request):
    """The admin stays closed to staff whose roles are all the panel's newer ones (PACKER, FINANCE …: not in
    accounts.roles.ADMIN_SITE_ROLES): they work through the staff API, whose lists are scoped, and the admin's are
    not. The roles it was made for, superusers and staff without a role (who see nothing) open it as before."""
    from accounts.roles import ADMIN_SITE_ROLES, STAFF_ROLES

    if not _has_permission(request):
        return False
    held = set(request.user.groups.values_list("name", flat=True))
    return request.user.is_superuser or not (held & STAFF_ROLES) or bool(held & ADMIN_SITE_ROLES)


admin.site.has_permission = has_permission


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(admin.ModelAdmin):
    """Addresses the site no longer emails (bounces, complaints; ops.models). Delete a row to email the address again,
    once the student says it works (RUNBOOK.md "Email")."""

    list_display = ["email", "reason", "esp", "created"]
    list_filter = ["reason", "esp", "created"]
    search_fields = ["email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SmsLog)
class SmsLogAdmin(admin.ModelAdmin):
    """What the site texted, for support ("did my code go?"): search by the whole mobile number, which is hashed as the
    log keeps it. The log is written by ops.sms only."""

    list_display = ["created", "kind", "phone_last4", "status", "provider_id"]
    list_filter = ["status", "kind", "created"]
    search_fields = ["phone_hash"]
    search_help_text = "A whole mobile number, e.g. 98640 12345"

    def get_search_results(self, request, queryset, search_term):
        from accounts.forms import normalise_phone  # (accounts.admin imports this module)

        if not search_term:
            return queryset, False
        phone = normalise_phone(search_term)
        return queryset.filter(phone_hash=phone_hash(phone)) if phone else queryset.none(), False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
