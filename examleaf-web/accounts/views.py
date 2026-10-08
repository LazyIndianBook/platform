import re
import unicodedata
from datetime import timedelta

from allauth.account.decorators import reauthentication_required
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.formats import date_format
from django.utils.http import base36_to_int, int_to_base36
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import CreateView, TemplateView

from ops.models import EmailSuppression
from ops.sms import queue_sms
from ops.tasks import queue_text_email

from .forms import TeacherRequestForm, parent_link_contact
from .models import ConsentRecord, DeletionRequest, TeacherProfile, User

PROFILE_FIELDS = [
    "email",
    "full_name",
    "phone",
    "login_phone",
    "login_phone_verified",
    "sms_updates",
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
        "items", "shipments", "refunds", "payments", "notes", "invoice__credit_notes"
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
            "staff_notes": [{"text": note.text, "created": note.created} for note in order.notes.all()],  # L10
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


def export_shop_requests(user):
    """The user's reviews, and what the shop keeps under the account's email address: school quotation requests and
    "email me when it is back" requests."""
    from shop.models import QuoteRequest, StockAlert

    quote_fields = ["school", "contact_name", "email", "gstin", "items", "delivery_pin", "note", "status", "created"]
    return {
        "reviews": list(user.reviews.values("product__title", "rating", "text", "status", "created")),
        "quote_requests": [
            {**{name: getattr(quote, name) for name in quote_fields}, "phone": str(quote.phone)}
            for quote in QuoteRequest.objects.filter(email__iexact=user.email)
        ],
        "stock_alerts": list(StockAlert.objects.filter(email__iexact=user.email).values("product__title", "created")),
    }


def export_course(user):
    """The revision course's data (learn.services.export_learning), while that app is installed."""
    try:
        from learn.services import export_learning
    except ImportError:
        return None
    return export_learning(user)


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
        "passkeys_and_authenticators": list(user.authenticator_set.values("type", "created_at", "last_used_at")),
        "google_accounts": list(user.socialaccount_set.values("provider", "uid", "extra_data", "date_joined")),
        "teacher_profile": TeacherProfile.objects.filter(user=user)
        .values("school_name", "district", "subject", "verified", "verified_at", "created")
        .first(),
        "attempts": list(
            user.attempts.values("paper__code", "date", "marks_obtained", "time_taken_minutes", "notes", "created")
        ),
        "answer_sheets": list(user.answer_sheets.values("paper__code", "status", "image", "created")),
        "consents": list(
            user.consents.values(
                "event", "purpose", "notice_version", "by_parent", "method", "verified_at", "ip_hash", "created"
            )
        ),
        "deletion_requests": list(user.deletion_requests.values("status", "requested_at", "due_at", "closed_at")),
        "addresses": [{**a.snapshot(), "is_default": a.is_default, "created": a.created} for a in user.addresses.all()],
        "cart": export_cart(user),
        "orders": export_orders(user),
        **export_shop_requests(user),
        "learning": export_course(user),
        # L10: the texts sent to the account (no numbers), and whether the address gets no more email (bounces)
        "sms": list(user.sms_messages.values("kind", "status", "phone_last4", "created")),
        "email_suppressed": EmailSuppression.objects.filter(email__iexact=user.email)
        .values("reason", "created")
        .first(),
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
def sms_updates(request):
    """My account: order updates by SMS on or off (ops.sms.send_order_sms); only with a confirmed mobile number."""
    user = request.user
    user.sms_updates = user.login_phone_verified and "sms_updates" in request.POST
    user.save(update_fields=["sms_updates"])
    messages.success(request, f"Order updates by SMS: {'on' if user.sms_updates else 'off'}.")
    return redirect("account")


@login_required
@require_POST
def cancel_deletion(request):
    if keep_account(request):
        messages.success(request, "Your account will not be deleted.")
    return redirect("account")


PARENT_LINK_SALT, PARENT_LINK_DAYS = "accounts.parent-consent", 7


class ShortSigner(signing.TimestampSigner):
    """Django's timestamped signature cut to 16 characters (96 bits), so that the link's token (about 28 characters)
    fits a DLT SMS variable (30 at most)."""

    def signature(self, value, key=None):
        return super().signature(value, key)[:16]


def parent_signer(contact):
    """The parent's link names their contact: one sent before the contact was corrected stops working."""
    return ShortSigner(salt=f"{PARENT_LINK_SALT}:{contact}", sep=".")


A_STUDENT, PARENT_LINKS_PER_DAY = "a student", 3
NAME_WORDS = re.compile(r"[^ .-]+(?:-[^ .-]+)*\.?(?: [^ .-]+(?:-[^ .-]+)*\.?)*")


def shown_name(full_name):
    """The student's name as the parent's email and SMS may carry it (M3): letters of any script with their marks,
    single spaces, a hyphen inside a word and a dot at the end of one ("A. K. Das"), at most 60 characters; anything
    else (a web address, digits, a sign) is "a student". The rest of the messages is fixed text."""
    name = " ".join(str(full_name).split())
    letters = all(unicodedata.category(char)[0] in "LM" or char in " .-" for char in name)
    return name if 0 < len(name) <= 60 and letters and NAME_WORDS.fullmatch(name) else A_STUDENT


def parent_link_allowed(contact):
    """At most PARENT_LINKS_PER_DAY links a day to one parent's address or number, whichever accounts ask (M3)."""
    key = "accounts:parent-links:" + salted_hmac(PARENT_LINK_SALT, contact, algorithm="sha256").hexdigest()
    cache.add(key, 0, 24 * 3600)
    try:
        return (cache.incr(key) or 0) <= PARENT_LINKS_PER_DAY  # 0: the cache is down; the SMS limits still hold
    except ValueError:  # expired in between
        return True


def send_parent_link(user):
    """PARENTAL_CONSENT_MODE "verified" (M9): the parent gets a signed link to confirm, valid PARENT_LINK_DAYS days, by
    email, or by SMS when the contact is a mobile number. Who receives it is not proof of parenthood (DPDP rules: the
    SMS, like the email, only reaches the contact the student gave; RUNBOOK.md "Parental consent"). Sent once the
    student has confirmed their own address (accounts.models), then on My account; fixed text with the student's
    name only as shown_name allows (M3). Returns whether it went (a limit may stop it: M2, M3)."""
    if not parent_link_allowed(user.parent_contact):
        return False
    token, name = parent_signer(user.parent_contact).sign(int_to_base36(user.pk)), shown_name(user.full_name)
    if "@" not in user.parent_contact:
        variables = {"var1": A_STUDENT if name == A_STUDENT else name.split()[0][:30], "var2": token}
        return queue_sms("parent_consent", user.parent_contact, variables, user=user)
    queue_text_email(
        user.parent_contact,
        "Please confirm your child's account",
        f"{name[0].upper()}{name[1:]} has registered at ExamLeaf, for the free solutions of the ExamLeaf sample "
        f"papers, and gave this address as their parent's or guardian's. The law asks for your consent before we keep "
        f"the details of a student under 18. Read what we keep, and confirm, here (the link works for "
        f"{PARENT_LINK_DAYS} days):\n\n{settings.SITE_URL}{reverse('parent_consent', args=[token])}\n\n"
        f"If you do not agree, do nothing: the account cannot save marks or order books. To have it deleted, write "
        f"to us: {settings.SITE_URL}{reverse('contact')}",
    )
    return True


@never_cache
@require_http_methods(["GET", "POST"])
def parent_consent(request, token):
    """The parent's link (M9): the page says who registered and links the privacy notice; "I agree" records the
    consent, verified by the link (ConsentRecord.Method EMAIL_LINK or SMS_LINK, with the time)."""
    try:
        student = User.objects.get(pk=base36_to_int(token.partition(".")[0]), is_active=True)
        parent_signer(student.parent_contact).unsign(token, max_age=timedelta(days=PARENT_LINK_DAYS))
    except ValueError, signing.BadSignature, User.DoesNotExist:
        return render(request, "parent_consent.html", {"expired": True}, status=400)
    done = not student.consent_pending
    if request.method == "POST" and not done:
        method = ConsentRecord.Method.EMAIL_LINK if "@" in student.parent_contact else ConsentRecord.Method.SMS_LINK
        ConsentRecord.record(request, student, by_parent=True, method=method, verified_at=timezone.now())
        done = True
    return render(request, "parent_consent.html", {"student": student, "done": done})


def resend_parent_link(user, value):
    """While the parent's consent is pending (M9), for the website and the API: the link again, to the contact on
    record or a corrected one. ValidationError: not a contact (or the student's own), or a link went less than ten
    minutes ago (code "too_soon"), or a limit stopped it (code "not_sent": never reported as sent, M2)."""
    contact = parent_link_contact(value)
    if not contact or contact in (user.email, user.login_phone):
        raise ValidationError("Enter your parent's or guardian's email address or mobile number (not your own).")
    if not cache.add(f"accounts:parent-link:{user.pk}", 1, 600):
        message = "A link was sent a few minutes ago: wait ten minutes before asking for another."
        raise ValidationError(message, code="too_soon")
    user.parent_contact = contact
    user.save(update_fields=["parent_contact"])
    if not send_parent_link(user):
        message = "The link was not sent: that address or number has had several today. Try again tomorrow."
        raise ValidationError(message, code="not_sent")


@login_required
@require_POST
def parent_consent_resend(request):
    """While the parent's consent is pending: the link again, to the contact on record or a corrected one (M9)."""
    user = request.user
    if not user.consent_pending:
        return redirect("account")
    try:
        resend_parent_link(user, request.POST.get("parent_contact"))
    except ValidationError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"We have sent {user.parent_contact} a link to confirm.")
    return redirect("account")
