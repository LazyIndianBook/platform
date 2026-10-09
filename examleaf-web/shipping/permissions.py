from rest_framework.permissions import BasePermission


class StaffOnly(BasePermission):
    """A placeholder for the staff app's catalogued permissions, which replace it: an active member of staff (who
    has an authenticator app: StaffMFAMiddleware answers 403 under /api/ otherwise). Deny by default."""

    message = "For staff only."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)
