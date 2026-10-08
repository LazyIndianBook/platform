"""Redesign stage 2a: the home page's prices and delivery fees come from the shop, the footer's and the 404 page's
books from the database; covers take attributes; the code pages have the box the six digits fill; every email gets an
HTML part made from its text, and keeps its own if it has one."""

from decimal import Decimal

import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template import Context, Template
from django.urls import reverse

from content.tests import make_paper
from ops import tasks
from shop.factories import ProductFactory, ShippingRateFactory
from shop.models import Product

pytestmark = pytest.mark.django_db


def test_the_home_page_prices_and_delivery_fees_come_from_the_shop(client):
    make_paper()
    ProductFactory(), ProductFactory(price=Decimal("329.00"))  # two Sample Papers books: "from" the cheaper one
    ProductFactory(kind=Product.Kind.BUNDLE, price=Decimal("499.00"), mrp=Decimal("548.00"))
    ProductFactory(kind=Product.Kind.SOLUTIONS, is_active=False)
    ShippingRateFactory()
    page = client.get(reverse("home")).text
    assert '<span class="price-from">from</span><span class="price-now">₹299</span>' in page
    assert '<s class="price-mrp"><span class="sr-only">MRP </span>₹548</s>' in page and "Save ₹49 (9%)" in page
    assert '<span class="badge badge-muted">Solutions</span>' not in page  # not on sale
    assert "Assam ₹40, free on books worth ₹499 or more." in page
    assert "Official solutions" in page and "Scan<br>verified" not in page  # nothing checks a scan


def test_the_footer_and_the_404_page_list_the_books_of_the_database(client):
    book = make_paper().book
    assert f'<a href="{book.get_absolute_url()}">Physics</a>' in client.get(reverse("about")).text
    page = client.get("/no-such-page/").text
    assert f'class="tile tile-physics" href="{book.get_absolute_url()}"' in page and "chemistry-2027" not in page


def test_covers_take_attributes_and_display_prices_drop_zero_paise():
    cover = '{% static_cover "img/physics.png" "Cover" fetchpriority="high" %}'
    html = Template("{% load web %}" + cover + " {{ a|inr_short }} {{ b|inr_short }}").render(
        Context({"a": Decimal("299"), "b": Decimal("718.2")})
    )
    assert 'height="678" fetchpriority="high"></picture> ₹299 ₹718.20' in html


def test_the_code_page_has_the_one_box_the_six_digits_fill(client):
    client.post(reverse("account_request_login_code"), {"email": "nobody@example.com"})
    page = client.get(reverse("account_confirm_login_code")).text
    assert 'name="code"' in page and "data-otp" in page and 'autocomplete="one-time-code"' in page
    assert "js/account.js" in page and ">Log in</button>" in page


def test_allauth_forms_without_fields_keep_their_buttons(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"APPS": [{"client_id": "id", "secret": "s"}]}}
    page = client.get(reverse("google_login")).text  # Google's "Continue" page: a form with only a button
    assert '<form class="form-col" method="post">' in page and ">Continue</button>" in page


def test_every_email_gets_an_html_part_made_from_its_text(mailoutbox):
    text = "Hello <b>!\n\n483920\n\nhttps://examleaf.in/c/x.y/"
    tasks.queue_email(EmailMessage("[ExamLeaf] Your code", text, to=["a@example.com"]))
    message = mailoutbox[-1]
    html, mimetype = message.alternatives[0]
    assert message.body == text and mimetype == "text/html"
    assert ">Your code</h1>" in html and "Hello &lt;b&gt;!" in html and "<b>" not in html
    assert 'color: #0B2A5B">483920</p>' in html and '<a href="https://examleaf.in/c/x.y/"' in html
    own = EmailMultiAlternatives("Hi", "text", to=["a@example.com"])
    own.attach_alternative("<p>mine</p>", "text/html")
    tasks.queue_email(own)
    assert mailoutbox[-1].alternatives == [("<p>mine</p>", "text/html")]
