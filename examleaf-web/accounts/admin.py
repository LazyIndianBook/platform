from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import forms as auth_forms
from import_export import resources
from import_export.admin import ExportMixin

from .models import User


class UserResource(resources.ModelResource):  # CSV export (no password hashes)
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "class_level", "board__short_name", "district", "date_of_birth",
                  "parent_name", "parent_contact", "consent_at", "created", "is_active")


class UserCreationForm(auth_forms.AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")


class UserChangeForm(auth_forms.UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(ExportMixin, auth_admin.UserAdmin):
    resource_classes = [UserResource]
    form, add_form = UserChangeForm, UserCreationForm
    ordering = ["-created"]
    list_display = ["email", "full_name", "class_level", "board", "district", "under_18", "created"]
    list_filter = ["class_level", "board", "is_staff", "is_active", "created"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["created", "modified", "last_login", "consent_at"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Student", {"fields": ["full_name", "phone", "class_level", "board", "district", "date_of_birth"]}),
        ("Parent or guardian", {"fields": ["parent_name", "parent_contact", "consent_at"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Dates", {"fields": ["last_login", "created", "modified"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"],
                             "fields": ["email", "full_name", "usable_password", "password1", "password2"]})]

    @admin.display(boolean=True)
    def under_18(self, obj):
        return obj.is_minor
