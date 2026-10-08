from django.http import Http404
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
