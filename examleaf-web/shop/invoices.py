"""The invoice and credit note PDFs, and the arithmetic every tax report reads (export_gstr1, the ERPNext contract, the
threshold monitor), so that the reports are the legal documents. Prices include tax: each line's taxable value is
what it costs after its share of the order's discounts, divided by (1 + rate), to the paisa (the tax is the rest).
A bundle invoiced split shows its components as lines (OrderItem.parts, shop/tax.py). The shipping follows the goods
it carries (research 5.2): shared over the parcel's goods by their amounts and taxed with each, so exempt books ship
exempt and a course, which ships nothing, takes none; a cash-on-delivery fee, if one is ever charged, goes the same
way (`charges`). Same state as the seller: CGST + SGST; another: IGST. The place of supply is the order's billing
state. The document's type comes from its lines: a tax invoice, a bill of supply, or an invoice-cum-bill of supply
(Rule 46A); goods documents carry three copies (Rule 48)."""

import base64
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string
from django.utils import timezone
from djmoney.money import Money

from . import tax as rules
from .cart import split
from .models import (
    INR,
    STATES,
    BundleItem,
    CreditNote,
    DocumentType,
    HsnCode,
    PinCode,
    Product,
    QuoteRequest,
    SlugHistory,
    Taxability,
    address_lines,
    rupees,
)

ZERO = Decimal("0.00")
COPIES = {  # Rule 48: goods in triplicate, services in duplicate
    "goods": ["Original for recipient", "Duplicate for transporter", "Triplicate for supplier"],
    "services": ["Original for recipient", "Duplicate for supplier"],
}


def check_seller(live):
    """Invoices of the real series carry the seller's details for good (the numbers cannot be reissued): while one of
    them is still a [placeholder] of the defaults, none is made (the task is retried; set SELLER_* in .env). Documents
    of test-mode orders (`live` False: their own series) and DEBUG are not held up."""
    if settings.DEBUG or not live:
        return
    if missing := [name for name, value in settings.SHOP_SELLER.items() if "[" in str(value)]:
        raise ImproperlyConfigured(f"SELLER_* still holds placeholders for {', '.join(missing)}: see .env.example")


@dataclass(frozen=True)
class Part:
    """One component of a bundle invoiced split, as a line of the invoice: what the documents and the ERPNext payload
    read of an order item, under OrderItem's names."""

    product: Product
    title: str
    hsn_code: str
    gst_rate: Decimal
    mrp: Money
    unit_price: Money
    quantity: int
    bundle: str  # the bundle's title

    @property
    def product_id(self):
        return self.product.pk

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Catalogue:
    """The products a run over many documents reads, loaded once (the GSTR-1 export, the threshold monitor): no query
    per document for a split bundle's components or for whether a line is goods."""

    def __init__(self):
        self.products = Product.objects.in_bulk()
        self.components = defaultdict(list)
        for item in BundleItem.objects.select_related("product"):
            self.components[item.bundle_id].append(item.product)

    def goods(self, product):
        if product.kind == Product.Kind.BUNDLE:
            components = self.components.get(product.pk, [])
            return not components or any(not component.is_digital for component in components)
        return not product.is_digital


def is_goods(product, catalogue=None):
    """Whether the line travels in a parcel (not the course, nor a bundle of courses only)."""
    return catalogue.goods(product) if catalogue else not product.digital_only


def tax_on(rate, amount, intra_state):
    """The taxable value and GST inside `amount` rupees, tax included, at `rate` per cent."""
    taxable = rupees(amount * 100 / (100 + rate))
    gst = amount - taxable
    cgst = rupees(gst / 2) if intra_state else ZERO
    return {
        "taxable": taxable,
        "cgst": cgst,
        "sgst": gst - cgst if intra_state else ZERO,
        "igst": ZERO if intra_state else gst,
    }


def tax(item, amount, intra_state):
    """The taxable value and GST inside `amount` rupees (tax included) of an order item (or a part)."""
    return tax_on(item.gst_rate, amount, intra_state)


def parts_of(item, catalogue=None):
    """A split bundle's components as Parts with their extras (OrderItem.parts, per bundle: times its quantity)."""
    rows = item.parts or []
    known = catalogue.products if catalogue else Product.objects.in_bulk([row["product"] for row in rows])
    found = []
    for row in rows:
        product = known.get(row["product"]) or Product(pk=row["product"], title=row["title"], kind=row["kind"])
        quantity = int(row["quantity"]) * item.quantity
        part = Part(
            product=product,
            title=row["title"],
            hsn_code=row["hsn_code"],
            gst_rate=Decimal(row["gst_rate"]),
            mrp=Money(row["mrp"], INR),
            unit_price=Money(row["unit_price"], INR),
            quantity=quantity,
            bundle=item.title,
        )
        found.append((part, Decimal(row["extra"]) * item.quantity))
    return found


def line(item, value, discount, intra_state, goods, bundle="", source=None, per_unit=1):
    """One line of a document: `source` is the order item it comes from (a split bundle's components share one) and
    `per_unit` how many of it one copy of that item holds (a refund of n copies credits n × per_unit of a part)."""
    amount = value - discount  # what the line costs: taxable value and GST
    return {
        "item": item,
        "value": value,
        "discount": discount,
        "amount": amount,
        "half_rate": item.gst_rate / 2,
        "goods": goods,
        "bundle": bundle,
        "source": source,
        "per_unit": per_unit,
        **tax(item, amount, intra_state),
    }


def discount_shares(order, items):
    """Each item's share of the order's discounts, as its invoice prints it: the split kept at checkout (cart.split),
    or for orders made before it was kept, shared out by value, the last line taking the rounding remainder (the
    refund pricing of shop.services reads it)."""
    subtotal, left = order.subtotal.amount, order.discount.amount
    kept = all(item.discount is not None for item in items)
    shares = []
    for index, item in enumerate(items):
        if kept:
            share = item.discount.amount
        elif index == len(items) - 1:
            share = left
        else:
            share = rupees(order.discount.amount * item.line_total.amount / subtotal) if subtotal else ZERO
        left -= share
        shares.append(share)
    return shares


def lines_of(order, intra_state, catalogue=None):
    """The invoice's lines: each order item at its price less its share of the discounts (the split made at checkout,
    cart.split; orders from before it was kept share the discount out as their invoices always did), a split bundle's
    as its components, the bundle's share of the discounts shared over them by their values."""
    items = list(order.items.all())
    subtotal, left = order.subtotal.amount, order.discount.amount
    kept = all(item.discount is not None for item in items)
    lines = []
    for index, item in enumerate(items):
        value = item.line_total.amount
        if kept:
            share = item.discount.amount
        elif index == len(items) - 1:
            share = left  # the last line takes the rounding remainder
        else:
            share = rupees(order.discount.amount * value / subtotal) if subtotal else ZERO
        left -= share
        if not item.parts:
            lines.append(line(item, value, share, intra_state, is_goods(item.product, catalogue), source=item.pk))
            continue
        parts = parts_of(item, catalogue)
        values = [part.line_total.amount for part, _extra in parts]
        for (part, extra), part_value, part_share in zip(parts, values, split(share, values), strict=True):
            goods = part.product.kind != Product.Kind.DIGITAL
            per_unit = max(part.quantity // max(item.quantity, 1), 1)
            lines.append(line(part, part_value, part_share + extra, intra_state, goods, bundle=item.title,
                              source=item.pk, per_unit=per_unit))  # fmt: skip
    return lines


def charges_of(order, lines, intra_state):
    """The shipping, shared over the goods lines by their amounts (all the lines when there are no goods), each share
    taxed at its line's rate, then summed by rate: [{label, rate, amount, taxable, cgst, sgst, igst}]."""
    fees = [("Shipping", order.shipping_fee.amount)]  # a cash-on-delivery fee, once charged, joins it here
    carriers = [entry for entry in lines if entry["goods"]] or lines
    by_rate = {}
    for label, fee in fees:
        if not fee or not carriers:
            continue
        amounts = [entry["amount"] for entry in carriers]
        shares = split(fee, amounts if any(amounts) else [Decimal(1)] * len(carriers))
        for entry, share in zip(carriers, shares, strict=True):
            rate = entry["item"].gst_rate
            by_rate.setdefault((label, rate), Decimal(0))
            by_rate[(label, rate)] += share
    charges = []
    for (label, rate), amount in sorted(by_rate.items()):
        charges.append({"label": label, "rate": rate, "amount": amount, **tax_on(rate, amount, intra_state)})
    return charges


def sums(lines, charges):
    """The document's taxable value (taxed lines and charges, without their tax), exempt value (the untaxed ones)
    and GST."""
    rows = [(entry["item"].gst_rate, entry) for entry in lines] + [(entry["rate"], entry) for entry in charges]
    taxable = sum((entry["taxable"] for rate, entry in rows if rate), ZERO)
    exempt = sum((entry["amount"] for rate, entry in rows if not rate), ZERO)
    gst = sum((entry["cgst"] + entry["sgst"] + entry["igst"] for _rate, entry in rows), ZERO)
    return {"taxable_value": taxable, "exempt_value": exempt, "tax_amount": gst}


def place(order):
    """The order's place of supply: its billing state (the parcel's state for orders from before it was kept)."""
    return order.billing_state or order.shipping_address.get("state", "") or settings.SHOP_SELLER["state"]


def supply(order, catalogue=None):
    """What the order's invoice says, before and after it is numbered: its lines, the charges that follow the goods,
    any round-off (what was paid less what the lines add up to, on a line of its own: none while the checkout's sums
    hold), the place of supply, the document's type, and its kept totals."""
    state = place(order)
    intra_state = state == settings.SHOP_SELLER["state"]
    lines = lines_of(order, intra_state, catalogue)
    charges = charges_of(order, lines, intra_state)
    added = sum((entry["amount"] for entry in [*lines, *charges]), ZERO)
    kept = sums(lines, charges)
    return {
        "lines": lines,
        "charges": charges,
        "round_off": order.total.amount - added,
        "state": state,
        "intra_state": intra_state,
        "document_type": rules.document_type(entry["item"].gst_rate for entry in lines),
        "goods": any(entry["goods"] for entry in lines),
        "kept": kept,
        "taxable_total": kept["taxable_value"],
        "tax_total": kept["tax_amount"],
        "exempt_total": kept["exempt_value"],
    }


def context(invoice, catalogue=None):
    """The invoice as its PDF, the ERPNext contract and the reports read it."""
    order, seller = invoice.order, settings.SHOP_SELLER
    data = supply(order, catalogue)
    kind = invoice.document_type or data["document_type"]
    return {
        **data,
        "document": invoice,
        "invoice": invoice,
        "order": order,
        "seller": seller,
        "seller_state": STATES.get(seller["state"], seller["state"]),
        "buyer_lines": address_lines(order.shipping_address),
        "place_of_supply": rules.state_label(data["state"]),
        "billed_elsewhere": data["state"] != order.shipping_address.get("state", data["state"]),
        "document_type": kind,
        "title": DocumentType(kind).label,
        "copies": COPIES["goods" if data["goods"] else "services"],
    }


def credit_lines(data, amount, refund=None):
    """The credit shared out as the invoice charged it: first its lines, in proportion to what each was invoiced (all
    of it for a full refund), then the charges (the shipping) with what is left, each part reversing its tax at its
    rate. A refused parcel refunded less the shipping credits the goods only. A refund of chosen lines (the panel's,
    Refund.lines: [{item, quantity, amount}]) credits those lines by what each was refunded, a split bundle's amount
    shared over its components by their values, with the copies refunded on each line (`quantity`); the shipping is
    what is left of the amount."""
    entries = data["lines"]
    invoiced = [entry["amount"] for entry in entries]
    books = sum(invoiced, ZERO)
    wanted = {int(row["item"]): row for row in (refund.lines or []) if refund is not None} if refund else {}
    if wanted:
        shares, copies = [ZERO] * len(entries), [0] * len(entries)
        by_source = defaultdict(list)
        for index, entry in enumerate(entries):
            by_source[entry.get("source")].append(index)
        for source, indexes in by_source.items():
            row = wanted.get(source)
            if row is None:
                continue
            credit, values = Decimal(str(row["amount"])), [invoiced[i] for i in indexes]
            parts = split(credit, values) if any(values) else [credit, *([ZERO] * (len(indexes) - 1))]
            for i, share in zip(indexes, parts, strict=True):
                shares[i] = share
                copies[i] = int(row.get("quantity") or 0) * entries[i].get("per_unit", 1)
        books_credit = sum(shares, ZERO)
    else:
        books_credit = min(amount, books)
        shares = [rupees(part * books_credit / books) if books else ZERO for part in invoiced[:-1]]
        shares.append(books_credit - sum(shares, ZERO))  # the last line takes the rounding remainder
        copies = [entry["item"].quantity for entry in entries]
    intra_state = data["intra_state"]
    lines = [
        {**entry, "value": share, "amount": share, "quantity": count, **tax(entry["item"], share, intra_state)}
        for entry, share, count in zip(entries, shares, copies, strict=True)
    ]
    charged = [entry["amount"] for entry in data["charges"]]
    shipping_credit = min(amount - books_credit, sum(charged, ZERO))
    charges = []
    for entry, share in zip(data["charges"], split(shipping_credit, charged) if any(charged) else [], strict=False):
        charges.append({**entry, "amount": share, **tax_on(entry["rate"], share, intra_state)})
    return lines, charges, books_credit, shipping_credit


def credit_supply(note, catalogue=None):
    """What a credit note says, before and after it is numbered: its invoice's supply (rates, place of supply) and
    the refund shared out over it."""
    order = note.invoice.order
    data = supply(order, catalogue)
    amount = min(note.refund.amount.amount, order.total.amount)
    lines, charges, books_credit, shipping_credit = credit_lines(data, amount, note.refund)
    kept = sums(lines, charges)
    return {
        **data,
        "lines": lines,
        "charges": charges,
        "books_credit": books_credit,
        "shipping_credit": shipping_credit,
        "total_credit": books_credit + shipping_credit,
        "kept": kept,
        "taxable_total": kept["taxable_value"],
        "tax_total": kept["tax_amount"],
        "exempt_total": kept["exempt_value"],
    }


def credit_note_context(note, catalogue=None):
    """The credit note as its PDF, the ERPNext contract and the reports read it: against its invoice, at its rates
    and place of supply."""
    data = context(note.invoice, catalogue)
    credited = credit_supply(note, catalogue)
    return {
        **data,
        **{key: credited[key] for key in ("lines", "charges", "books_credit", "shipping_credit", "total_credit")},
        **{key: credited[key] for key in ("kept", "taxable_total", "tax_total", "exempt_total")},
        "document": note,
        "note": note,
        "title": "Credit note",
        "copies": [""],
    }


def hsn_printed(code):
    """The HSN or SAC code as a document prints it: its first SHOP_HSN_DIGITS digits (4 up to ₹5 crore of turnover,
    6 above: Notification 78/2020-CT)."""
    return str(code)[: settings.SHOP_HSN_DIGITS]


def exemptions(data, day):
    """Why the untaxed lines carry no tax, as a bill of supply must say (Rule 49): each code's master entry on the
    document's day, its taxability and notification."""
    untaxed = sorted({entry["item"].hsn_code for entry in data["lines"] if not entry["item"].gst_rate})
    rows = rules.rates_on(untaxed, day)
    described = {code: (kind, text) for code, kind, text in HsnCode.objects.filter(code__in=untaxed).values_list(
        "code", "kind", "description")}  # fmt: skip
    found = []
    for code in untaxed:
        row = rows.get(code)
        kind, text = described.get(code, ("", ""))
        what = f"{text.rstrip('.')} ({kind.upper()} {code})" if text else f"HSN or SAC {code}"
        if row is None or row.taxability == Taxability.TAXABLE:
            found.append(f"{what}: not taxed.")
            continue
        serial = f", serial number {row.serial}" if row.serial else ""
        found.append(f"{what}: {row.get_taxability_display()} under Notification {row.notification}{serial}.")
    return found


def pdf_context(document):
    """What the PDF template reads: the document's context, the HSN codes as printed, the exemptions' reasons and its
    copies."""
    data = credit_note_context(document) if isinstance(document, CreditNote) else context(document)
    for entry in data["lines"]:
        entry["hsn"] = hsn_printed(entry["item"].hsn_code)
    day = timezone.localdate(document.created) if document.created else None
    return {**data, "exemptions": exemptions(data, day) if day else [], "hsn_digits": settings.SHOP_HSN_DIGITS}


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
    """The PDF of an Invoice, a CreditNote, a QuoteRequest's quotation, or a Print (the panel's slips, labels, pick
    lists and invoice batches)."""
    from weasyprint import HTML  # imported here: it needs Pango, a system library (Dockerfile, README)

    if isinstance(document, Print) and document.kind == "invoices":  # each invoice as it was, one PDF
        rendered = [
            HTML(
                string=render_to_string("shop/invoice.html", pdf_context(order.invoice)),
                base_url=str(settings.BASE_DIR),
                url_fetcher=static_files_only(),
            ).render()
            for order in document.orders
        ]
        return rendered[0].copy([page for one in rendered for page in one.pages]).write_pdf()
    if isinstance(document, Print):
        html = print_html(document)
    elif isinstance(document, CreditNote):
        html = render_to_string("shop/credit_note.html", pdf_context(document))
    elif isinstance(document, QuoteRequest):
        html = render_to_string("shop/quotation.html", quotation_context(document))
    else:
        html = render_to_string("shop/invoice.html", pdf_context(document))
    return HTML(string=html, base_url=str(settings.BASE_DIR), url_fetcher=static_files_only()).write_pdf()
