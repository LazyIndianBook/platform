"""ExamLeaf web settings. Deployment values come from the environment or a .env file (see .env.example)."""

import base64
import sys
from datetime import timedelta
from importlib.util import find_spec
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
# .env.example's development values must never serve the internet (I1): refuse to start instead.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
if DEBUG and any(host not in LOCAL_HOSTS and not host.endswith(".localhost") for host in ALLOWED_HOSTS):
    raise SystemExit(f"DEBUG=1 with ALLOWED_HOSTS={','.join(ALLOWED_HOSTS)}: set DEBUG=0 on a server (DEPLOYMENT.md).")
if not DEBUG and (SECRET_KEY.startswith("dev-") or len(SECRET_KEY) < 50):
    raise SystemExit("SECRET_KEY is the development one or shorter than 50 characters: make a new one (DEPLOYMENT.md).")
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")  # base of the URLs inside the QR codes
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[SITE_URL])
TESTING = sys.argv[1:2] == ["test"] or "pytest" in sys.modules  # manage.py test, or pytest
# A checkout of the books repository LazyIndianBook/Class-12-Assam (the folder that holds production/), for
# import_papers and import_chapter_insights: PAPERS_ROOT, else "Class 12" beside this repository when it is there. The
# tests and CI import the copies in content/fixtures/papers/ instead (--fixtures).
PAPERS_ROOT = env("PAPERS_ROOT", default="")
if not PAPERS_ROOT and (BASE_DIR.parent.parent / "Class 12").is_dir():
    PAPERS_ROOT = str(BASE_DIR.parent.parent / "Class 12")
# The solutions behind the QR codes (/s/<CODE>/ and the API): for signed-in students only (1), or open to everyone (0;
# then only saving marks needs an account). README "Open or registered solutions" explains the trade-off.
SOLUTIONS_REQUIRE_LOGIN = env.bool("SOLUTIONS_REQUIRE_LOGIN", default=True)
# A parent's consent for a student under 18 (DPDP Act s. 9; M9): "declared", the parent ticks the box on the sign-up
# form; "verified", the parent also confirms through a link emailed to them, and until then the account can read but
# not save marks or order. The DPDP Rules, 2025 ask for verifiable consent from May 2027 (DEPLOYMENT.md, RUNBOOK.md).
PARENTAL_CONSENT_MODE = env("PARENTAL_CONSENT_MODE", default="declared")
if PARENTAL_CONSENT_MODE not in {"declared", "verified"}:
    raise SystemExit(f'PARENTAL_CONSENT_MODE must be "declared" or "verified", not "{PARENTAL_CONSENT_MODE}".')

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
    "allauth",
    "allauth.account",
    "allauth.mfa",  # staff: an authenticator app (TOTP) and recovery codes; everyone: passkeys
    "allauth.socialaccount",  # Google sign-in, listed only when GOOGLE_CLIENT_ID and _SECRET are set
    "allauth.socialaccount.providers.google",
    "allauth.headless",  # allauth's flows as JSON, for the app and a decoupled web frontend: /_allauth/ (API.md)
    "axes",
    "simple_history",
    "taggit",
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
    "pictures",  # django-pictures: AVIF and WebP sizes of the product pictures (PICTURES below)
    "shop",  # after ops: its admin index template extends the ops dashboard
    "learn",  # the revision course (Phase 6 D): LEARN_* below
]

MIDDLEWARE = [
    "examleaf.middleware.FrontendClientMiddleware",  # first: the frontend's calls count as the visitor's (S4)
    "django_guid.middleware.guid_middleware",  # request ID (X-Request-ID from the proxy, or new), in every log line
    "examleaf.middleware.NullByteMiddleware",  # %00 in an address: 404 (PostgreSQL would fail with a 500)
    "django.middleware.security.SecurityMiddleware",
    "examleaf.middleware.PermissionsPolicyMiddleware",
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
    "examleaf.middleware.StaffMFAMiddleware",  # staff must set up an authenticator app before anything else
    "simple_history.middleware.HistoryRequestMiddleware",
    "axes.middleware.AxesMiddleware",  # keep last
]

DEBUG_TOOLBAR = DEBUG and not TESTING and find_spec("debug_toolbar") is not None  # requirements-dev.txt
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
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
# Persistent connections (one per gunicorn thread or Celery process, checked before reuse) rather than a pool: each
# thread serves one request at a time, so a pool would hold the same number of connections (3 workers x 8 threads).
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# CACHE_URL=redis://… uses django-redis; without it, the local-memory cache (one per process). A Redis of its own, not
# Celery's queue (CELERY_BROKER_URL): docker-compose.yml's redis-cache, 256 MB, the least used keys evicted. With Redis
# down every cache call gives up within a second and counts as a miss (logged): pages keep working, rate limits and
# throttles let requests through meanwhile (sessions and axes are in the database) except the shop's own (order
# lookup, checkout, place order, coupon codes), which refuse until it is back; /health/ reports the cache.
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
AUTH_PASSWORD_VALIDATORS = [  # L11: at least 10 characters, and none found in data breaches
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    # Pwned Passwords (haveibeenpwned.com): only the first 5 characters of the password's SHA-1 leave the server
    # (k-anonymity). If the service cannot be reached within a second, the common-passwords list decides instead.
    {"NAME": "pwned_passwords_django.validators.PwnedPasswordsValidator"},
]
PASSWORD_RESET_TIMEOUT = 3600  # a reset link works for an hour (Django's default: 3 days)
# The website's log-in page (examleaf-frontend); the admin sends there when signed out (examleaf/urls.py).
LOGIN_URL = f"{SITE_URL}/account/login/"
LOGIN_REDIRECT_URL = "/"

# SMS (ops/sms.py): "console" prints them (development), "msg91" sends them through MSG91 with the DLT templates whose
# ids are MSG91_TEMPLATE_<KIND> (DEPLOYMENT.md, RUNBOOK.md "SMS"). At most SMS_DAILY_CAP a day, counted in the database.
# A server without a real backend has no phone log-in and sends no SMS (SMS_ENABLED): nobody would get the codes.
SMS_BACKEND = env("SMS_BACKEND", default="console")
MSG91_AUTHKEY = env("MSG91_AUTHKEY", default="")
if SMS_BACKEND not in {"console", "msg91"} or (SMS_BACKEND == "msg91" and not MSG91_AUTHKEY):
    raise SystemExit(f'SMS_BACKEND="{SMS_BACKEND}": use "console", or "msg91" with MSG91_AUTHKEY set (DEPLOYMENT.md).')
SMS_ENABLED = SMS_BACKEND != "console" or DEBUG or TESTING
SMS_DAILY_CAP = env.int("SMS_DAILY_CAP", default=500)
SMS_KINDS = [
    *["otp", "order_placed", "order_shipped", "order_delivered", "parent_consent"],
    *["order_arriving", "order_not_delivered"],  # a courier's news (shipping/messages.py)
]
MSG91_TEMPLATES = {kind: env(f"MSG91_TEMPLATE_{kind.upper()}", default="") for kind in SMS_KINDS}

# django-allauth: email is the login, verified by a code typed on the same page (phone friendly). With SMS on, also a
# mobile number confirmed on My account (never at sign-up: two codes in a row), with the password or a code by SMS
# (accounts.adapter). "phone" in the sign-up fields lets allauth change a number; the sign-up form drops it.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email", "phone"} if SMS_ENABLED else {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", *(["phone"] if SMS_ENABLED else []), "password1*", "password2*"]
ACCOUNT_LOGIN_BY_CODE_ENABLED = True  # "Log in with a code": emailed, or texted to a confirmed number
# No "send a new code" on the log-in code page: allauth 65.19 answers it with a server error for a number no account
# has (a way to tell which numbers are registered), and each is one more SMS. The form gives a new code (limits below).
ACCOUNT_LOGIN_BY_CODE_SUPPORTS_RESEND = False
ACCOUNT_PHONE_VERIFICATION_SUPPORTS_RESEND = True
ACCOUNT_PHONE_VERIFICATION_TIMEOUT = 300
ALLAUTH_USER_CODE_FORMAT = {"length": 6, "numeric": True, "dashed": False}  # every code, emailed or texted: 483920
# A code is one of a million: guessing is held back by the tries per code (three, then a new code is needed) and by
# how many codes an address or number gets (M1). SMS cost money; ops.sms adds its own limits per number (M2).
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_MAX_ATTEMPTS = ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS = 3
ACCOUNT_PHONE_VERIFICATION_MAX_ATTEMPTS = 3
# allauth keeps one history per action and kind of key (ip, key, user): two rates of one kind in one action would share
# it, the shorter window cutting the longer one short. A second window is therefore an action of its own.
ACCOUNT_RATE_LIMITS = {
    "request_login_code": "30/h/ip,3/h/key",  # log-in codes: 3 an hour per address or number, 30 per client address
    "verify_phone": "1/60s/key,10/h/ip",  # a phone confirmation code: one a minute per number
    "change_phone": "3/h/user",
    "confirm_email": "1/10s/key",  # allauth's own: an email confirmation code at most every 10 seconds per address
    "email_code_hour": "5/h/key",  # and these two (accounts.adapter): at most 5 an hour and 10 a day per address
    "email_code_day": "10/d/key",
    "code_try": "60/h/ip,3/15m/key",  # tries of one code, counted in the cache as well (accounts.forms.spend_try)
}
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
# Every sign-up form is built on this one (allauth.headless's for the website and the app, after Google too, and the
# API's): the student details, the consent and its record, the STUDENT role, no phone at sign-up, Turnstile. The code
# forms count three tries per code in the cache too (I7: allauth's count in the session lags behind parallel requests):
# examleaf/urls.py gives them to allauth.headless.
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.signup.StudentDetailsForm"
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"  # sends allauth's emails through a Celery task
ACCOUNT_CHANGE_EMAIL = True  # one address: a new one replaces it only once its emailed code is confirmed
ACCOUNT_EMAIL_NOTIFICATIONS = True  # the old address is told of email and password changes
ACCOUNT_REAUTHENTICATION_REQUIRED = True  # password again (if not entered in the last 5 minutes) before such changes
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[ExamLeaf] "
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if SITE_URL.startswith("https") else "http"
# allauth.mfa (H2): every member of staff logs in with a code from an authenticator app (TOTP), a recovery code, or a
# passkey; the admin's own login form goes through allauth (urls.py). Staff sessions end 8 hours after the log-in
# (accounts.models). Passkeys (WebAuthn) for everyone, added on My account; one relying party, the host of SITE_URL
# (accounts.adapter.MFAAdapter); HTTPS only, except in development. No sign-up by passkey.
MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG
MFA_TOTP_ISSUER = "ExamLeaf"
MFA_ADAPTER = "accounts.adapter.MFAAdapter"
# allauth.headless (API.md "Frontend integration guide"): allauth's flows as JSON at /_allauth/browser/v1/ (the session
# cookie and the CSRF token; same origin only: CORS stays on /api/) and /_allauth/app/v1/ (the X-Session-Token header;
# POST /api/v1/auth/exchange/ then gives the JWT pair). Headless only: the website's pages are the Next.js frontend's
# (examleaf-frontend), so allauth serves no page of its own, only Google's callback (/account/google/login/callback/).
# Its emails link to the website's pages, whichever client asked (no confirmation link: addresses are confirmed by
# code). The OpenAPI files are /_allauth/openapi.yaml and .json; no HTML page (allauth's loads Redoc from a CDN, which
# the CSP refuses).
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("app", "browser")
HEADLESS_FRONTEND_URLS = {
    "account_reset_password": f"{SITE_URL}/account/password/reset/",
    "account_reset_password_from_key": f"{SITE_URL}/account/password/reset/key/{{key}}/",
    "account_signup": f"{SITE_URL}/account/signup/",
    # where a failed Google log-in lands when its own callback_url is lost: the log-in page shows ?error=
    "socialaccount_login_error": f"{SITE_URL}/account/login/",
}
HEADLESS_SERVE_SPECIFICATION = True
HEADLESS_SPECIFICATION_TEMPLATE_NAME = None

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
# The secret the Next.js frontend sends with its server-side calls (X-Internal-Token): only then is the visitor's
# address it forwards trusted (examleaf.middleware.FrontendClientMiddleware). The same value in the frontend's
# environment; empty: the frontend's calls count as the frontend's own address.
INTERNAL_API_TOKEN = env.str("INTERNAL_API_TOKEN", default="")
# allauth's limits per address (log-in, reset, sign-up) must see the client too, not Caddy: one address for everybody
# would turn ten failed log-ins a minute anywhere into a lock-out of the whole site (M7).
ALLAUTH_TRUSTED_PROXY_COUNT = PROXY_COUNT
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

# Content-Security-Policy of Django's own pages (the admin, the staff clip player, the API docs; the website's pages
# have the frontend's): scripts, styles and fonts only from this site. 'unsafe-inline' is for styles only, and stays
# (I6): the admin and its add-ons use style attributes. Scripts never get it.
CONTENT_SECURITY_POLICY = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "font-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}
# Google sign-in (allauth.socialaccount), offered only when both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set
# (DEPLOYMENT.md). A new student always fills in our form after Google (class, board, date of birth, parent, consent:
# Google gives none of them); an address with an account logs in as before and connects Google from there.
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"  # Google's URLs are 404 without its keys
SOCIALACCOUNT_PROVIDERS = {"google": {"SCOPE": ["profile", "email"], "OAUTH_PKCE_ENABLED": True}}
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [{"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET}]
# Cloudflare Turnstile (a check for bots, mostly without a puzzle) on sign-up, code requests and the public forms
# (accounts.forms TurnstileMixin), only when both keys are set: the frontend shows the widget, Django checks its token.
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", default="")
TURNSTILE = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
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
# Amazon SES in Mumbai (EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend; DEPLOYMENT.md "Email"), with keys of
# its own, not the S3 ones. Bounces and complaints come back to /anymail/<esp>/tracking/ (examleaf/urls.py), which
# exists only with ANYMAIL_WEBHOOK_SECRET set (user:password, given to the provider inside the webhook URL), and fill
# ops.models.EmailSuppression. Brevo and Postmark work the same way through their own EMAIL_BACKEND and ANYMAIL_* keys.
if env("SES_ACCESS_KEY_ID", default=""):
    ANYMAIL["AMAZON_SES_CLIENT_PARAMS"] = {
        "region_name": env("SES_REGION", default="ap-south-1"),
        "aws_access_key_id": env("SES_ACCESS_KEY_ID"),
        "aws_secret_access_key": env("SES_SECRET_ACCESS_KEY"),
    }
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
    "clear-expired-sessions": {"task": "ops.tasks.clear_sessions", "schedule": crontab(hour=3, minute=45)},  # M10
    "shop-clean-up": {"task": "shop.tasks.clean_up", "schedule": crontab(hour=4, minute=30)},
    "shop-stock-alerts": {"task": "shop.tasks.send_stock_alerts", "schedule": crontab(minute=15)},  # hourly
    "shop-low-stock": {"task": "shop.tasks.low_stock_report", "schedule": crontab(hour=8, minute=0)},
}

# Shop (shop/, README.md "Shop"): Razorpay test keys (rzp_test_…) until going live, an optional cash on delivery,
# and the seller's details printed on the invoices.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
# The webhook secrets, one per Razorpay mode: the one of the keys' mode is checked; empty refuses every webhook.
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")  # live mode
RAZORPAY_WEBHOOK_SECRET_TEST = env("RAZORPAY_WEBHOOK_SECRET_TEST", default="")  # test mode
# 0: only staff reach the cart, checkout and payment (website and API); the catalogue says "Shop opens soon". For
# Razorpay's activation review on test keys, when the shop must be public but nobody may "buy" with a test card.
SHOP_OPEN = env.bool("SHOP_OPEN", default=True)
SHOP_COD_ENABLED = env.bool("SHOP_COD_ENABLED", default=False)
# Cash on delivery: only for accounts with a confirmed email address, two orders on their way at a time, each worth at
# most this many rupees (shipping included).
SHOP_COD_MAX_VALUE = env.int("SHOP_COD_MAX_VALUE", default=1500)
# Each morning the SALES role is emailed the books on sale with fewer copies than this (shop.tasks.low_stock_report).
SHOP_LOW_STOCK = env.int("SHOP_LOW_STOCK", default=5)
SHOP_SELLER = {
    "name": env("SELLER_LEGAL_NAME", default="ExamLeaf LLP"),
    "address": env("SELLER_ADDRESS", default="[address], [city], Assam [PIN]"),
    "gstin": env("SELLER_GSTIN", default=""),  # empty: "not registered" on the invoice
    "state": env("SELLER_STATE", default="AS"),  # two-letter code: same state as the buyer = CGST + SGST, else IGST
    "state_code": env("SELLER_STATE_CODE", default="18"),  # GST state code (Assam: 18)
    "email": env("SELLER_EMAIL", default="[email]"),
    "phone": env("SELLER_PHONE", default="[phone]"),
}
# Where the contact form (website and POST /api/v1/contact/) sends messages and what config/ gives as the support email;
# empty: SELLER_EMAIL. While it is a [placeholder] the form is off (the API answers 503).
SUPPORT_EMAIL = env("SUPPORT_EMAIL", default="")
# django-pictures: each uploaded product picture is also saved in AVIF and WebP sizes (<source> order: the browser takes
# the first it supports) by the Celery worker, which reads only the default queue "celery" (no -Q in
# docker-compose.yml), never in the request. Django 6's default processor would need a TASKS queue "pictures".
PICTURES = {
    "FILE_TYPES": ["AVIF", "WEBP"],
    "BREAKPOINTS": {"s": 576, "m": 992, "l": 1200},
    "GRID_COLUMNS": 12,
    "CONTAINER_WIDTH": 1200,
    "PIXEL_DENSITIES": [1, 2],
    "QUEUE_NAME": "celery",
    "PROCESSOR": "examleaf.images.queue_picture_sizes",  # the Celery task, with a fallback (examleaf/images.py)
    "USE_PLACEHOLDERS": False,
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
        "httpx": {"level": "WARNING"},  # not the Pwned Passwords requests: they name a prefix of a password's hash
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
        include_local_variables=False,  # stack frames' variables hold email texts: reset links and codes (M4)
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
# Two S3-compatible buckets through django-storages (Cloudflare R2; DEPLOYMENT.md 15 and 17), keys S3_* of their own
# (not AWS_*: SES and the backups read those). "default" is private: invoices, credit notes, quotations, answer sheets,
# by URLs signed for 5 minutes. "public": product pictures and their AVIF/WebP sizes, the Open Graph images, through
# PUBLIC_MEDIA_DOMAIN with a year's immutable caching (a new upload never reuses a name: file_overwrite False). No ACLs
# (R2 ignores them, new AWS buckets refuse them). boto3 needs AWS_REQUEST_CHECKSUM_CALCULATION and
# AWS_RESPONSE_CHECKSUM_VALIDATION=when_required in the environment for R2 (docker-compose.yml), not a client_config:
# django-pictures sends the storage's settings to Celery as JSON. Without MEDIA_BUCKET (development, tests, one
# server): both in MEDIA_ROOT; the public files by shop.views.product_media under /shop/media/.
_s3 = {
    "endpoint_url": env("S3_ENDPOINT_URL", default=None),  # R2: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    "region_name": env("S3_REGION", default="auto"),  # R2 "auto"; AWS "ap-south-1"
    "access_key": env("S3_ACCESS_KEY_ID", default=None),
    "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
    "file_overwrite": False,
    "default_acl": None,
}
# India only (a Privacy Policy promise): the private bucket on AWS S3 Mumbai (S3_REGION=ap-south-1, no S3_ENDPOINT_URL),
# the public one still on R2 with its own endpoint, region and keys: PUBLIC_S3_ENDPOINT_URL, PUBLIC_S3_REGION, …
_public_s3 = {**_s3}
for _option, _name in [("endpoint_url", "ENDPOINT_URL"), ("region_name", "REGION"), ("access_key", "ACCESS_KEY_ID")]:
    _public_s3[_option] = env(f"PUBLIC_S3_{_name}", default=_s3[_option])
_public_s3["secret_key"] = env("PUBLIC_S3_SECRET_ACCESS_KEY", default=_s3["secret_key"])
if env("MEDIA_BUCKET", default=""):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {**_s3, "bucket_name": env("MEDIA_BUCKET"), "querystring_auth": True, "querystring_expire": 300},
    }
    STORAGES["public"] = {
        "BACKEND": "examleaf.storage.PublicS3Storage",  # S3Storage that keeps its key out of the picture tasks (L12)
        "OPTIONS": {
            **_public_s3,
            "bucket_name": env("PUBLIC_MEDIA_BUCKET"),
            "custom_domain": env("PUBLIC_MEDIA_DOMAIN"),  # media.examleaf.in
            "querystring_auth": False,
            "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"},
        },
    }
    CONTENT_SECURITY_POLICY["img-src"].append(f"https://{env('PUBLIC_MEDIA_DOMAIN')}")
else:
    STORAGES["public"] = {**STORAGES["default"], "OPTIONS": {"base_url": "/shop/media/"}}

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
# Admin exports need the model's "export_…" permission (ADMIN role and superusers; accounts/roles.py), and a cell that
# starts with "=" loses it, so that a name typed by a customer cannot become a spreadsheet formula (M5, L7).
IMPORT_EXPORT_EXPORT_PERMISSION_CODE = "export"
IMPORT_EXPORT_ESCAPE_FORMULAE_ON_EXPORT = True

# REST API (api/, /api/v1/): DRF, JWT, OpenAPI, CORS and throttle settings are in examleaf/api_settings.py.
from .api_settings import *  # noqa: E402, F403

INSTALLED_APPS += API_APPS  # noqa: F405
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.common.CommonMiddleware"), "corsheaders.middleware.CorsMiddleware"
)

# Revision course (learn/; DEPLOYMENT.md "Revision course"). Clip videos are uploaded in the admin and processed by
# ffmpeg on the "media" queue (docker-compose.yml media-worker) into HLS for phones, kept in the private storage and
# played through links signed for LEARN_URL_SECONDS (learn/views.py), or in the public storage (LEARN_PUBLIC_VIDEO=1).
LEARN_MAX_UPLOAD_MB = env.int("LEARN_MAX_UPLOAD_MB", default=500)
LEARN_PUBLIC_VIDEO = env.bool("LEARN_PUBLIC_VIDEO", default=False)
LEARN_URL_SECONDS = 600
LEARN_FREE_PREVIEW = env.bool("LEARN_FREE_PREVIEW", default=True)  # first clip of each revision, first chapter's cards
LEARN_ACCESS_DAYS = env.int("LEARN_ACCESS_DAYS", default=365)  # what a book code or a purchase opens, from that day
# The key of the book codes' hashes: set it once, before the first print run, and never change it (printed codes
# would stop working). Empty: an unkeyed hash, which a copy of the database could be searched against.
LEARN_CODE_SECRET = env("LEARN_CODE_SECRET", default="")
# Firebase Cloud Messaging (the daily revision reminder in the app): the service account's JSON, or a path to it.
FCM_SERVICE_ACCOUNT_JSON = env("FCM_SERVICE_ACCOUNT_JSON", default="")
CELERY_TASK_ROUTES = {"learn.tasks.process_clip": {"queue": "media"}}
CELERY_BEAT_SCHEDULE["learn-reminders"] = {"task": "learn.tasks.send_reminders", "schedule": crontab(hour=18, minute=0)}
# The staff player (hls.js: media from blob: URLs). The bucket's own origin is added on the pages that need it only, as
# their storage's links name it (learn.uploads.allow_storage: the staff player, the clip pages that upload to it; I3).
CONTENT_SECURITY_POLICY["media-src"] = [CSP.SELF, "blob:"]
# Clip videos go from the editor's browser straight to the bucket (H1, learn/uploads.py); without one they come with
# the form, and only signed-in staff may send a body that large to the clip pages (Caddy lets 500 MB through there).
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1, "learn.uploads.LargeBodyGuard"
)

# Store (Phase 6 E): the category tree (django-treebeard: its admin templates), and imports of products and categories
# only with the model's "import_…" permission (ADMIN), as exports (M5).
INSTALLED_APPS += ["treebeard"]
IMPORT_EXPORT_IMPORT_PERMISSION_CODE = "import"

# Signed-in devices (Phase 8 account): allauth.usersessions keeps each session's client address, browser and last
# request, listed and ended through allauth.headless's auth/sessions (API.md "Profile and data rights"); the rows are
# in Download my data and go with the account (accounts.models.DeletionRequest.complete).
INSTALLED_APPS += ["allauth.usersessions"]
MIDDLEWARE.insert(
    MIDDLEWARE.index("axes.middleware.AxesMiddleware"), "allauth.usersessions.middleware.UserSessionsMiddleware"
)
USERSESSIONS_TRACK_ACTIVITY = True
# The app's store pages (config/ app_links); empty until the app is out.
APP_LINK_ANDROID = env("APP_LINK_ANDROID", default="")
APP_LINK_IOS = env("APP_LINK_IOS", default="")
# The revision course's pages on the website (config/ web_course): off until the product decision is made; the
# course stays in the app. The frontend draws /revision/<subject>/<chapter>/, its flash cards and quiz only when on.
WEB_COURSE = env.bool("WEB_COURSE", default=False)

# Integrations (integrations/README.md; DEPLOYMENT.md "Integrations"): the services others run for us. Their secrets
# are encrypted with INTEGRATION_KEYS, Fernet keys separated by commas, newest first (make one with
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"); a server refuses to
# start without one once an account exists (integrations.E001), development and the tests use one made from
# SECRET_KEY. A call waits INTEGRATIONS_CONNECT_TIMEOUT seconds to connect and INTEGRATIONS_READ_TIMEOUT for its
# answer; the call log, the inbound events and the dead letters dealt with go after INTEGRATIONS_RETENTION_DAYS.
INSTALLED_APPS += ["integrations"]
INTEGRATION_KEYS = env.list("INTEGRATION_KEYS", default=[])
for _key in INTEGRATION_KEYS:
    try:
        _fernet_key = len(base64.urlsafe_b64decode(_key)) == 32
    except ValueError:  # not base64 (binascii.Error)
        _fernet_key = False
    if not _fernet_key:
        raise SystemExit("INTEGRATION_KEYS holds a value that is not a Fernet key (44 characters): see DEPLOYMENT.md.")
INTEGRATIONS_CONNECT_TIMEOUT = env.float("INTEGRATIONS_CONNECT_TIMEOUT", default=5)
INTEGRATIONS_READ_TIMEOUT = env.float("INTEGRATIONS_READ_TIMEOUT", default=20)
INTEGRATIONS_RETENTION_DAYS = env.int("INTEGRATIONS_RETENTION_DAYS", default=90)
CELERY_BEAT_SCHEDULE["integrations-retention"] = {
    "task": "integrations.tasks.purge_old_records",
    "schedule": crontab(hour=4, minute=45),
}

# Shipping (shipping/README.md; DEPLOYMENT.md "Shipping"): parcels booked with a courier through Shiprocket (an
# integration account) or sent by hand. A parcel weighs its books plus SHIPPING_PACKING_GRAMS and is a flyer of
# SHIPPING_PARCEL_CM (length, breadth, height) unless staff say otherwise. The quote waits SHIPPING_QUOTE_TIMEOUT
# seconds and is kept 10 minutes; it ranks first the cheapest couriers rated SHIPPING_MIN_RATING or more that deliver
# within SHIPPING_MAX_DAYS. India Post's Gyan Post is offered only with SHIPPING_GYAN_POST, once the postal division has
# confirmed in writing that the books qualify. Parcels silent for 6 hours are read again every two hours; exceptions
# open for staff after 5 days without a scan, at a failed delivery (24 hours to act), for a COD remittance 2 working
# days late (expected 10 working days after delivery) and for a weight dispute (7 working days to contest). The
# webhook takes API_THROTTLE_PARCEL_EVENTS per client address; the PIN survey reads SHIPPING_SURVEY_BATCH PINs a week.
INSTALLED_APPS += ["shipping"]
SHIPPING_PACKING_GRAMS = env.int("SHIPPING_PACKING_GRAMS", default=50)
SHIPPING_PARCEL_CM = env.list("SHIPPING_PARCEL_CM", default=["25", "20", "3"])
SHIPPING_QUOTE_TIMEOUT = env.float("SHIPPING_QUOTE_TIMEOUT", default=3)
SHIPPING_QUOTE_CACHE_SECONDS = 600
SHIPPING_MIN_RATING = env.float("SHIPPING_MIN_RATING", default=4)
SHIPPING_MAX_DAYS = env.int("SHIPPING_MAX_DAYS", default=7)
SHIPPING_GYAN_POST = env.bool("SHIPPING_GYAN_POST", default=False)
SHIPPING_POLL_AFTER_HOURS = 6
SHIPPING_NO_MOVEMENT_DAYS = 5
SHIPPING_NDR_HOURS = 24
SHIPPING_COD_REMITTANCE_DAYS = 10
SHIPPING_COD_GRACE_DAYS = 2
SHIPPING_DISPUTE_DAYS = 7
SHIPPING_SURVEY_BATCH = env.int("SHIPPING_SURVEY_BATCH", default=500)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["parcel_events"] = env(  # noqa: F405  the couriers' webhook, per address
    "API_THROTTLE_PARCEL_EVENTS", default="300/minute"
)
_STAFF_TAG = {"name": "shipping (staff)", "description": "Parcels, couriers, exceptions and COD, for staff (API.md)."}
if _STAFF_TAG not in SPECTACULAR_SETTINGS["TAGS"]:  # noqa: F405  (once: tests reload this module, the dict is shared)
    SPECTACULAR_SETTINGS["TAGS"].append(_STAFF_TAG)  # noqa: F405
SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"].update(  # noqa: F405  "status", "state" and "kind" with choices
    StateEnum="localflavor.in_.in_states.STATE_CHOICES",  # an address's state: its name as before
    ParcelStatusEnum="shipping.status.Status",
    ShippingExceptionStateEnum="shipping.models.ShippingException.State",
    ShippingExceptionKindEnum="shipping.models.ShippingException.Kind",
    CodRemittanceStateEnum="shipping.models.CodRemittance.State",
    ShipmentChargeKindEnum="shipping.models.ShipmentCharge.Kind",
)
CELERY_BEAT_SCHEDULE.update(
    {
        "shipping-poll-tracking": {"task": "shipping.tasks.poll_tracking", "schedule": crontab(minute=10, hour="*/2")},
        "shipping-sync-statement": {"task": "shipping.tasks.sync_statement", "schedule": crontab(hour=5, minute=0)},
        "shipping-check-cod": {"task": "shipping.tasks.check_cod_remittances", "schedule": crontab(hour=5, minute=15)},
        "shipping-check-discrepancies": {
            "task": "shipping.tasks.check_weight_discrepancies",
            "schedule": crontab(hour=5, minute=30),
        },
        "shipping-renew-token": {"task": "shipping.tasks.renew_token", "schedule": crontab(hour=5, minute=45)},
        "shipping-survey-pins": {
            "task": "shipping.tasks.survey_pins",
            "schedule": crontab(hour=6, minute=0, day_of_week="sun"),
        },
        "shipping-held-messages": {"task": "shipping.tasks.send_held_messages", "schedule": crontab(hour=8, minute=0)},
    }
)
