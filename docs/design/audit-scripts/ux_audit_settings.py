"""Audit-only settings (kept outside the project): the project's own settings as configured for development, then
DEBUG switched off at run time so that 404/403/500 render the site's own branded templates (Django's technical 404
page replaces them while DEBUG is on). Everything derived from DEBUG at import time (SMS_ENABLED, plain static
storage, report-only CSP, no secure cookies) stays as in development."""

from examleaf.settings import *  # noqa: F401,F403

DEBUG = False

# With DEBUG off, WhiteNoise would look in STATIC_ROOT only (no collectstatic here): keep serving from the source folders.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
