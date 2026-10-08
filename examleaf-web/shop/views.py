import hashlib
from functools import wraps

from axes.helpers import get_client_ip_address
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payments
from .models import (
    public_storage,
)


def hits(scope, who, seconds):
    """One more request of `who` (a client address, a hash) in `scope`, counted for `seconds` in Django's cache (Redis
    in production). Returns the count, or None when it cannot be read (Redis down)."""
    key = f"shop:rate:{scope}:{who}"
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, seconds)
        return 1


def too_many(request, seconds):
    response = render(request, "429.html", status=429)
    response["Retry-After"] = str(seconds)
    return response


def over_limit(request, scope, limit, seconds, while_down=False):
    """Counts the request for its client address: True over `limit` in `seconds`, and while the count cannot be read
    (Redis down), so the limit never just stops, unless `while_down` (Razorpay's webhooks must go on)."""
    count = hits(scope, get_client_ip_address(request), seconds)
    return (count is None and not while_down) or (count or 0) > limit


def rate_limit(scope, limit, seconds, while_down=False):
    """At most `limit` POSTs per client address in `seconds` (over_limit)."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST" and over_limit(request, scope, limit, seconds, while_down):
                return too_many(request, seconds)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


LOOKUPS_AN_HOUR = 10


def lookup_allowed(number, email):
    """Guests' order lookup (website and API), besides the limit per client address: at most LOOKUPS_AN_HOUR per email
    address and per order number, whatever address they come from; none while the counts cannot be read."""
    counts = [
        hits(f"lookup-{kind}", hashlib.sha256(value.lower().encode()).hexdigest(), 3600)  # no email in the cache
        for kind, value in (("email", email), ("number", number))
    ]
    return all(count is not None and count <= LOOKUPS_AN_HOUR for count in counts)


PUBLIC_FOLDERS = ("products/", "og/")  # the public storage's folders: pictures, their sizes, Open Graph images


@cache_control(public=True, max_age=31536000, immutable=True)  # a year: a new upload never reuses a name
def product_media(request, name):
    """The public storage's files while it is MEDIA_ROOT (no buckets: settings.STORAGES). Private uploads share that
    folder, so only PUBLIC_FOLDERS are sent, and no name that climbs out of them. Cached as the bucket's are."""
    if not name.startswith(PUBLIC_FOLDERS) or ".." in name.split("/"):
        raise Http404
    try:
        return FileResponse(public_storage().open(name))
    except FileNotFoundError as error:
        raise Http404 from error


QUOTE_SENT = "Thank you: we will email you a quotation."


def pdf_response(document):
    """An Invoice's or a CreditNote's PDF as a download (404 until the file has been made)."""
    if document is None or not document.pdf:
        raise Http404
    try:
        file = document.pdf.open("rb")
    except OSError as error:  # the file deleted, or its storage unreachable: as if not made yet, not a server error
        raise Http404 from error
    return FileResponse(file, as_attachment=True, filename=f"ExamLeaf-{document.number.replace('/', '-')}.pdf")


@csrf_exempt  # signed by Razorpay instead (X-Razorpay-Signature)
@require_POST
@rate_limit("webhook", 300, 60, while_down=True)
def razorpay_webhook(request):
    headers = request.headers
    if payments.handle_webhook(
        request.body, headers.get("X-Razorpay-Signature", ""), headers.get("X-Razorpay-Event-Id", "")
    ):
        return HttpResponse("ok")
    return HttpResponse("bad signature", status=400)
