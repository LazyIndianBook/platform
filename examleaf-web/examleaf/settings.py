"""ExamLeaf web settings. Deployment values come from the environment or a .env file (see .env.example)."""
import sys
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")  # base of the URLs inside the QR codes
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[SITE_URL])
TESTING = "test" in sys.argv
# Where book.py and the Markdown papers live (the book repository root).
BOOK_ROOT = Path(env("BOOK_ROOT", default=str(BASE_DIR.parent)))

INSTALLED_APPS = [
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
    "accounts",
    "content",
    "practice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}
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
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[ExamLeaf] "
ACCOUNT_LOGOUT_REDIRECT_URL = "home"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if SITE_URL.startswith("https") else "http"

# django-axes: lock an account for 15 minutes after 10 failed logins from one address.
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_CALLABLE = "accounts.forms.axes_username"
AXES_RESET_ON_SUCCESS = True

PROXY_COUNT = env.int("PROXY_COUNT", default=0)
if PROXY_COUNT:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    AXES_IPWARE_PROXY_COUNT = PROXY_COUNT
    AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")
if not DEBUG:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)

# Email: console in development; an ESP through django-anymail in production (ANYMAIL_* variables).
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
ANYMAIL = {k.removeprefix("ANYMAIL_"): v for k, v in env.ENVIRON.items() if k.startswith("ANYMAIL_")}
DEFAULT_FROM_EMAIL = SERVER_EMAIL = env("DEFAULT_FROM_EMAIL", default="ExamLeaf <noreply@localhost>")

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
if env("MEDIA_BUCKET", default=""):  # django-storages: private S3-compatible bucket (pip install boto3)
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("MEDIA_BUCKET"),
            "endpoint_url": env("MEDIA_ENDPOINT_URL", default=None),
            "default_acl": "private",
            "file_overwrite": False,
        },
    }

from import_export.formats.base_formats import CSV  # noqa: E402

EXPORT_FORMATS = [CSV]
