from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        # drf-spectacular's dj-rest-auth extension also describes dj-rest-auth's sign-up views, which this API does not
        # use (they need allauth.socialaccount; api/auth.py has its own): mark them absent rather than warn.
        from drf_spectacular.contrib import rest_auth

        for extension in (
            rest_auth.RestAuthRegisterView,
            rest_auth.RestAuthVerifyEmailView,
            rest_auth.RestAuthResendEmailVerificationView,
        ):
            extension.target_class = None
