"""The panel's records in the Django admin, read-only (they change through the staff API, which audits each change;
the audit log itself is read there only, where each read is logged), but for the processor register."""

from django.contrib import admin

from accounts.admin import ReadOnlyAdmin

from .models import (
    ApiKey,
    ChangeRequest,
    DataRequest,
    FeatureFlag,
    Incident,
    ProcessorRecord,
    RoleGrant,
    SiteSetting,
    StaffInvite,
    StaffScope,
)


@admin.register(ChangeRequest)
class ChangeRequestAdmin(ReadOnlyAdmin):
    list_display = ["id", "action", "target_label", "amount", "maker", "status", "created", "expires_at"]
    list_filter = ["status", "action", "created"]
    search_fields = ["target_label", "action"]


@admin.register(DataRequest)
class DataRequestAdmin(ReadOnlyAdmin):
    list_display = ["id", "kind", "channel", "status", "received_at", "ack_due_at", "due_at", "closed_at"]
    list_filter = ["status", "kind", "channel"]
    search_fields = ["summary"]


@admin.register(Incident)
class IncidentAdmin(ReadOnlyAdmin):
    list_display = ["id", "title", "kind", "detected_at", "cert_in_reported_at", "board_report_at", "closed_at"]
    list_filter = ["kind", "children_affected"]
    search_fields = ["title"]


@admin.register(ProcessorRecord)
class ProcessorRecordAdmin(admin.ModelAdmin):
    list_display = ["name", "purpose", "country", "contract_signed_on", "contract_ends_on", "active"]
    list_filter = ["active", "country"]
    search_fields = ["name", "purpose"]


@admin.register(SiteSetting, FeatureFlag)
class SwitchAdmin(ReadOnlyAdmin):
    list_display = ["key", "value", "effective_from", "changed_by", "reason"]
    list_filter = ["key"]
    search_fields = ["key"]


@admin.register(ApiKey)
class ApiKeyAdmin(ReadOnlyAdmin):
    list_display = ["prefix", "name", "sponsor", "expires_at", "last_used_at", "revoked_at"]
    search_fields = ["name", "prefix"]
    exclude = ["secret_hash"]


@admin.register(StaffInvite)
class StaffInviteAdmin(ReadOnlyAdmin):
    list_display = ["id", "role", "invited_by", "created", "expires_at", "accepted_at", "revoked_at"]
    list_filter = ["role"]
    exclude = ["token_hash", "email"]


@admin.register(StaffScope, RoleGrant)
class AccessAdmin(ReadOnlyAdmin):
    list_select_related = ["user"]
    search_fields = ["user__email"]
