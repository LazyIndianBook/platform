"""The craft pass (docs/design/motion.md, components.md): every page loads under 60 KB of CSS, has one H1 inside <main>
and the polite live region, renders a long Assamese name and a long title, draws its empty states, and describes a
field's error to screen readers even when the field has no help text."""

from pathlib import Path

import pytest
from django import forms
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.factories import UserFactory
from content.tests import make_paper
from practice.models import Attempt
from shop.factories import ProductFactory

pytestmark = pytest.mark.django_db

CSS = Path(settings.BASE_DIR) / "static" / "css"
NAME = "অনুৰাধা বৰদলৈ শইকীয়া ফুকন (Anuradha Bordoloi Saikia Phukan)"
TITLE = "ExamLeaf Physics Sample Papers and Solutions, the complete set for the Assam Board Higher Secondary 2027"


def test_every_page_loads_less_than_60_kb_of_css():
    site = (CSS / "site.css").stat().st_size
    assert site < 60_000
    for area in ("home.css", "shop.css", "account.css"):  # rules only those pages use, loaded after site.css
        assert site + (CSS / area).stat().st_size < 60_000


def h1_inside_main(page):
    main = page[page.index('<main id="main" tabindex="-1"') : page.index("</main>")]
    return page.count("<h1") == 1 and "<h1" in main and '<p id="announce" class="sr-only" role="status"></p>' in main


def test_pages_have_one_h1_in_main_the_live_region_and_long_text(client):
    paper = make_paper()
    product = ProductFactory(title=TITLE, subject=paper.book.subject)
    book, shop, login = paper.book.get_absolute_url(), reverse("shop:catalogue"), reverse("account_login")
    for url in ("/", shop, product.get_absolute_url(), book, login, "/no-such-page/"):
        assert h1_inside_main(client.get(url).text), url
    client.force_login(UserFactory(full_name=NAME))
    for url in (paper.get_absolute_url(), "/account/", reverse("record"), reverse("shop:cart"), "/account/orders/"):
        assert h1_inside_main(client.get(url).text), url
    assert NAME in client.get(reverse("account")).text
    page = client.get(product.get_absolute_url()).text
    assert f"<h1>{TITLE}</h1>" in page and f'style="view-transition-name: cover-{product.pk}"' in page
    assert "css/shop.css" in page and "css/account.css" not in page


def test_empty_states_draw_their_picture_and_say_what_to_do(client):
    assert 'class="empty-art"' in client.get(reverse("shop:cart")).text
    user = UserFactory()
    client.force_login(user)
    assert 'class="empty-art"' in client.get(reverse("shop:orders")).text
    assert "Nothing recorded yet" in client.get(reverse("record") + "?tier=H").text  # nothing saved at all
    paper = make_paper()
    Attempt.objects.create(user=user, paper=paper, marks_obtained=40)  # an Easy paper
    page = client.get(reverse("record"), {"subject": paper.book.subject_id, "tier": "H"}).text  # finds nothing
    assert "No Hard Physics papers saved yet" in page and "The filter shows Hard Physics papers only" in page
    assert f'<a class="btn btn-primary" href="{reverse("record")}">Show all</a>' in page


def test_a_field_error_is_described_even_without_help_text():
    class Form(forms.Form):
        code = forms.CharField()

    form = Form(data={})
    assert not form.is_valid()
    html = render_to_string("_field.html", {"field": form["code"]})
    assert 'aria-describedby="id_code_error"' in html and 'id="id_code_error"' in html and 'aria-invalid="true"' in html


def test_fonts_preload_messages_never_cover_a_control_and_forms_say_they_are_busy(client):
    page = client.get("/").text
    for font in ("poppins-700", "poppins-800", "hind-siliguri-400", "hind-siliguri-600"):  # audit-lighthouse.md P1
        assert f'<link rel="preload" href="/static/fonts/{font}.woff2" as="font"' in page
    assert "@media (max-width:600px){.toast{--rise:-8px;position:static" in (CSS / "site.css").read_text()
    script = (Path(settings.BASE_DIR) / "static" / "js" / "site.js").read_text()
    assert 'button.setAttribute("aria-busy", "true")' in script  # every form sent shows its button busy, once
    assert "is not in our list: type the district and state" in script  # a PIN code the directory lacks
    client.force_login(UserFactory())
    form = client.get("/account/addresses/add/").text  # the help site.js writes the PIN's answer into
    assert '<div class="field-help" id="id_pin_helptext">6 digits, such as 781001.</div>' in form
    assert "data-pin-lookup" in form
