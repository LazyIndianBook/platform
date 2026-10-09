"""Support in the Django admin, for superusers: read-only lists (the panel owns every flow: /support/). No contact
detail, message or file is shown here."""

from django.contrib import admin

from .models import SavedReply, Ticket


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(ReadOnly):
    list_display = ["number", "category", "source", "status", "received_at", "next_due_at", "ack_breached"]
    list_display += ["due_breached"]
    list_filter = ["status", "category", "source", "ack_breached", "due_breached"]
    search_fields = ["number", "nch_docket"]
    fields = [
        *["number", "source", "nch_docket", "category", "priority", "status", "language", "assignee", "order"],
        *["data_request", "received_at", "acknowledged_at", "first_response_at", "resolved_at", "closed_at"],
        *["ack_due_at", "due_at", "redress_due_at", "nch_due_at", "dpdp_due_at", "it_due_at", "ack_breached"],
        *["due_breached", "reopened_count", "complaint_copy_sent_at"],
    ]


@admin.register(SavedReply)
class SavedReplyAdmin(ReadOnly):
    list_display = ["title", "language", "modified", "deleted_at"]
    list_filter = ["language"]
