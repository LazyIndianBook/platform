from django.urls import path

from . import views

app_name = "shop"
urlpatterns = [
    path("shop/webhooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
    path("shop/media/<path:name>", views.product_media, name="media"),
]
