from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import cache_page

from .models import Paper

OPEN_SOLUTIONS_MAX_AGE = 300  # seconds a shared cache may keep open solutions


def cache_solutions(response, user, sample=False):
    """The API's solutions (api.views): private while they depend on the log-in. Open solutions seen by a visitor
    (all of them with SOLUTIONS_REQUIRE_LOGIN=0, or a book's open sample) are the same for everyone: public for a few
    minutes."""
    if (settings.SOLUTIONS_REQUIRE_LOGIN and not sample) or user.is_authenticated:
        patch_cache_control(response, private=True)
    else:
        patch_cache_control(response, public=True, max_age=OPEN_SOLUTIONS_MAX_AGE)
    return response


@cache_page(86400)  # a day, in the cache and in browsers: it never changes, and drawing it costs a little each time
def qr_png(request, code):
    """/qr/<code>.png: the QR code printed on the paper, for the printing side; published papers only (I3)."""
    paper = get_object_or_404(Paper, code__iexact=code, is_published=True)
    return HttpResponse(paper.qr_image("png"), content_type="image/png")
