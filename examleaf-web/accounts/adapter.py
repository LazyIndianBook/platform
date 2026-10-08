import io
from urllib.parse import urlparse

import segno
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from allauth.mfa.adapter import DefaultMFAAdapter
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site

from ops.sms import queue_sms
from ops.tasks import queue_email

from .forms import IndianPhoneField, normalise_phone
from .models import User


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        """allauth's send_mail, with the sending done by a Celery task (rendering stays here: it needs the request)."""
        request = allauth_context.request
        context = {"request": request, "email": email, "current_site": get_current_site(request), **context}
        queue_email(self.render_mail(template_prefix, email, context))

    # Log-in by mobile number (allauth's "phone" method): User.login_phone holds a number only once its SMS code was
    # confirmed. send_unknown_account_sms and send_account_already_exists_sms stay allauth's empty ones: anything else
    # would let a stranger make the site text any number.
    def phone_form_field(self, **kwargs):
        return IndianPhoneField(**kwargs)

    def send_verification_code_sms(self, user, phone, code, **kwargs):
        queue_sms("otp", phone, {"otp": code})

    def get_user_by_phone(self, phone):
        phone = normalise_phone(phone)  # a password log-in passes the number as typed
        users = User.objects.filter(login_phone=phone, login_phone_verified=True, is_active=True)
        return users.first() if phone else None

    def get_phone(self, user):
        return (user.login_phone, True) if user.login_phone_verified else None

    def set_phone(self, user, phone, verified):
        user.login_phone, user.login_phone_verified = phone, verified
        user.save(update_fields=["login_phone", "login_phone_verified"])

    def set_phone_verified(self, user, phone):
        """The number moves to this account: any other account loses it (one account per number)."""
        others = User.objects.filter(login_phone=phone).exclude(pk=user.pk)
        others.update(login_phone="", login_phone_verified=False, sms_updates=False)
        self.set_phone(user, phone, True)

    def _get_login_attempts_cache_key(self, request, **credentials):
        """allauth's limit of failed log-ins per account (5 in 5 minutes) is keyed on the email: every phone log-in
        would share one empty key, a lock-out of all of them. Their key is the number."""
        if phone := credentials.get("phone"):
            return f"phone:{normalise_phone(phone) or phone}"
        return super()._get_login_attempts_cache_key(request, **credentials)


class MFAAdapter(DefaultMFAAdapter):
    def get_public_key_credential_rp_entity(self):
        """Passkeys belong to the host of SITE_URL, whichever host name the page was opened on (allauth's default is
        the request's host: www. and the bare domain would not share passkeys)."""
        return {"id": urlparse(settings.SITE_URL).hostname, "name": "ExamLeaf"}

    def build_totp_svg(self, url):
        """The authenticator app's QR code, drawn by segno (the papers' QR codes) rather than the qrcode package."""
        svg = io.BytesIO()
        segno.make(url).save(svg, kind="svg", xmldecl=False, scale=4)
        return svg.getvalue().decode()
