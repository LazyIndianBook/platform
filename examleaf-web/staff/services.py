"""What the panel does to people, staff and customers, each step audited (staff.audit.record): roles and scopes with
separation of duties, invitations, ending sessions, offboarding in one transaction; and the account actions support
needs (suspend, unlock, the parent's link again, a password reset link, a second factor reset, logging in as a
customer). The business rules stay where they are (accounts, shop); these call them."""

import hashlib
import secrets
from datetime import timedelta
from importlib import import_module

from allauth.account.forms import ResetPasswordForm
from allauth.account.models import EmailAddress
from allauth.usersessions.models import UserSession
from axes.utils import reset as axes_reset
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.db import IntegrityError, transaction
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import roles
from accounts.views import send_parent_link
from ops.tasks import queue_text_email

from .audit import Outcome, alert, record
from .middleware import IMPERSONATING, IMPERSONATION_ID, IMPERSONATION_REASON, IMPERSONATION_UNTIL
from .models import ApiKey, ChangeRequest, DataRequest, Impersonation, InboxItem, RoleGrant, StaffInvite, StaffScope

IMPERSONATION_SALT, IMPERSONATION_SECONDS = "staff.impersonation", 15 * 60


def staff_roles(user):
    """The person's role names (a break-glass account, a superuser, may have none: it passes every check anyway)."""
    return set(user.groups.values_list("name", flat=True))


def can_manage(actor, target):
    """Only a break-glass account changes a break-glass account's access (as in the admin), and only an owner an
    owner's: nobody demotes or offboards the people who approve their own requests."""
    if target.is_superuser and not actor.is_superuser:
        raise exceptions.PermissionDenied("Only a superuser changes a superuser's access.")
    if target.is_owner and not actor.is_owner:
        raise exceptions.PermissionDenied("Only an owner changes an owner's access.")


def _check_role(role):
    if role not in roles.STAFF_ROLES:
        raise serializers.ValidationError({"role": [f"Not a staff role: {role}."]})


def sod_problem(held, role):
    """Why `role` may not join `held` (SOD_CONFLICTS), or None."""
    if pairs := roles.conflicts({*held, role}):
        a, b = pairs[0]
        return f"{a} and {b} may not be held by one person (separation of duties)."
    return None


def grant_role(user, role, *, by, expires_at=None, reason="", change_request=None):
    """Give a role now: the group, `is_staff`, and a RoleGrant with who, why and until when. Refuses a role that SSD
    keeps apart from one the person holds (400). The audit event is the group change's (staff.signals)."""
    _check_role(role)
    if problem := sod_problem(staff_roles(user) - {role}, role):
        raise serializers.ValidationError({"role": [problem]})
    with transaction.atomic():
        user._audit_context = {"reason": reason, "expires_at": expires_at, "change_request": change_request}
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        RoleGrant.objects.update_or_create(
            user=user,
            role=role,
            defaults={"granted_by": by, "reason": reason, "expires_at": expires_at, "created": timezone.now()},
        )
    return user


def revoke_role(user, role, *, by, reason=""):
    """Take a role away at once (no approval: removing access is safe); privileged roles alert the owners."""
    _check_role(role)
    with transaction.atomic():
        user._audit_context = {"reason": reason}
        user.groups.remove(*Group.objects.filter(name=role))
        RoleGrant.objects.filter(user=user, role=role).delete()
        staff = user.is_superuser or user.groups.filter(name__in=roles.STAFF_ROLES).exists()
        if staff != user.is_staff:
            user.is_staff = staff
            user.save(update_fields=["is_staff"])
        if role in roles.PRIVILEGED_ROLES:
            who = f"user #{by.pk}" if by else "the nightly task"
            alert(f"{role} taken from user #{user.pk}", f"By {who}. Reason: {reason or '(none given)'}")
    return user


def add_scope(user, kind, value, *, by, expires_at=None):
    try:
        with transaction.atomic():
            scope = StaffScope.objects.create(user=user, kind=kind, value=value, granted_by=by, expires_at=expires_at)
            record(
                "authz_change",
                target=user,
                details={"scope": {"kind": kind, "value": value}, "added": True, "expires_at": expires_at},
            )
    except IntegrityError as error:
        raise serializers.ValidationError({"value": ["This scope is there already."]}) from error
    return scope


def remove_scope(scope, *, by):
    with transaction.atomic():
        details = {"scope": {"kind": scope.kind, "value": scope.value}, "added": False}
        scope.delete()
        record("authz_change", target=scope.user, details=details)


def end_sessions(user, *, request=None, audit=True):
    """Sign the person out everywhere: every session allauth.usersessions tracks (the website, the panel, the app's
    allauth session) and the app's refresh tokens (blacklisted). Returns (sessions, tokens)."""
    sessions = 0
    for session in UserSession.objects.filter(user=user):
        session.end()
        sessions += 1
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create([BlacklistedToken(token=token) for token in tokens], ignore_conflicts=True)
    if audit:
        record(
            "session_ended_by_staff",
            request=request,
            target=user,
            details={"sessions": sessions, "tokens": len(tokens)},
        )
    return sessions, len(tokens)


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def send_invite(email, role, *, by, change_request=None):
    """An invitation to join the staff as `role`: a link valid StaffInvite.VALID that only the email holds."""
    _check_role(role)
    token = secrets.token_urlsafe(32)
    invite = StaffInvite.objects.create(
        email=email.lower(),
        role=role,
        token_hash=token_digest(token),
        invited_by=by,
        expires_at=timezone.now() + StaffInvite.VALID,
    )
    record("staff.invited", target=invite, change_request=change_request, details={"role": role, "email": email})
    link = f"{settings.STAFF_PANEL_URL}/invite/{token}/"
    queue_text_email(
        invite.email,
        "You are invited to ExamLeaf's staff",
        f"You have been invited to join ExamLeaf's staff as {role}. Open this link within 7 days to accept (log in "
        f"first if you have an account with this address; otherwise you choose a password there):\n\n{link}\n\n"
        "After that you set up an authenticator app or a passkey before anything opens. If you were not expecting "
        "this, ignore the email.",
    )
    return invite


def accept_invite(token, *, user=None, full_name="", password="", request=None):
    """The invitation's link: the role for the signed-in account with the invitation's (confirmed) address, or a new
    account made with it (the link proves the address). Returns the user."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    invite = StaffInvite.objects.filter(token_hash=token_digest(token)).first()
    if invite is None or not invite.is_open:
        raise serializers.ValidationError({"token": ["This invitation is not valid: it was used, revoked or expired."]})
    User = get_user_model()
    new = user is None or not user.is_authenticated
    if not new:
        confirmed = EmailAddress.objects.filter(user=user, email__iexact=invite.email, verified=True).exists()
        if not confirmed:
            raise exceptions.PermissionDenied("This invitation is for another address.")
    elif User.objects.filter(email__iexact=invite.email).exists():
        raise exceptions.NotAuthenticated("An account has this address: log in first, then open the link again.")
    elif not full_name or not password:
        raise serializers.ValidationError({"full_name": ["Give your name and a password."]})
    else:
        try:
            validate_password(password)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
    with transaction.atomic():
        invite = StaffInvite.objects.select_for_update().get(pk=invite.pk)
        if not invite.is_open:  # two clicks at once
            raise serializers.ValidationError({"token": ["This invitation was used."]})
        if new:
            user = User.objects.create_user(invite.email, password, full_name=full_name)
            EmailAddress.objects.create(user=user, email=invite.email, verified=True, primary=True)
        grant_role(user, invite.role, by=invite.invited_by, reason=f"Invitation #{invite.pk}")
        invite.accepted_at, invite.accepted_by = timezone.now(), user
        invite.save(update_fields=["accepted_at", "accepted_by"])
        record("staff.invite_accepted", request=request, actor=user, target=invite, details={"role": invite.role})
    return user


def offboard(user, *, by, reason, request=None):
    """Research 2.9 in one transaction: deactivated, roles, grants and scopes gone, every session ended and refresh
    token blacklisted, the API keys they sponsor revoked, their pending requests expired, their inbox items and data
    requests unassigned. The owners are told. Returns what was done."""
    can_manage(by, user)
    if user.pk == by.pk:
        raise exceptions.PermissionDenied("Nobody offboards themselves.")
    with transaction.atomic():
        # the rows first, the audit log's lock last (as every writer: no deadlock with an approval of these)
        pending = list(ChangeRequest.objects.select_for_update().filter(maker=user, status__in=["pending", "approved"]))
        held = sorted(staff_roles(user))
        user._audit_context = {"reason": reason, "offboarding": True}
        user.groups.clear()
        RoleGrant.objects.filter(user=user).delete()
        scopes = StaffScope.objects.filter(user=user).delete()[0]
        keys = ApiKey.objects.filter(sponsor=user, revoked_at=None).update(revoked_at=timezone.now(), revoked_by=by)
        for change_request in pending:
            change_request.expire()
            change_request.save()
            record(
                f"{change_request.action}.expired",
                request=request,
                change_request=change_request,
                reason="The maker was offboarded.",
            )
        InboxItem.objects.filter(assignee=user, done_at=None).update(assignee=None)
        DataRequest.objects.filter(assignee=user).exclude(status=DataRequest.Status.CLOSED).update(assignee=None)
        user.is_active = user.is_staff = user.is_superuser = False
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        sessions, tokens = end_sessions(user, audit=False)
        done = {
            "roles": held,
            "scopes": scopes,
            "api_keys": keys,
            "change_requests": len(pending),
            "sessions": sessions,
            "tokens": tokens,
        }
        record("user.offboarded", request=request, target=user, reason=reason, details=done)
        alert(f"Staff member #{user.pk} offboarded", f"By user #{by.pk}. Reason: {reason}\n\n{done}")
    return done


# Customers' accounts (users/)


def suspend(user, *, reason, request=None):
    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])
        sessions, tokens = end_sessions(user, audit=False)
        record("user.suspended", request=request, target=user, reason=reason, details={"sessions": sessions})
    queue_text_email(
        user.email,
        "Your ExamLeaf account is suspended",
        f"Your ExamLeaf account has been suspended and signed out. If you think this is a mistake, write to us: "
        f"{settings.SITE_URL}/contact/",
    )


def unsuspend(user, *, reason, request=None):
    with transaction.atomic():
        user.is_active = True
        user.save(update_fields=["is_active"])
        record("user.unsuspended", request=request, target=user, reason=reason)


def unlock(user, *, request=None):
    """Lift django-axes' lock-out of the account (its email address and its log-in number)."""
    names = [user.email, *([user.login_phone] if user.login_phone else [])]
    cleared = sum(axes_reset(username=name) for name in names)
    record("user.unlocked", request=request, target=user, details={"attempts_cleared": cleared})
    return cleared


def resend_verification(user, *, request=None):
    """The parent's consent link again (PARENTAL_CONSENT_MODE "verified", while it waits). An email address is
    confirmed by a code at log-in: nothing to send for it from here."""
    if not user.consent_pending:
        raise serializers.ValidationError(
            {
                "non_field_errors": [
                    "Nothing waits: no parent's consent is pending. An email address is confirmed by "
                    "the code it gets at its next log-in."
                ]
            }
        )
    sent = send_parent_link(user)
    record("user.verification_resent", request=request, target=user, details={"what": "parent_link", "sent": sent})
    if not sent:
        raise exceptions.Throttled(detail="The parent's address or number has had its links for today.")


def start_password_reset(user, *, request):
    """allauth's reset email to the account's address (staff never see or set a password: ASVS 6.4.6)."""
    form = ResetPasswordForm(data={"email": user.email})
    if not form.is_valid() or not user.is_active:
        raise serializers.ValidationError({"non_field_errors": ["This account cannot reset its password."]})
    form.save(getattr(request, "_request", request))
    record("user.password_reset_started", request=request, target=user)


def reset_mfa(user):
    """A second factor reset (after approval: staff.approvals): authenticator apps, recovery codes and passkeys go,
    every session ends, the person is told; the next log-in sets a new one up (staff must)."""
    deleted = user.authenticator_set.all().delete()[0]
    sessions, _ = end_sessions(user, audit=False)
    queue_text_email(
        user.email,
        "Your second factor was reset",
        "The authenticator apps, recovery codes and passkeys of your ExamLeaf account were removed at your request, "
        "and every device was signed out. If you did not ask for this, write to us at once: "
        f"{settings.SITE_URL}/contact/",
    )
    return {"authenticators": deleted, "sessions": sessions}


def impersonable(user):
    """Why `user` may not be logged in as, or None: never staff, a student under 18, a suspended account."""
    if user.is_staff or user.is_superuser:
        return "Staff accounts are never impersonated."
    if user.is_minor:
        return "Accounts of students under 18 are never impersonated."
    if not user.is_active:
        return "The account is suspended or erased."
    return None


def impersonation_token(staff, user, *, reason, ticket, request=None):
    """Research 2.7: a signed token, valid IMPERSONATION_SECONDS, that the website's account area accepts once for a
    session as the customer (accept_impersonation), read-only for money, passwords, email, second factors, consent,
    addresses and deletion (staff.middleware). Never for staff or for a student under 18. Its Impersonation row binds
    it to the member of staff and to the panel's session it was asked from. Logged, and the owners told."""
    if user.is_staff or user.is_superuser or user.is_minor:
        raise exceptions.PermissionDenied(impersonable(user))
    if not user.is_active:
        raise serializers.ValidationError({"non_field_errors": [impersonable(user)]})
    expires_at = timezone.now() + timedelta(seconds=IMPERSONATION_SECONDS)
    with transaction.atomic():
        grant = Impersonation.objects.create(
            staff=staff,
            user=user,
            reason=reason[:300],
            ticket=ticket[:60],
            staff_session_key=getattr(getattr(request, "session", None), "session_key", None) or "",
            expires_at=expires_at,
        )
        event = record(
            "user.impersonation_started",
            request=request,
            target=user,
            reason=reason,
            details={"ticket": ticket, "expires_at": expires_at, "impersonation": grant.pk},
        )
    payload = {"staff": staff.pk, "user": user.pk, "event": event.pk, "id": grant.pk}
    token = signing.dumps(payload, salt=IMPERSONATION_SALT, compress=True)
    alert(f"User #{staff.pk} logs in as customer #{user.pk}", f"Reason: {reason}\nTicket: {ticket}")
    return token, expires_at


def read_impersonation_token(token, max_age=IMPERSONATION_SECONDS):
    """The token's {"staff", "user", "event", "id"}, or None when forged or expired."""
    try:
        return signing.loads(token, salt=IMPERSONATION_SALT, max_age=max_age)
    except signing.BadSignature:
        return None


def end_impersonation(staff, user, token, *, request=None):
    """The panel's end: the website's session, if one was opened, ends at its next request."""
    data = read_impersonation_token(token, max_age=None)
    if not data or data["staff"] != staff.pk or data["user"] != user.pk:
        raise serializers.ValidationError({"token": ["Not a token of yours for this account."]})
    Impersonation.objects.filter(pk=data.get("id"), ended_at=None).update(ended_at=timezone.now())
    record("user.impersonation_ended", request=request, target=user, details={"started": data["event"]})


# The website's side of logging in as a customer (the account API's account/impersonate/)

NOT_VALID = {"token": ["This link to log in as the customer is not valid: used, expired, ended or forged."]}


def staff_session_alive(grant):
    """Whether the panel's session the token was asked from is still signed in as its member of staff."""
    if not grant.staff_session_key:
        return False
    store = import_module(settings.SESSION_ENGINE).SessionStore(session_key=grant.staff_session_key)
    return store.load().get(SESSION_KEY) == str(grant.staff_id)


def accept_impersonation(request, token):
    """Log the visitor's browser in as the token's customer (research 2.7): once per token (accepted_at, set by the
    first request only), within its 15 minutes, while its member of staff may and the panel's session it came from is
    still signed in. A new session, marked with who, until when and why, ending at `until`; its device-list row says
    "Staff (support) until <time>". Not the customer's own log-in: their last log-in, lock-outs and authentication
    records stay theirs (so no django.contrib.auth.login and its signals). Returns the Impersonation."""
    data = read_impersonation_token(token) or {}
    grant = (
        Impersonation.objects.select_related("staff", "user")
        .filter(pk=data.get("id"), staff_id=data.get("staff"), user_id=data.get("user"))
        .first()
    )
    if grant is None:  # forged, or older than 15 minutes: nobody to name in the log
        raise serializers.ValidationError(NOT_VALID)
    now, staff, user = timezone.now(), grant.staff, grant.user
    unused = Impersonation.objects.filter(pk=grant.pk, accepted_at=None, ended_at=None, expires_at__gt=now)
    claimed, why = unused.update(accepted_at=now), None  # (one request only can set it)
    if not claimed:
        why = "used, ended or expired"
    elif not (staff.is_active and staff.has_perm("staff.impersonate_user")) or not staff_session_alive(grant):
        why = "the member of staff may no longer, or signed out of the panel"
    elif problem := impersonable(user):
        why = problem
    if why:
        if claimed:  # taken by this request, opened nothing: it is over
            Impersonation.objects.filter(pk=grant.pk).update(ended_at=now)
        record(
            "user.impersonation_refused",
            request=request,
            actor=staff,
            target=user,
            outcome=Outcome.DENIED,
            on_behalf_of=user,
            details={"impersonation": grant.pk, "why": why},
        )
        raise serializers.ValidationError(NOT_VALID)
    session = request.session
    if session.get(IMPERSONATION_ID):  # this browser was logged in as another customer: that ends here
        impersonation_ended(request, request.user, "another opened")
    session.flush()  # a new session: nothing of the browser's before carries over
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session[IMPERSONATING], session[IMPERSONATION_UNTIL] = staff.pk, grant.expires_at.isoformat()
    session[IMPERSONATION_REASON], session[IMPERSONATION_ID] = grant.reason, grant.pk
    session.set_expiry(grant.expires_at)
    session.save()
    rotate_token(request)
    request.user = user
    UserSession.objects.create_from_request(request)
    label = f"Staff (support) until {timezone.localtime(grant.expires_at):%H:%M}"
    UserSession.objects.filter(session_key=session.session_key).update(
        user_agent=label, data={"impersonation": grant.pk, "staff_label": label}
    )
    record("user.impersonation_accepted", request=request, target=user, details={"impersonation": grant.pk})
    return grant


def website_impersonation_over(request):
    """Why the session's impersonation is over (its time, its end by either side, the panel's session gone), or
    None. Only a marked session is asked."""
    until = parse_datetime(request.session.get(IMPERSONATION_UNTIL) or "")
    if until is None or until <= timezone.now():
        return "expired"
    grant = Impersonation.objects.filter(pk=request.session.get(IMPERSONATION_ID)).first()
    if grant is None or grant.ended_at is not None:
        return "ended"
    if not staff_session_alive(grant):
        return "the panel's session ended"
    return None


def impersonation_banner(request, user):
    """{"until", "by": the member of staff's masked address} while a member of staff is logged in as `user` in this
    session (the website's banner on every page), else None."""
    from .privacy import mask_email

    session = getattr(request, "session", None)
    if session is None or not session.get(IMPERSONATING) or session.get(SESSION_KEY) != str(user.pk):
        return None
    staff = get_user_model().objects.filter(pk=session[IMPERSONATING]).only("email").first()
    return {"until": session.get(IMPERSONATION_UNTIL), "by": mask_email(staff.email) if staff else ""}


def impersonation_ended(request, user, why):
    """The session's end (its log-out, by DELETE account/impersonate/, the customer's own log-out, or the middleware
    when it is over): the Impersonation is ended, and the event names the member of staff."""
    grant = request.session.get(IMPERSONATION_ID)
    Impersonation.objects.filter(pk=grant, ended_at=None).update(ended_at=timezone.now())
    record("user.impersonation_ended", request=request, target=user, details={"impersonation": grant, "why": why})
