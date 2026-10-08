"""The invoice and credit note PDFs: GST columns on every line even at 0 % (books, HSN 4901, are exempt, so the document
is a bill of supply until a taxed item is sold). Prices include tax: each line's taxable value is its price, less its
share of the order's discount, divided by (1 + rate). Same state as the seller: CGST + SGST; another state: IGST."""

from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string

from .models import STATES, CreditNote, PinCode, Product, QuoteRequest, SlugHistory, address_lines, rupees


def check_seller(live):
    """Invoices of the real series carry the seller's details for good (the numbers cannot be reissued): while one of
    them is still a [placeholder] of the defaults, none is made (the task is retried; set SELLER_* in .env). Documents
    of test-mode orders (`live` False: their own series) and DEBUG are not held up."""
    if settings.DEBUG or not live:
        return
    if missing := [name for name, value in settings.SHOP_SELLER.items() if "[" in str(value)]:
        raise ImproperlyConfigured(f"SELLER_* still holds placeholders for {', '.join(missing)}: see .env.example")


def tax(item, amount, intra_state):
    """The taxable value and GST inside `amount` rupees (tax included) of an order item."""
    taxable = rupees(amount * 100 / (100 + item.gst_rate))
    gst = amount - taxable
    cgst = rupees(gst / 2) if intra_state else Decimal("0.00")
    zero = Decimal("0.00")
    return {
        "taxable": taxable,
        "cgst": cgst,
        "sgst": gst - cgst if intra_state else zero,
        "igst": zero if intra_state else gst,
    }


def context(invoice):
    order, seller = invoice.order, settings.SHOP_SELLER
    buyer_state = order.shipping_address["state"]
    intra_state = buyer_state == seller["state"]
    items = list(order.items.all())
    subtotal, discount_left = order.subtotal.amount, order.discount.amount
    kept = all(item.discount is not None for item in items)  # the split made at checkout (cart.split)
    lines = []
    for index, item in enumerate(items):
        value = item.line_total.amount
        if kept:
            share = item.discount.amount
        elif index == len(items) - 1:  # orders made before the split was kept: shared out as their invoices were
            share = discount_left  # the last line takes the rounding remainder
        else:
            share = rupees(order.discount.amount * value / subtotal) if subtotal else Decimal("0.00")
        discount_left -= share
        half_rate = item.gst_rate / 2
        lines.append(
            {
                "item": item,
                "value": value,
                "discount": share,
                "amount": value - share,  # what is payable for the line: taxable value and GST
                "half_rate": half_rate,
                **tax(item, value - share, intra_state),
            }
        )
    return {
        "document": invoice,
        "invoice": invoice,
        "order": order,
        "seller": seller,
        "seller_state": STATES.get(seller["state"], seller["state"]),
        "buyer_lines": address_lines(order.shipping_address),
        "place_of_supply": STATES.get(buyer_state, buyer_state),
        "intra_state": intra_state,
        "lines": lines,
        **totals(lines),
        "title": "Tax invoice" if any(item.gst_rate for item in items) else "Bill of supply",
    }


def totals(lines):
    return {
        "taxable_total": sum((line["taxable"] for line in lines), Decimal("0.00")),
        "tax_total": sum((line["cgst"] + line["sgst"] + line["igst"] for line in lines), Decimal("0.00")),
    }


def credit_note_context(note):
    """The refund shared out as the invoice charged it: first the books, over the lines in proportion to what each was
    invoiced (all of it for a full refund), then the shipping with what is left; each line's GST is reversed at its
    rate. A refused parcel refunded less the shipping credits the books only."""
    data = context(note.invoice)
    order = data["order"]
    invoiced = [line["value"] - line["discount"] for line in data["lines"]]
    books = sum(invoiced, Decimal("0.00"))
    amount = min(note.refund.amount.amount, order.total.amount)
    books_credit = min(amount, books)
    shares = [rupees(part * books_credit / books) if books else Decimal("0.00") for part in invoiced[:-1]]
    shares.append(books_credit - sum(shares, Decimal("0.00")))  # the last line takes the rounding remainder
    lines = [
        {**line, "value": share, "amount": share, **tax(line["item"], share, data["intra_state"])}
        for line, share in zip(data["lines"], shares, strict=True)
    ]
    return {
        **data,
        "document": note,
        "note": note,
        "lines": lines,
        **totals(lines),
        "books_credit": books_credit,
        "shipping_credit": amount - books_credit,
        "total_credit": amount,
        "title": "Credit note",
    }


def quotation_context(quote):
    """A school's quotation: today's prices of the books asked for, the staff's discount and shipping."""
    seller = settings.SHOP_SELLER
    slugs = [item["product"] for item in quote.items]
    products = Product.objects.in_bulk(slugs, field_name="slug")
    for old in SlugHistory.objects.filter(slug__in=set(slugs) - products.keys()).select_related("product"):
        products[old.slug] = old.product  # renamed since the request: quoted all the same
    lines = [
        {"product": product, "quantity": item["quantity"], "amount": product.price.amount * item["quantity"]}
        for item in quote.items
        if (product := products.get(item["product"]))
    ]
    books = sum((line["amount"] for line in lines), Decimal("0.00"))
    discount = rupees(books * quote.discount_percent / 100)
    states = PinCode.objects.filter(pin=quote.delivery_pin).values_list("states", flat=True).first() or [""]
    buyer = [quote.school, quote.contact_name, f"Delivery PIN code {quote.delivery_pin}", f"Mobile {quote.phone}"]
    return {
        "document": quote,
        "quote": quote,
        "title": "Quotation",
        "seller": seller,
        "seller_state": STATES.get(seller["state"], seller["state"]),
        "buyer_lines": [*buyer, quote.email, *([f"GSTIN {quote.gstin}"] if quote.gstin else [])],
        "place_of_supply": STATES.get(states[0]) or f"PIN code {quote.delivery_pin}",
        "intra_state": states[0] == seller["state"],
        "lines": lines,
        "books": books,
        "discount": discount,
        "total": books - discount + quote.shipping_fee,
    }


def static_files_only():
    """WeasyPrint's URL fetcher for the PDFs: data: URLs and files under the static folders, nothing else (no other
    local file, no network), so that a mistake in a template can never put a server file or an internal URL into a
    customer's invoice. A refused URL raises; WeasyPrint leaves that resource out."""
    from weasyprint.urls import URLFetcher

    roots = [Path(folder).resolve() for folder in [settings.STATIC_ROOT, *settings.STATICFILES_DIRS]]

    class StaticFilesOnly(URLFetcher):
        def fetch(self, url, headers=None):
            if url.startswith("file:"):
                path = Path(url2pathname(urlsplit(url).path)).resolve()
                if any(path.is_relative_to(root) for root in roots):
                    return super().fetch(url, headers)
            elif url.startswith("data:"):
                return super().fetch(url, headers)
            raise ValueError(f"Not fetched for a PDF: {url[:100]}")

    return StaticFilesOnly(allowed_protocols={"file", "data"})


def render_pdf(document):
    """The PDF of an Invoice, a CreditNote or a QuoteRequest's quotation."""
    from weasyprint import HTML  # imported here: it needs Pango, a system library (Dockerfile, README)

    if isinstance(document, CreditNote):
        html = render_to_string("shop/credit_note.html", credit_note_context(document))
    elif isinstance(document, QuoteRequest):
        html = render_to_string("shop/quotation.html", quotation_context(document))
    else:
        html = render_to_string("shop/invoice.html", context(document))
    return HTML(string=html, base_url=str(settings.BASE_DIR), url_fetcher=static_files_only()).write_pdf()
