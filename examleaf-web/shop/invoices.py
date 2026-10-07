"""The invoice and credit note PDFs: GST columns on every line even at 0 % (books, HSN 4901, are exempt, so the document
is a bill of supply until a taxed item is sold). Prices include tax: each line's taxable value is its price, less its
share of the order's discount, divided by (1 + rate). Same state as the seller: CGST + SGST; another state: IGST."""

from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string

from .models import STATES, CreditNote, address_lines, rupees


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
    lines = []
    for index, item in enumerate(items):
        value = item.line_total.amount
        if index == len(items) - 1:
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
        {**line, "value": share, **tax(line["item"], share, data["intra_state"])}
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


def render_pdf(document):
    """The PDF of an Invoice or a CreditNote."""
    from weasyprint import HTML  # imported here: it needs Pango, a system library (Dockerfile, README)

    if isinstance(document, CreditNote):
        html = render_to_string("shop/credit_note.html", credit_note_context(document))
    else:
        html = render_to_string("shop/invoice.html", context(document))
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
