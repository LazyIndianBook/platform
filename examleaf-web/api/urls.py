"""/api/v1/ (namespace "api"); the version comes from the path (DRF URLPathVersioning)."""

from dj_rest_auth import views as rest_auth
from dj_rest_auth.jwt_auth import get_refresh_view
from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenVerifyView

from . import auth, learn, shop, views

router = SimpleRouter()
router.register("boards", views.BoardViewSet)
router.register("subjects", views.SubjectViewSet)
router.register("books", views.BookViewSet)
router.register("papers", views.PaperViewSet)
router.register("pages", views.PageViewSet)  # the legal pages
router.register("attempts", views.AttemptViewSet, basename="attempt")
router.register("products", shop.ProductViewSet)
router.register("addresses", shop.AddressViewSet, basename="address")
router.register("orders", shop.OrderViewSet, basename="order")
router.register("learn/chapters", learn.ChapterViewSet)  # the revision course: api/learn.py
router.register("learn/clips", learn.ClipViewSet)
router.register("learn/quiz", learn.QuizViewSet)
router.register("learn/flash-cards", learn.FlashCardViewSet)
router.register("learn/entitlements", learn.EntitlementViewSet, basename="entitlement")
cart = shop.CartViewSet.as_view  # one cart per account: its own routes, not a collection
CART_LINE = {"put": "change", "patch": "change", "delete": "remove"}

NO_AUTH = {"authentication_classes": []}  # an expired token left in the header must not stop these

urlpatterns = [
    path("auth/registration/", auth.RegisterView.as_view(**NO_AUTH), name="register"),
    path("auth/registration/verify-email/", auth.VerifyEmailView.as_view(**NO_AUTH), name="verify-email"),
    path("auth/phone/code/", auth.PhoneCodeView.as_view(**NO_AUTH), name="phone-code"),
    path("auth/phone/confirm/", auth.PhoneConfirmView.as_view(**NO_AUTH), name="phone-confirm"),
    path("auth/exchange/", auth.ExchangeView.as_view(), name="exchange"),  # allauth.headless's app session to JWT
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
    path("me/teacher/", views.TeacherView.as_view(), name="me-teacher"),
    path("me/parent-consent/", views.ParentConsentView.as_view(), name="me-parent-consent"),
    path("config/", views.ConfigView.as_view(), name="config"),
    path("qr/<str:code>/", views.QrView.as_view(), name="qr"),
    path("orders/t/<slug:token>/", shop.OrderLinkView.as_view(), name="order-link"),  # the emails' link
    path("quotes/", shop.QuoteView.as_view(), name="quotes"),  # school and bulk orders
    path("cart/", cart({"get": "retrieve"}), name="cart"),
    path("cart/items/", cart({"post": "add"}), name="cart-items"),
    path("cart/items/<slug:product>/", cart(CART_LINE), name="cart-line"),
    path("cart/coupon/", cart({"post": "apply_coupon", "delete": "remove_coupon"}), name="cart-coupon"),
    path("learn/plan/", learn.PlanView.as_view(), name="learn-plan"),
    path("learn/revise-again/", learn.ReviseAgainView.as_view(), name="learn-revise-again"),
    path("learn/redeem/", learn.RedeemView.as_view(), name="learn-redeem"),
    path("learn/settings/", learn.LearnerView.as_view(), name="learn-settings"),
    path("devices/", learn.DeviceView.as_view(), name="devices"),
    *router.urls,
]

# The shop's category tree and collections (Phase 6 E)
store_router = SimpleRouter()
store_router.register("categories", shop.CategoryViewSet)
store_router.register("collections", shop.CollectionViewSet)
urlpatterns += store_router.urls
