"""The integrations in the admin, read-mostly. An account's credentials are written and never shown (their last four
characters only); its connection test, a new webhook token (shown once), opening and resetting its circuit are actions.
The call log, the dead letters (replay, or discard with a reason) and the inbound events (replay) are records, never
edited."""

import json

from django import forms
from django.contrib import admin, messages
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.utils.html import format_html_join

from .crypto import SecretUnreadable
from .models import InboundEvent, IntegrationAccount, IntegrationCall, IntegrationFailure
from .services import test_connection


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records the site keeps (logs, events): viewed, never added, edited or deleted here."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def action_page(modeladmin, request, queryset, action, title, form):
    """An action's own form (a reason, a resolution) before it runs: integrations/admin/action_form.html."""
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "opts": modeladmin.model._meta,
        "queryset": queryset,
        "action": action,
        "form": form,
    }
    return render(request, "integrations/admin/action_form.html", context)


class AccountForm(forms.ModelForm):
    new_credentials = forms.CharField(
        label="Replace the credentials",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='JSON, as the provider needs them; Shiprocket: {"email": "…", "password": "…"} of its API user. '
        "Left empty, the stored ones stay. They are never shown again: test the connection after saving.",
    )

    class Meta:
        model = IntegrationAccount
        fields = ["provider", "mode", "label", "enabled", "rotate_by", "scopes", "where_else_configured"]

    def clean_new_credentials(self):
        text = self.cleaned_data["new_credentials"]
        if not text:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            raise forms.ValidationError('This is not JSON: {"name": "value", …}.') from None
        if not isinstance(data, dict) or not data or not all(isinstance(v, str) and v for v in data.values()):
            raise forms.ValidationError('A JSON object of texts, none empty: {"email": "…", "password": "…"}.')
        return data


@admin.register(IntegrationAccount)
class IntegrationAccountAdmin(admin.ModelAdmin):
    form = AccountForm
    list_display = ["__str__", "enabled", "circuit_state", "last_success_at", "last_error_at", "last_test_ok"]
    list_filter = ["provider", "mode", "enabled", "circuit_state"]
    search_fields = ["label"]
    readonly_fields = [
        *["secrets", "credentials_updated_at", "credentials_updated_by", "token_expires_at", "webhook_rotated_at"],
        *["last_success_at", "last_error_at", "last_error", "last_test_at", "last_test_ok", "last_test_message"],
        *["circuit_state", "held_open", "failure_count", "opened_at", "trial_started_at", "created", "modified"],
    ]
    fieldsets = [
        (None, {"fields": ["provider", "mode", "label", "enabled"]}),
        ("Credentials", {"fields": ["new_credentials", "secrets", "credentials_updated_at", "credentials_updated_by"]}),
        (None, {"fields": ["rotate_by", "scopes", "where_else_configured", "token_expires_at", "webhook_rotated_at"]}),
        ("Health", {"fields": readonly_fields[5:]}),
    ]
    actions = ["run_connection_test", "new_webhook_token", "hold_circuit_open", "reset_circuit"]

    @admin.display(description="stored secrets (last four characters)")
    def secrets(self, account):
        try:
            shown = account.masked()
        except SecretUnreadable:
            return 'Cannot be read with INTEGRATION_KEYS (RUNBOOK.md "Integration keys").'
        rows = [*shown["credentials"].items(), ("webhook token", shown["webhook_token"] or "none")]
        return format_html_join(", ", "{}: {}", rows) if rows else "none"

    def save_model(self, request, obj, form, change):
        if (data := form.cleaned_data.get("new_credentials")) is not None:
            obj.set_credentials(data, by=request.user)
        super().save_model(request, obj, form, change)

    @admin.action(description="Test the connection (a harmless read)", permissions=["change"])
    def run_connection_test(self, request, queryset):
        for account in queryset:
            ok, message = test_connection(account)
            level = messages.SUCCESS if ok else messages.WARNING if ok is None else messages.ERROR
            self.message_user(request, f"{account}: {message}", level)

    @admin.action(description="New webhook token (shown once)", permissions=["change"])
    def new_webhook_token(self, request, queryset):
        """The new tokens on a page of their own (never in a message, which the session would keep). The previous
        token still works for 24 hours: paste the new one at the provider within that time."""
        tokens = [(account, account.rotate_webhook_token()) for account in queryset]
        context = {**self.admin_site.each_context(request), "title": "New webhook tokens", "tokens": tokens}
        return TemplateResponse(request, "integrations/admin/webhook_token.html", context)

    @admin.action(description="Hold the circuit open (calls wait until reset)", permissions=["change"])
    def hold_circuit_open(self, request, queryset):
        for account in queryset:
            account.force_open()
        self.message_user(request, f"Held open: {len(queryset)} account(s). Calls wait until the circuit is reset.")

    @admin.action(description="Reset the circuit (calls go through)", permissions=["change"])
    def reset_circuit(self, request, queryset):
        for account in queryset:
            account.reset()
        self.message_user(request, f"Reset: {len(queryset)} account(s).")


@admin.register(IntegrationCall)
class IntegrationCallAdmin(ReadOnlyAdmin):
    list_display = ["created", "account", "operation", "method", "path", "status_code", "duration_ms", "error"]
    list_filter = ["account", "operation", "status_code"]
    search_fields = ["operation", "path", "provider_request_id", "error"]
    date_hierarchy = "created"


class DiscardForm(forms.Form):
    reason = forms.CharField(max_length=300, help_text="Why it is given up (kept with it).")


@admin.register(IntegrationFailure)
class IntegrationFailureAdmin(ReadOnlyAdmin):
    list_display = ["created", "operation", "account", "attempts", "state", "last_error"]
    list_filter = ["state", "operation", "account"]
    search_fields = ["operation", "task_name", "last_error"]
    actions = ["replay", "discard"]

    def has_resolve_permission(self, request):
        return request.user.has_perm("integrations.change_integrationfailure")

    @admin.action(description="Replay (run the task again, once)", permissions=["resolve"])
    def replay(self, request, queryset):
        replayed = [failure for failure in queryset if failure.replay(by=request.user)]
        self.message_user(request, f"Queued again: {len(replayed)} task(s) (dead letters already dealt with skipped).")

    @admin.action(description="Discard (with a reason)", permissions=["resolve"])
    def discard(self, request, queryset):
        form = DiscardForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            done = [f for f in queryset if f.discard(form.cleaned_data["reason"], by=request.user)]
            self.message_user(request, f"Discarded: {len(done)} dead letter(s).")
            return None
        return action_page(self, request, queryset, "discard", "Discard dead letters", form)


@admin.register(InboundEvent)
class InboundEventAdmin(ReadOnlyAdmin):
    list_display = ["received_at", "provider", "account", "state", "processed_at", "error"]
    list_filter = ["provider", "state"]
    search_fields = ["sha256", "error"]
    date_hierarchy = "received_at"
    actions = ["replay"]

    def has_replay_permission(self, request):
        return request.user.has_perm("integrations.change_inboundevent")

    @admin.action(description="Process again", permissions=["replay"])
    def replay(self, request, queryset):
        done = [event for event in queryset if event.replay()]
        self.message_user(request, f"Queued again: {len(done)} event(s) (rejected ones are never processed).")
