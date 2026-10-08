from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView

from accounts.forms import TurnstileMixin
from ops.tasks import queue_email
from shop.views import rate_limit

from .models import PLACEHOLDER, Page

CONTACT_SENT = "Thank you: your message is on its way to us. We reply by email."


class PageView(DetailView):
    model = Page
    template_name = "page.html"


def support_email():
    """Where the contact form writes to: SUPPORT_EMAIL, else the seller's address (SELLER_EMAIL); "" while that is
    empty or still a [placeholder], and the page then shows no form."""
    address = getattr(settings, "SUPPORT_EMAIL", "") or settings.SHOP_SELLER["email"]
    return "" if not address or PLACEHOLDER.search(address) else address


class ContactForm(TurnstileMixin, forms.Form):
    name = forms.CharField(label="Your name", max_length=120, error_messages={"required": "Tell us your name."})
    email = forms.EmailField(
        label="Your email address",
        help_text="We reply to this address.",
        error_messages={"required": "Enter the address we should reply to.", "invalid": "Enter an email address."},
    )
    message = forms.CharField(
        label="Your message",
        max_length=3000,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="About an order? Give its number, such as EL-2026-000123.",
        error_messages={"required": "Write your message."},
    )


@method_decorator(rate_limit("contact", 5, 3600), name="post")  # five messages an hour from one address
class ContactView(PageView):
    """/contact/: the page, and a form that emails the message to support_email() with the sender's address to reply
    to. Nothing is stored: the email is the only copy. A filled-in "website" field is the honeypot."""

    def get_context_data(self, **kwargs):
        form = kwargs.pop("form", None) or (ContactForm() if support_email() else None)
        return super().get_context_data(form=form, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object, form = self.get_object(), ContactForm(request.POST)
        if not support_email() or request.POST.get("website"):
            messages.success(request, CONTACT_SENT)  # bots learn nothing
            return redirect("contact")
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        data = form.cleaned_data
        body = f"{data['message']}\n\n{data['name']} <{data['email']}>, through the contact form."
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Contact form: {data['name']}"
        queue_email(EmailMessage(subject, body, to=[support_email()], headers={"Reply-To": data["email"]}))
        messages.success(request, CONTACT_SENT)
        return redirect("contact")
