"""What the panel does to people, staff and customers, each step audited (staff.audit.record): roles and scopes with
separation of duties, invitations, ending sessions, offboarding in one transaction; and the account actions support
needs (suspend, unlock, the parent's link again, a password reset link, a second factor reset, logging in as a
customer). The business rules stay where they are (accounts, shop); these call them."""

import hashlib
import secrets
from datetime import timedelta

from allauth.account.forms import ResetPasswordForm
from allauth.account.models import EmailAddress
from allauth.usersessions.models import UserSession
from axes.utils import reset as axes_reset
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import roles
from accounts.views import send_parent_link
from ops.tasks import queue_text_email

from .audit import alert, record
from .models import ApiKey, ChangeRequest, DataRequest, InboxItem, RoleGrant, StaffInvite, StaffScope

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


def impersonation_token(staff, user, *, reason, ticket, request=None):
    """Research 2.7: a signed token, valid IMPERSONATION_SECONDS, that the website's account area will accept for a
    session as the customer, read-only for money, passwords, email, second factors, consent, addresses and deletion
    (staff.middleware.ImpersonationGuard). Never for staff or for a student under 18. Logged, and the owners told."""
    if user.is_staff or user.is_superuser:
        raise exceptions.PermissionDenied("Staff accounts are never impersonated.")
    if user.is_minor:
        raise exceptions.PermissionDenied("Accounts of students under 18 are never impersonated.")
    if not user.is_active:
        raise serializers.ValidationError({"non_field_errors": ["The account is suspended or erased."]})
    expires_at = timezone.now() + timedelta(seconds=IMPERSONATION_SECONDS)
    event = record(
        "user.impersonation_started",
        request=request,
        target=user,
        reason=reason,
        details={"ticket": ticket, "expires_at": expires_at},
    )
    payload = {"staff": staff.pk, "user": user.pk, "event": event.pk}
    token = signing.dumps(payload, salt=IMPERSONATION_SALT, compress=True)
    alert(f"User #{staff.pk} logs in as customer #{user.pk}", f"Reason: {reason}\nTicket: {ticket}")
    return token, expires_at


def read_impersonation_token(token, max_age=IMPERSONATION_SECONDS):
    """The token's {"staff", "user", "event"}, or None when forged or expired (for the website's account area)."""
    try:
        return signing.loads(token, salt=IMPERSONATION_SALT, max_age=max_age)
    except signing.BadSignature:
        return None


def end_impersonation(staff, user, token, *, request=None):
    data = read_impersonation_token(token, max_age=None)
    if not data or data["staff"] != staff.pk or data["user"] != user.pk:
        raise serializers.ValidationError({"token": ["Not a token of yours for this account."]})
    record("user.impersonation_ended", request=request, target=user, details={"started": data["event"]})
