from django.urls import path

from . import views

app_name = "shop"
urlpatterns = [
    path("shop/", views.CatalogueView.as_view(), name="catalogue"),
    path("shop/webhooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
    path("shop/media/<path:name>", views.product_media, name="media"),
    path("shop/<slug:slug>/", views.ProductView.as_view(), name="product"),
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/<str:number>/pay/", views.pay, name="pay"),
    path("checkout/<str:number>/paid/", views.pay_verify, name="pay_verify"),
    path("checkout/<str:number>/done/", views.order_detail, {"thanks": True}, name="done"),
    path("account/orders/", views.OrderListView.as_view(), name="orders"),
    path("account/orders/<str:number>/", views.order_detail, name="order"),
    path("account/orders/<str:number>/cancel/", views.order_cancel, name="order_cancel"),
    path("account/orders/<str:number>/invoice/", views.invoice_pdf, name="invoice"),
    path("orders/lookup/", views.lookup, name="lookup"),
]
