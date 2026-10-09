"""The site's switches that the panel changes without a deploy (SiteSetting) and the feature flags (FeatureFlag). The
environment's value (settings.py) stands until the database says otherwise; a value set to null goes back to it.
`site_setting(key)` is what the code reads (config/, the shop's open and cash-on-delivery checks, the parent's consent
mode); each read is the cache's (a minute, or until the next scheduled change), cleared at every change."""

import re
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

FLAG_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


@dataclass(frozen=True)
class Spec:
    kind: object  # bool, str, or the list of allowed values
    label: str
    permission: str = "staff.manage_settings"
    default: object = None  # when settings.py has no such name

    def check(self, value):
        """The value, or ValueError with what is wrong; None is always allowed (the environment's value)."""
        if value is None:
            return value
        if isinstance(self.kind, list):
            if value not in self.kind:
                raise ValueError(f"One of: {', '.join(self.kind)}.")
        elif self.kind is bool:
            if not isinstance(value, bool):
                raise ValueError("true or false.")
        elif not isinstance(value, str) or len(value) > 300:
            raise ValueError("A text of 300 characters at most.")
        return value


SETTINGS = {
    "SHOP_OPEN": Spec(bool, "The shop is open: carts, checkout and payment for everyone (off: staff only)"),
    "SHOP_COD_ENABLED": Spec(bool, "Cash on delivery is offered"),
    "PARENTAL_CONSENT_MODE": Spec(
        ["declared", "verified"], "A parent's consent: ticked on the form, or verified through a link"
    ),
    "WEB_COURSE": Spec(bool, "The revision course's pages on the website"),
    "MAINTENANCE_MODE": Spec(
        bool, "Maintenance mode: the frontends show the banner", "staff.toggle_maintenance", False
    ),
    "MAINTENANCE_BANNER": Spec(str, "The maintenance banner's text", "staff.toggle_maintenance", ""),
    # Orders (shop.services.assess_risk)
    "SHOP_COD_HIGH_RISK_HOLD": Spec(bool, "A cash-on-delivery order scored high risk waits on hold for a check"),
}


def _active(model):
    """{key: value} of the rows in effect now (the newest `effective_from` that has come), cached."""
    key = f"staff:switches:{model._meta.model_name}"
    values = cache.get(key)
    if values is None:
        now, values = timezone.now(), {}
        rows = model.objects.filter(effective_from__lte=now).order_by("key", "-effective_from", "-pk")
        for name, value in rows.values_list("key", "value"):
            values.setdefault(name, value)
        upcoming = model.objects.filter(effective_from__gt=now).order_by("effective_from").first()
        seconds = (upcoming.effective_from - now).total_seconds() if upcoming else 60
        cache.set(key, values, max(1, min(60, int(seconds))))
    return values


def environment_value(key):
    return getattr(settings, key, SETTINGS[key].default)


def site_setting(key):
    """The value of one of SETTINGS: the database's if one is in effect, else the environment's."""
    from .models import SiteSetting

    value = _active(SiteSetting).get(key)
    return environment_value(key) if value is None else value


def feature_flag(key):
    """A feature flag's value (off, None, until set)."""
    from .models import FeatureFlag

    return _active(FeatureFlag).get(key)


def feature_flags():
    from .models import FeatureFlag

    return {key: value for key, value in _active(FeatureFlag).items() if value is not None}


def changed(model):
    cache.delete(f"staff:switches:{model._meta.model_name}")
