"""The invoice and credit note PDFs: GST columns on every line even at 0 % (books, HSN 4901, are exempt, so the document
is a bill of supply until a taxed item is sold). Prices include tax: each line's taxable value is its price, less its
share of the order's discount, divided by (1 + rate). Same state as the seller: CGST + SGST; another state: IGST."""

import base64
from dataclasses import dataclass
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


def discount_shares(order, items):
    """Each item's share of the order's discounts, as its invoice prints it: the split kept at checkout (cart.split),
    or for orders made before it was kept, shared out by value, the last line taking the rounding remainder."""
    subtotal, left = order.subtotal.amount, order.discount.amount
    kept = all(item.discount is not None for item in items)
    shares = []
    for index, item in enumerate(items):
        if kept:
            share = item.discount.amount
        elif index == len(items) - 1:
            share = left
        else:
            share = rupees(order.discount.amount * item.line_total.amount / subtotal) if subtotal else Decimal("0.00")
        left -= share
        shares.append(share)
    return shares


def context(invoice):
    order, seller = invoice.order, settings.SHOP_SELLER
    buyer_state = order.shipping_address["state"]
    intra_state = buyer_state == seller["state"]
    items = list(order.items.all())
    lines = []
    for item, share in zip(items, discount_shares(order, items), strict=True):
        value = item.line_total.amount
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
    rate. A refused parcel refunded less the shipping credits the books only. A refund of chosen lines (the panel's,
    Refund.lines) credits those lines by what each was refunded, with the copies refunded, and its shipping."""
    data = context(note.invoice)
    order, refund = data["order"], note.refund
    invoiced = [line["value"] - line["discount"] for line in data["lines"]]
    books = sum(invoiced, Decimal("0.00"))
    amount = min(refund.amount.amount, order.total.amount)
    if refund.lines:
        refunded = {int(line["item"]): line for line in refund.lines}
        shares = [
            Decimal(refunded[line["item"].pk]["amount"]) if line["item"].pk in refunded else Decimal("0.00")
            for line in data["lines"]
        ]
        books_credit = sum(shares, Decimal("0.00"))
        copies = [refunded[line["item"].pk]["quantity"] if line["item"].pk in refunded else 0 for line in data["lines"]]
    else:
        books_credit = min(amount, books)
        shares = [rupees(part * books_credit / books) if books else Decimal("0.00") for part in invoiced[:-1]]
        shares.append(books_credit - sum(shares, Decimal("0.00")))  # the last line takes the rounding remainder
        copies = [line["item"].quantity for line in data["lines"]]
    lines = [
        {**line, "value": share, "amount": share, "quantity": count, **tax(line["item"], share, data["intra_state"])}
        for line, share, count in zip(data["lines"], shares, copies, strict=True)
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


@dataclass
class Print:
    """A document the panel prints for one order or several (shop/staff_orders.py, the bulk print job): `kind` is
    packing_slip (A4: the books with their ISBN and copies, the school or class, the number as a QR), label (4 × 6
    inches, for a parcel sent by hand), pick_list (A4: each book once, with its copies and orders) or invoices (each
    order's invoice again, one after the other)."""

    kind: str
    orders: list


def qr_data_uri(text):
    """A QR code of `text` as an SVG data: URL (django-qr-code, as content.views.qr_png makes the papers' codes)."""
    from qr_code.qrcode.maker import make_qr_code_image
    from qr_code.qrcode.utils import QRCodeOptions

    svg = make_qr_code_image(text, QRCodeOptions(size=8, border=2, image_format="svg"))
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


def school_or_class(order):
    """Who the books are for, on the slip: the school of the quotation it came from, else the buyer's class."""
    quote = getattr(order, "quote", None)
    if quote is not None:
        return quote.school
    user = order.user
    if user is not None and user.class_level:
        board = getattr(user.board, "short_name", "")
        return f"Class {user.class_level}" + (f", {board}" if board else "")
    return ""


def books_of(order):
    """The books to pack for an order, each once with its copies: a bundle's books; courses have none."""
    copies, products = {}, {}
    for item in order.items.all():
        product = item.product
        if product.kind == Product.Kind.BUNDLE:
            parts = [(entry.product, entry.quantity * item.quantity) for entry in product.bundle_items.all()]
        else:
            parts = [(product, item.quantity)]
        for book, count in parts:
            if not book.is_digital:
                copies[book.pk] = copies.get(book.pk, 0) + count
                products[book.pk] = book
    return [{"product": products[pk], "quantity": count} for pk, count in copies.items()]


def print_context(document):
    seller = settings.SHOP_SELLER
    orders = [
        {
            "order": order,
            "qr": qr_data_uri(order.number),
            "books": books_of(order),
            "for": school_or_class(order),
            "to": address_lines(order.shipping_address),
            "collect": order.total.amount if order.is_cod else None,
        }
        for order in document.orders
    ]
    picks = {}
    for entry in orders:
        for book in entry["books"]:
            row = picks.setdefault(book["product"].pk, {"product": book["product"], "quantity": 0, "orders": []})
            row["quantity"] += book["quantity"]
            row["orders"].append(f"{entry['order'].number} × {book['quantity']}")
    return {
        "seller": seller,
        "seller_state": STATES.get(seller["state"], seller["state"]),
        "orders": orders,
        "picks": sorted(picks.values(), key=lambda row: row["product"].title),
        "copies": sum(row["quantity"] for row in picks.values()),
    }


def print_html(document):
    """The HTML of a Print (the tests read it; render_pdf makes it a PDF)."""
    return render_to_string(f"shop/{document.kind}.html", print_context(document))


def render_pdf(document):
    """The PDF of an Invoice, a CreditNote, a QuoteRequest's quotation, or a Print."""
    from weasyprint import HTML  # imported here: it needs Pango, a system library (Dockerfile, README)

    if isinstance(document, Print) and document.kind == "invoices":  # each invoice as it was, one PDF
        rendered = [
            HTML(
                string=render_to_string("shop/invoice.html", context(order.invoice)),
                base_url=str(settings.BASE_DIR),
                url_fetcher=static_files_only(),
            ).render()
            for order in document.orders
        ]
        return rendered[0].copy([page for one in rendered for page in one.pages]).write_pdf()
    if isinstance(document, Print):
        html = print_html(document)
    elif isinstance(document, CreditNote):
        html = render_to_string("shop/credit_note.html", credit_note_context(document))
    elif isinstance(document, QuoteRequest):
        html = render_to_string("shop/quotation.html", quotation_context(document))
    else:
        html = render_to_string("shop/invoice.html", context(document))
    return HTML(string=html, base_url=str(settings.BASE_DIR), url_fetcher=static_files_only()).write_pdf()
