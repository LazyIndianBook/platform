from django.urls import path

from . import views

app_name = "learn"
urlpatterns = [
    path("hls/<str:token>/<path:name>", views.hls, name="hls"),
]
