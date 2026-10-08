from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib import messages
from django.http import Http404
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
    pages: private; the catalogue: public for a while) keep it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated and "Cache-Control" not in response:
            add_never_cache_headers(response)
        return response


class StaffMFAMiddleware:
    """A member of staff without an authenticator app or a passkey is sent to set one up (H2) before anything else
    opens: the admin, the site, the API with the session. Open meanwhile: allauth's own pages (log-out,
    reauthentication, email confirmation; mfa_… for the set-up itself) and the static files."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.is_staff and not self.open_during_setup(request):
            if not is_mfa_enabled(user, [Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN]):
                messages.info(request, "Staff accounts need an authenticator app: set it up to go on.")
                return redirect("mfa_activate_totp")
        return self.get_response(request)

    @staticmethod
    def open_during_setup(request):
        if request.path.startswith(settings.STATIC_URL):
            return True
        try:
            name = resolve(request.path_info).url_name or ""
        except Resolver404:
            return False
        return name.startswith(("account_", "mfa_"))
