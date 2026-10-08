from django import forms
from localflavor.in_.forms import INZipCodeField
from localflavor.in_.in_states import STATE_CHOICES
from stdnum.in_ import gstin

from accounts.forms import TurnstileMixin

from .models import Address, PinCode, Product, QuoteRequest, Shipment

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

    pin = INZipCodeField(
        label="PIN code",
        help_text="6 digits, such as 781001.",
        error_messages={"required": "Enter the 6-digit PIN code.", "invalid": "Enter the 6-digit PIN code."},
    )
    state = forms.ChoiceField(
        choices=sorted(STATE_CHOICES, key=lambda choice: choice[1]),
        initial="AS",
        error_messages={"required": "Choose the state.", "invalid_choice": "Choose the state from the list."},
    )

    class Meta:
        model = Address
        fields = Address.FIELDS
        error_messages = {  # what each box needs, rather than "This field is required."
            "name": {"required": "Enter the name of the person who receives the parcel."},
            "phone": {"required": "Enter a 10-digit mobile number for the courier."},
            "line1": {"required": "Enter the house number and street."},
            "city": {"required": "Enter the city, town or village."},
            "district": {"required": "Enter the district."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, value in AUTOCOMPLETE.items():
            self.fields[name].widget.attrs["autocomplete"] = value
        self.fields["phone"].widget.attrs.update(inputmode="tel", placeholder="98640 12345")
        self.fields["phone"].error_messages["invalid"] = "Enter a 10-digit Indian mobile number."
        self.fields["pin"].widget.attrs.update(inputmode="numeric", maxlength=7)

    def clean(self):
        data = super().clean()
        if data.get("pin") and data.get("state") and (problem := PinCode.state_problem(data["pin"], data["state"])):
            self.add_error("state", problem)  # the state decides the GST (CGST + SGST, or IGST)
        return data


class ShipForm(forms.Form):  # admin: "mark shipped", one row per order
    order = forms.IntegerField(widget=forms.HiddenInput)
    courier = forms.ChoiceField(choices=Shipment.Courier.choices, initial=Shipment.Courier.INDIA_POST)
    tracking_number = forms.CharField(max_length=80)
    tracking_url = forms.URLField(
        required=False, assume_scheme="https", help_text="Empty: the courier's tracking page (17TRACK for the others)."
    )


class StaffOrderForm(forms.Form):  # admin: "Add order", a phone or school order (services.create_staff_order)
    email = forms.EmailField(
        help_text="The customer's: the order, the payment link and the invoice go there. An account whose confirmed "
        "address it is gets the order (a course needs one)."
    )
    discount = forms.DecimalField(
        label="Discount (₹)",
        required=False,
        min_value=0,
        decimal_places=2,
        help_text="Off the books, after the offers.",
    )
    shipping = forms.DecimalField(
        label="Shipping (₹)", required=False, min_value=0, decimal_places=2, help_text="Empty: the shipping rates'."
    )
    send_link = forms.BooleanField(label="Email a Razorpay payment link now", required=False, initial=True)
    note = forms.CharField(
        label="Internal note", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3})
    )


class StaffOrderLineForm(forms.Form):
    product = forms.ModelChoiceField(Product.objects.filter(is_active=True))
    quantity = forms.IntegerField(min_value=1, max_value=5000)  # no initial value: rows left empty are skipped


class OfflinePaymentForm(forms.Form):  # admin: "record a payment received offline"
    reference = forms.CharField(
        label="Bank or UPI reference",
        max_length=60,
        help_text="The UTR of the NEFT/IMPS transfer, or the UPI reference, as on the bank statement. Printed on the "
        "invoice. Check that the whole total has arrived first.",
    )


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


class QuoteRequestForm(TurnstileMixin, forms.ModelForm):
    """School and bulk orders (api/v1/quotes/): the buyer's details and a number of copies per book on sale."""

    delivery_pin = INZipCodeField(label="Delivery PIN code", error_messages={"invalid": "Enter the 6-digit PIN code."})

    class Meta:
        model = QuoteRequest
        fields = ["school", "contact_name", "email", "phone", "gstin", "delivery_pin", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 3, "maxlength": 1000})}
        help_texts = {"gstin": "If the school or shop is registered for GST: it goes on the quotation and the invoice."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].widget.attrs.update(inputmode="tel", placeholder="98640 12345")
        self.fields["phone"].error_messages["invalid"] = "Enter a 10-digit Indian mobile number."
        # books only: a course opens in one account (one per order), so a school's pupils get book codes instead
        self.products = [product for product in Product.objects.filter(is_active=True) if not product.has_digital]
        for product in self.products:
            self.fields[f"copies_{product.pk}"] = forms.IntegerField(
                label=f"Copies of {product.title}", min_value=0, max_value=10000, required=False
            )

    def clean_gstin(self):
        return gstin.compact(self.cleaned_data["gstin"])  # " 18aabcu9603r1zm " -> 18AABCU9603R1ZM

    def clean(self):
        data = super().clean()
        self.instance.items = [
            {"product": product.slug, "title": product.title, "quantity": data[f"copies_{product.pk}"]}
            for product in self.products
            if data.get(f"copies_{product.pk}")
        ]
        if not self.instance.items:
            raise forms.ValidationError("Enter the number of copies of at least one book.")
        return data
