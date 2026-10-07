"""The invoice PDF: GST columns on every line even at 0 % (books, HSN 4901, are exempt, so the document is a bill of
supply until a taxed item is sold). Prices include tax: each line's taxable value is its price, less its share of the
order's discount, divided by (1 + rate). Same state as the seller: CGST + SGST; another state: IGST."""

from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string

from .models import STATES, address_lines, rupees


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
        taxable = rupees((value - share) * 100 / (100 + item.gst_rate))
        tax = value - share - taxable
        cgst = rupees(tax / 2) if intra_state else Decimal("0.00")
        lines.append(
            {
                "item": item,
                "value": value,
                "discount": share,
                "taxable": taxable,
                "cgst": cgst,
                "sgst": tax - cgst if intra_state else Decimal("0.00"),
                "igst": Decimal("0.00") if intra_state else tax,
                "half_rate": item.gst_rate / 2,
            }
        )
    return {
        "invoice": invoice,
        "order": order,
        "seller": seller,
        "seller_state": STATES.get(seller["state"], seller["state"]),
        "buyer_lines": address_lines(order.shipping_address),
        "place_of_supply": STATES.get(buyer_state, buyer_state),
        "intra_state": intra_state,
        "lines": lines,
        "taxable_total": sum((line["taxable"] for line in lines), Decimal("0.00")),
        "tax_total": sum((line["cgst"] + line["sgst"] + line["igst"] for line in lines), Decimal("0.00")),
        "title": "Tax invoice" if any(item.gst_rate for item in items) else "Bill of supply",
    }


def render_pdf(invoice):
    from weasyprint import HTML  # imported here: it needs Pango, a system library (Dockerfile, README)

    html = render_to_string("shop/invoice.html", context(invoice))
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
