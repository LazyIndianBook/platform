"""What the panel does to people, staff and customers, each step audited (staff.audit.record): roles and scopes with
separation of duties, invitations, ending sessions, offboarding in one transaction; and the account actions support
needs (suspend, unlock, the parent's link again, a password reset link, a second factor reset, logging in as a
customer). The business rules stay where they are (accounts, shop); these call them. Phase B adds what the panel shows
about access (the role catalogue, a person's Access tab, a role change's preview, the ERPNext role mirror), a person's
own sessions, and the offboarding's checklist."""

import hashlib
import secrets
from datetime import timedelta
from importlib import import_module

from allauth.account.forms import ResetPasswordForm
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.usersessions.models import UserSession
from axes.utils import reset as axes_reset
from django.apps import apps
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import roles
from accounts.views import send_parent_link
from examleaf.middleware import idle_limit, idle_limit_of_roles, needs_passkey
from ops.tasks import queue_text_email

from . import catalogue
from .audit import Outcome, alert, record
from .middleware import IMPERSONATING, IMPERSONATION_ID, IMPERSONATION_REASON, IMPERSONATION_UNTIL
from .models import (
    ApiKey,
    AuditEvent,
    ChangeRequest,
    DataRequest,
    Impersonation,
    InboxItem,
    OffboardingStep,
    RoleGrant,
    StaffInvite,
    StaffOffboarding,
    StaffScope,
)
from .privacy import mask_ip

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
    token blacklisted, the API keys they sponsor revoked, their pending requests expired, their inbox items, data
    requests (and tickets, once the support desk exists) unassigned. Each step is a row of a StaffOffboarding, with the
    steps an owner does by hand (the ERPNext user, the external accounts, the security keys, the last 90 days) to tick
    off (tick_offboarding); an inbox item waits for them. The owners are told. Returns what was done."""
    can_manage(by, user)
    if user.pk == by.pk:
        raise exceptions.PermissionDenied("Nobody offboards themselves.")
    with transaction.atomic():
        # the rows first, the audit log's lock last (as every writer: no deadlock with an approval of these)
        pending = list(ChangeRequest.objects.select_for_update().filter(maker=user, status__in=["pending", "approved"]))
        held = sorted(staff_roles(user))
        user._audit_context = {"reason": reason, "offboarding": True}
        user.groups.clear()
        grants = RoleGrant.objects.filter(user=user)
        temporary = grants.exclude(expires_at=None).count()
        grants.delete()
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
        items = InboxItem.objects.filter(assignee=user, done_at=None).update(assignee=None)
        requests = DataRequest.objects.filter(assignee=user).exclude(status=DataRequest.Status.CLOSED)
        requests = requests.update(assignee=None)
        tickets = unassign_tickets(user)
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
        counts = {**done, "temporary": temporary, "inbox_items": items, "data_requests": requests, "tickets": tickets}
        offboarding = record_offboarding(user, by=by, reason=reason, counts=counts)
        done["offboarding"] = offboarding.pk
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


# Phase B: what a role and a person may do (the role catalogue, the Access tab, a role change's preview: research 1.8)

ROLE_ORDER = [roles.OWNER, roles.ADMIN, roles.FINANCE, roles.SALES, roles.SALES_REP, roles.PACKER, roles.SUPPORT]
ROLE_ORDER += [roles.CONTENT_EDITOR, roles.REVIEWER, roles.MARKETING, roles.AUDITOR]
LAST_USE_DAYS = 365  # the Access tab's last use of a high or critical permission: the audit log of a year at most
# The ERPNext role profiles each role maps to (examleaf-erp/README.md "Roles", research-erpnext 5.5), applied by hand
# in ERPNext while the staff are fewer than about 15 (people/<id>/erp/); the other roles have no ERPNext access.
ERP_ROLE_PROFILES = {
    roles.OWNER: ["EL Admin", "EL Finance"],
    roles.ADMIN: ["EL Admin"],
    roles.FINANCE: ["EL Finance"],
    roles.PACKER: ["EL Packer"],
    roles.SALES: ["EL Sales"],
    roles.SALES_REP: ["EL Sales"],
    roles.AUDITOR: ["EL Auditor"],
}


def role_names_in_order():
    return [*ROLE_ORDER, *sorted(roles.STAFF_ROLES - set(ROLE_ORDER))]


def group_permissions(names):
    """{role: {"app_label.codename", …}} of the role groups named, in one query (a role without its group: none)."""
    found = {name: set() for name in names}
    rows = Permission.objects.filter(group__name__in=list(names))
    for group, app_label, codename in rows.values_list("group__name", "content_type__app_label", "codename"):
        found[group].add(f"{app_label}.{codename}")
    return found


def capabilities(perms, last_used=None):
    """The catalogued permissions among `perms`, by area (label, risk and what it triggers), with the last use of each
    high or critical one when `last_used` ({perm: time}) is given. Uncatalogued ones (the superusers' own) are left
    out: no role holds them."""
    areas = {}
    for perm in sorted(perms):
        if (entry := catalogue.entry(perm)) is None:
            continue
        row = entry.as_dict()
        if last_used is not None:
            row["last_used"] = last_used.get(perm) if entry.reauth else None
        areas.setdefault(entry.area, []).append(row)
    return [{"area": area, "permissions": rows} for area, rows in sorted(areas.items())]


def erp_profiles(names):
    return sorted({profile for name in names for profile in ERP_ROLE_PROFILES.get(name, [])})


def role_catalogue(language="en"):
    """Every staff role (plan 4.1) as the role catalogue page draws it: what it is for and what it can't do, its
    capabilities by area with their risk, its limits and scopes, the roles it may not be held with, its ERPNext role
    profiles, whether it needs a passkey, its idle limit and how many active people hold it."""
    names = role_names_in_order()
    perms = group_permissions(names)
    active = Count("user", filter=Q(user__is_active=True))
    members = dict(Group.objects.filter(name__in=names).annotate(n=active).values_list("name", "n"))
    rows = []
    for name in names:
        cards = roles.ROLE_CARDS.get(name, {})
        card = cards.get(language) or cards.get("en") or {"for": "", "cannot": ""}
        rows.append(
            {
                "name": name,
                "card": card,
                "privileged": name in roles.PRIVILEGED_ROLES,
                "admin_site": name in roles.ADMIN_SITE_ROLES,
                "passkey": name in settings.STAFF_PASSKEY_ROLES,
                "idle_timeout_s": idle_limit_of_roles({name}),
                "limits": {limit: roles.limit({name}, limit) for limit in roles.LIMITS},
                "scopes": roles.ROLE_SCOPES.get(name, {}),
                "conflicts": sorted({b if a == name else a for a, b in roles.SOD_CONFLICTS if name in (a, b)}),
                "erp_profiles": ERP_ROLE_PROFILES.get(name, []),
                "members": members.get(name, 0),
                "permissions": len(perms[name]),
                "capabilities": capabilities(perms[name]),
            }
        )
    return rows


def access(person):
    """A person's Access tab (research 1.8): their roles with who gave them, when, why and until when (RoleGrant; a
    role given in the Django admin has no grant), their scopes and limits, every permission they hold by area with the
    last use of each high or critical one (the audit log of the last LAST_USE_DAYS, one grouped query), the change
    requests about them or by them still open, their second factors, and their ERPNext role profiles."""
    names = staff_roles(person)
    grants = {grant.role: grant for grant in person.role_grants.all()}
    perms = person.get_all_permissions()
    risky = [perm for perm in perms if catalogue.needs_reauth(perm)]
    since = timezone.now() - timedelta(days=LAST_USE_DAYS)
    events = AuditEvent.objects.filter(
        actor_id=person.pk, permission__in=risky, outcome=AuditEvent.Outcome.SUCCESS, ts__gte=since
    )
    used = dict(events.order_by().values_list("permission").annotate(last=Max("ts")))
    about = Q(target_type="accounts.user", target_id=str(person.pk)) | Q(maker=person)
    open_requests = ChangeRequest.objects.filter(about, status__in=[ChangeRequest.Status.PENDING, "approved"])
    factors = set(person.authenticator_set.values_list("type", flat=True))
    return {
        "id": person.pk,
        "email": person.email,
        "full_name": person.full_name,
        "is_active": person.is_active,
        "is_superuser": person.is_superuser,
        "last_login": person.last_login,
        "roles": [
            {
                "name": name,
                "source": "panel" if name in grants else "admin",
                "granted_by": grants[name].granted_by_id if name in grants else None,
                "granted_at": grants[name].created if name in grants else None,
                "expires_at": grants[name].expires_at if name in grants else None,
                "reason": grants[name].reason if name in grants else "",
            }
            for name in sorted(names)
        ],
        "scopes": [
            {
                "id": scope.pk,
                "kind": scope.kind,
                "value": scope.value,
                "granted_by": scope.granted_by_id,
                "created": scope.created,
                "expires_at": scope.expires_at,
            }
            for scope in person.staff_scopes.all()
        ],
        "role_scopes": {name: roles.ROLE_SCOPES[name] for name in sorted(names) if name in roles.ROLE_SCOPES},
        "limits": {limit: None if person.is_superuser else roles.limit(names, limit) for limit in roles.LIMITS},
        "idle_timeout_s": idle_limit(person),
        "permissions": len(perms),
        "capabilities": capabilities(perms, used),
        "pending": [
            {
                "id": change.pk,
                "action": change.action,
                "status": change.status,
                "target_label": change.target_label,
                "about_them": change.target_type == "accounts.user" and change.target_id == str(person.pk),
                "by_them": change.maker_id == person.pk,
                "created": change.created,
                "expires_at": change.expires_at,
            }
            for change in open_requests.order_by("-created")[:50]
        ],
        "second_factors": {
            "authenticator_app": Authenticator.Type.TOTP in factors,
            "passkey": Authenticator.Type.WEBAUTHN in factors,
            "recovery_codes": Authenticator.Type.RECOVERY_CODES in factors,
        },
        "passkey_required": needs_passkey(person),
        "erp_profiles": erp_profiles(names),
    }


def preview_role_change(person, role, *, action="grant", actor=None):
    """What giving (or taking away) `role` would change for `person`, before anything is asked (research 1.8, 6): the
    permissions gained and lost (by area), the limits, role scopes and idle limit that change, the separation-of-duty
    conflicts that would refuse it (as the grant does), whether a second person must approve it and who, whether a
    passkey becomes due, and the ERPNext role profiles before and after. Changes nothing."""
    _check_role(role)
    if person.is_superuser:
        raise serializers.ValidationError(
            {"non_field_errors": ["A break-glass account holds every permission: a role changes nothing for it."]}
        )
    held = staff_roles(person)
    if action == "revoke" and role not in held:
        raise serializers.ValidationError({"role": ["They do not hold this role."]})
    after = held - {role} if action == "revoke" else held | {role}
    perms = group_permissions(held | after)
    before_perms = set().union(*(perms[name] for name in held))
    after_perms = set().union(*(perms[name] for name in after))
    limits = []
    for name in roles.LIMITS:
        was, will = roles.limit(held, name), roles.limit(after, name)
        if was != will:
            limits.append({"name": name, "before": was, "after": will})
    scopes = []
    for name in sorted(held ^ after):
        if name in roles.ROLE_SCOPES:
            scopes.append({"role": name, "scopes": roles.ROLE_SCOPES[name], "added": name in after})
    conflicts = [
        {"roles": [a, b], "text": f"{a} and {b} may not be held by one person (separation of duties)."}
        for a, b in (roles.conflicts(after) if action == "grant" else [])
    ]
    rule = None
    if action == "grant" and actor is not None and person.pk == actor.pk:
        rule = "A role for yourself: a second person approves it (just-in-time elevation)."
    elif action == "grant" and role in roles.PRIVILEGED_ROLES:
        rule = f"{role} is a privileged role: a second person approves it."
    passkey = (
        action == "grant"
        and role in settings.STAFF_PASSKEY_ROLES
        and not person.authenticator_set.filter(type=Authenticator.Type.WEBAUTHN).exists()
    )
    return {
        "role": role,
        "action": action,
        "holds_already": action == "grant" and role in held,
        "gains": capabilities(after_perms - before_perms),
        "losses": capabilities(before_perms - after_perms),
        "limits": limits,
        "scopes": scopes,
        "idle_timeout_s": {"before": idle_limit_of_roles(held), "after": idle_limit_of_roles(after)},
        "conflicts": conflicts,
        "blocked": bool(conflicts),
        "needs_approval": rule is not None,
        "rule": rule or "",
        "checker": "staff.approve_role_change" if rule else "",
        "passkey_needed": passkey,
        "erp_profiles": {"before": erp_profiles(held), "after": erp_profiles(after)},
    }


def erp_in_use():
    """Whether ERPNext is in use: its sync switched on, or an ERPNext account made."""
    from erp.producers import switch
    from integrations.models import IntegrationAccount

    return bool(switch("ERP_ENABLED")) or IntegrationAccount.objects.filter(provider="erpnext").exists()


def erp_mirror(person):
    """The ERPNext user a person should have, from their roles (research-erpnext 5.5: by hand under about 15 staff):
    their address, whether the user is enabled, its role profiles and which role gives each. Never deleted in ERPNext:
    disabled, so that its documents' links survive."""
    names = staff_roles(person) & roles.STAFF_ROLES
    profiles = erp_profiles(names)
    return {
        "email": person.email,
        "enabled": person.is_active and bool(profiles),
        "role_profiles": profiles,
        "by_role": [{"role": name, "profiles": ERP_ROLE_PROFILES.get(name, [])} for name in sorted(names)],
        "erp_in_use": erp_in_use(),
    }


# Phase B: a person's own sessions (plan 3.5, research 2.3: the device list, "end this session" and "end all", the
# offer after a second factor's change)

OFFER_END_SESSIONS = "staff:offer-end-sessions:{user}"
OFFER_DAYS = 7
BROWSERS = [("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox")]
BROWSERS += [("FxiOS", "Firefox"), ("Chrome/", "Chrome"), ("CriOS", "Chrome"), ("Safari/", "Safari")]
SYSTEMS = [("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iOS"), ("Windows", "Windows"), ("CrOS", "ChromeOS")]
SYSTEMS += [("Macintosh", "macOS"), ("Mac OS X", "macOS"), ("Linux", "Linux")]


def device_of(user_agent):
    """(browser, system) from a user agent, enough to recognise a device (the whole string is never shown)."""
    user_agent = user_agent or ""
    browser = next((name for mark, name in BROWSERS if mark in user_agent), "")
    system = next((name for mark, name in SYSTEMS if mark in user_agent), "")
    return browser, system


def own_sessions(request):
    """The signed-in person's sessions (allauth.usersessions: the website's, the panel's, the app's allauth session),
    each with its browser and system, the address cut to its first octets, when it began and was last seen, and which
    is this one. Sessions already over are left out (and forgotten)."""
    key = request.session.session_key
    rows = sorted(
        UserSession.objects.purge_and_list(request.user), key=lambda row: (row.last_seen_at, row.pk), reverse=True
    )
    found = []
    for row in rows:
        browser, system = device_of(row.user_agent)
        found.append(
            {
                "id": row.pk,
                "browser": browser,
                "system": system,
                "place": mask_ip(row.ip),
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "current": row.session_key == key,
            }
        )
    return found


def end_own_session(request, pk):
    """End one of the person's other sessions (this one: sign out instead)."""
    row = UserSession.objects.filter(user=request.user, pk=pk).first()
    if row is None:
        raise exceptions.NotFound("No such session of yours.")
    if row.session_key == request.session.session_key:
        raise serializers.ValidationError(
            {"non_field_errors": ["This is the session you are using: sign out instead."]}
        )
    with transaction.atomic():
        row.end()
        record("session_ended_by_self", request=request, target=request.user, details={"sessions": 1, "tokens": 0})


def end_other_sessions(request):
    """End every session of the person but this one, and blacklist the app's refresh tokens: "end all" (and the answer
    to the offer after a second factor's change). Returns (sessions, tokens)."""
    user, key = request.user, request.session.session_key
    with transaction.atomic():
        others = list(UserSession.objects.filter(user=user).exclude(session_key=key))
        for row in others:
            row.end()
        tokens = list(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True))
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=token) for token in tokens], ignore_conflicts=True)
        details = {"sessions": len(others), "tokens": len(tokens), "others": True}
        record("session_ended_by_self", request=request, target=user, details=details)
    take_offer(user)
    return len(others), len(tokens)


def factor_changed(user):
    """A second factor of a member of staff added, removed or reset (allauth.mfa's signals: staff.signals): their next
    manifest offers to end their other sessions (ASVS 7.4.3). Kept per person, not per session: the factors are changed
    on the website's own host, whose session the panel's does not share."""
    if user is not None and getattr(user, "is_staff", False):
        cache.set(OFFER_END_SESSIONS.format(user=user.pk), True, OFFER_DAYS * 24 * 3600)


def take_offer(user):
    """Whether the offer to end the other sessions is due, once: reading it answers it."""
    key = OFFER_END_SESSIONS.format(user=user.pk)
    offered = bool(cache.get(key))
    if offered:
        cache.delete(key)
    return offered


# Phase B: the offboarding's checklist (research 2.9), each step a row of a StaffOffboarding

AUTO, MANUAL = OffboardingStep.Kind.AUTO, OffboardingStep.Kind.MANUAL
OFFBOARDING_STEPS = [  # (key, kind, label), research 2.9's order: what the panel does at once, then by hand
    ("deactivated", AUTO, "Deactivated: signing in stops at once"),
    ("sessions_ended", AUTO, "Every session ended"),
    ("tokens_blacklisted", AUTO, "The app's refresh tokens blacklisted"),
    ("roles_removed", AUTO, "Roles and scopes removed (the audit trail keeps them)"),
    ("grants_cancelled", AUTO, "Temporary role grants cancelled"),
    ("requests_withdrawn", AUTO, "Their pending change requests withdrawn"),
    ("work_unassigned", AUTO, "Their inbox items, data requests and tickets back to the queues"),
    ("api_keys_revoked", AUTO, "The API keys they sponsor revoked"),
    ("erpnext_user", MANUAL, "ERPNext: disable their user (never delete it) and take its role profiles away"),
    ("workspace", MANUAL, "Google Workspace: suspend the account (it stops new sign-ins, not open sessions)"),
    ("razorpay", MANUAL, "Razorpay: remove them from the dashboard"),
    ("msg91", MANUAL, "MSG91: remove them from the account"),
    ("aws", MANUAL, "AWS (SES): remove their access"),
    ("cloudflare", MANUAL, "Cloudflare (R2 and DNS): remove them"),
    ("error_tracker", MANUAL, "The error tracker: remove them"),
    ("github", MANUAL, "GitHub: remove them from the organisation"),
    ("registrar", MANUAL, "The domain's registrar: remove their access"),
    ("ssh_keys", MANUAL, "The servers: remove their SSH keys"),
    ("shared_passwords", MANUAL, "Shared passwords: remove them, and rotate the secrets they could read (RUNBOOK.md)"),
    ("security_keys", MANUAL, "Their security keys: collected"),
    ("last_90_days", MANUAL, "Their last 90 days reviewed: exports, reveals, refunds (the audit trail)"),
]
STEP_LABELS = {key: label for key, _, label in OFFBOARDING_STEPS}


def unassign_tickets(user):
    """The support desk's open tickets assigned to them, back to its queue: how many, or None while there is no desk
    (the support app comes with its own package)."""
    if not apps.is_installed("support"):
        return None
    try:
        model = apps.get_model("support", "Ticket")
        model._meta.get_field("assignee")
    except LookupError, FieldDoesNotExist:
        return None
    tickets = model._default_manager.filter(assignee=user)
    try:
        model._meta.get_field("closed_at")
        tickets = tickets.filter(closed_at=None)
    except FieldDoesNotExist:
        pass
    return tickets.update(assignee=None)


def record_offboarding(user, *, by, reason, counts):
    """The offboarding's rows (inside offboard's transaction): the steps done now, with their counts, and the steps an
    owner does by hand; ERPNext's is not needed without a role profile or while ERPNext is not in use. An inbox item
    waits for the owners until every step is ticked."""
    profiles = erp_profiles(counts["roles"])
    in_use = erp_in_use()
    offboarding = StaffOffboarding.objects.create(user=user, started_by=by, reason=str(reason)[:500])
    now, Step = timezone.now(), OffboardingStep
    work = f"{counts['inbox_items']} inbox items, {counts['data_requests']} data requests"
    done = {
        "deactivated": "",
        "sessions_ended": f"{counts['sessions']} ended",
        "tokens_blacklisted": f"{counts['tokens']} blacklisted",
        "roles_removed": f"{', '.join(counts['roles']) or 'no role'}; {counts['scopes']} scopes",
        "grants_cancelled": f"{counts['temporary']} cancelled",
        "requests_withdrawn": f"{counts['change_requests']} withdrawn",
        "work_unassigned": work if counts["tickets"] is None else f"{work}, {counts['tickets']} tickets",
        "api_keys_revoked": f"{counts['api_keys']} revoked",
    }
    rows = []
    for position, (key, kind, _) in enumerate(OFFBOARDING_STEPS):
        row = Step(offboarding=offboarding, key=key, kind=kind, position=position)
        if kind == AUTO:
            row.state, row.detail, row.done_at, row.done_by = Step.State.DONE, done[key], now, by
        elif key == "erpnext_user" and not profiles:
            row.state, row.detail, row.done_at = Step.State.NOT_NEEDED, "No ERPNext role profile.", now
        elif key == "erpnext_user" and not in_use:
            row.state, row.detail, row.done_at = Step.State.NOT_NEEDED, "ERPNext is not in use yet.", now
        elif key == "erpnext_user":
            row.detail = f"Role profiles: {', '.join(profiles)}."
        rows.append(row)
    Step.objects.bulk_create(rows)
    offboarding_item(offboarding, sum(1 for row in rows if row.state == Step.State.TODO))
    return offboarding


def offboarding_item(offboarding, todo):
    """The owners' inbox item while an offboarding has steps to do by hand (its count in the title), done when none
    is left. It names the person (target "staff.offboarding", their id): the console opens their checklist."""
    items = InboxItem.objects.filter(
        kind=InboxItem.Kind.OFFBOARDING, target_type="staff.offboarding", target_id=str(offboarding.user_id)
    ).filter(done_at=None)
    if not todo:
        items.update(done_at=timezone.now())
        return
    title = f"Offboarding #{offboarding.pk} of user #{offboarding.user_id}: {todo} steps to do by hand"
    item, created = InboxItem.objects.get_or_create(
        kind=InboxItem.Kind.OFFBOARDING,
        target_type="staff.offboarding",
        target_id=str(offboarding.user_id),
        done_at=None,
        defaults={"title": title, "permission": "staff.assign_role", "data": {"offboarding": offboarding.pk}},
    )
    if not created and item.title != title:
        items.update(title=title, data={"offboarding": offboarding.pk})


def tick_offboarding(offboarding, key, state, note="", *, by, request=None):
    """An owner's tick of a step done by hand (done, or not needed, with a note; back to "to do"): audited. Once every
    step is done the offboarding is finished and its inbox item done; a step put back opens it again."""
    Step = OffboardingStep
    with transaction.atomic():
        step = offboarding.steps.select_for_update().filter(key=key).first()
        if step is None:
            raise exceptions.NotFound("No such step.")
        if step.kind != MANUAL:
            raise serializers.ValidationError({"step": ["The panel did this step itself when it offboarded them."]})
        step.state = state
        step.detail = str(note or "").strip()[:300] or step.detail
        step.done_at, step.done_by = (None, None) if state == Step.State.TODO else (timezone.now(), by)
        step.save(update_fields=["state", "detail", "done_at", "done_by"])
        todo = offboarding.steps.filter(state=Step.State.TODO).count()
        offboarding.finished_at = None if todo else timezone.now()
        offboarding.save(update_fields=["finished_at"])
        offboarding_item(offboarding, todo)
        record(
            "offboarding.ticked",
            request=request,
            target=offboarding.user,
            details={"offboarding": offboarding.pk, "step": key, "state": state, "left": todo},
        )
    return step
