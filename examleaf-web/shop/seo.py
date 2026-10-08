"""JSON-LD for search engines ({% jsonld %}): Product + Book on product pages with their breadcrumbs, Organization on
the home page. Google's rich results read Product (merchant listings: offers with shipping and returns), Organization,
BreadcrumbList and review ratings; FAQ results are retired (May 2026), so there is no FAQPage."""

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from content.templatetags.web import absolute

from .models import ShippingRate

SCHEMA = "https://schema.org"
# As the Refund and Cancellation Policy says: damaged or wrong books within 7 days, the return paid by ExamLeaf.
RETURN_POLICY = {
    "@type": "MerchantReturnPolicy",
    "applicableCountry": "IN",
    "returnPolicyCategory": f"{SCHEMA}/MerchantReturnFiniteReturnWindow",
    "merchantReturnDays": 7,
    "returnFees": f"{SCHEMA}/FreeReturn",
}
# As the Shipping Policy says: dispatch within 2 working days, delivery within 10 more.
DELIVERY_TIME = {
    "@type": "ShippingDeliveryTime",
    "handlingTime": {"@type": "QuantitativeValue", "minValue": 0, "maxValue": 2, "unitCode": "DAY"},
    "transitTime": {"@type": "QuantitativeValue", "minValue": 2, "maxValue": 10, "unitCode": "DAY"},
}


def product_jsonld(product, rating=None):
    """`rating`: (average, count) of the approved reviews, or None (no aggregateRating without real reviews)."""
    url = absolute(product.get_absolute_url())
    shipping = ShippingRate.fee_for("", product.price.amount)  # the rate of the states no other rate names
    data = {
        "@context": SCHEMA,
        "@type": ["Product", "Book"],
        "name": product.title,
        "url": url,
        "image": [absolute(product.cover.url if product.cover else static("img/og-default.jpg"))],
        "description": product.seo_description or product.title,
        "sku": product.slug,
        "brand": {"@type": "Brand", "name": "ExamLeaf"},
        "bookFormat": f"{SCHEMA}/Paperback",
        "inLanguage": "en",
        "offers": {
            "@type": "Offer",
            "url": url,
            "priceCurrency": "INR",
            "price": str(product.price.amount),
            "availability": f"{SCHEMA}/{'InStock' if product.available else 'OutOfStock'}",
            "itemCondition": f"{SCHEMA}/NewCondition",
            "seller": {"@type": "Organization", "name": settings.SHOP_SELLER["name"]},
            "shippingDetails": {
                "@type": "OfferShippingDetails",
                "shippingRate": {"@type": "MonetaryAmount", "value": str(shipping), "currency": "INR"},
                "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "IN"},
                "deliveryTime": DELIVERY_TIME,
            },
            "hasMerchantReturnPolicy": {**RETURN_POLICY, "merchantReturnLink": absolute(reverse("refunds"))},
        },
    }
    if product.isbn:
        data["isbn"] = product.isbn
        if len(digits := product.isbn.replace("-", "")) == 13:  # an ISBN-13 is a GTIN-13
            data["gtin13"] = digits
    if product.pages:
        data["numberOfPages"] = product.pages
    if rating:
        average, count = rating
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": f"{average:.1f}", "reviewCount": count}
    return data


def breadcrumbs(*crumbs):
    """(name, path) pairs, from the home page down."""
    items = [
        {"@type": "ListItem", "position": position, "name": name, "item": absolute(path)}
        for position, (name, path) in enumerate(crumbs, start=1)
    ]
    return {"@context": SCHEMA, "@type": "BreadcrumbList", "itemListElement": items}


def organization_jsonld():
    """The publisher, with the seller's contact details once SELLER_* holds real ones (not [placeholders])."""
    seller = settings.SHOP_SELLER
    data = {
        "@context": SCHEMA,
        "@type": "Organization",
        "name": "ExamLeaf",
        "legalName": seller["name"],
        "url": absolute("/"),
        "logo": absolute(static("img/icon-512.png")),
    }
    for key, name in [("email", "email"), ("phone", "telephone"), ("address", "address")]:
        if seller[key] and "[" not in seller[key]:
            data[name] = seller[key]
    return data
