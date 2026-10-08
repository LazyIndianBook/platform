from allauth.account.utils import has_verified_email
from django import forms
from django.conf import settings
from localflavor.in_.forms import INZipCodeField
from localflavor.in_.in_states import STATE_CHOICES

from .models import Address, Order

AUTOCOMPLETE = {
    "name": "name",
    "phone": "tel-national",
    "line1": "address-line1",
    "line2": "address-line2",
    "city": "address-level2",
    "state": "address-level1",
    "pin": "postal-code",
}


class AddressForm(forms.ModelForm):
    """Indian address: state from the list, 6-digit PIN code ("781 001" accepted), 10-digit mobile number."""

    pin = INZipCodeField(label="PIN code", error_messages={"invalid": "Enter the 6-digit PIN code."})
    state = forms.ChoiceField(choices=sorted(STATE_CHOICES, key=lambda choice: choice[1]), initial="AS")

    class Meta:
        model = Address
        fields = Address.FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, value in AUTOCOMPLETE.items():
            self.fields[name].widget.attrs["autocomplete"] = value
        self.fields["phone"].widget.attrs.update(inputmode="tel", placeholder="98640 12345")
        self.fields["phone"].error_messages["invalid"] = "Enter a 10-digit Indian mobile number."
        self.fields["pin"].widget.attrs.update(inputmode="numeric", maxlength=7)


class AddressBookForm(AddressForm):  # My account: the saved addresses
    class Meta(AddressForm.Meta):
        fields = [*Address.FIELDS, "is_default"]


class CheckoutForm(forms.Form):
    email = forms.EmailField(
        label="Email address", help_text="For the confirmation, tracking and the invoice; no account needed."
    )
    saved_address = forms.ModelChoiceField(
        label="Deliver to",
        queryset=Address.objects.none(),
        required=False,
        widget=forms.RadioSelect,
        empty_label="A new address (below)",
    )
    save_address = forms.BooleanField(label="Save this address in my account", required=False, initial=True)
    payment_method = forms.ChoiceField(label="Payment", widget=forms.RadioSelect, initial=Order.Method.RAZORPAY)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:  # the account's address is used; saved addresses offered
            del self.fields["email"]
            self.fields["saved_address"].queryset = user.addresses.all()
            self.fields["saved_address"].initial = user.addresses.filter(is_default=True).first()
            if not user.addresses.exists():
                del self.fields["saved_address"]
        else:
            del self.fields["saved_address"], self.fields["save_address"]
        cod = settings.SHOP_COD_ENABLED and user is not None and has_verified_email(user)
        methods = [Order.Method.RAZORPAY, *([Order.Method.COD] if cod else [])]
        self.fields["payment_method"].choices = [(m.value, m.label[0].upper() + m.label[1:]) for m in methods]
        if settings.SHOP_COD_ENABLED and not cod:
            self.fields["payment_method"].help_text = "Cash on delivery: log in with a confirmed email address."


class CouponForm(forms.Form):
    code = forms.CharField(label="Coupon code", max_length=30)


class LookupForm(forms.Form):
    number = forms.CharField(label="Order number", max_length=20, widget=forms.TextInput({"placeholder": "EL-2026-…"}))
    email = forms.EmailField(label="Email address used for the order")


class ShipForm(forms.Form):  # admin: "mark shipped", one row per order
    order = forms.IntegerField(widget=forms.HiddenInput)
    courier = forms.CharField(max_length=80, initial="India Post")
    tracking_number = forms.CharField(max_length=80)
    tracking_url = forms.URLField(required=False, assume_scheme="https")


class RefundForm(forms.Form):  # admin: "refund"
    reason = forms.CharField(max_length=200, initial="Refunded by ExamLeaf.")
    amount = forms.DecimalField(
        label="Amount (₹)",
        required=False,
        min_value=1,
        decimal_places=2,
        help_text="Empty: everything paid. Less, e.g. a refused parcel: the books without the shipping. Orders not "
        "yet shipped are always cancelled and refunded in full.",
    )
