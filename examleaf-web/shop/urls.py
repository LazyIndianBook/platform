from django.urls import path

from . import views

app_name = "shop"
urlpatterns = [
    path("shop/", views.CatalogueView.as_view(), name="catalogue"),
    path("shop/webhooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
    path("shop/media/<path:name>", views.product_media, name="media"),
    path("shop/pin/<str:pin>/", views.pin_lookup, name="pin"),
    path("shop/school-orders/", views.quote_request, name="quote"),  # before shop/<slug>/: it is a slug too
    path("shop/category/<slug:slug>/", views.CategoryView.as_view(), name="category"),  # Product.RESERVED_SLUGS
    path("shop/collection/<slug:slug>/", views.CollectionView.as_view(), name="collection"),
    path("shop/<slug:slug>/", views.ProductView.as_view(), name="product"),
    path("shop/<slug:slug>/review/", views.review, name="review"),
    path("shop/<slug:slug>/stock-alert/", views.stock_alert, name="stock_alert"),
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
    path("account/orders/<str:number>/credit-notes/<int:note>/", views.invoice_pdf, name="credit_note"),
    path("orders/lookup/", views.lookup, name="lookup"),
    path("orders/t/<slug:token>/", views.order_detail, name="order_link"),  # the link in the order's emails
    path("orders/t/<slug:token>/cancel/", views.order_cancel, name="order_link_cancel"),
    path("orders/t/<slug:token>/invoice/", views.invoice_pdf, name="order_link_invoice"),
    path("orders/t/<slug:token>/credit-notes/<int:note>/", views.invoice_pdf, name="order_link_credit_note"),
    path("account/addresses/add/", views.AddressCreate.as_view(), name="address_add"),
    path("account/addresses/<int:pk>/", views.AddressUpdate.as_view(), name="address_edit"),
    path("account/addresses/<int:pk>/delete/", views.AddressDelete.as_view(), name="address_delete"),
]
