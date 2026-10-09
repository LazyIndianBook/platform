"""The audit log and the inbox, fed from what already happens (research 3.1): staff log-ins (with an alert email to
the person, and to the owners for a break-glass account), log-outs, failed log-ins and lock-outs of staff accounts;
role changes from anywhere (the admin's role actions, a teacher's verification, the panel); refunds and payments
recorded offline, through shop.services; and the inbox items for approvals, teachers' requests, account deletions,
data requests, incidents, failed clips and failed tasks, the parcels' exceptions (due when they are), the integrations'
dead letters, failed events and open circuits, each closed again once settled. A receiver never breaks what sent the
signal: its failure is logged."""

import functools
import logging
import time

from allauth.account.signals import user_logged_in
from axes.signals import user_locked_out
from celery.signals import task_failure
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_out, user_login_failed
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone
from django_fsm.signals import post_transition

from accounts import roles
from accounts.models import DeletionRequest, TeacherProfile
from examleaf.middleware import STAFF_LOGIN_AT, STAFF_SEEN
from integrations import signals as integration_signals
from ops.tasks import queue_text_email
from shipping import signals as shipping_signals

from .audit import ActorType, Outcome, alert, current_request, record, request_fields
from .models import ChangeRequest, DataRequest, InboxItem, Incident

logger = logging.getLogger(__name__)
User = get_user_model()
AUDITED_ROLES = roles.STAFF_ROLES | {roles.TEACHER}  # a student's own role (every sign-up) is not an event


def quietly(receiver_function):
    """Run a receiver in a savepoint; a failure is logged and the sender goes on."""

    @functools.wraps(receiver_function)
    def wrapped(*args, **kwargs):
        try:
            with transaction.atomic():
                receiver_function(*args, **kwargs)
        except Exception:
            logger.exception("staff: %s failed", receiver_function.__name__)

    return wrapped


# Staff log-ins and log-outs


@receiver(user_logged_in)  # allauth's: the website's and the panel's log-ins (the app's API has no session)
@quietly
def staff_logged_in(sender, request, user, **kwargs):
    if not user.is_staff:
        return
    now = time.time()
    request.session[STAFF_LOGIN_AT] = request.session[STAFF_SEEN] = now
    record("authn_login_success", request=request, actor=user)
    where = request_fields(request)
    if user.is_superuser:  # a break-glass account (research 1.6): the owners are told at once
        alert(
            f"Break-glass account #{user.pk} signed in",
            f"From the address {where['ip'] or 'unknown'}. Every event of this session is marked break_glass in the "
            "audit log (audit/?break_glass=true): review them within 24 hours.",
        )
    queue_text_email(
        user.email,
        "New sign-in to your ExamLeaf staff account",
        f"Your staff account signed in on {timezone.localtime():%d %b %Y at %H:%M} (India time) from the address "
        f"{where['ip'] or 'unknown'}, with: {where['user_agent'] or 'an unknown browser'}.\n\nIf this was not you, "
        "tell the owner at once and change your password; your sessions can be ended from the panel (people).",
    )


@receiver(user_logged_out)
@quietly
def staff_logged_out(sender, request, user, **kwargs):
    if user is not None and user.is_staff and not getattr(request, "_staff_session_ended", None):
        record("session_logout", request=request, actor=user)


def staff_with(username):
    username = (username or "").strip()
    return User.objects.filter(is_staff=True).filter(email__iexact=username).first() if username else None


@receiver(user_login_failed)
@quietly
def staff_login_failed(sender, credentials, request=None, **kwargs):
    if user := staff_with(credentials.get("email") or credentials.get("username")):
        record("authn_login_fail", request=request, actor=user, outcome=Outcome.FAILED)


@receiver(user_locked_out)
@quietly
def staff_locked_out(sender, request, username, ip_address, **kwargs):
    if user := staff_with(username):
        record("authn_login_lock", request=request, actor=user, outcome=Outcome.DENIED)
        alert(f"Staff account #{user.pk} locked out", "Ten failed log-ins from one address (django-axes).")


# Role changes, from anywhere


def _names(pk_set):
    from django.contrib.auth.models import Group

    return set(Group.objects.filter(pk__in=pk_set or ()).values_list("name", flat=True))


def _role_event(user, added, removed):
    context = user.__dict__.pop("_audit_context", {})  # (staff.services: the why of this change, never the next's)
    added, removed = added & AUDITED_ROLES, removed & AUDITED_ROLES
    if not (added or removed):
        return
    change_request = context.pop("change_request", None)
    reason = context.pop("reason", "")
    details = {"added": sorted(added), "removed": sorted(removed), **context}
    record("authz_change", target=user, reason=reason, change_request=change_request, details=details)
    if added & roles.PRIVILEGED_ROLES:
        alert(f"{', '.join(sorted(added & roles.PRIVILEGED_ROLES))} given to user #{user.pk}", f"Reason: {reason}")


@receiver(m2m_changed, sender=User.groups.through)
@quietly
def roles_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "pre_clear"):
        return
    if reverse:  # group.user_set.add(…): instance is the group
        for user in User.objects.filter(pk__in=pk_set or ()):
            _role_event(
                user,
                {instance.name} if action == "post_add" else set(),
                {instance.name} if action == "post_remove" else set(),
            )
        return
    if action == "pre_clear":
        _role_event(instance, set(), set(instance.groups.values_list("name", flat=True)))
    else:
        names = _names(pk_set)
        _role_event(instance, names if action == "post_add" else set(), names if action == "post_remove" else set())


# Money: refunds started and payments recorded offline (shop.services), whoever started them


@receiver(post_save, sender="shop.Refund")
@quietly
def refund_started(sender, instance, created, **kwargs):
    if not created:
        return
    staff = instance.created_by
    request = current_request()
    actor_type = None if staff or (request and request.user.is_authenticated) else ActorType.SYSTEM
    record(
        "refund.started",
        actor=staff,
        actor_type=actor_type,
        target=instance.order,
        reason=instance.reason,
        details={"refund": instance.pk, "amount": instance.amount.amount, "payment": instance.payment_id},
    )


@receiver(post_transition, sender="shop.Order")
@quietly
def offline_payment(sender, instance, name, source, target, **kwargs):
    """An order paid by a payment staff recorded offline (shop.services.record_offline_payment): at its `pay`, once
    its stock rows are locked (the audit log's lock comes after every other)."""
    if name == "pay" and instance.payment_method == "offline":
        payment = instance.payments.filter(method="offline", status="captured").order_by("-pk").first()
        record(
            "payment.offline_recorded",
            target=instance,
            details={"payment": getattr(payment, "pk", None), "amount": instance.total.amount},
        )


# The inbox


def open_item(kind, target, title, permission, due_at=None, **data):
    target_type, target_id = target._meta.label_lower, str(target.pk)
    InboxItem.objects.get_or_create(
        kind=kind,
        target_type=target_type,
        target_id=target_id,
        done_at=None,
        defaults={"title": title[:200], "permission": permission, "due_at": due_at, "data": data},
    )


def close_items(target, kind=None):
    items = InboxItem.objects.filter(target_type=target._meta.label_lower, target_id=str(target.pk), done_at=None)
    (items.filter(kind=kind) if kind else items).update(done_at=timezone.now())


@receiver(post_save, sender=ChangeRequest)
@quietly
def approval_waits(sender, instance, **kwargs):
    if getattr(instance, "_runs_at_once", False):  # within the maker's limits: nothing waits
        return
    if instance.status == ChangeRequest.Status.PENDING:
        from .approvals import ACTIONS

        action = ACTIONS[instance.action]
        title = f"Approve: {action.label} ({instance.target_label})" if instance.target_label else action.label
        open_item(InboxItem.Kind.APPROVAL, instance, title, action.checker_for(instance), instance.expires_at)
    else:
        close_items(instance, InboxItem.Kind.APPROVAL)


@receiver(post_save, sender=TeacherProfile)
@quietly
def teacher_waits(sender, instance, **kwargs):
    if instance.verified:
        close_items(instance)
    else:
        open_item(
            InboxItem.Kind.TEACHER_REQUEST,
            instance,
            f"Teacher access request #{instance.pk}",
            "accounts.change_teacherprofile",
        )


@receiver(post_save, sender=DeletionRequest)
@quietly
def deletion_waits(sender, instance, **kwargs):
    if instance.status == DeletionRequest.Status.PENDING:
        open_item(
            InboxItem.Kind.DELETION_REQUEST,
            instance,
            f"Account deletion #{instance.pk}",
            "staff.handle_data_request",
            instance.due_at,
        )
    else:
        close_items(instance)


@receiver(post_save, sender=DataRequest)
@quietly
def data_request_waits(sender, instance, **kwargs):
    if instance.status == DataRequest.Status.CLOSED:
        close_items(instance)
        return
    due = instance.due_at if instance.acknowledged_at else instance.ack_due_at
    open_item(
        InboxItem.Kind.DATA_REQUEST,
        instance,
        f"Data request DR-{instance.pk} ({instance.get_kind_display()})",
        "staff.handle_data_request",
        due,
    )
    InboxItem.objects.filter(target_type="staff.datarequest", target_id=str(instance.pk), done_at=None).update(
        due_at=due
    )


@receiver(post_save, sender=Incident)
@quietly
def incident_waits(sender, instance, **kwargs):
    if instance.closed_at:
        close_items(instance)
        return
    due = instance.cert_in_due if instance.cert_in_reported_at is None else instance.board_due
    open_item(
        InboxItem.Kind.INCIDENT,
        instance,
        f"Incident #{instance.pk}: {instance.get_kind_display()}",
        "staff.manage_incident",
        due,
    )
    InboxItem.objects.filter(target_type="staff.incident", target_id=str(instance.pk), done_at=None).update(due_at=due)


@receiver(post_save, sender="learn.Clip")
@quietly
def clip_failed(sender, instance, **kwargs):
    if instance.processing == "failed":
        open_item(InboxItem.Kind.FAILED_JOB, instance, f"Clip #{instance.pk}: its video failed", "learn.change_clip")
    elif instance.processing == "ready":
        close_items(instance)


# The parcels' exceptions (shipping.signals) and the integrations' failures (integrations.signals)


@receiver(shipping_signals.exception_opened)
@quietly
def parcel_needs_staff(sender, exception, **kwargs):
    order = exception.shipment.order
    money = exception.kind == exception.Kind.COD_OVERDUE  # FINANCE's: the cash a courier owes
    open_item(
        InboxItem.Kind.SHIPPING_EXCEPTION,
        exception,
        f"Parcel of {order.number}: {exception.get_kind_display()}",
        "staff.reconcile_cod" if money else "staff.act_on_exception",
        exception.due_at,
        order=order.number,
        shipment=exception.shipment_id,
        exception_kind=exception.kind,
    )


@receiver(post_save, sender="shipping.ShippingException")
@quietly
def parcel_deadline_moved(sender, instance, created, **kwargs):
    """A second failed attempt brings an open exception's deadline forward: its item's too."""
    if not created:
        InboxItem.objects.filter(
            target_type="shipping.shippingexception", target_id=str(instance.pk), done_at=None
        ).update(due_at=instance.due_at)


@receiver(shipping_signals.exceptions_closed)
@quietly
def parcel_settled(sender, ids, **kwargs):
    InboxItem.objects.filter(
        target_type="shipping.shippingexception", target_id__in=[str(pk) for pk in ids], done_at=None
    ).update(done_at=timezone.now())


FILED_ELSEWHERE = {"erp.tasks.replay_row"}  # the ERPNext sync files its dead letters itself (erp/inbox.py)


@receiver(integration_signals.dead_letter_created)
@quietly
def dead_letter_waits(sender, failure, **kwargs):
    if failure.task_name in FILED_ELSEWHERE:
        return
    open_item(
        InboxItem.Kind.DEAD_LETTER,
        failure,
        f"Dead letter #{failure.pk}: {failure.operation} gave up",
        "staff.view_system",
        operation=failure.operation,
    )


@receiver(integration_signals.dead_letter_closed)
@quietly
def dead_letter_done(sender, failure, **kwargs):
    close_items(failure)


@receiver(integration_signals.inbound_event_failed)
@quietly
def inbound_event_waits(sender, event, **kwargs):
    title = f"{event.get_provider_display()} event #{event.pk} not processed"
    open_item(InboxItem.Kind.FAILED_EVENT, event, title, "staff.view_system", provider=event.provider)


@receiver(post_save, sender="integrations.InboundEvent")
@quietly
def inbound_event_processed(sender, instance, **kwargs):
    if instance.processed_at and instance.state != instance.State.FAILED:  # a replay that went through
        close_items(instance, InboxItem.Kind.FAILED_EVENT)


@receiver(integration_signals.integration_failed)
@quietly
def integration_down(sender, account, **kwargs):
    title = f"{account.get_provider_display()} unavailable: calls wait (its circuit is open)"
    open_item(InboxItem.Kind.INTEGRATION_DOWN, account, title, "staff.view_system", provider=account.provider)


@receiver(integration_signals.integration_recovered)
@quietly
def integration_back(sender, account, **kwargs):
    close_items(account, InboxItem.Kind.INTEGRATION_DOWN)


@task_failure.connect
def task_failed(sender=None, task_id=None, exception=None, **kwargs):
    """A Celery task that failed for good (its retries spent): one inbox item per task name and day."""
    try:
        name = getattr(sender, "name", "task")
        InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.FAILED_JOB,
            target_type="celery.task",
            target_id=f"{name}:{timezone.localdate().isoformat()}"[:64],
            done_at=None,
            defaults={
                "title": f"Task {name} failed"[:200],
                "permission": "staff.view_system",
                "data": {"task_id": task_id, "error": type(exception).__name__},
            },
        )
    except Exception:
        logger.exception("staff: could not file the failed task %s", task_id)
