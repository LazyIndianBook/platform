"""ExamLeaf web settings. Deployment values come from the environment or a .env file (see .env.example)."""

import sys
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
from django.utils.csp import CSP
from django_guid.integrations import CeleryIntegration
from pythonjsonlogger.core import RESERVED_ATTRS

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY")
SECRET_KEY_FALLBACKS = env.list("SECRET_KEY_FALLBACKS", default=[])  # old keys while rotating (RUNBOOK.md)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")  # base of the URLs inside the QR codes
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[SITE_URL])
TESTING = sys.argv[1:2] == ["test"] or "pytest" in sys.modules  # manage.py test, or pytest
# Where book.py and the Markdown papers live (the book repository root).
BOOK_ROOT = Path(env("BOOK_ROOT", default=str(BASE_DIR.parent)))
# The solutions behind the QR codes (/s/<CODE>/ and the API): for signed-in students only (1), or open to everyone (0;
# then only saving marks needs an account). README "Open or registered solutions" explains the trade-off.
SOLUTIONS_REQUIRE_LOGIN = env.bool("SOLUTIONS_REQUIRE_LOGIN", default=True)

INSTALLED_APPS = [
    "admin_interface",  # admin theme (before django.contrib.admin); ExamLeaf colours set in ops/migrations
    "colorfield",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "allauth",
    "allauth.account",
    "axes",
    "simple_history",
    "taggit",
    "widget_tweaks",
    "phonenumber_field",
    "import_export",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "django_guid",
    "health_check",
    "accounts",
    "content",
    "practice",
    "pages",
    "ops",
    "djmoney",
    "shop",  # after ops: its admin index template extends the ops dashboard
]

MIDDLEWARE = [
    "django_guid.middleware.guid_middleware",  # request ID (X-Request-ID from the proxy, or new), in every log line
    "examleaf.middleware.NullByteMiddleware",  # %00 in an address: 404 (PostgreSQL would fail with a 500)
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "examleaf.middleware.PrivatePagesMiddleware",  # a signed-in user's pages are not kept by the browser (log-out)
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "axes.middleware.AxesMiddleware",  # keep last
]

DEBUG_TOOLBAR = DEBUG and not TESTING
if DEBUG_TOOLBAR:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]

ROOT_URLCONF = "examleaf.urls"
WSGI_APPLICATION = "examleaf.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "examleaf.context_processors.site",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
# Persistent connections (one per gunicorn worker or Celery process, checked before reuse) rather than a pool: the
# sync workers serve one request at a time, so a pool would hold the same number of connections.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# CACHE_URL=redis://… uses django-redis; without it, the local-memory cache (one per process). With Redis down every
# cache call gives up within a second and counts as a miss (logged): pages keep working, rate limits and throttles
# let requests through meanwhile (sessions and axes are in the database), and /health/ reports the cache.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}
REDIS_CACHE_OPTIONS = {"SOCKET_CONNECT_TIMEOUT": 1, "SOCKET_TIMEOUT": 1, "IGNORE_EXCEPTIONS": True}
if CACHES["default"]["BACKEND"] == "django_redis.cache.RedisCache":
    CACHES["default"]["BACKEND"] = "examleaf.cache.SoftRedisCache"  # also for allauth's locks, see examleaf/cache.py
    CACHES["default"]["OPTIONS"] = {**REDIS_CACHE_OPTIONS, **CACHES["default"].get("OPTIONS", {})}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "home"

# django-allauth: email is the login, verified by a code typed on the same page (phone friendly).
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_FORMS = {"signup": "accounts.forms.SignupForm"}
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"  # sends allauth's emails through a Celery task
ACCOUNT_CHANGE_EMAIL = True  # one address: a new one replaces it only once its emailed code is confirmed
ACCOUNT_EMAIL_NOTIFICATIONS = True  # the old address is told of email and password changes
ACCOUNT_REAUTHENTICATION_REQUIRED = True  # password again (if not entered in the last 5 minutes) before such changes
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[ExamLeaf] "
ACCOUNT_LOGOUT_REDIRECT_URL = "home"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if SITE_URL.startswith("https") else "http"

# django-axes: lock an account for 15 minutes after 10 failed logins from one address.
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_CALLABLE = "accounts.forms.axes_username"
AXES_RESET_ON_SUCCESS = True
# keep failed attempts only, as the privacy policy says: no IP/browser record of good logins
AXES_DISABLE_ACCESS_LOG = True

# Reverse proxy (Caddy in docker-compose.yml): PROXY_COUNT=1 trusts its X-Forwarded-Proto/-For headers.
PROXY_COUNT = env.int("PROXY_COUNT", default=0)
USE_X_FORWARDED_HOST = env.bool("USE_X_FORWARDED_HOST", default=False)
if PROXY_COUNT:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    AXES_IPWARE_PROXY_COUNT = PROXY_COUNT
    AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")
if not DEBUG:  # secure by default; behind a proxy that already redirects, SECURE_SSL_REDIRECT=0 turns the redirect off
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not TESTING)
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# Content-Security-Policy: scripts, styles and fonts only from this site and from KaTeX on jsDelivr (the one third-party
# file set the site loads; keep the version in step with templates/solutions.html). jsDelivr serves any npm package, so
# only the KaTeX folder is allowed, not the host. 'unsafe-inline' is for styles only (admin add-ons' style attributes).
KATEX_CDN = "https://cdn.jsdelivr.net/npm/katex@0.19.0/dist/"
CONTENT_SECURITY_POLICY = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, KATEX_CDN],
    "style-src": [CSP.SELF, KATEX_CDN, CSP.UNSAFE_INLINE],
    "font-src": [CSP.SELF, KATEX_CDN],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}
# report-only in development: the debug toolbar needs inline scripts; the browser console still lists violations
if DEBUG:
    SECURE_CSP_REPORT_ONLY = CONTENT_SECURITY_POLICY
else:
    SECURE_CSP = CONTENT_SECURITY_POLICY

# Request sizes. Caddy refuses bodies over 10 MB. Django: at most 1 MB of form or JSON data (files not counted; the API
# answers 413), at most 10 files in one request; an upload over 2.5 MB is streamed to a temporary file instead of
# being held in memory. An upload view must still check its file's size and type.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FILES = 10
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440

# Email (Django 6.1 mailers): console in development; an ESP through django-anymail in production (ANYMAIL_* variables).
# The variable keeps its old name, EMAIL_BACKEND.
MAILERS = {"default": {"BACKEND": env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")}}
ANYMAIL = {k.removeprefix("ANYMAIL_"): v for k, v in env.ENVIRON.items() if k.startswith("ANYMAIL_")}
DEFAULT_FROM_EMAIL = SERVER_EMAIL = env("DEFAULT_FROM_EMAIL", default="ExamLeaf <noreply@localhost>")

# Celery (examleaf/celery.py). Without a broker, and always in tests, tasks run inline in the web process.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
CELERY_TASK_ALWAYS_EAGER = TESTING or env.bool("CELERY_TASK_ALWAYS_EAGER", default=not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = True
# An unreachable Redis fails at once and a half-open one (accepts the connection, never answers) within seconds, not
# never: queueing an email then falls back to sending it in the web process (ops/tasks.py), not a hung request.
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 2, "socket_timeout": 2}
CELERY_TASK_PUBLISH_RETRY_POLICY = {"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5}
CELERY_RESULT_BACKEND = "django-db"  # django-celery-results; beat removes results after CELERY_RESULT_EXPIRES
CELERY_RESULT_EXPIRES = timedelta(days=7)
CELERY_TASK_TIME_LIMIT = 300
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # keep the JSON logging below
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"  # editable in the admin
CELERY_BEAT_SCHEDULE = {  # written into the beat tables at start-up
    "purge-due-account-deletions": {
        "task": "accounts.tasks.purge_due_deletions",
        "schedule": crontab(hour=3, minute=0),
    },
    "reset-failed-logins": {"task": "ops.tasks.reset_failed_logins", "schedule": crontab(hour=3, minute=30)},
    "shop-clean-up": {"task": "shop.tasks.clean_up", "schedule": crontab(hour=4, minute=30)},
}

# Shop (shop/, README.md "Shop"): Razorpay test keys (rzp_test_…) until going live, an optional cash on delivery,
# and the seller's details printed on the invoices.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")  # webhooks are refused while it is empty
SHOP_COD_ENABLED = env.bool("SHOP_COD_ENABLED", default=False)
SHOP_SELLER = {
    "name": env("SELLER_LEGAL_NAME", default="ExamLeaf LLP"),
    "address": env("SELLER_ADDRESS", default="[address], [city], Assam [PIN]"),
    "gstin": env("SELLER_GSTIN", default=""),  # empty: "not registered" on the invoice
    "state": env("SELLER_STATE", default="AS"),  # two-letter code: same state as the buyer = CGST + SGST, else IGST
    "state_code": env("SELLER_STATE_CODE", default="18"),  # GST state code (Assam: 18)
    "email": env("SELLER_EMAIL", default="[email]"),
    "phone": env("SELLER_PHONE", default="[phone]"),
}

# Logging: one JSON object per line on stdout (LOG_JSON=0 for plain text), each with the request ID set by django-guid
# (taken from the proxy's X-Request-ID header when it is a valid UUID, otherwise new; sent back in the response).
# A task's log lines carry the request ID of the request that queued it.
DJANGO_GUID = {"GUID_HEADER_NAME": "X-Request-ID", "INTEGRATIONS": [CeleryIntegration(use_django_logging=True)]}
LOG_JSON = env.bool("LOG_JSON", default=not DEBUG)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "django_guid.log_filters.CorrelationId", "correlation_id_field": "request_id"},
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            "rename_fields": {"asctime": "time", "levelname": "level", "name": "logger"},
            "reserved_attrs": [*RESERVED_ATTRS, "data"],  # not Celery's task arguments: they hold email texts
        },
        "text": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["request_id"],
            "formatter": "json" if LOG_JSON else "text",
        },
    },
    "root": {"handlers": ["stdout"], "level": "ERROR" if TESTING else env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": [], "level": "INFO"},  # through the root handler (no duplicate in DEBUG)
        "axes": {"level": "WARNING"},  # not its start-up banner in every command
        "django_guid": {"level": "WARNING"},  # not a line per request saying that an ID was generated
        "weasyprint": {"level": "WARNING"},  # not a line per step of every invoice PDF
        "fontTools": {"level": "WARNING"},
    },
}

# Errors to Sentry when SENTRY_DSN is set; server side only (no browser script), without personal data: no cookies,
# users or addresses, and examleaf/sentry.py scrubs passwords, codes, tokens, signatures, card and phone numbers.
if SENTRY_DSN := env("SENTRY_DSN", default=""):
    import sentry_sdk

    from .sentry import before_send

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        release=env("RELEASE", default=None),
        send_default_pii=False,
        before_send=before_send,
        before_send_transaction=before_send,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
    )

LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
PHONENUMBER_DEFAULT_REGION = "IN"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # not served publicly: answer-sheet photos are personal data
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG or TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
WHITENOISE_AUTOREFRESH = DEBUG or TESTING  # no collectstatic needed in development and tests
# django-storages: private S3-compatible bucket for uploads (keys: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
if env("MEDIA_BUCKET", default=""):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("MEDIA_BUCKET"),
            "endpoint_url": env("MEDIA_ENDPOINT_URL", default=None),
            "default_acl": "private",
            "file_overwrite": False,
        },
    }

if env("BACKUP_BUCKET", default=""):  # scripts/backup.sh uploads database dumps here (manage.py upload_backup)
    STORAGES["backups"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("BACKUP_BUCKET"),
            "endpoint_url": env("BACKUP_ENDPOINT_URL", default=None),
            "default_acl": "private",
            "file_overwrite": False,
        },
    }

from import_export.formats.base_formats import CSV  # noqa: E402

EXPORT_FORMATS = [CSV]

# REST API (api/, /api/v1/): DRF, JWT, OpenAPI, CORS and throttle settings are in examleaf/api_settings.py.
from .api_settings import *  # noqa: E402, F403

INSTALLED_APPS += API_APPS  # noqa: F405
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.common.CommonMiddleware"), "corsheaders.middleware.CorsMiddleware"
)
