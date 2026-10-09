"""Maker-checker (research 1.5). `ask()` stores the action's exact payload with its SHA-256; within the maker's limits
(accounts.roles.ROLE_LIMITS) it runs at once, otherwise it waits for a second person. `approve()` binds the approval to
the payload the checker saw (they send its hash back); `execute()` re-checks the preconditions and runs the stored
payload, never one sent again, in one transaction; the request expires after STAFF_CHANGE_REQUEST_HOURS. Separation
of duties per transaction (DSD): the approver is not the maker and never the person the change is about; when nobody
else can, an owner overrides with a reason, the owners are told and the event is marked break-glass. Who approves
(plan 4.1): FINANCE money (refunds, offline payments, prices and coupons), ADMIN roles, staff second factors, erasures
and exports, and the owners anything.

The rules (research 1.5's table) are the actions below: a refund above the maker's cap, an offline payment above a
value (or of a ₹0 order), a price or a coupon beyond the discount limit, an erasure started by staff, a privileged
role (or one for yourself), a staff invitation to one, a second factor reset, a job (an export, a bulk action) above
the row limits. Each step's audit event names the person who took it, also when a job runs it (no request then)."""

import hashlib
import json
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_fsm import TransitionNotAllowed, can_proceed
from rest_framework import exceptions, serializers

from accounts import roles

from . import services
from .audit import Outcome, alert, describe_target, plain, record
from .backends import scoped
from .models import Approval, ChangeRequest

Status = ChangeRequest.Status


class Refused(Exception):
    """A precondition no longer holds when the request runs (the order changed, the code is taken …)."""


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def limit_of(user, name):
    """The maker's limit `name` (accounts.roles.ROLE_LIMITS); none for a break-glass account."""
    return None if user.is_superuser else roles.limit(services.staff_roles(user), name)


def rupees(value, field="amount"):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise serializers.ValidationError({field: ["A number of rupees."]}) from error
    if amount < 0:
        raise serializers.ValidationError({field: ["Not below zero."]})
    return amount


def over(amount, limit, text):
    """The rule's `text` (with {amount} and {limit}) when `amount` is above `limit` (None: no limit), else None."""
    if limit is not None and amount > limit:
        return text.format(amount=f"{amount:,}", limit=f"{limit:,}")
    return None


class Action:
    name = label = maker = checker = ""
    generic = True  # may be asked for through POST change-requests/, and named by a bulk action (staff.jobs)

    def checker_for(self, change_request):
        return self.checker

    def account(self, change_request):
        """The id of the account the change is about: its owner never approves it."""
        return None

    def validate(self, maker, target, payload):
        """(the target, the payload to store, the amount in rupees or None); raises ValidationError."""
        raise NotImplementedError

    def rule(self, maker, change_request):
        """Why a second person must approve it, or None: it runs at once."""
        raise NotImplementedError

    def run(self, change_request, by):
        """Do it from the stored payload; returns the result (JSON); raises Refused."""
        raise NotImplementedError


def _order(maker, number):
    from shop.models import Order

    order = scoped(Order.objects.all(), maker, "shop.view_order").filter(number=str(number)).first()
    if order is None:
        raise serializers.ValidationError({"target": ["No such order (or not one you may see)."]})
    return order


class Refund(Action):
    """A Razorpay refund through shop.services.refund_order (start_refund): an order not yet shipped is cancelled
    (stock back) and refunded in full; a shipped one by the amount (at most what was paid)."""

    name, label, maker, checker = "order.refund", "Refund an order", "staff.refund_order", "staff.approve_refund"

    @staticmethod
    def _paid(order):
        from shop.models import Order, Payment
        from shop.models import Refund as RefundRow

        return (
            order.payments.filter(method=Order.Method.RAZORPAY, status=Payment.Status.CAPTURED)
            .exclude(refunds__status__in=[RefundRow.Status.PENDING, RefundRow.Status.PROCESSED])
            .first()
        )

    def validate(self, maker, target, payload):
        order = _order(maker, target)
        paid = self._paid(order)
        if paid is None:
            raise serializers.ValidationError(
                {
                    "target": [
                        "Nothing to refund online: not paid online, or a refund is under way (cash on delivery "
                        "and offline payments are refunded by bank transfer)."
                    ]
                }
            )
        cancel = can_proceed(order.cancel)
        asked = payload.get("amount")
        amount = paid.amount.amount if cancel or asked in (None, "") else min(rupees(asked), paid.amount.amount)
        if amount <= 0:
            raise serializers.ValidationError({"amount": ["More than ₹0."]})
        return order, {"order": order.number, "amount": str(amount), "cancel": cancel}, amount

    def rule(self, maker, change_request):
        return over(
            change_request.amount,
            limit_of(maker, "refund_inr"),
            "A refund of ₹{amount} is above the limit of ₹{limit}.",
        )

    def run(self, change_request, by):
        from shop import services as shop
        from shop.models import Order

        payload = change_request.payload
        order = Order.objects.get(number=payload["order"])
        if can_proceed(order.cancel) != payload["cancel"]:
            raise Refused("The order changed since the request (packed, shipped or cancelled): ask again.")
        paid = self._paid(order)
        if paid is None or Decimal(payload["amount"]) > paid.amount.amount:
            raise Refused("Nothing left to refund online: a refund is under way or done.")
        try:
            refund = shop.refund_order(
                order, change_request.reason[:200], by=change_request.maker, amount=Decimal(payload["amount"])
            )
        except TransitionNotAllowed as error:
            raise Refused("The order cannot be cancelled now: ask again.") from error
        if refund is None:
            raise Refused("Nothing was refunded: the payment is not captured, or a refund is under way.")
        return {"refund": refund.pk, "amount": str(refund.amount.amount), "status": refund.status}


class OfflinePayment(Action):
    """A payment received outside Razorpay, through shop.services.record_offline_payment (the order paid, the
    customer emailed, the invoice made). A ₹0 order, or one above the maker's `offline_inr`, needs approval (I6)."""

    name, label = "order.offline_payment", "Record a payment received offline"
    maker, checker = "staff.record_offline_payment", "staff.approve_payment"

    def validate(self, maker, target, payload):
        order = _order(maker, target)
        if order.status != order.Status.PENDING or order.placed_at or order.is_cod:
            raise serializers.ValidationError({"target": [f"Order {order.number} is not waiting for a payment."]})
        reference = str(payload.get("reference") or "").strip()
        if not reference or len(reference) > 60:
            raise serializers.ValidationError({"reference": ["The UTR or UPI reference (60 characters at most)."]})
        amount = order.total.amount
        return order, {"order": order.number, "reference": reference, "amount": str(amount)}, amount

    def rule(self, maker, change_request):
        if change_request.amount == 0:
            return "A ₹0 order gives the books away: a second person approves it."
        return over(
            change_request.amount,
            limit_of(maker, "offline_inr"),
            "₹{amount} paid offline is above the limit of ₹{limit}.",
        )

    def run(self, change_request, by):
        from shop import services as shop
        from shop.models import Order

        payload = change_request.payload
        order = Order.objects.get(number=payload["order"])
        if order.total.amount != Decimal(payload["amount"]):
            raise Refused("The order's total changed since the request: ask again.")
        try:
            shop.record_offline_payment(order, payload["reference"])
        except shop.ShopError as error:
            raise Refused(str(error)) from error
        return {"order": order.number, "paid": True}


def discount_percent(full, price):
    return Decimal(0) if not full else ((full - price) * 100 / full).quantize(Decimal("0.01"))


class Price(Action):
    """A product's selling price; more off the MRP than the maker's `discount_percent` needs approval."""

    name, label, maker, checker = "product.price", "Change a price", "shop.change_product", "staff.approve_discount"

    def validate(self, maker, target, payload):
        from shop.models import Product

        product = scoped(Product.objects.all(), maker, "shop.change_product").filter(slug=str(target)).first()
        if product is None:
            raise serializers.ValidationError({"target": ["No such product."]})
        price = rupees(payload.get("price"), "price")
        if not 0 < price <= product.mrp.amount:
            raise serializers.ValidationError({"price": [f"Above ₹0 and at most the MRP, ₹{product.mrp.amount}."]})
        payload = {"product": product.slug, "from": str(product.price.amount), "price": str(price)}
        return product, payload, price

    def rule(self, maker, change_request):
        from shop.models import Product

        product = Product.objects.get(slug=change_request.payload["product"])
        off = discount_percent(product.mrp.amount, Decimal(change_request.payload["price"]))
        return over(off, limit_of(maker, "discount_percent"), "{amount}% off is beyond the limit of {limit}%.")

    def run(self, change_request, by):
        from shop.models import Product

        payload = change_request.payload
        product = Product.objects.select_for_update().get(slug=payload["product"])
        if product.price.amount != Decimal(payload["from"]):
            raise Refused("The price changed since the request: ask again.")
        product.price = Decimal(payload["price"])
        product.save(update_fields=["price", "modified"])
        return {"product": product.slug, "price": payload["price"]}


COUPON_CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{2,29}")


class Coupon(Action):
    """A new coupon; a percentage (or a fixed amount as a share of its minimum order) beyond the maker's
    `discount_percent` needs approval."""

    name, label, maker, checker = "coupon.create", "Make a coupon", "shop.add_coupon", "staff.approve_discount"

    def validate(self, maker, target, payload):
        from shop.models import Coupon as CouponRow

        code = str(target or "").strip().upper()
        if not COUPON_CODE.fullmatch(code):
            raise serializers.ValidationError({"target": ["The code: 3 to 30 capitals, digits and hyphens."]})
        if CouponRow.objects.filter(code=code).exists():
            raise serializers.ValidationError({"target": ["This code exists."]})
        kind = payload.get("kind", CouponRow.Kind.PERCENT)
        if kind not in CouponRow.Kind.values:
            raise serializers.ValidationError({"kind": ["percent or fixed."]})
        value, min_order = rupees(payload.get("value"), "value"), rupees(payload.get("min_order") or 0, "min_order")
        if kind == CouponRow.Kind.PERCENT and not 0 < value <= 100:
            raise serializers.ValidationError({"value": ["Above 0 and at most 100 per cent."]})
        uses = payload.get("max_uses")
        if uses is not None and (not isinstance(uses, int) or uses < 1):
            raise serializers.ValidationError({"max_uses": ["A whole number from 1, or null."]})
        until = payload.get("valid_until")
        if until is not None and parse_datetime(str(until)) is None:
            raise serializers.ValidationError({"valid_until": ["A date and time (ISO 8601), or null."]})
        clean = {
            "code": code,
            "kind": kind,
            "value": str(value),
            "min_order": str(min_order),
            "max_uses": uses,
            "valid_until": until,
        }
        return ("shop.coupon", code, code), clean, None

    def rule(self, maker, change_request):
        payload = change_request.payload
        value, min_order = Decimal(payload["value"]), Decimal(payload["min_order"])
        if payload["kind"] == "percent":
            off = value
        else:  # rupees off: as a share of the smallest order it applies to (no minimum: all of a cheap book)
            off = Decimal(100) if not min_order else min(Decimal(100), value * 100 / min_order)
        return over(
            off.quantize(Decimal("0.01")),
            limit_of(maker, "discount_percent"),
            "{amount}% off is beyond the limit of {limit}%.",
        )

    def run(self, change_request, by):
        from shop.models import Coupon as CouponRow

        payload = change_request.payload
        try:
            with transaction.atomic():
                coupon = CouponRow.objects.create(
                    code=payload["code"],
                    kind=payload["kind"],
                    value=Decimal(payload["value"]),
                    min_order=Decimal(payload["min_order"]),
                    max_uses=payload["max_uses"],
                    valid_until=parse_datetime(payload["valid_until"]) if payload["valid_until"] else None,
                )
        except IntegrityError as error:
            raise Refused("This code was taken meanwhile.") from error
        return {"coupon": coupon.code}


def _user(pk):
    user = get_user_model().objects.filter(pk=pk).first()
    if user is None:
        raise Refused("The account is gone.")
    return user


class GrantRole(Action):
    """A role given through people/ (an owner's: staff.assign_role): a privileged one (accounts.roles.PRIVILEGED_ROLES),
    or any role for yourself (just-in-time elevation), waits for a second person with staff.approve_role_change (ADMIN,
    or another owner)."""

    name, label, maker, checker = "staff.grant_role", "Give a role", "staff.assign_role", "staff.approve_role_change"
    generic = False

    def account(self, change_request):
        return change_request.payload["user"]

    def validate(self, maker, target, payload):
        user = target
        expires_at = payload.get("expires_at")
        return user, {"user": user.pk, "role": payload["role"], "expires_at": plain(expires_at)}, None

    def rule(self, maker, change_request):
        payload = change_request.payload
        if payload["user"] == maker.pk:
            return "A role for yourself: a second person approves it (just-in-time elevation)."
        if payload["role"] in roles.PRIVILEGED_ROLES:
            return f"{payload['role']} is a privileged role: a second person approves it."
        return None

    def run(self, change_request, by):
        payload = change_request.payload
        user = _user(payload["user"])
        expires_at = parse_datetime(payload["expires_at"]) if payload["expires_at"] else None
        if expires_at and expires_at <= timezone.now():
            raise Refused("Its expiry has passed: ask again.")
        try:
            services.grant_role(
                user,
                payload["role"],
                by=change_request.maker,
                expires_at=expires_at,
                reason=change_request.reason,
                change_request=change_request,
            )
        except serializers.ValidationError as error:
            raise Refused(str(error.detail)) from error
        return {"user": user.pk, "role": payload["role"]}


class Invite(Action):
    """An invitation to a privileged role waits for a second person, as the role itself would."""

    name, label, maker, checker = (
        "staff.invite",
        "Invite to the staff",
        "staff.assign_role",
        "staff.approve_role_change",
    )
    generic = False

    def validate(self, maker, target, payload):
        email = str(payload["email"]).lower()
        return (
            ("staff.staffinvite", "", f"Invitation as {payload['role']}"),
            {"email": email, "role": payload["role"]},
            None,
        )

    def rule(self, maker, change_request):
        role = change_request.payload["role"]
        return (
            f"{role} is a privileged role: a second person approves the invitation."
            if role in roles.PRIVILEGED_ROLES
            else None
        )

    def run(self, change_request, by):
        invite = services.send_invite(**change_request.payload, by=change_request.maker, change_request=change_request)
        return {"invite": invite.pk}


class ResetMfa(Action):
    """A second factor reset always waits for a second person: another holder of staff.reset_user_mfa for a
    customer, a holder of staff.approve_role_change (ADMIN, OWNER) for a member of staff (research 5)."""

    name, label, maker = "user.reset_mfa", "Reset a second factor", "staff.reset_user_mfa"
    checker = "staff.reset_user_mfa"
    generic = False

    def checker_for(self, change_request):
        staff = get_user_model().objects.filter(pk=change_request.payload["user"], is_staff=True).exists()
        return "staff.approve_role_change" if staff else self.checker

    def account(self, change_request):
        return change_request.payload["user"]

    def validate(self, maker, target, payload):
        return target, {"user": target.pk}, None

    def rule(self, maker, change_request):
        return "A second factor is reset only with a second person's approval."

    def run(self, change_request, by):
        return services.reset_mfa(_user(change_request.payload["user"]))


class Erase(Action):
    """An erasure started by staff for a data request (research 4.5): the dry run's blocks are checked again, then
    accounts.models.DeletionRequest.complete erases at once and the person gets the goodbye email."""

    name, label, maker, checker = "user.erase", "Erase an account", "staff.handle_data_request", "staff.approve_erasure"
    generic = False

    def account(self, change_request):
        return change_request.payload["user"]

    def validate(self, maker, target, payload):
        return target, {"user": target.pk, "data_request": payload["data_request"]}, None

    def rule(self, maker, change_request):
        return "An erasure started by staff: a second person approves it."

    def run(self, change_request, by):
        from accounts.models import DeletionRequest
        from ops.tasks import queue_text_email

        from .models import DataRequest
        from .privacy import erasure_confirmation, erasure_report, parent_confirmed

        user = _user(change_request.payload["user"])
        data_request = DataRequest.objects.filter(pk=change_request.payload["data_request"]).first()
        if blocks := erasure_report(user, data_request)["blocks"]:
            raise Refused(" ".join(blocks))
        subject, body = erasure_confirmation(user, data_request)  # what stays: read before the erasure
        deletion = user.pending_deletion or DeletionRequest.objects.create(user=user, due_at=timezone.now())
        if user.is_minor and not deletion.parent_confirmed_at and parent_confirmed(user, deletion, data_request):
            details = data_request.details  # the parent's confirmation, as staff recorded it on the request
            deletion.parent_confirmed_at, deletion.parent_confirmed_by = timezone.now(), change_request.maker
            deletion.parent_evidence_ref = str(details.get("parent_evidence") or details.get("parent_confirmed"))[:200]
            deletion.save(update_fields=["parent_confirmed_at", "parent_confirmed_by", "parent_evidence_ref"])
        try:
            email = deletion.complete(data_request=data_request)
        except DeletionRequest.Held as held:
            raise Refused(" ".join(held.reasons)) from held
        if email is None:
            raise Refused("The account was erased meanwhile.")
        queue_text_email(email, subject, body)
        if data_request is not None:
            data_request.details = {**data_request.details, "erased_at": plain(timezone.now())}
            data_request.save(update_fields=["details"])
        return {"user": user.pk, "deletion_request": deletion.pk}


class RunJob(Action):
    """A job above its starter's limit (staff.jobs: an export above `export_rows`, a bulk action above `bulk_rows`):
    approved and run, it is queued. The approver reads its exact filters or targets in the payload. ADMIN approves
    large exports and bulk actions; the starter held the job's own permission when it was asked for."""

    name, label = "job.run", "Run a large job"
    maker, checker = "staff.view_job", "staff.approve_export"
    generic = False

    def validate(self, maker, target, payload):
        job = target
        return job, {"job": job.pk, "kind": job.kind, "total": job.total, "params": job.params}, None

    def rule(self, maker, change_request):
        payload = change_request.payload
        limit = "export_rows" if payload["kind"] == "audit_export" else "bulk_rows"
        return over(payload["total"], limit_of(maker, limit), "{amount} rows are above the limit of {limit}.")

    def run(self, change_request, by):
        from .jobs import enqueue
        from .models import Job

        job = Job.objects.select_for_update().get(pk=change_request.payload["job"])
        if job.state != Job.State.QUEUED or job.cancel_requested:
            raise Refused("The job was cancelled.")
        enqueue(job)
        return {"job": job.pk}


ACTIONS = {
    action.name: action
    for action in [
        Refund(),
        OfflinePayment(),
        Price(),
        Coupon(),
        GrantRole(),
        Invite(),
        ResetMfa(),
        Erase(),
        RunJob(),
    ]
}


def bulk_rule(maker, rows):
    """For bulk actions: why `rows` at once need an approver (above the maker's `bulk_rows`), or None."""
    return over(rows, limit_of(maker, "bulk_rows"), "{amount} rows at once are above the limit of {limit}.")


def _event(change_request, verb, request=None, **kwargs):
    target = (change_request.target_type, change_request.target_id, change_request.target_label)
    return record(
        f"{change_request.action}.{verb}", request=request, target=target, change_request=change_request, **kwargs
    )


def ask(action_name, *, maker, target, payload, reason, idempotency_key="", request=None):
    """A ChangeRequest for the action; within the maker's limits it is approved by the rule and run at once. A key
    the maker used before answers that request again (Idempotency-Key). Returns (request, created)."""
    action = ACTIONS[action_name]
    if not maker.has_perm(action.maker):
        raise exceptions.PermissionDenied(f"Needs {action.maker}.")
    if not str(reason or "").strip():
        raise serializers.ValidationError({"reason": ["Say why."]})
    if idempotency_key and (seen := ChangeRequest.objects.filter(maker=maker, idempotency_key=idempotency_key).first()):
        if seen.action != action_name:
            raise serializers.ValidationError({"idempotency_key": ["Used for another request: send a new key."]})
        return seen, False  # the same key answers the first request again, whatever came since
    target, clean, amount = action.validate(maker, target, payload)
    clean = plain(clean)
    target_type, target_id, target_label = describe_target(target)
    hours = settings.STAFF_CHANGE_REQUEST_HOURS
    change_request = ChangeRequest(
        action=action_name,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        payload=clean,
        payload_sha256=digest(clean),
        amount=amount,
        maker=maker,
        reason=str(reason)[:500],
        expires_at=timezone.now() + timedelta(hours=hours),
        idempotency_key=idempotency_key[:80],
    )
    rule = action.rule(maker, change_request)
    change_request.rule = (rule or "Within the maker's limits: no approval needed.")[:200]
    change_request._runs_at_once = rule is None  # no inbox item for it (staff.signals)
    try:
        with transaction.atomic():
            change_request.save()
            _event(
                change_request, "requested", request, actor=maker, reason=change_request.reason, details={"rule": rule}
            )
    except IntegrityError:  # the same key twice at once: the other request made it
        return ChangeRequest.objects.get(maker=maker, idempotency_key=idempotency_key), False
    if rule is None:
        with transaction.atomic():
            change_request = ChangeRequest.objects.select_for_update().get(pk=change_request.pk)
            change_request.approve()
            change_request.save()
            _event(change_request, "approved", request, actor=maker, details={"by_rule": True})
        change_request = execute(change_request, by=maker, request=request)
    return change_request, True


def _lock(change_request):
    return ChangeRequest.objects.select_for_update().get(pk=change_request.pk)


def expire_if_due(change_request, request=None):
    """Expire it (locked) if its time is over; returns whether it did."""
    if change_request.status in (Status.PENDING, Status.APPROVED) and change_request.is_expired:
        change_request.expire()
        change_request.save()
        _event(change_request, "expired", request)
        return True
    return False


EXPIRED = {"non_field_errors": ["Its time was over: it expired. Ask again."]}


def check_approver(action, change_request, user, override=False, comment=""):
    """DSD (research 1.2): the checker's permission; never the person the change is about; never the maker, unless
    an owner overrides, with a reason. Raises PermissionDenied (403) or ValidationError."""
    checker = action.checker_for(change_request)
    if not user.has_perm(checker):
        raise exceptions.PermissionDenied(f"Needs {checker}.")
    if action.account(change_request) == user.pk:
        raise exceptions.PermissionDenied("Nobody approves a change to their own account.")
    if user.pk == change_request.maker_id:
        if not override:
            raise exceptions.PermissionDenied("Another person approves it: the maker never does.")
        if not (user.is_owner and user.has_perm("staff.break_glass")):
            raise exceptions.PermissionDenied("Only an owner overrides.")
        if not comment.strip():
            raise serializers.ValidationError({"comment": ["Say why nobody else can approve it."]})


def approve(change_request, *, user, payload_sha256, comment="", override=False, request=None):
    """The checker's approval of the payload they read (its hash sent back); then it may run (execute)."""
    action = ACTIONS[change_request.action]
    with transaction.atomic():
        change_request = _lock(change_request)
        check_approver(action, change_request, user, override, comment)
        expired = expire_if_due(change_request, request)
        if not expired:
            if change_request.status != Status.PENDING:
                raise serializers.ValidationError({"non_field_errors": ["Only a request waiting for approval."]})
            if payload_sha256 != change_request.payload_sha256:
                raise serializers.ValidationError(
                    {"payload_sha256": ["The request is not the one you read: read it again."]}
                )
            change_request.overridden = user.pk == change_request.maker_id
            Approval.objects.create(
                change_request=change_request, user=user, decision=Approval.Decision.APPROVE, comment=comment[:500]
            )
            change_request.approve()
            change_request.save()
            overridden = change_request.overridden  # marked break-glass in the log, whoever overrode
            _event(change_request, "overridden" if overridden else "approved", request, actor=user, reason=comment,
                   break_glass=True if overridden else None)  # fmt: skip
            if change_request.overridden:
                alert(
                    f"An owner approved their own request #{change_request.pk}",
                    f"{action.label}: {change_request.target_label}. Reason: {comment}",
                )
    if expired:
        raise serializers.ValidationError(EXPIRED)
    return change_request


def reject(change_request, *, user, comment="", request=None):
    """A checker refuses it, or its maker withdraws it."""
    action = ACTIONS[change_request.action]
    with transaction.atomic():
        change_request = _lock(change_request)
        if user.pk != change_request.maker_id and not user.has_perm(action.checker_for(change_request)):
            raise exceptions.PermissionDenied(f"Needs {action.checker_for(change_request)}.")
        expired = expire_if_due(change_request, request)
        if not expired:
            if change_request.status != Status.PENDING:
                raise serializers.ValidationError({"non_field_errors": ["Only a request waiting for approval."]})
            Approval.objects.create(
                change_request=change_request, user=user, decision=Approval.Decision.REJECT, comment=comment[:500]
            )
            change_request.reject()
            change_request.save()
            _event(change_request, "rejected", request, actor=user, reason=comment)
    if expired:
        raise serializers.ValidationError(EXPIRED)
    return change_request


def execute(change_request, *, by, request=None):
    """Run an approved request once, from its stored payload: the hash checked, the action's preconditions checked
    again; done or failed, with the result kept and audited."""
    action = ACTIONS[change_request.action]
    with transaction.atomic():
        change_request = _lock(change_request)
        expired = expire_if_due(change_request, request)
        if not expired and change_request.status != Status.APPROVED:
            raise serializers.ValidationError({"non_field_errors": ["Only an approved request runs, once."]})
    if expired:
        raise serializers.ValidationError(EXPIRED)
    error = None
    try:
        with transaction.atomic():
            change_request = _lock(change_request)
            if change_request.status != Status.APPROVED:  # run by someone else meanwhile
                raise serializers.ValidationError({"non_field_errors": ["Only an approved request runs, once."]})
            if digest(change_request.payload) != change_request.payload_sha256:
                raise Refused("The stored payload does not match the one approved: not run.")
            result = action.run(change_request, by)
            change_request.execute(by, plain(result))
            change_request.save()
            _event(change_request, "executed", request, actor=by, details={"result": change_request.result})
    except Refused as refused:
        error = str(refused)
    if error is not None:
        with transaction.atomic():
            change_request = _lock(change_request)
            change_request.fail(by, error)
            change_request.save()
            _event(change_request, "failed", request, actor=by, outcome=Outcome.FAILED, reason=error)
    return change_request


def expire_due():
    """Expire the requests whose time is over (hourly: staff.tasks)."""
    count = 0
    now = timezone.now()
    for pk in ChangeRequest.objects.filter(
        status__in=[Status.PENDING, Status.APPROVED], expires_at__lte=now
    ).values_list("pk", flat=True):
        with transaction.atomic():
            count += expire_if_due(ChangeRequest.objects.select_for_update().get(pk=pk))
    return count
