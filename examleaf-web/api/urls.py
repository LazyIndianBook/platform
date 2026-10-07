"""/api/v1/ (namespace "api"); the version comes from the path (DRF URLPathVersioning)."""

from dj_rest_auth import views as rest_auth
from dj_rest_auth.jwt_auth import get_refresh_view
from django.urls import path
from health_check.views import HealthCheckView
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenVerifyView

from examleaf.urls import ALL_CHECKS  # /health/'s checks (examleaf.urls is loaded first: it includes this file)

from . import auth, views

router = SimpleRouter()
router.register("boards", views.BoardViewSet)
router.register("subjects", views.SubjectViewSet)
router.register("books", views.BookViewSet)
router.register("papers", views.PaperViewSet)
router.register("attempts", views.AttemptViewSet, basename="attempt")

NO_AUTH = {"authentication_classes": []}  # an expired token left in the header must not stop these

urlpatterns = [
    path("auth/registration/", auth.RegisterView.as_view(**NO_AUTH), name="register"),
    path("auth/registration/verify-email/", auth.VerifyEmailView.as_view(**NO_AUTH), name="verify-email"),
    # dj-rest-auth (its urls.py, listed here to drop the authentication where it gets in the way)
    path("auth/login/", rest_auth.LoginView.as_view(**NO_AUTH), name="rest_login"),
    path("auth/logout/", rest_auth.LogoutView.as_view(**NO_AUTH), name="rest_logout"),
    path("auth/token/refresh/", get_refresh_view().as_view(), name="token_refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/password/reset/", rest_auth.PasswordResetView.as_view(**NO_AUTH), name="rest_password_reset"),
    path(
        "auth/password/reset/confirm/",
        rest_auth.PasswordResetConfirmView.as_view(**NO_AUTH),
        name="rest_password_reset_confirm",
    ),
    path("auth/password/change/", rest_auth.PasswordChangeView.as_view(), name="rest_password_change"),
    path("me/", rest_auth.UserDetailsView.as_view(), name="me"),
    path("me/export/", views.DataExportView.as_view(), name="me-export"),
    path("me/deletion/", views.DeletionView.as_view(), name="me-deletion"),
    path("qr/<str:code>/", views.QrView.as_view(), name="qr"),
    path("health/", HealthCheckView.as_view(checks=ALL_CHECKS), name="health"),
    *router.urls,
]
