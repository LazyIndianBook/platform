"""REST API settings (the api/ app, /api/v1/). settings.py imports this file at its end and adds API_APPS and the CORS
middleware. Every value comes from the environment (.env.example, "REST API"); API.md explains them to the app side."""

from datetime import timedelta

import environ
from corsheaders.defaults import default_headers as _cors_default_headers

_env = environ.Env()  # settings.py has already read .env into the environment

API_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # refresh tokens die on log-out and after each rotation
    "dj_rest_auth",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # Swagger UI and Redoc files served by the site: the CSP allows no CDN for them
    "corsheaders",
    "api",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # the app: Authorization: Bearer <access>
        "rest_framework.authentication.SessionAuthentication",  # the website's own pages (with the CSRF token)
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # public views say AllowAny
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],  # JSON only, no browsable API
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "api.views.exception_handler",  # DRF's, and a JSON 413 for a body over Django's limit
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_PAGINATION_CLASS": "api.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "api.filters.BoundedSearchFilter",  # DRF's SearchFilter: five words of 50 characters at most
        "rest_framework.filters.OrderingFilter",
    ],
    # Counted in the cache (Redis in production), per client address (anon) or per user.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": _env("API_THROTTLE_ANON", default="200/minute"),
        "user": _env("API_THROTTLE_USER", default="600/minute"),
        # log-in, sign-up, email codes, passwords, data export and deletion; a classroom shares one address
        "dj_rest_auth": _env("API_THROTTLE_AUTH", default="30/minute"),
        "order_lookup": _env("API_THROTTLE_ORDER_LOOKUP", default="10/hour"),  # guests' order lookup, per address
        "payment": _env("API_THROTTLE_PAYMENT", default="30/minute"),  # starting and confirming payments (Razorpay)
        "coupon": _env("API_THROTTLE_COUPON", default="10/hour"),  # coupon codes tried, per user (not guessed)
    },
    "NUM_PROXIES": _env.int("PROXY_COUNT", default=0),  # the client address behind Caddy, as for axes
    "DEFAULT_SCHEMA_CLASS": "api.schema.AutoSchema",  # drf-spectacular's, its operations tagged by area
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# JWT for the app. Each token carries a hash of the password hash: changing or resetting the password, or the account
# deletion, ends every token at once. The signing key is JWT_SIGNING_KEY, or SECRET_KEY while that is unset (I5):
# rotating it logs every app out (RUNBOOK.md).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=_env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=_env.int("JWT_REFRESH_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,  # a refresh returns a new refresh token ...
    "BLACKLIST_AFTER_ROTATION": True,  # ... and the old one stops working
    "CHECK_REVOKE_TOKEN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
if _jwt_signing_key := _env("JWT_SIGNING_KEY", default=""):
    SIMPLE_JWT["SIGNING_KEY"] = _jwt_signing_key

# dj-rest-auth: log-in, log-out, token refresh, password reset/change, user details (api/auth.py has the rest).
REST_AUTH = {
    "USE_JWT": True,
    "TOKEN_MODEL": None,
    "SESSION_LOGIN": False,  # the app has no session
    "JWT_AUTH_HTTPONLY": False,  # the refresh token comes back in the body, for the app to keep
    "LOGIN_SERIALIZER": "api.auth.LoginSerializer",
    "JWT_SERIALIZER": "api.auth.JWTSerializer",
    "USER_DETAILS_SERIALIZER": "api.serializers.ProfileSerializer",
    "PASSWORD_RESET_SERIALIZER": "api.auth.PasswordResetSerializer",
    "PASSWORD_RESET_CONFIRM_SERIALIZER": "api.auth.PasswordResetConfirmSerializer",
    "PASSWORD_CHANGE_SERIALIZER": "api.auth.PasswordChangeSerializer",
    "OLD_PASSWORD_FIELD_ENABLED": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ExamLeaf API",
    "DESCRIPTION": "Catalogue, solutions, attempts, accounts and the shop for the ExamLeaf app. Guide: API.md.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "TAGS": [  # the areas of api.schema.AREAS, in this order
        {
            "name": "auth",
            "description": "Log-in, sign-up, codes, tokens and passwords; auth/exchange/ turns an allauth.headless "
            "app session (/_allauth/app/v1/; its OpenAPI file: /_allauth/openapi.json) into the JWT pair.",
        },
        {
            "name": "account",
            "description": "The signed-in user: profile, data rights, teacher access, a parent's consent, devices.",
        },
        {"name": "catalogue", "description": "Boards, subjects, books, papers and their solutions; scanned QR codes."},
        {"name": "record", "description": "The student's own attempts (My record)."},
        {"name": "shop", "description": "Products, reviews, cart, addresses, orders and payment, school quotations."},
        {"name": "learn", "description": "The revision course: chapters, clips, quiz, flash cards, the plan."},
        {"name": "site", "description": "What the server has switched on, and the legal pages."},
        {"name": "insights", "description": "Staff only: forecasts, print runs, item analysis, cohorts, fraud."},
        {
            "name": "staff",
            "description": "The Admin Control Panel (staff only: the panel's session or an API key): the manifest, "
            "inbox, audit log, approvals, settings and flags, staff and customers, data requests, incidents, system.",
        },
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "ENUM_NAME_OVERRIDES": {  # two models have a "status" with choices
        "OrderStatusEnum": "shop.models.Order.Status",
        "DeletionStatusEnum": "accounts.models.DeletionRequest.Status",
        "PaymentMethodEnum": "shop.models.Order.Method",  # an order's; checkout offers two of the three
        "CheckoutMethodEnum": "shop.services.CUSTOMER_METHOD_CHOICES",
    },
}

# CORS, for browser clients on other origins only (the app and the site itself need none); /api/ only.
CORS_ALLOWED_ORIGINS = _env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = (*_cors_default_headers, "x-request-id", "x-cart-token")  # no cookies: a visitor's cart by token

# The revision course (api/learn.py): book codes tried per user and per client address (a classroom shares one: raise
# the second while a teacher has a class redeem their codes together), and quiz answers per user.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
    learn_redeem=_env("API_THROTTLE_LEARN_REDEEM", default="5/hour"),
    learn_redeem_address=_env("API_THROTTLE_LEARN_REDEEM_ADDRESS", default="5/hour"),
    learn_quiz=_env("API_THROTTLE_LEARN_QUIZ", default="600/hour"),
)
SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"].update(  # "kind" with choices: products, clips, quiz items
    ClipKindEnum="learn.models.Clip.Kind", QuizItemKindEnum="learn.models.QuizItem.Kind"
)

# The staff API (staff/api.py): per member of staff (or API key); searches of customers, reveals of their details,
# exports, money actions and approvals, and the invitation links (per client address).
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
    staff=_env("STAFF_THROTTLE", default="600/minute"),
    staff_search=_env("STAFF_THROTTLE_SEARCH", default="60/minute"),
    staff_reveal=_env("STAFF_THROTTLE_REVEAL", default="30/hour"),
    staff_export=_env("STAFF_THROTTLE_EXPORT", default="10/hour"),
    staff_money=_env("STAFF_THROTTLE_MONEY", default="120/hour"),
    staff_invite=_env("STAFF_THROTTLE_INVITE", default="10/hour"),
    impersonate=_env("API_THROTTLE_IMPERSONATE", default="20/hour"),  # account/impersonate/, per client address
)
SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"].update(
    ChangeRequestStatusEnum="staff.models.ChangeRequest.Status",
    DataRequestStatusEnum="staff.models.DataRequest.Status",
    DataRequestKindEnum="staff.models.DataRequest.Kind",
    DataRequestOutcomeEnum="staff.models.DataRequest.Outcome",
    InboxKindEnum="staff.models.InboxItem.Kind",
    IncidentKindEnum="staff.models.Incident.Kind",
    ScopeKindEnum="staff.models.StaffScope.Kind",
    AuditOutcomeEnum="staff.models.AuditEvent.Outcome",
    SettingSourceEnum="staff.serializers.SETTING_SOURCES",  # "source": a setting's (an entitlement's: settings.py)
    JobKindEnum="staff.models.Job.Kind",
    JobStateEnum="staff.models.Job.State",
)
