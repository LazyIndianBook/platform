from allauth.account.decorators import reauthentication_required
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, TemplateView

from ops.tasks import queue_text_email

from .forms import TeacherRequestForm
from .models import ConsentRecord, DeletionRequest, TeacherProfile

PROFILE_FIELDS = [
    "email",
    "full_name",
    "phone",
    "class_level",
    "district",
    "date_of_birth",
    "parent_name",
    "parent_contact",
    "consent_at",
    "created",
    "last_login",
]


class AccountView(LoginRequiredMixin, TemplateView):
    """/account/: the student's details, teacher access, and the DPDP self-service (download, delete)."""

    template_name = "my_account.html"


class TeacherRequestView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = TeacherRequestForm
    template_name = "teacher_request.html"
    success_url = reverse_lazy("account")
    success_message = "Thank you. Once we have checked with your school, this page shows you as a verified teacher."

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and TeacherProfile.objects.filter(user=request.user).exists():
            return redirect("account")  # one request per account; its status is on the account page
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except IntegrityError:  # a double click: the other request has made the profile
            return redirect("account")


def export_orders(user):
    """The user's orders as kept (tax records), with their invoice and credit notes by number (the PDFs stay on the
    order pages)."""
    orders = user.orders.select_related("invoice").prefetch_related(
        "items", "shipments", "refunds", "payments", "invoice__credit_notes"
    )
    return [
        {
            "number": order.number,
            "created": order.created,
            "status": order.status_label,
            "placed_at": order.placed_at,
            "email": order.email,
            "shipping_address": order.shipping_address,
            "payment_method": order.get_payment_method_display(),
            **{name: str(getattr(order, name).amount) for name in ["subtotal", "discount", "shipping_fee", "total"]},
            "coupon_code": order.coupon_code,
            "items": [
                {"title": item.title, "quantity": item.quantity, "unit_price": str(item.unit_price.amount)}
                for item in order.items.all()
            ],
            "shipments": [
                {"courier": s.courier, "tracking_number": s.tracking_number, "shipped_at": s.shipped_at}
                for s in order.shipments.all()
            ],
            "refunds": [
                {"amount": str(r.amount.amount), "status": r.status, "reason": r.reason, "created": r.created}
                for r in order.refunds.all()
            ],
            "payments": [
                {
                    "method": p.get_method_display(),
                    "status": p.status,
                    "amount": str(p.amount.amount),
                    "razorpay_payment_id": p.razorpay_payment_id,
                    "created": p.created,
                }
                for p in order.payments.all()
            ],
            "timeline": [{"status": label, "at": at} for label, at in order.timeline()],
            "invoice": order.invoice.number if hasattr(order, "invoice") else None,
            "credit_notes": [n.number for n in order.invoice.credit_notes.all()] if hasattr(order, "invoice") else [],
        }
        for order in orders
    ]


def export_cart(user):
    """The cart kept for the user (deleted with the account), if there is one."""
    if cart := getattr(user, "cart", None):
        items = [{"title": i.product.title, "quantity": i.quantity} for i in cart.items.select_related("product")]
        return {"coupon": cart.coupon.code if cart.coupon else None, "items": items}
    return None


def export_user_data(user):
    """Everything kept about a user (Download my data; staff use it for a data request by letter, see RUNBOOK.md)."""
    return {
        "exported_at": timezone.now(),
        "profile": {
            **{name: getattr(user, name) for name in PROFILE_FIELDS},
            "phone": str(user.phone),
            "board": str(user.board or ""),
            "roles": sorted(user.role_names),
        },
        "email_addresses": list(user.emailaddress_set.values("email", "verified", "primary")),
        "teacher_profile": TeacherProfile.objects.filter(user=user)
        .values("school_name", "district", "subject", "verified", "verified_at", "created")
        .first(),
        "attempts": list(
            user.attempts.values("paper__code", "date", "marks_obtained", "time_taken_minutes", "notes", "created")
        ),
        "answer_sheets": list(user.answer_sheets.values("paper__code", "status", "image", "created")),
        "consents": list(user.consents.values("event", "purpose", "notice_version", "by_parent", "ip_hash", "created")),
        "deletion_requests": list(user.deletion_requests.values("status", "requested_at", "due_at", "closed_at")),
        "addresses": [{**a.snapshot(), "is_default": a.is_default, "created": a.created} for a in user.addresses.all()],
        "cart": export_cart(user),
        "orders": export_orders(user),
    }


@never_cache
@login_required
@reauthentication_required  # the password again unless it was entered in the last few minutes
def data_export(request):
    """Download my data, as one JSON file."""
    data = export_user_data(request.user)
    response = JsonResponse(data, encoder=DjangoJSONEncoder, json_dumps_params={"indent": 2, "ensure_ascii": False})
    response["Content-Disposition"] = f'attachment; filename="examleaf-my-data-{timezone.localdate()}.json"'
    return response


class DeleteAccountForm(forms.Form):
    confirm = forms.BooleanField(
        label=f"I understand that my account, my record and my details will be deleted "
        f"{DeletionRequest.GRACE.days} days from now, unless I cancel before then."
    )


def deletion_day(deletion):
    return date_format(timezone.localtime(deletion.due_at), "j F Y")


def request_deletion(request):
    """Delete my account, for the website and the API: the request (due after DeletionRequest.GRACE), the consent
    withdrawn and the email. Returns (deletion, created); a request already waiting is returned as it is."""
    user = request.user
    if deletion := user.pending_deletion:
        return deletion, False
    try:
        with transaction.atomic():
            deletion = DeletionRequest.objects.create(user=user)
            ConsentRecord.record(request, user, event=ConsentRecord.Event.WITHDRAWN)
    except IntegrityError:  # a double click: the other request has made it (one waiting request per user)
        return DeletionRequest.objects.get(user=user, status=DeletionRequest.Status.PENDING), False
    queue_text_email(
        user.email,
        "Your account will be deleted",
        f"We have your request to delete your ExamLeaf account. It will be deleted on {deletion_day(deletion)}.\n\n"
        f'Changed your mind, or did not ask for this? Log in before then and press "Keep my '
        f'account" on {settings.SITE_URL}{reverse("account")}',
    )
    return deletion, True


def keep_account(request):
    """Cancel the waiting deletion, for the website and the API: consent given again and an email. Returns the
    cancelled request, or None if none was waiting."""
    if deletion := request.user.pending_deletion:
        deletion.status, deletion.closed_at = DeletionRequest.Status.CANCELLED, timezone.now()
        deletion.save()
        ConsentRecord.record(request, request.user)  # staying on is consenting again
        queue_text_email(
            request.user.email,
            "Your account will not be deleted",
            "The deletion of your ExamLeaf account has been cancelled. Your account stays as it was.",
        )
    return deletion


@login_required
@reauthentication_required(allow_get=True)  # the page is shown; pressing Delete asks for the password
def delete_account(request):
    if request.user.pending_deletion:
        return redirect("account")
    form = DeleteAccountForm(request.POST or None)
    if form.is_valid():
        deletion, _ = request_deletion(request)
        day = deletion_day(deletion)
        messages.success(request, f"Your account will be deleted on {day}. Until then you can log in and cancel.")
        return redirect("account")
    return render(request, "account_delete.html", {"form": form})


@login_required
@require_POST
def cancel_deletion(request):
    if keep_account(request):
        messages.success(request, "Your account will not be deleted.")
    return redirect("account")
