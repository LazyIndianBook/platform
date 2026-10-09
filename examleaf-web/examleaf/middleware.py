import ipaddress
import time
from datetime import UTC, datetime

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import constant_time_compare

from accounts.models import STAFF_SESSION


class FrontendClientMiddleware:
    """The Next.js frontend's server-side calls (examleaf-frontend/src/lib/api/server.ts) send the visitor's address in
    X-Forwarded-For and the shared secret INTERNAL_API_TOKEN in X-Internal-Token. With the right secret that address
    becomes REMOTE_ADDR (X-Forwarded-For is dropped), so DRF's throttles, axes, allauth's limits and the device list
    count the visitor: the frontend's own address is never one shared anonymous bucket (frontend review S4), and each
    visitor keeps their own limits. Without the secret, or with a wrong one, nothing changes (Caddy's requests rely on
    PROXY_COUNT as before); the header never goes further."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sent = request.META.pop("HTTP_X_INTERNAL_TOKEN", None)
        token = settings.INTERNAL_API_TOKEN
        if sent is not None and token and constant_time_compare(sent, token):
            client = request.META.pop("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
            try:
                request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(client))
            except ValueError:
                pass  # no address to speak for: the frontend's own
        return self.get_response(request)


class NullByteMiddleware:
    """A NUL byte in the address (a scanner's `%00`) names nothing here, and PostgreSQL refuses it in a query: answer
    404, not a 500 that Sentry reports (`/qr/AB%00C.png`, an order number, the API's detail pages)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "\x00" in request.path:
            raise Http404
        return self.get_response(request)


class PermissionsPolicyMiddleware:
    """Browser features the site never uses are switched off on every page (Permissions-Policy, I6); the payment
    request API only for the site's own pages (the payment page)."""

    POLICY = "camera=(), microphone=(), geolocation=(), payment=(self)"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", self.POLICY)
        return response


class PrivatePagesMiddleware:
    """What a signed-in user gets is not kept by the browser: after "Log out" on a shared computer (a cyber café) the
    Back button must not show their account, record or orders. Views that set their own Cache-Control (the API's
    solutions: private; its catalogue: public for a while) keep it. allauth.headless's answers (/_allauth/) are never
    kept: the app signs them in with a header this middleware does not see."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        private = request.user.is_authenticated or request.path.startswith("/_allauth/")
        if private and "Cache-Control" not in response:
            add_never_cache_headers(response)
        return response


MFA_SETUP = "Staff accounts need an authenticator app: set it up to go on."


def needs_mfa_setup(user):
    """A member of staff without an authenticator app or a passkey (H2)."""
    return user.is_staff and not is_mfa_enabled(user, [Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN])


# A member of staff's session (research 2.3): when it was signed in and last used, in the session itself.
STAFF_LOGIN_AT, STAFF_SEEN = "staff:login_at", "staff:seen"
SESSION_ENDED = {
    "idle": "Signed out after {minutes} minutes without activity: log in again.",
    "absolute": "Signed out: a staff session lasts {hours} hours. Log in again.",
}


def idle_limit(user):
    """Seconds without a request after which the person's staff session ends (plan 3.5): the shortest of their roles'
    (STAFF_IDLE_TIMEOUTS: 15 minutes for OWNER, ADMIN, FINANCE and PACKER), STAFF_IDLE_TIMEOUT (30 minutes) for any
    other role; a break-glass account (a superuser) has the shortest of all."""
    limits, default = settings.STAFF_IDLE_TIMEOUTS, settings.STAFF_IDLE_TIMEOUT
    if user.is_superuser:
        return min([default, *limits.values()])
    return min([limits.get(name, default) for name in user.role_names], default=default)


def absolute_expiry(session):
    """When a staff session ends at the latest: its expiry, or 8 hours after its log-in (accounts.models.STAFF_SESSION,
    the absolute limit a staff session is given at log-in)."""
    ends = session.get_expiry_date()
    if login_at := session.get(STAFF_LOGIN_AT):
        ends = min(ends, datetime.fromtimestamp(login_at, UTC) + STAFF_SESSION)
    return ends


class StaffMFAMiddleware:
    """A member of staff without an authenticator app or a passkey is sent to set one up (H2) before anything else
    opens: the admin and the staff pages (to the website's /account/2fa/, where the set-up is), the API with the
    session (403 in JSON there). Open meanwhile: allauth.headless's JSON flows (/_allauth/: the TOTP set-up, log-out,
    reauthentication) and the static files. The app's session token becomes no JWT pair either (api.auth.ExchangeView).

    Before that, a staff session ends after its idle limit without a request (idle_limit: 15 or 30 minutes by role)
    and 8 hours after its log-in: signed out, an API call is answered 401 with `code` "session_idle" or
    "session_expired", any other page goes on signed out (the admin then asks for a log-in).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user, path = request.user, request.path
        if user.is_authenticated and user.is_staff and not path.startswith(settings.STATIC_URL):
            limit = idle_limit(user)
            if why := self.ended(request, limit):
                code = "session_idle" if why == "idle" else "session_expired"
                hours = int(STAFF_SESSION.total_seconds() // 3600)
                detail = SESSION_ENDED[why].format(minutes=limit // 60, hours=hours)
                if path.startswith("/api/"):
                    return JsonResponse({"detail": detail, "code": code}, status=401)
                user = request.user  # signed out now: what follows sees an anonymous visitor
        open_during_setup = path.startswith((settings.STATIC_URL, "/_allauth/"))
        if user.is_authenticated and user.is_staff and not open_during_setup and needs_mfa_setup(user):
            if path.startswith("/api/"):
                return JsonResponse({"detail": MFA_SETUP, "code": "mfa_setup_required"}, status=403)
            return redirect(f"{settings.SITE_URL}/account/2fa/")
        return self.get_response(request)

    @staticmethod
    def ended(request, idle_seconds):
        """Sign the member of staff out if their session is idle or past its limit; returns why, or None. The time of
        the last request is written at most once a minute (the idle limit is then up to a minute longer)."""
        session, now = request.session, time.time()
        login_at, seen = session.get(STAFF_LOGIN_AT), session.get(STAFF_SEEN)
        if login_at is None:  # a session signed in before these were kept (or by force_login): from now
            session[STAFF_LOGIN_AT] = login_at = now
        why = None
        if seen is not None and now - seen > idle_seconds:
            why = "idle"
        elif now - login_at > STAFF_SESSION.total_seconds():
            why = "absolute"
        if why is None:
            if seen is None or now - seen > 60:
                session[STAFF_SEEN] = now
            return None
        from staff.audit import record  # (staff imports this module)

        record("session_expired", request=request, details={"why": why})
        request._staff_session_ended = why  # the log-out's own event is not recorded again (staff.signals)
        logout(request)
        return why
