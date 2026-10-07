from allauth.account.decorators import reauthentication_required
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
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
        return super().form_valid(form)


def export_user_data(user):
    """Everything kept about a user (Download my data; staff use it for a data request by letter, see RUNBOOK.md)."""
    return {
        "exported_at": timezone.now(),
        "profile": {
            **{name: getattr(user, name) for name in PROFILE_FIELDS},
            "phone": str(user.phone),
            "board": str(user.board or ""),
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


@login_required
@reauthentication_required(allow_get=True)  # the page is shown; pressing Delete asks for the password
def delete_account(request):
    if request.user.pending_deletion:
        return redirect("account")
    form = DeleteAccountForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            deletion = DeletionRequest.objects.create(user=request.user)
            ConsentRecord.record(request, request.user, event=ConsentRecord.Event.WITHDRAWN)
        day = date_format(timezone.localtime(deletion.due_at), "j F Y")
        queue_text_email(
            request.user.email,
            "Your account will be deleted",
            f"We have your request to delete your ExamLeaf account. It will be deleted on {day}.\n\n"
            f'Changed your mind, or did not ask for this? Log in before then and press "Keep my '
            f'account" on {settings.SITE_URL}{reverse("account")}',
        )
        messages.success(request, f"Your account will be deleted on {day}. Until then you can log in and cancel.")
        return redirect("account")
    return render(request, "account_delete.html", {"form": form})


@login_required
@require_POST
def cancel_deletion(request):
    if deletion := request.user.pending_deletion:
        deletion.status, deletion.closed_at = DeletionRequest.Status.CANCELLED, timezone.now()
        deletion.save()
        ConsentRecord.record(request, request.user)  # staying on is consenting again
        queue_text_email(
            request.user.email,
            "Your account will not be deleted",
            "The deletion of your ExamLeaf account has been cancelled. Your account stays as it was.",
        )
        messages.success(request, "Your account will not be deleted.")
    return redirect("account")
