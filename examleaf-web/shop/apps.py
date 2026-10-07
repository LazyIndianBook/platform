from django.apps import AppConfig


class ShopConfig(AppConfig):
    name = "shop"

    def ready(self):
        from . import cart  # noqa: F401  the guest cart joins the user's cart at log-in (signal receiver)
