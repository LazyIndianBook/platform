from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import Resolver404, resolve
from django.utils.cache import add_never_cache_headers


class NullByteMiddleware:
    """A NUL byte in the address (a scanner's `%00`) names nothing here, and PostgreSQL refuses it in a query: answer
    404, not a 500 that Sentry reports (`/s/AB%00C/`, `/qr/…`, an order number, the API's detail pages)."""

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
    """What a signed-in user sees is not kept by the browser: after "Log out" on a shared computer (a cyber café) the
    Back button must not show their account, record or orders. Views that set their own Cache-Control (the solutions
    pages: private; the catalogue: public for a while) keep it. allauth.headless's answers (/_allauth/) are never kept:
    the app signs them in with a header this middleware does not see."""

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


class StaffMFAMiddleware:
    """A member of staff without an authenticator app or a passkey is sent to set one up (H2) before anything else
    opens: the admin, the site, the API with the session (403 in JSON there). Open meanwhile: allauth's own pages
    (log-out, reauthentication, email confirmation; mfa_… for the set-up itself), allauth.headless's JSON flows
    (/_allauth/, its TOTP set-up included) and the static files. The app's session token becomes no JWT pair either
    (api.auth.ExchangeView)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.is_staff and not self.open_during_setup(request) and needs_mfa_setup(user):
            if request.path.startswith("/api/"):
                return JsonResponse({"detail": MFA_SETUP, "code": "mfa_setup_required"}, status=403)
            messages.info(request, MFA_SETUP)
            return redirect("mfa_activate_totp")
        return self.get_response(request)

    @staticmethod
    def open_during_setup(request):
        if request.path.startswith((settings.STATIC_URL, "/_allauth/")):
            return True
        try:
            name = resolve(request.path_info).url_name or ""
        except Resolver404:
            return False
        return name.startswith(("account_", "mfa_"))
