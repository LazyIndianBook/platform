"""The staff's endpoints answer on the admin host only (staff.middleware.STAFF_APIS: a 404 for everyone on any other
host). test_session.py proves the rule on two endpoints; this walks every route of the project, so that a module's new
staff endpoint mounted outside the rule's prefixes (a deployment hole: it would answer on the public host) fails here,
and so that no public endpoint is caught by the rule."""

import re

from django.urls import URLPattern, URLResolver, get_resolver

from staff.api import StaffView
from staff.middleware import STAFF_APIS


def routes(patterns=None, prefix=""):
    """(the route's text, its view) for every route of the project, the groups of included patterns joined."""
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(pattern, URLResolver):
            yield from routes(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


def request_path(route):
    """A path the route answers, near enough for the rule's prefixes: `^` and `$` dropped, the API's version group
    written v1, any other group or converter filled in with a value."""
    path = route.replace("^", "").replace("$", "")
    path = path.replace("(?P<version>v1)", "v1")
    path = re.sub(r"\(\?P<\w+>[^)]*\)", "1", path)
    return "/" + re.sub(r"<(?:\w+:)?\w+>", "x", path)


def test_every_staff_route_is_behind_the_admin_host_rule_and_no_public_one_is():
    staff, public = [], []
    for route, callback in routes():
        view = getattr(callback, "cls", None)
        (staff if view is not None and issubclass(view, StaffView) else public).append(request_path(route))
    assert len(staff) > 300, len(staff)  # the staff API, the shipping app's staff views and the insights'
    assert [path for path in staff if not STAFF_APIS.match(path)] == []
    # the rule catches no public endpoint (the checkout's shipping/ and shipping/quote/ among them) but the invitation's
    # link, which is no StaffView (its token is the credential, for people not yet staff) and belongs on the admin host
    assert [path for path in public if STAFF_APIS.match(path)] == ["/api/v1/staff/invites/accept/"]
