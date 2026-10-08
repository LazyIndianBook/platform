import io
from urllib.parse import urlparse

import segno
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.core import context as allauth_context
from allauth.core import ratelimit
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.core.internal.httpkit import headed_redirect_response
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.webauthn.internal.flows import did_use_passwordless_login
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.http import Http404

from ops.sms import queue_sms
from ops.tasks import queue_email, queue_text_email

from .forms import IndianPhoneField, normalise_phone
from .models import User


class TooManyCodes(ImmediateHttpResponse):
    """No code made: its address or number has had its share (M1, M2). allauth's 429 page (or headless answer) on the
    website; the API answers 429 with `detail` (api.views.exception_handler). Raised before allauth keeps the code."""

    def __init__(self, request, detail):
        super().__init__(ratelimit.respond_429(request))
        self.detail = detail


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        """allauth's send_mail, with the sending done by a Celery task (rendering stays here: it needs the request)."""
        request = allauth_context.request
        context = {"request": request, "email": email, "current_site": get_current_site(request), **context}
        queue_email(self.render_mail(template_prefix, email, context))

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """An email confirmation code: allauth makes one at the sign-up and at every log-in of an address not yet
        confirmed. At most 5 an hour and 10 a day per address (ACCOUNT_RATE_LIMITS email_code_hour and _day), so that
        an address without an account cannot be confirmed by guessing (M1): over them nothing is sent or kept."""
        email = emailconfirmation.email_address.email.lower()
        for action in ("email_code_day", "email_code_hour"):
            if not ratelimit.consume(request, action=action, key=email):
                raise TooManyCodes(request, "Too many codes have gone to this address: try again later.")
        super().send_confirmation_mail(request, emailconfirmation, signup)

    # Log-in by mobile number (allauth's "phone" method): User.login_phone holds a number only once its SMS code was
    # confirmed. send_unknown_account_sms and send_account_already_exists_sms stay allauth's empty ones: anything else
    # would let a stranger make the site text any number.
    def phone_form_field(self, **kwargs):
        return IndianPhoneField(**kwargs)

    def send_verification_code_sms(self, user, phone, code, **kwargs):
        """allauth's SMS codes (phone log-in, phone confirmation), within ops.sms's limits per number, account and
        purpose (M2). A refused one is not kept, and the page says so (429) instead of "sent"."""
        if not queue_sms("otp", phone, {"otp": code}, user=user):
            detail = "Too many messages have gone to this number: try again tomorrow, or log in with your email."
            raise TooManyCodes(allauth_context.request, detail)

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
        """The number moves to this account: any other account loses it (one account per number). A new number is a
        whole new way to log in, so the account is told by email, and so is the one that lost it (L6)."""
        others = User.objects.filter(login_phone=phone).exclude(pk=user.pk)
        losers = list(others.filter(login_phone_verified=True).values_list("email", flat=True))
        others.update(login_phone="", login_phone_verified=False, sms_updates=False)
        new = not (user.login_phone == phone and user.login_phone_verified)  # also called at each log-in by SMS code
        self.set_phone(user, phone, True)
        account = f"{settings.SITE_URL}/account/"
        if new:
            queue_text_email(
                user.email,
                "A mobile number was added to your account",
                f"The mobile number ending {phone[-4:]} now logs in to your ExamLeaf account with a code by SMS.\n\n"
                f"If you did not add it, log in, change your password and remove the number on My account: {account}",
            )
        for email in losers:
            queue_text_email(
                email,
                "Your mobile number was moved to another account",
                f"The mobile number ending {phone[-4:]} was confirmed on another ExamLeaf account: it no longer logs "
                f"in to yours, and order updates by SMS are off.\n\nIf the number is yours, add it again on My "
                f"account: {account}",
            )

    def pre_login(self, request, user, **kwargs):
        """Staff log in with the password and then the authenticator app or a passkey, never with a passkey alone
        (L5): allauth asks a key for user verification only as "preferred", so a lost key might sign in without its
        PIN. The passkey's record is dropped, so that the password log-in that follows is not taken for one."""
        if user.is_staff and did_use_passwordless_login(request):
            request.session.pop(AUTHENTICATION_METHODS_SESSION_KEY, None)
            self.add_message(request, messages.ERROR, message="Staff log in with the password, then the passkey.")
            return headed_redirect_response("account_login")
        return super().pre_login(request, user, **kwargs)

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


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_app(self, request, provider, client_id=None):
        """Google's URLs exist whether or not GOOGLE_CLIENT_ID and _SECRET are set; without them allauth failed every
        request to them (a crawler's, a stale bookmark's) with a server error. Here they are not found."""
        try:
            return super().get_app(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist:
            raise Http404("This way of logging in is not set up.") from None
