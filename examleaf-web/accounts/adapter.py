from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.core import context as allauth_context
from allauth.core import ratelimit
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.core.internal.httpkit import headed_redirect_response
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.webauthn.internal.flows import did_use_passwordless_login
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.base import AuthProcess
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
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


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user):
        """allauth.headless's user (`auth/session`, which the website reads on every page) with `impersonation`:
        {"until", "by"} while a member of staff is logged in as this customer (the website's banner), else null."""
        from staff.services import impersonation_banner

        return {**super().serialize_user(user), "impersonation": impersonation_banner(self.request, user)}


class MFAAdapter(DefaultMFAAdapter):
    def get_public_key_credential_rp_entity(self):
        """Passkeys belong to the host of SITE_URL, whichever host name the page was opened on (allauth's default is
        the request's host: www. and the bare domain would not share passkeys)."""
        return {"id": urlparse(settings.SITE_URL).hostname, "name": "ExamLeaf"}


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_app(self, request, provider, client_id=None):
        """Google's URLs exist whether or not GOOGLE_CLIENT_ID and _SECRET are set; without them allauth failed every
        request to them (a crawler's, a stale bookmark's) with a server error. Here they are not found."""
        try:
            return super().get_app(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist:
            raise Http404("This way of logging in is not set up.") from None

    def list_apps(self, request, provider=None, client_id=None):
        """One Google client per host: the staff's own (STAFF_GOOGLE_CLIENT_ID, the Workspace's Internal consent
        screen) on the admin host when there is one, the website's everywhere else."""
        apps = super().list_apps(request, provider=provider, client_id=client_id)
        staffs = {app.provider for app in apps if app.settings.get("staff")}
        admin_host = request is not None and explicit_admin_host(request)
        return [app for app in apps if app.provider not in staffs or bool(app.settings.get("staff")) == admin_host]

    def pre_social_login(self, request, sociallogin):
        """Google Workspace for staff (plan 3.5; research-integrations.md 4.4). With STAFF_GOOGLE_DOMAIN set, a staff
        Google sign-in (on the admin host, into or onto a staff account, or by an account of the domain) needs the ID
        token's `hd` claim to be the domain and its address confirmed (the `hd` request parameter is only a hint),
        never reaches a break-glass account (outside Google sign-in), and makes a new account only with
        STAFF_GOOGLE_AUTO_STAFF; otherwise the account exists already and is staff, linked by Google's `sub` (never by
        the email). Refused: a ValidationError (headless: `?error=<code>`) and `authz_fail`. A student's Google sign-in
        on the website is as before. allauth's second-factor stage still runs after the sign-in."""
        domain = settings.STAFF_GOOGLE_DOMAIN
        if not domain or sociallogin.account.provider != "google":
            return
        claims = sociallogin.account.extra_data
        matches = str(claims.get("hd") or "").lower() == domain
        verified = claims.get("email_verified") is True or claims.get("verified_email") is True  # id token, userinfo
        connect = sociallogin.state.get("process") == AuthProcess.CONNECT
        signed_in = request.user if request.user.is_authenticated else None
        user = sociallogin.user if sociallogin.is_existing else (signed_in if connect else None)
        staff = user is not None and (user.is_staff or user.is_superuser)
        if not (staff or matches or explicit_admin_host(request)):
            return
        if not (matches and verified):
            refuse_google(request, user, "staff_google_domain", f"Staff sign in with their @{domain} Google account.")
        if user is not None and user.is_superuser:
            refuse_google(request, user, "staff_google_break_glass", BREAK_GLASS_NOT_GOOGLE)
        if connect:
            return  # onto the signed-in account: its own second factor was asked at its log-in
        if user is not None:
            if not staff:
                refuse_google(request, user, "staff_google_not_staff", "This account is not a member of staff.")
            return
        email = (sociallogin.user.email or "").lower()
        if not (settings.STAFF_GOOGLE_AUTO_STAFF and email.endswith(f"@{domain}")):
            refuse_google(request, None, "staff_google_no_account", NO_STAFF_ACCOUNT)
        if User.objects.filter(email__iexact=email).exists():  # (linked by `sub` only: never joined by the address)
            refuse_google(request, None, "staff_google_no_account", NO_STAFF_ACCOUNT)
        sociallogin.staff_signup = True

    def is_auto_signup_allowed(self, request, sociallogin):
        """A Workspace account of the domain with STAFF_GOOGLE_AUTO_STAFF (pre_social_login allowed it): signed up at
        once, without the student details."""
        return getattr(sociallogin, "staff_signup", False) or super().is_auto_signup_allowed(request, sociallogin)

    def save_user(self, request, sociallogin, form=None):
        """A staff sign-up through Google: a member of staff with no role (nothing opens until an owner gives one) who
        sets up a second factor before anything (StaffMFAMiddleware)."""
        if getattr(sociallogin, "staff_signup", False):
            user = sociallogin.user
            user.full_name = sociallogin.account.extra_data.get("name") or user.email.split("@")[0]
            user.is_staff = True
        return super().save_user(request, sociallogin, form=form)


BREAK_GLASS_NOT_GOOGLE = "A break-glass account signs in with its password and security key, never with Google."
NO_STAFF_ACCOUNT = (
    "No staff account is linked to this Google account: sign in with your password and connect Google on your "
    "account's page, or ask an owner for an invitation."
)


def explicit_admin_host(request):
    """On a host of ADMIN_HOSTS when it is set (empty, every host is one for the staff API: not for Google)."""
    from staff.middleware import on_admin_host

    return bool(settings.ADMIN_HOSTS) and on_admin_host(request)


def refuse_google(request, user, code, message):
    """Refuse the staff Google sign-in: recorded as `authz_fail` (committed whatever follows), then a ValidationError
    (allauth.headless: the frontend's callback with `?error=<code>`; the app's token flow: 400 with the message)."""
    from staff.audit import ActorType, Outcome, record

    record(
        "authz_fail",
        request=request,
        actor=user,
        actor_type=None if user else ActorType.ANONYMOUS,
        outcome=Outcome.DENIED,
        details={"provider": "google", "error": code},
    )
    raise ValidationError(message, code=code)
