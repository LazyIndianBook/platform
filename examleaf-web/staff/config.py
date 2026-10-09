"""The site's switches that the panel changes without a deploy (SiteSetting) and the feature flags (FeatureFlag). The
environment's value (settings.py) stands until the database says otherwise; a value set to null goes back to it.
`site_setting(key)` is what the code reads (config/, the shop's open and cash-on-delivery checks, the parent's consent
mode); each read is the cache's (a minute, or until the next scheduled change), cleared at every change."""

import re
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_date

FLAG_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


@dataclass(frozen=True)
class Spec:
    kind: object  # bool, str, or the list of allowed values
    label: str
    permission: str = "staff.manage_settings"
    default: object = None  # when settings.py has no such name
    # Phase B: legal
    group: str = ""  # settings drawn together (the disclosures: staff/privacy_api.py)
    max_length: int = 300  # a text's
    validate: object = None  # a text's own check: raises ValueError with what is wrong

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
        elif not isinstance(value, str) or len(value) > self.max_length:
            raise ValueError(f"A text of {self.max_length:,} characters at most.")
        elif self.validate:
            self.validate(value)
        return value


def iso_date(value):
    try:
        valid = not value or parse_date(value) is not None
    except ValueError:  # well formed, not a day (2027-02-30)
        valid = False
    if not valid:
        raise ValueError("A date as YYYY-MM-DD, or empty.")


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
}

# Legal and privacy (Phase B): the e-commerce disclosures and the privacy contacts (E-Commerce Rules r.4(1), (2), (4)
# and (5); DPDP Rules r.9 and r.14(1); CERT-In's Directions, Annexure II), edited together on the panel's Disclosures
# page (staff/privacy_api.py) and shown by the website from config/ (all but CERT-In's contact). Until the panel sets
# one, settings.py's value stands: the seller's for the name, the address and customer care.
DISCLOSURES = "disclosures"
SETTINGS |= {
    "DISCLOSURE_LEGAL_NAME": Spec(str, "The legal name", group=DISCLOSURES),
    "DISCLOSURE_REGISTERED_ADDRESS": Spec(str, "The registered office's address", group=DISCLOSURES),
    "DISCLOSURE_OPERATING_ADDRESS": Spec(
        str, "The address it works from, when not the registered one", default="", group=DISCLOSURES
    ),
    "DISCLOSURE_CARE_PHONE": Spec(str, "Customer care's phone number", group=DISCLOSURES),
    "DISCLOSURE_CARE_EMAIL": Spec(str, "Customer care's email address", group=DISCLOSURES),
    "DISCLOSURE_CARE_HOURS": Spec(str, "Customer care's hours", default="", group=DISCLOSURES),
    "DISCLOSURE_GRIEVANCE_OFFICER": Spec(str, "The Grievance Officer's name", default="", group=DISCLOSURES),
    "DISCLOSURE_GRIEVANCE_DESIGNATION": Spec(str, "The Grievance Officer's designation", default="", group=DISCLOSURES),
    "DISCLOSURE_GRIEVANCE_CONTACT": Spec(
        str, "The Grievance Officer's email address and phone number", default="", group=DISCLOSURES
    ),
    "DISCLOSURE_NODAL_CONTACT": Spec(
        str, "The nodal contact person resident in India: name and contact", default="", group=DISCLOSURES
    ),
    "DISCLOSURE_RETURNS_PAGE": Spec(
        ["refunds", "shipping", "terms"],
        "The page of the return and refund terms",
        default="refunds",
        group=DISCLOSURES,
    ),
    "DISCLOSURE_RIGHTS_TEXT": Spec(
        str,
        "How to make a request about one's personal data, and what to give with it (published)",
        default="",
        group=DISCLOSURES,
        max_length=2000,
    ),
    "DATA_PROTECTION_OFFICER": Spec(
        str, "The contact person for personal data, quoted in every answer to a data request", group=DISCLOSURES
    ),
    "CERT_IN_POINT_OF_CONTACT": Spec(
        str, "CERT-In's point of contact (in the incident alerts; never on the website)", group=DISCLOSURES
    ),
    "NCH_STATUS": Spec(
        ["not_joined", "applied", "member"],
        "The National Consumer Helpline's convergence programme",
        default="not_joined",
        group=DISCLOSURES,
    ),
    "NCH_SINCE": Spec(str, "Applied or joined on (YYYY-MM-DD)", default="", group=DISCLOSURES, validate=iso_date),
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
