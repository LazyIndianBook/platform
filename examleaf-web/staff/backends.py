"""Scopes: which objects a permission reaches (research 1.9). `scoped(queryset, user, perm)` narrows a queryset to
them and every staff viewset's get_queryset goes through it (DRF applies object permissions neither to lists nor to
creates); ScopeBackend answers `user.has_perm(perm, obj)` the same way for one object (Django's ModelBackend answers
False for any object). One rule for both: with the model permission, an object is in scope unless a scope kind that
applies to its model narrows the person, by their StaffScope rows of that kind or, without any, by the roles that give
them the permission when all of those are scoped (accounts.roles.ROLE_SCOPES)."""

from django.contrib.auth.backends import BaseBackend
from django.db.models import Q
from django.utils import timezone

from accounts.roles import ROLE_SCOPES

from .models import StaffScope

SUBJECT = StaffScope.Kind.SUBJECT
BOARD_CLASS = StaffScope.Kind.BOARD_CLASS
ORDER_STATUS = StaffScope.Kind.ORDER_STATUS
SCHOOL = StaffScope.Kind.SCHOOL
TICKET_QUEUE = StaffScope.Kind.TICKET_QUEUE
# StaffScope.Kind.WAREHOUSE applies to no model yet: stock and warehouses live in ERPNext (the plan's 3.1); the panel's
# stock views will name their field here.


def _content(subject):
    """A model under the subject tree: the path to its Subject ("" for Subject itself)."""
    return {SUBJECT: f"{subject}code", BOARD_CLASS: subject}


def _order(order):
    return {ORDER_STATUS: f"{order}status"}


# Model (app_label.model_name) → scope kind → the path to the field (for board_class: to the Subject).
MODEL_SCOPES = {
    "content.subject": _content(""),
    "content.book": _content("subject__"),
    "content.paper": _content("book__subject__"),
    "content.question": _content("paper__book__subject__"),
    "content.solution": _content("question__paper__book__subject__"),
    "learn.chapter": _content("subject__"),
    "learn.revision": _content("chapter__subject__"),
    "learn.clip": _content("revision__chapter__subject__"),
    "learn.flashcard": _content("chapter__subject__"),
    "learn.quizitem": _content("chapter__subject__"),
    "learn.bookcode": _content("subject__"),
    "learn.entitlement": _content("subject__"),
    "shop.product": _content("subject__"),
    "shop.order": _order(""),
    **{f"shop.{model}": _order("order__") for model in ["orderitem", "orderdiscount", "ordernote", "shipment"]},
    **{f"shop.{model}": _order("order__") for model in ["payment", "refund"]},
    "shop.quoterequest": {SCHOOL: "school"},
    "accounts.teacherprofile": {SCHOOL: "school_name"},
    "staff.inboxitem": {TICKET_QUEUE: "kind"},
}


def _condition(kind, path, values):
    if kind == BOARD_CLASS:  # "ASSEB:12": the board's short name and the class
        condition = Q(pk__in=[])
        for value in values:
            board, _, number = value.partition(":")
            if number.isdigit():
                condition |= Q(**{f"{path}board__short_name": board, f"{path}class_level__number": int(number)})
        return condition
    if kind == SCHOOL:  # schools are typed by hand: any case
        condition = Q(pk__in=[])
        for value in values:
            condition |= Q(**{f"{path}__iexact": value})
        return condition
    return Q(**{f"{path}__in": values})


def staff_scopes(user):
    """{kind: values} of the person's StaffScope rows not yet expired, read once per user object."""
    if not hasattr(user, "_staff_scopes"):
        rows = StaffScope.objects.filter(user=user).filter(Q(expires_at=None) | Q(expires_at__gt=timezone.now()))
        scopes = {}
        for kind, value in rows.values_list("kind", "value"):
            scopes.setdefault(kind, set()).add(value)
        user._staff_scopes = scopes
    return user._staff_scopes


def granting_roles(user, perm):
    """The person's roles whose group holds `perm` (direct user permissions are not used: roles are groups)."""
    cache = user.__dict__.setdefault("_granting_roles", {})
    if perm not in cache:
        app_label, _, codename = perm.partition(".")
        groups = user.groups.filter(permissions__content_type__app_label=app_label, permissions__codename=codename)
        cache[perm] = set(groups.values_list("name", flat=True))
    return cache[perm]


def scope_values(user, perm, kind):
    """The values of `kind` that `user` is narrowed to with `perm`, or None (no narrowing of that kind)."""
    if values := staff_scopes(user).get(kind):
        return values
    roles = granting_roles(user, perm)
    if roles and all(kind in ROLE_SCOPES.get(role, {}) for role in roles):
        return {value for role in roles for value in ROLE_SCOPES[role][kind]}
    return None


def scoped(queryset, user, perm):
    """The objects of `queryset` that `user` reaches with `perm`: none without the permission, every one for a
    superuser or an API key (whose permissions are its whole grant), else narrowed by each scope kind that applies."""
    if not user.has_perm(perm):
        return queryset.none()
    if user.is_superuser or getattr(user, "api_key", None) is not None:
        return queryset
    for kind, path in MODEL_SCOPES.get(queryset.model._meta.label_lower, {}).items():
        values = scope_values(user, perm, kind)
        if values is not None:
            queryset = queryset.filter(_condition(kind, path, values))
    return queryset


class ScopeBackend(BaseBackend):
    """`user.has_perm(perm, obj)`: True only with the model permission and `obj` in scope (`scoped`). Without an
    object it answers nothing (ModelBackend does). Authenticates nobody."""

    def has_perm(self, user_obj, perm, obj=None):
        if obj is None or not user_obj.is_active or not user_obj.has_perm(perm):
            return False
        return scoped(type(obj)._default_manager.filter(pk=obj.pk), user_obj, perm).exists()
