"""Who may call the staff API (deny by default, research 1.1): a member of staff on the panel's session (signed in
with a second factor; never the app's JWT, which carries no session for re-authentication or the idle timeout), or an
integration's API key. Every endpoint names the permission it needs per action (StaffView.permissions); high and
critical ones (staff.catalogue) need a re-authentication in the last 5 minutes, which an API key never has; objects
are reached only in scope (staff.backends). A refusal is recorded as `authz_fail` (staff.middleware)."""

import hashlib
import ipaddress
import secrets
from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import constant_time_compare
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions, permissions, throttling

from api.views import ReauthenticationRequired, recently_authenticated
from examleaf.middleware import BREAK_GLASS, needs_mfa_setup

from . import catalogue
from .models import ApiKey

KEY_PREFIX = "elk"


def make_key():
    """(the whole key, shown once; its prefix, kept visible; its SHA-256, kept)."""
    prefix = secrets.token_hex(4)
    key = f"{KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix, hashlib.sha256(key.encode()).hexdigest()


class ApiKeyUser:
    """The principal of an API key: holds exactly the key's permissions, is never staff, has no scopes."""

    is_active = is_authenticated = True
    is_anonymous = is_staff = is_superuser = is_owner = False
    pk = id = None

    def __init__(self, key):
        self.api_key = key
        self.role_names = {"INTEGRATION"}

    def __str__(self):
        return f"API key {self.api_key.prefix}"

    def has_perm(self, perm, obj=None):
        return perm in self.api_key.scopes

    def has_perms(self, perms, obj=None):
        return all(self.has_perm(perm, obj) for perm in perms)

    def get_all_permissions(self, obj=None):
        return set(self.api_key.scopes)


def allowed_from(key, ip):
    if not key.allowed_ips:
        return True
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(network, strict=False) for network in key.allowed_ips)


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """`Authorization: Api-Key elk_<prefix>_<secret>`: a key not revoked, not expired, from an allowed address."""

    keyword = "Api-Key"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="replace").split()
        if len(header) != 2 or header[0] != self.keyword:
            return None
        parts = header[1].split("_", 2)  # the secret may hold _ itself (token_urlsafe)
        key = ApiKey.objects.filter(prefix=parts[1]).first() if len(parts) == 3 and parts[0] == KEY_PREFIX else None
        if key is None or not constant_time_compare(hashlib.sha256(header[1].encode()).hexdigest(), key.secret_hash):
            raise exceptions.AuthenticationFailed("Not a valid API key.")
        if not key.is_usable:
            raise exceptions.AuthenticationFailed("This API key is revoked or expired.")
        ip = request.META.get("REMOTE_ADDR", "")
        if not allowed_from(key, ip):
            raise exceptions.AuthenticationFailed("This API key is not used from this address.")
        now = timezone.now()  # at most a write a minute per key
        ApiKey.objects.filter(pk=key.pk).exclude(last_used_at__gt=now - timedelta(minutes=1)).update(
            last_used_at=now, last_used_ip=ip or None
        )
        return ApiKeyUser(key), key

    def authenticate_header(self, request):
        return self.keyword


class ApiKeyScheme(OpenApiAuthenticationExtension):
    target_class = ApiKeyAuthentication
    name = "apiKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "Authorization", "description": "Api-Key elk_…"}


class IsStaff(permissions.BasePermission):
    """A member of staff, active, with a second factor (StaffMFAMiddleware sends the others to set one up); or a
    valid API key, whose permissions are then all it has."""

    message = "Staff only."

    def has_permission(self, request, view):
        user = request.user
        if isinstance(request.auth, ApiKey):
            return True
        return bool(user and user.is_authenticated and user.is_staff and user.is_active and not needs_mfa_setup(user))


ANY_STAFF = "any_staff"  # the manifest and the catalogue: every member of staff reads their own


class BreakGlassReasonRequired(exceptions.PermissionDenied):
    """A break-glass session (a superuser's) says why before anything but the manifest and the catalogue (research
    1.6): a step asked for, like a re-authentication, not a refusal."""

    default_detail = "A break-glass session gives its reason first: POST session/reason/."
    default_code = "break_glass_reason_required"


class StaffPermission(permissions.BasePermission):
    """The permission the view names for this action (or method); none named is refused (deny by default). A
    break-glass session's reason first (BreakGlassReasonRequired). Then a recent re-authentication when the catalogue's
    risk says so, or the view's `reauth` actions (approving, running); its `no_reauth` actions skip it (ending an
    impersonation)."""

    def has_permission(self, request, view):
        perm = view.required_permission(request)
        request._request._staff_perm = "" if perm == ANY_STAFF else perm or ""
        if perm == ANY_STAFF:
            return True
        if request.user.is_superuser and not request.session.get(BREAK_GLASS):
            raise BreakGlassReasonRequired()
        if not perm:
            self.message = "This endpoint names no permission for this: refused."
            return False
        if not request.user.has_perm(perm):
            self.message = f"You need the permission {perm} ({label(perm)})."
            return False
        name = getattr(view, "action", None)
        if (catalogue.needs_reauth(perm) or name in view.reauth) and name not in view.no_reauth:
            if isinstance(request.auth, ApiKey):
                self.message = f"{perm} is not for API keys."
                return False
            if not recently_authenticated(request):
                raise ReauthenticationRequired()
        return True

    def has_object_permission(self, request, view, obj):
        perm = view.object_permission(request, obj)
        return not perm or request.user.has_perm(perm, obj)


def label(perm):
    entry = catalogue.entry(perm)
    return entry.label if entry else "not catalogued"


class StaffThrottle(throttling.ScopedRateThrottle):
    """Per member of staff (or per API key), at the view's `throttle_scope` rate (api_settings: staff_*)."""

    def get_cache_key(self, request, view):
        if isinstance(request.auth, ApiKey):
            return self.cache_format % {"scope": self.scope, "ident": f"key-{request.auth.pk}"}
        return super().get_cache_key(request, view)
