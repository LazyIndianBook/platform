from functools import wraps

from axes.helpers import get_client_ip_address
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django_fsm import TransitionNotAllowed

from content.models import Paper

from . import payments, services
from .cart import COUNT_KEY, SESSION_KEY, get_cart, remember_count, set_quantity, totals
from .forms import AddressBookForm, AddressForm, CheckoutForm, CouponForm, LookupForm
from .models import Coupon, CreditNote, Order, Product, ProductImage, ShippingRate

ORDERS_KEY = "shop_orders"  # numbers of the orders this browser session placed or looked up (guests' access)
# Razorpay Checkout: its script, its frames and its API calls, allowed on the payment page only.
RAZORPAY_CSP = {
    "script-src": ["https://checkout.razorpay.com"],
    "frame-src": ["https://api.razorpay.com", "https://checkout.razorpay.com"],
    "connect-src": ["https://api.razorpay.com", "https://lumberjack.razorpay.com"],
}


def allow_razorpay(response):
    for attr, setting in (("_csp_config", "SECURE_CSP"), ("_csp_ro_config", "SECURE_CSP_REPORT_ONLY")):
        if policy := getattr(settings, setting, None):
            fallback = policy.get("default-src", [])
            directives = {*policy, *RAZORPAY_CSP}
            setattr(response, attr, {d: [*policy.get(d, fallback), *RAZORPAY_CSP.get(d, [])] for d in directives})
    response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"  # Checkout's bank and 3-D Secure windows
    return response


def rate_limit(scope, limit, seconds):
    """At most `limit` POSTs per client address in `seconds`, counted in Django's cache (Redis in production)."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                key = f"shop:rate:{scope}:{get_client_ip_address(request)}"
                cache.add(key, 0, seconds)
                try:
                    count = cache.incr(key)
                except ValueError:  # expired between add and incr
                    count = 1
                    cache.set(key, count, seconds)
                if (count or 0) > limit:  # None: the cache (Redis) is down; let the request through
                    response = render(request, "429.html", status=429)
                    response["Retry-After"] = str(seconds)
                    return response
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def grant(request, order):
    request.session[ORDERS_KEY] = [*request.session.get(ORDERS_KEY, [])[-19:], order.number]


def visible_order(request, number):
    """The order, if this visitor may see it: their account's, or placed or looked up in this browser session."""
    order = get_object_or_404(Order, number=number)
    mine = request.user.is_authenticated and order.user_id == request.user.pk
    if not mine and number not in request.session.get(ORDERS_KEY, []):
        raise Http404
    return order


def empty_cart(request):
    if cart := get_cart(request):
        cart.delete()
    request.session.pop(SESSION_KEY, None)
    request.session[COUNT_KEY] = 0


class CatalogueView(ListView):
    template_name = "shop/catalogue.html"
    queryset = Product.objects.filter(is_active=True).select_related("subject__board", "subject__class_level")


class ProductView(DetailView):
    template_name = "shop/product.html"
    queryset = Product.objects.filter(is_active=True).select_related("subject__board", "subject__class_level", "book")

    def get_context_data(self, **kwargs):
        product, context = self.object, super().get_context_data(**kwargs)
        if product.book:
            papers = list(product.book.papers.filter(is_published=True))  # by code: E01 first
            context["tiers"] = [(label, sum(p.tier == tier for p in papers)) for tier, label in Paper.Tier.choices]
            context["sample_paper"] = papers[0] if papers else None
        context["bundle_items"] = product.bundle_items.select_related("product")
        return context


@cache_control(public=True, max_age=86400)
def product_media(request, name):
    """A product's cover or picture. Uploads are otherwise private (media/ is not served): only files that a product
    names are sent."""
    if not (Product.objects.filter(cover=name).exists() or ProductImage.objects.filter(image=name).exists()):
        raise Http404
    try:
        return FileResponse(default_storage.open(name))
    except FileNotFoundError as error:
        raise Http404 from error


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    if product.available < 1:
        messages.error(request, f"{product} is out of stock.")
        return redirect(product)
    cart = get_cart(request, create=True)
    try:
        quantity = max(int(request.POST.get("quantity", 1)), 1)
    except ValueError:
        quantity = 1
    set_quantity(cart, product, quantity, add=True)
    remember_count(request, cart)
    messages.success(request, f"{product} is in your cart.")
    return redirect("shop:cart")


@never_cache
def cart_view(request):
    cart = get_cart(request)
    user = request.user if request.user.is_authenticated else None
    coupon_form = CouponForm(request.POST if request.POST.get("action") == "coupon" else None)
    if request.method == "POST" and cart:
        action = request.POST.get("action")
        if (remove := request.POST.get("remove", "")).isdigit():
            cart.items.filter(product_id=remove).delete()
        elif action == "update":
            for item in cart.items.select_related("product"):
                value = request.POST.get(f"qty-{item.product_id}", "")
                if value.isdigit():
                    set_quantity(cart, item.product, int(value))
        elif action == "remove-coupon":
            cart.coupon = None
            cart.save(update_fields=["coupon", "modified"])
        elif action == "coupon" and coupon_form.is_valid():
            coupon = Coupon.objects.filter(code__iexact=coupon_form.cleaned_data["code"].strip()).first()
            problem = (
                coupon.problem(totals(cart).subtotal, user=user, email=user.email if user else "")
                if coupon
                else "This coupon code is not valid."
            )
            if problem:
                messages.error(request, problem)
            else:
                cart.coupon = coupon
                cart.save(update_fields=["coupon", "modified"])
                messages.success(request, f"Coupon {coupon} applied.")
        remember_count(request, cart)
        return redirect("shop:cart")
    result = totals(cart, user=user, email=user.email if user else "")
    return render(request, "shop/cart.html", {"cart": cart, "totals": result, "coupon_form": coupon_form})


@never_cache
def checkout(request):
    cart = get_cart(request)
    if cart is None or not cart.items.exists():
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart")
    user = request.user if request.user.is_authenticated else None
    form = CheckoutForm(request.POST or None, user=user)
    address_form = AddressForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        saved = form.cleaned_data.get("saved_address")
        if saved:
            address_form = AddressForm()  # not used: no errors to show
        if saved or address_form.is_valid():
            address = saved or address_form.save(commit=False)
            try:
                with transaction.atomic():  # the order and the address saved with it, or neither
                    order = services.create_order(
                        cart,
                        user=user,
                        email=user.email if user else form.cleaned_data["email"],
                        address=address.snapshot(),
                        method=form.cleaned_data["payment_method"],
                    )
                    if user and not saved and form.cleaned_data.get("save_address"):
                        address.user, address.is_default = user, not user.addresses.exists()
                        address.save()
            except services.ShopError as error:
                form.add_error(None, str(error))
            else:
                grant(request, order)
                return redirect("shop:pay", order.number)
    context = {
        "form": form,
        "address_form": address_form,
        "totals": totals(cart, user=user, email=user.email if user else ""),
        "rates": ShippingRate.objects.filter(is_active=True),
    }
    return render(request, "shop/checkout.html", context)


@never_cache
def pay(request, number):
    """Review and pay: Razorpay Checkout for online payment, or "place order" for cash on delivery."""
    order = visible_order(request, number)
    if request.method == "POST" and order.is_cod:
        try:
            services.place_cod(order)
        except services.ShopError as error:  # the last copies, or the coupon's last use, went meanwhile
            services.cancel_order(order, f"Not placed: {error}", email=False)
            messages.error(request, f"{error} {error.advice}")
            return redirect("shop:cart")
        empty_cart(request)
        return redirect("shop:done", order.number)
    if order.status != Order.Status.PENDING or order.placed_at:
        return redirect(order)
    context = {"order": order, "coupon_problem": services.coupon_problem(order)}  # nothing to pay for if it is gone
    if not order.is_cod and not context["coupon_problem"]:
        try:
            context["checkout"] = payments.checkout_options(order)
        except payments.Unavailable as error:
            context["unavailable"] = str(error)
        context["test_mode"] = payments.test_mode()
    return allow_razorpay(render(request, "shop/pay.html", context))


@require_POST
def pay_verify(request, number):
    """Checkout's success handler posts here (the hidden form on the payment page)."""
    order = visible_order(request, number)
    payment = order.payments.filter(razorpay_order_id=request.POST.get("razorpay_order_id") or None).first()
    if payment is None or not payments.confirm_return(payment, request.POST):
        messages.error(
            request,
            "We could not confirm this payment. Please try again. If money was taken from your account, we "
            "confirm the order or refund it by ourselves within a few minutes.",
        )
        return redirect("shop:pay", number)
    if Order.objects.values_list("status", flat=True).get(pk=order.pk) == Order.Status.CANCELLED:
        return redirect("shop:done", number)  # sold out or coupon used up while paying: refunded; the cart is kept
    empty_cart(request)
    return redirect("shop:done", number)


@never_cache
def order_detail(request, number, thanks=False):
    order = visible_order(request, number)
    invoice = getattr(order, "invoice", None)
    context = {
        "order": order,
        "thanks": thanks,
        "items": order.items.all(),
        "shipments": order.shipments.all(),
        "refunds": order.refunds.all(),
        "invoice": invoice if invoice and invoice.pdf else None,
        "credit_notes": CreditNote.objects.filter(invoice__order=order).exclude(pdf=""),
        "payment": order.payments.first(),
    }
    return render(request, "shop/order_detail.html", context)


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class OrderListView(ListView):
    template_name = "shop/order_list.html"

    def get_queryset(self):
        return self.request.user.orders.prefetch_related("items")


@require_POST
def order_cancel(request, number):
    order = visible_order(request, number)
    if not order.can_cancel:
        messages.error(request, "This order can no longer be cancelled; see the Refund Policy.")
        return redirect(order)
    try:
        order = services.cancel_order(order, "Cancelled by the customer.")
    except TransitionNotAllowed:  # changed meanwhile (e.g. packed by staff)
        messages.error(request, "This order can no longer be cancelled; see the Refund Policy.")
        return redirect(order)
    refund = order.refunds.first()
    messages.success(
        request,
        f"Order {order.number} is cancelled."
        + (
            f" {refund.amount} will be refunded to the account, card or UPI ID you paid from within 5–7 working days."
            if refund
            else ""
        ),
    )
    return redirect(order)


def pdf_response(document):
    """An Invoice's or a CreditNote's PDF as a download (404 until the file has been made)."""
    if document is None or not document.pdf:
        raise Http404
    filename = f"ExamLeaf-{document.number.replace('/', '-')}.pdf"
    return FileResponse(document.pdf.open("rb"), as_attachment=True, filename=filename)


@never_cache
def invoice_pdf(request, number, note=None):
    """The invoice, or with `note` a credit note, of an order the visitor may see (or staff who may view them)."""
    if request.user.has_perm("shop.view_creditnote" if note else "shop.view_invoice"):
        order = get_object_or_404(Order, number=number)
    else:
        order = visible_order(request, number)
    if note:
        return pdf_response(CreditNote.objects.filter(invoice__order=order, pk=note).first())
    return pdf_response(getattr(order, "invoice", None))


@never_cache
@rate_limit("lookup", 10, 600)
def lookup(request):
    """Guests find an order by its number and the email address used for it."""
    form = LookupForm(request.POST or None)
    if form.is_valid():
        number, email = form.cleaned_data["number"].strip().upper(), form.cleaned_data["email"]
        if order := Order.objects.filter(number=number, email__iexact=email).first():
            grant(request, order)
            return redirect(order)
        form.add_error(None, "No order has this number and email address.")
    return render(request, "shop/lookup.html", {"form": form})


@csrf_exempt  # signed by Razorpay instead (X-Razorpay-Signature)
@require_POST
@rate_limit("webhook", 300, 60)
def razorpay_webhook(request):
    headers = request.headers
    if payments.handle_webhook(
        request.body, headers.get("X-Razorpay-Signature", ""), headers.get("X-Razorpay-Event-Id", "")
    ):
        return HttpResponse("ok")
    return HttpResponse("bad signature", status=400)


class MyAddresses(LoginRequiredMixin):
    """The address book on My account: the user's own addresses only (anyone else's: 404)."""

    success_url = reverse_lazy("account")

    def get_queryset(self):
        return self.request.user.addresses.all()


class AddressCreate(MyAddresses, SuccessMessageMixin, CreateView):
    form_class, template_name, success_message = AddressBookForm, "shop/address_form.html", "Address saved."

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class AddressUpdate(MyAddresses, SuccessMessageMixin, UpdateView):
    form_class, template_name, success_message = AddressBookForm, "shop/address_form.html", "Address saved."


class AddressDelete(MyAddresses, DeleteView):
    http_method_names = ["post"]  # the button on My account
