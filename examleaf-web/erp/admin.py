"""The ERPNext sync in the admin, read-mostly: the outbox (a dead row replayed, or discarded with a reason), the links,
the pull's cursors, the stock snapshots, the B2B mirrors and the reconciliation runs with their differences (resolved
with a note). The ERPNext account itself, its credentials, webhook secret, circuit and call log, are in Admin →
Integrations."""

from django import forms
from django.contrib import admin

from integrations.admin import ReadOnlyAdmin, action_page

from .models import (
    ErpCursor,
    ErpLink,
    ErpMirror,
    ErpOutbox,
    ErpReconciliationDifference,
    ErpReconciliationRun,
    ErpStockSnapshot,
)


class ReasonForm(forms.Form):
    reason = forms.CharField(max_length=300, help_text="Why it is given up (kept with its dead letter).")


class NoteForm(forms.Form):
    note = forms.CharField(max_length=300, help_text="What was done about it.")


@admin.register(ErpOutbox)
class ErpOutboxAdmin(ReadOnlyAdmin):
    list_display = ["id", "created", "event", "examleaf_ref", "aggregate", "state", "attempts", "next_at", "last_error"]
    list_filter = ["state", "event", "aggregate_type"]
    search_fields = ["examleaf_ref", "aggregate_id"]
    date_hierarchy = "created"
    actions = ["replay", "discard"]

    @admin.display(description="aggregate", ordering="aggregate_id")
    def aggregate(self, row):
        return f"{row.aggregate_type} {row.aggregate_id} #{row.sequence}"

    def has_resolve_permission(self, request):
        return request.user.has_perm("erp.replay_sync")

    @admin.action(description="Replay (send again now, from its first try)", permissions=["resolve"])
    def replay(self, request, queryset):
        done = [row for row in queryset if row.replay(by=request.user)]
        self.message_user(request, f"Queued again: {len(done)} row(s) (rows neither dead nor failing skipped).")

    @admin.action(description="Discard (with a reason: its aggregate goes on)", permissions=["resolve"])
    def discard(self, request, queryset):
        form = ReasonForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            done = [row for row in queryset if row.discard(form.cleaned_data["reason"], by=request.user)]
            self.message_user(request, f"Discarded: {len(done)} dead row(s) (others skipped).")
            return None
        return action_page(self, request, queryset, "discard", "Discard dead rows", form)


@admin.register(ErpLink)
class ErpLinkAdmin(ReadOnlyAdmin):
    list_display = ["examleaf_ref", "doctype", "name", "model", "object_id", "synced_at"]
    list_filter = ["doctype", "model"]
    search_fields = ["examleaf_ref", "name"]


@admin.register(ErpCursor)
class ErpCursorAdmin(ReadOnlyAdmin):
    list_display = ["doctype", "modified_after", "last_name", "rows_read", "last_run_at", "last_error"]
    search_fields = ["doctype"]


@admin.register(ErpStockSnapshot)
class ErpStockSnapshotAdmin(ReadOnlyAdmin):
    list_display = ["item_code", "product", "warehouse", "actual", "projected", "as_of"]
    list_filter = ["warehouse"]
    search_fields = ["item_code", "product__title"]


@admin.register(ErpMirror)
class ErpMirrorAdmin(ReadOnlyAdmin):
    list_display = ["doctype", "name", "status", "modified", "fetched_at"]
    list_filter = ["doctype", "status"]
    search_fields = ["name", "examleaf_ref"]


class DifferenceInline(admin.TabularInline):
    model = ErpReconciliationDifference
    fields = ["kind", "key", "platform_value", "erp_value", "note", "resolved_at", "resolved_by"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ErpReconciliationRun)
class ErpReconciliationRunAdmin(ReadOnlyAdmin):
    list_display = ["date", "state", "differences_count", "started_at", "finished_at", "error"]
    list_filter = ["state"]
    search_fields = ["error"]
    date_hierarchy = "date"
    inlines = [DifferenceInline]


@admin.register(ErpReconciliationDifference)
class ErpReconciliationDifferenceAdmin(ReadOnlyAdmin):
    list_display = ["run", "kind", "key", "platform_value", "erp_value", "resolved_at", "note"]
    list_filter = ["kind", ("resolved_at", admin.EmptyFieldListFilter)]
    search_fields = ["key", "note"]
    actions = ["resolve"]

    def has_resolve_permission(self, request):
        return request.user.has_perm("erp.resolve_difference")

    @admin.action(description="Resolve (with a note)", permissions=["resolve"])
    def resolve(self, request, queryset):
        form = NoteForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            done = [d for d in queryset if d.resolve(form.cleaned_data["note"], by=request.user)]
            self.message_user(request, f"Resolved: {len(done)} difference(s) (resolved ones skipped).")
            return None
        return action_page(self, request, queryset, "resolve", "Resolve differences", form)
