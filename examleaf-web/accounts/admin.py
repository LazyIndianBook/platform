from django.contrib import admin, messages
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.models import Group
from django.utils import timezone
from import_export import resources

from ops.admin import LoggedExportMixin

from . import roles
from .models import ConsentRecord, DeletionRequest, TeacherProfile, User


class UserResource(resources.ModelResource):  # CSV export: no password hashes, no dates of birth or parents' contacts
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "phone",
            "class_level",
            "board__short_name",
            "district",
            "parent_name",
            "consent_at",
            "created",
            "is_active",
        )


class UserCreationForm(auth_forms.AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")


class UserChangeForm(auth_forms.UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


def set_role(user, role, add):
    """Add or remove a role; staff roles also open (or, when the last one goes, close) the admin for the user."""
    group = Group.objects.get_or_create(name=role)[0]
    (user.groups.add if add else user.groups.remove)(group)
    if role in roles.STAFF_ROLES:
        user.is_staff = user.is_superuser or user.groups.filter(name__in=roles.STAFF_ROLES).exists()
        user.save(update_fields=["is_staff"])


def role_action(role, add):
    def action(modeladmin, request, queryset):
        for user in queryset:
            set_role(user, role, add)
        modeladmin.message_user(request, f"{role}: {'given to' if add else 'taken from'} {len(queryset)} user(s).")

    action.__name__ = f"{'add' if add else 'remove'}_role_{role.lower()}"
    return admin.action(description=f"{'Give' if add else 'Take away'} role {role}", permissions=["assign_roles"])(
        action
    )


@admin.register(User)
class UserAdmin(LoggedExportMixin, auth_admin.UserAdmin):
    resource_classes = [UserResource]
    form, add_form = UserChangeForm, UserCreationForm
    ordering = ["-created"]
    list_display = ["email", "full_name", "class_level", "board", "district", "under_18", "created"]
    list_filter = ["groups", "class_level", "board", "is_staff", "is_active", "created"]
    search_fields = ["email", "full_name", "login_phone"]
    readonly_fields = ["created", "modified", "last_login", "consent_at"]
    actions = [role_action(role, add) for add in (True, False) for role in roles.ROLES]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Student", {"fields": ["full_name", "phone", "class_level", "board", "district", "date_of_birth"]}),
        # a lost or recycled number (RUNBOOK.md "SMS"): empty login_phone and untick both
        ("Log-in by SMS", {"fields": ["login_phone", "login_phone_verified", "sms_updates"]}),
        ("Parent or guardian", {"fields": ["parent_name", "parent_contact", "consent_at"]}),
        ("Roles and permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Dates", {"fields": ["last_login", "created", "modified"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "full_name", "usable_password", "password1", "password2"]})
    ]

    @admin.display(boolean=True)
    def under_18(self, obj):
        return obj.is_minor

    def has_assign_roles_permission(self, request):  # roles carry permissions: only those who may edit groups
        return request.user.has_perm("auth.change_group")

    def get_readonly_fields(self, request, obj=None):  # who may do what is for superusers to decide (I7)
        fields = super().get_readonly_fields(request, obj)
        return fields if request.user.is_superuser else [*fields, "is_superuser", "groups", "user_permissions"]

    def has_change_permission(self, request, obj=None):  # and only a superuser changes a superuser (password too)
        allowed = super().has_change_permission(request, obj)
        return allowed and (request.user.is_superuser or not (obj and obj.is_superuser))


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "school_name", "district", "subject", "verified", "created"]
    list_filter = ["verified", "created"]
    list_select_related = ["user"]
    search_fields = ["user__email", "user__full_name", "school_name", "district"]
    raw_id_fields = ["user"]
    readonly_fields = ["verified", "verified_at", "verified_by", "created", "modified"]
    fields = ["user", "school_name", "district", "subject", "verification_note", *readonly_fields]
    actions = ["verify", "revoke"]

    @admin.action(description="Verify: give the TEACHER role", permissions=["change"])
    def verify(self, request, queryset):
        for profile in queryset.filter(verified=False):
            profile.verified, profile.verified_at, profile.verified_by = True, timezone.now(), request.user
            profile.save()
            set_role(profile.user, roles.TEACHER, add=True)
        self.message_user(request, "Verified. Add a note on how each was checked.", messages.SUCCESS)

    @admin.action(description="Revoke: take away the TEACHER role", permissions=["change"])
    def revoke(self, request, queryset):
        for profile in queryset.filter(verified=True):
            profile.verified, profile.verified_at, profile.verified_by = False, None, None
            profile.save()
            set_role(profile.user, roles.TEACHER, add=False)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records that are evidence (consents) or that the site manages (deletion requests): viewed, never edited."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ConsentRecordResource(resources.ModelResource):
    class Meta:
        model = ConsentRecord
        fields = (
            *("id", "user__email", "event", "purpose", "notice_version", "by_parent", "method", "verified_at"),
            *("ip_hash", "created"),
        )


@admin.register(ConsentRecord)
class ConsentRecordAdmin(LoggedExportMixin, ReadOnlyAdmin):
    resource_classes = [ConsentRecordResource]
    list_display = ["user", "event", "purpose", "notice_version", "by_parent", "method", "created"]
    list_filter = ["event", "by_parent", "method", "notice_version", "created"]
    list_select_related = ["user"]
    search_fields = ["user__email"]
    date_hierarchy = "created"


@admin.register(DeletionRequest)
class DeletionRequestAdmin(ReadOnlyAdmin):
    list_display = ["user", "status", "requested_at", "due_at", "closed_at"]
    list_filter = ["status", "due_at"]
    list_select_related = ["user"]
    search_fields = ["user__email"]
