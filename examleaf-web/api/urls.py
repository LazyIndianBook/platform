"""/api/v1/ (namespace "api"); the version comes from the path (DRF URLPathVersioning)."""

from dj_rest_auth import views as rest_auth
from dj_rest_auth.jwt_auth import get_refresh_view
from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenVerifyView

from insights import api as insights
from shipping import api as shipping
from staff import api as staff
from support import views as support

from . import auth, learn, parent_link, privacy, reports, shop, views

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
link = shop.OrderLinkViewSet.as_view  # what the order's link does without signing in

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
    # a member of staff logged in as a customer (the token from the panel): staff/api.py ImpersonationView
    path("account/impersonate/", staff.ImpersonationView.as_view(), name="account-impersonate"),
    path("me/export/", views.DataExportView.as_view(), name="me-export"),
    path("me/export/summary/", views.DataExportSummaryView.as_view(), name="me-export-summary"),
    path("me/record/", views.RecordView.as_view(), name="me-record"),  # My record in figures
    path("me/learning/", learn.LearningView.as_view(), name="me-learning"),  # the learning dashboard
    path("me/deletion/", views.DeletionView.as_view(), name="me-deletion"),
    path("me/teacher/", views.TeacherView.as_view(), name="me-teacher"),
    path("me/parent-consent/", views.ParentConsentView.as_view(), name="me-parent-consent"),
    path("me/nominee/", privacy.NomineeView.as_view(), name="me-nominee"),  # api/privacy.py: data rights
    path("me/consent/withdraw/", privacy.ConsentWithdrawView.as_view(), name="me-consent-withdraw"),
    path("pages/<slug:slug>/versions/", privacy.PageVersionsView.as_view(), name="page-versions"),
    path("me/tickets/", support.MyTicketsView.as_view(), name="me-tickets"),  # My requests (support/views.py)
    path("parent-consent/<str:token>/", parent_link.ParentLinkView.as_view(), name="parent-link"),  # the parent's link
    path("config/", views.ConfigView.as_view(), name="config"),
    path("contact/", views.ContactView.as_view(), name="contact"),  # the contact form
    path("qr/<str:code>/", views.QrView.as_view(), name="qr"),
    path("reports/", reports.ReportView.as_view(), name="reports"),  # Report a mistake (content.reports)
    path("errata/", reports.ErrataView.as_view(), name="errata"),
    path("orders/t/<slug:token>/", shop.OrderLinkView.as_view(), name="order-link"),  # the emails' link
    path("orders/t/<slug:token>/payment/", link({"post": "payment"}), name="order-link-payment"),  # a guest's order
    path("orders/t/<slug:token>/payment/confirm/", link({"post": "payment_confirm"}), name="order-link-confirm"),
    path("orders/t/<slug:token>/cancel/", link({"post": "cancel"}), name="order-link-cancel"),
    path("orders/t/<slug:token>/invoice/", link({"get": "invoice"}), name="order-link-invoice"),
    path("orders/t/<slug:token>/credit-notes/<int:note>/", link({"get": "credit_note"}), name="order-link-credit-note"),
    path("quotes/", shop.QuoteView.as_view(), name="quotes"),  # school and bulk orders
    path("shipping/", shop.ShippingView.as_view(), name="shipping"),  # the delivery rates
    path("shipping/quote/", shop.ShippingQuoteView.as_view(), name="shipping-quote"),  # the checkout's delivery step
    path("cart/", cart({"get": "retrieve", "post": "start"}), name="cart"),  # POST: a visitor's cart and its token
    path("cart/items/", cart({"post": "add"}), name="cart-items"),
    path("cart/items/<slug:product>/", cart(CART_LINE), name="cart-line"),
    path("cart/coupon/", cart({"post": "apply_coupon", "delete": "remove_coupon"}), name="cart-coupon"),
    path("learn/plan/", learn.PlanView.as_view(), name="learn-plan"),
    path("learn/revise-again/", learn.ReviseAgainView.as_view(), name="learn-revise-again"),
    path("learn/redeem/", learn.RedeemView.as_view(), name="learn-redeem"),
    path("learn/settings/", learn.LearnerView.as_view(), name="learn-settings"),
    path("devices/", learn.DeviceView.as_view(), name="devices"),
    path("insights/", include(insights.urlpatterns)),  # staff only: insights/api.py
    *router.urls,
]

# The shop's category tree and collections (Phase 6 E)
store_router = SimpleRouter()
store_router.register("categories", shop.CategoryViewSet)
store_router.register("collections", shop.CollectionViewSet)
urlpatterns += store_router.urls

# Parcels and couriers, for staff (shipping/api.py; API.md "Shipping (staff)"); beside the public shipping/ and
# shipping/quote/ above, which are the checkout's delivery rates.
shipping_router = SimpleRouter()
shipping_router.register("shipping/shipments", shipping.ShipmentViewSet, basename="shipping-shipment")
shipping_router.register("shipping/exceptions", shipping.ExceptionViewSet, basename="shipping-exception")
shipping_router.register("shipping/cod", shipping.CodRemittanceViewSet, basename="shipping-cod")
shipping_router.register("shipping/charges", shipping.ChargeViewSet, basename="shipping-charge")
shipping_router.register("shipping/pickup-locations", shipping.PickupLocationViewSet, basename="shipping-pickup")
urlpatterns += [
    path("shipping/orders/<str:number>/quote/", shipping.OrderQuoteView.as_view(), name="shipping-order-quote"),
    path("shipping/manifest/", shipping.ManifestView.as_view(), name="shipping-manifest"),
    *shipping_router.urls,
]
