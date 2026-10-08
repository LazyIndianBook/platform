import hashlib
from functools import wraps

from axes.helpers import get_client_ip_address
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django_fsm import TransitionNotAllowed

from content.models import Paper

from . import payments, services
from .cart import COUNT_KEY, SESSION_KEY, get_cart, remember_count, set_quantity, totals
from .forms import (
    AddressBookForm,
    AddressForm,
    CheckoutForm,
    CouponForm,
    LookupForm,
    QuoteRequestForm,
    ReviewForm,
)
from .models import (
    Category,
    Collection,
    Coupon,
    CreditNote,
    Order,
    PinCode,
    Product,
    Review,
    ShippingRate,
    SlugHistory,
    StockAlert,
    public_storage,
)
from .seo import breadcrumbs, product_jsonld

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


def hits(scope, who, seconds):
    """One more request of `who` (a client address, a hash) in `scope`, counted for `seconds` in Django's cache (Redis
    in production). Returns the count, or None when it cannot be read (Redis down)."""
    key = f"shop:rate:{scope}:{who}"
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, seconds)
        return 1


def too_many(request, seconds):
    response = render(request, "429.html", status=429)
    response["Retry-After"] = str(seconds)
    return response


def over_limit(request, scope, limit, seconds, while_down=False):
    """Counts the request for its client address: True over `limit` in `seconds`, and while the count cannot be read
    (Redis down), so the limit never just stops, unless `while_down` (Razorpay's webhooks must go on)."""
    count = hits(scope, get_client_ip_address(request), seconds)
    return (count is None and not while_down) or (count or 0) > limit


def rate_limit(scope, limit, seconds, while_down=False):
    """At most `limit` POSTs per client address in `seconds` (over_limit)."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST" and over_limit(request, scope, limit, seconds, while_down):
                return too_many(request, seconds)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


LOOKUPS_AN_HOUR = 10


def lookup_allowed(number, email):
    """Guests' order lookup (website and API), besides the limit per client address: at most LOOKUPS_AN_HOUR per email
    address and per order number, whatever address they come from; none while the counts cannot be read."""
    counts = [
        hits(f"lookup-{kind}", hashlib.sha256(value.lower().encode()).hexdigest(), 3600)  # no email in the cache
        for kind, value in (("email", email), ("number", number))
    ]
    return all(count is not None and count <= LOOKUPS_AN_HOUR for count in counts)


def shop_is_open(request):
    return settings.SHOP_OPEN or request.user.is_staff


def shop_open(view):
    """While SHOP_OPEN is off only staff reach the cart, checkout and payment; others land on the catalogue, which
    says "Shop opens soon" (Razorpay's review on test keys: nobody else may "buy" with a test card)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not shop_is_open(request):
            return redirect("shop:catalogue")
        return view(request, *args, **kwargs)

    return wrapped


def grant(request, order):
    request.session[ORDERS_KEY] = [*request.session.get(ORDERS_KEY, [])[-19:], order.number]


def visible_order(request, number=None, token=None):
    """The order, if this visitor may see it: by the link in its emails (`token`), or their account's, or placed in
    this browser session."""
    if token:
        return get_object_or_404(Order, token=token)
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
    """All products on sale (?kind= narrows them), with the top shelves of the category tree and the collections."""

    template_name = "shop/catalogue.html"
    related = ["subject__board", "subject__class_level"]

    def products(self):
        return Product.objects.filter(is_active=True)

    def get_queryset(self):
        products = self.products()
        if (kind := self.request.GET.get("kind")) in Product.Kind.values:
            products = products.filter(kind=kind)
        return products.select_related(*self.related)

    def get_context_data(self, **kwargs):
        shelves, collections = Category.objects.get_root_nodes(), Collection.objects.filter(is_active=True)
        context = {"shelves": shelves, "collections": collections}
        return {**super().get_context_data(**kwargs), "shop_open": shop_is_open(self.request), **context}


class CategoryView(CatalogueView):
    """A shelf: its products and those of its sub-shelves."""

    def products(self):
        self.category = get_object_or_404(Category, slug=self.kwargs["slug"])
        return self.category.products_on_sale()

    def get_context_data(self, **kwargs):
        category, context = self.category, super().get_context_data(**kwargs)
        crumbs = [(c.name, c.get_absolute_url()) for c in Category.objects.get_ancestors(category)]
        context.update(heading=category.name, intro=category.description, crumbs=crumbs, collections=None)
        context["shelves"] = Category.objects.get_children(category)
        return context


class CollectionView(CatalogueView):
    """A collection's products, in the order staff gave them."""

    def get_queryset(self):
        self.collection = get_object_or_404(Collection, slug=self.kwargs["slug"], is_active=True)
        return self.collection.products_on_sale()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(heading=self.collection.name, intro=self.collection.description, crumbs=[], shelves=None)
        return context


class ProductView(DetailView):
    template_name = "shop/product.html"
    queryset = Product.objects.filter(is_active=True).select_related("subject__board", "subject__class_level", "book")

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:  # an old address of a renamed product: 301 to its page
            moved = SlugHistory.objects.filter(slug=kwargs["slug"], product__is_active=True).first()
            if moved is None:
                raise
            return redirect(moved.product, permanent=True)

    def get_context_data(self, **kwargs):
        product, context = self.object, super().get_context_data(**kwargs)
        context["shop_open"] = shop_is_open(self.request)
        context["attributes"] = product.attribute_values.select_related("attribute")
        context["categories"] = product.categories.all()
        context["related"] = product.related.filter(is_active=True)
        if product.book:
            papers = list(product.book.papers.filter(is_published=True))  # by code: E01 first
            context["tiers"] = [(label, sum(p.tier == tier for p in papers)) for tier, label in Paper.Tier.choices]
            context["sample_paper"] = papers[0] if papers else None
        context["bundle_items"] = product.bundle_items.select_related("product")
        context["reviews"] = product.reviews.filter(status=Review.Status.APPROVED)
        rating = context["reviews"].aggregate(average=Avg("rating"), count=Count("pk"))
        context["rating"] = (rating["average"], rating["count"]) if rating["count"] else None
        if Review.can_review(self.request.user, product):
            context["review_form"] = ReviewForm()
        crumbs = [("Home", "/"), ("Shop", reverse("shop:catalogue")), (product.title, product.get_absolute_url())]
        context["jsonld"] = [product_jsonld(product, context["rating"]), breadcrumbs(*crumbs)]  # _head_meta.html
        context["og"] = {
            "type": "product",
            "title": product.title,
            "description": product.seo_description or product.title,
            "image": product.og_image.url if product.og_image else "",
        }
        return context


PUBLIC_FOLDERS = ("products/", "og/")  # the public storage's folders: pictures, their sizes, Open Graph images


@cache_control(public=True, max_age=86400)
def product_media(request, name):
    """The public storage's files while it is MEDIA_ROOT (no buckets: settings.STORAGES). Private uploads share that
    folder, so only PUBLIC_FOLDERS are sent, and no name that climbs out of them."""
    if not name.startswith(PUBLIC_FOLDERS) or ".." in name.split("/"):
        raise Http404
    try:
        return FileResponse(public_storage().open(name))
    except FileNotFoundError as error:
        raise Http404 from error


@require_POST
@rate_limit("stock-alert", 10, 3600)
def stock_alert(request, slug):
    """The "email me when it is back" button (StockAlert), for signed-in accounts, to their own address: an address a
    visitor types could be anyone's, emailed at the reprint without having asked (L3). A filled-in "website" field is
    the honeypot."""
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not request.user.is_authenticated:
        messages.info(request, "Log in, then press the button again: we email your account's address.")
        return redirect_to_login(product.get_absolute_url())
    email = request.user.email
    if not request.POST.get("website") and product.available < 1:
        StockAlert.objects.get_or_create(email=email.lower(), product=product)
    messages.success(request, f"We will email {email} once, when {product} is back in stock.")
    return redirect(product)


QUOTE_SENT = "Thank you: we will email you a quotation."


@never_cache
@rate_limit("quote", 5, 3600)
def quote_request(request):
    """School and bulk orders: the request form; staff are emailed. A filled-in "website" field is the honeypot."""
    form = QuoteRequestForm(request.POST or None)
    if request.method == "POST" and request.POST.get("website"):
        messages.success(request, QUOTE_SENT)
        return redirect("shop:quote")
    if form.is_valid():
        quote = form.save()
        services.email_staff(f"Quotation asked for: {quote.school}", "shop/email/quote_request.txt", {"quote": quote})
        messages.success(request, QUOTE_SENT)
        return redirect("shop:quote")
    return render(request, "shop/quote_request.html", {"form": form})


REVIEW_THANKS = "Thank you: your review shows on this page once we have read it."


@require_POST
@login_required
@rate_limit("review", 5, 3600)
def review(request, slug):
    """A review from the product page (Review.can_review). A filled-in "website" field is the honeypot: only bots see
    it; they are thanked and nothing is saved."""
    product = get_object_or_404(Product, slug=slug, is_active=True)
    form = ReviewForm(request.POST)
    if request.POST.get("website"):
        messages.success(request, REVIEW_THANKS)
    elif not Review.can_review(request.user, product):
        messages.error(request, "Reviews are from buyers whose order of this book has been delivered, one each.")
    elif form.is_valid():
        form.instance.product, form.instance.user = product, request.user
        try:
            form.save()
        except IntegrityError:  # sent twice at once
            pass
        messages.success(request, REVIEW_THANKS)
    else:
        messages.error(request, " ".join(error for errors in form.errors.values() for error in errors))
    return redirect(f"{product.get_absolute_url()}#reviews")


@cache_control(public=True, max_age=86400)  # public data: a day in browsers
def pin_lookup(request, pin):
    """The address form's autofill (static/js/site.js): the state(s) and districts of a PIN code in the directory
    (manage.py import_pincodes). A primary-key read: not kept in the server's cache, where `?x=1` … `?x=n` would each
    have stored a copy for a day beside the rate-limit counters (L9)."""
    if entry := PinCode.objects.filter(pin=pin).first():
        return JsonResponse({"pin": entry.pin, "states": entry.states, "districts": entry.districts})
    return JsonResponse({"detail": "Not in the PIN code directory."}, status=404)


@require_POST
@shop_open
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
@shop_open
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
            if over_limit(request, "coupon", 10, 3600):  # codes are not guessed
                messages.error(request, "Too many codes tried: please try again in an hour.")
            elif coupon is None or coupon.problem(totals(cart).subtotal, user=user, email=user.email if user else ""):
                messages.error(request, services.COUPON_REFUSED)  # the same for every reason: nothing to learn
            else:
                cart.coupon = coupon
                cart.save(update_fields=["coupon", "modified"])
                messages.success(request, f"Coupon {coupon} applied.")
        elif action == "coupon":  # no code typed, or the bot check (Turnstile) not passed
            messages.error(request, " ".join(error for errors in coupon_form.errors.values() for error in errors))
        remember_count(request, cart)
        return redirect("shop:cart")
    result = totals(cart, user=user, email=user.email if user else "")
    return render(request, "shop/cart.html", {"cart": cart, "totals": result, "coupon_form": coupon_form})


@never_cache
@shop_open
@rate_limit("checkout", 10, 600)  # orders hold stock (cash on delivery) and send emails
def checkout(request):
    cart = get_cart(request)
    if cart is None or not cart.items.exists():
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart")
    if request.user.is_authenticated and request.user.consent_pending:
        messages.error(request, "Your parent or guardian has not confirmed your account yet: see My account.")
        return redirect("account")
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
@shop_open
@rate_limit("place", 10, 600)  # "place order" (cash on delivery)
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
@shop_open
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
def order_detail(request, number=None, thanks=False, token=None):
    """The order's page; by the link in its emails (`token`) it shows the order without paying, and its own links."""
    order = visible_order(request, number, token)
    invoice = getattr(order, "invoice", None)
    context = {
        "order": order,
        "token": token,
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
def order_cancel(request, number=None, token=None):
    """Pending or paid orders only (can_cancel): once packed the Refund Policy applies."""
    order = visible_order(request, number, token)
    back = order.get_link_url() if token else order.get_absolute_url()
    if not order.can_cancel:
        messages.error(request, "This order can no longer be cancelled; see the Refund Policy.")
        return redirect(back)
    try:
        order = services.cancel_order(order, "Cancelled by the customer.")
    except TransitionNotAllowed:  # changed meanwhile (e.g. packed by staff)
        messages.error(request, "This order can no longer be cancelled; see the Refund Policy.")
        return redirect(back)
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
    return redirect(back)


def pdf_response(document):
    """An Invoice's or a CreditNote's PDF as a download (404 until the file has been made)."""
    if document is None or not document.pdf:
        raise Http404
    filename = f"ExamLeaf-{document.number.replace('/', '-')}.pdf"
    return FileResponse(document.pdf.open("rb"), as_attachment=True, filename=filename)


@never_cache
def invoice_pdf(request, number=None, note=None, token=None):
    """The invoice, or with `note` a credit note, of an order the visitor may see (or staff who may view them)."""
    if not token and request.user.has_perm("shop.view_creditnote" if note else "shop.view_invoice"):
        order = get_object_or_404(Order, number=number)
    else:
        order = visible_order(request, number, token)
    if note:
        return pdf_response(CreditNote.objects.filter(invoice__order=order, pk=note).first())
    return pdf_response(getattr(order, "invoice", None))


@never_cache
@rate_limit("lookup", LOOKUPS_AN_HOUR, 3600)
def lookup(request):
    """Guests ask for their order's link by its number and the email address used for it. The link goes to that
    address, never to this browser, and the answer is the same whether an order matched or not."""
    form = LookupForm(request.POST or None)
    if form.is_valid():
        number, email = form.cleaned_data["number"].strip().upper(), form.cleaned_data["email"]
        if not lookup_allowed(number, email):
            return too_many(request, 3600)
        services.email_order_link(number, email)
        return render(request, "shop/lookup.html", {"form": LookupForm(), "sent": services.LINK_SENT})
    return render(request, "shop/lookup.html", {"form": form})


@csrf_exempt  # signed by Razorpay instead (X-Razorpay-Signature)
@require_POST
@rate_limit("webhook", 300, 60, while_down=True)
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
