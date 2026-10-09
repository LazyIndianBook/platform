from rest_framework import permissions


class StaffOnly(permissions.BasePermission):
    """An active member of staff. A placeholder: the staff app is to replace it with its catalogued permissions."""

    message = "For staff only."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)
