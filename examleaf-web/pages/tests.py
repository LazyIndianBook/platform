import pytest
from django.urls import reverse

from accounts.factories import UserFactory
from pages.models import SLUGS, Page

pytestmark = pytest.mark.django_db


def test_every_legal_page_is_live_and_linked_from_the_footer(client):
    home = client.get(reverse("home")).text
    for slug in SLUGS:
        page = Page.objects.get(slug=slug)
        assert f'href="{reverse(slug)}"' in home
        assert page.title in client.get(reverse(slug)).text
    assert "ExamLeaf LLP" in Page.objects.get(slug="contact").body_md and "[GSTIN]" in client.get("/contact/").text
    assert "/refunds/" in client.get("/sitemap.xml").text


def test_staff_edit_a_page_in_the_admin_and_every_version_is_kept(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = Page.objects.get(slug="shipping")
    response = client.post(
        reverse("admin:pages_page_change", args=[page.pk]),
        {"title": page.title, "version": "2026-11-01", "body_md": "We deliver **across India**."},
    )
    assert response.status_code == 302
    assert "<strong>across India</strong>" in client.get("/shipping/").text
    assert page.history.count() == 3  # the draft, the shop's rules (migration 0003) and the edit (History button)
    assert client.get(reverse("admin:pages_page_add")).status_code == 403  # pages are fixed: edited, not added


def test_placeholders_are_marked_on_the_page_and_counted_in_the_pages_list_and_on_the_dashboard(client, settings):
    contact = Page.objects.get(slug="contact")
    assert contact.placeholders[:3] == ["[registered address]", "[GSTIN]", "[email]"]
    html = client.get("/contact/").text
    assert '<mark class="placeholder">[email]</mark>' in html and "[10 am to 6 pm]</mark>" in html
    assert 'href="/shipping/"' in html and "[Shipping Policy]" not in html  # a link's text is not a placeholder
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert "5 legal pages with [placeholders] to fill in" in client.get(reverse("admin:index")).text
    listing = client.get(reverse("admin:pages_page_changelist")).text
    assert "[placeholders] left" in listing and f">{len(contact.placeholders)}<" in listing
    contact.body_md = "Write to **orders@examleaf.in**. See the [Shipping Policy](/shipping/)."
    contact.save()
    settings.SHOP_SELLER = {**settings.SHOP_SELLER, "email": "orders@examleaf.in"}  # the form's address too
    assert "placeholder" not in client.get("/contact/").text
    assert "4 legal pages with [placeholders]" in client.get(reverse("admin:index")).text


def test_the_contact_form_emails_support_and_keeps_nothing(client, settings):
    from django.core import mail

    page = client.get("/contact/").text  # the seller's address is still a [placeholder]: no form to send nowhere
    assert 'name="message"' not in page and "[SUPPORT_EMAIL or SELLER_EMAIL]" in page
    settings.SUPPORT_EMAIL = "help@examleaf.in"
    assert 'name="message"' in client.get("/contact/").text
    page = client.post("/contact/", {"name": "", "email": "rahul@", "message": ""}).text
    assert "Tell us your name." in page and "Enter an email address." in page and "Write your message." in page
    client.post("/contact/", {"name": "Bot", "email": "bot@example.com", "message": "Buy", "website": "spam"})
    assert not mail.outbox  # the honeypot: thanked, nothing sent
    data = {"name": "Rahul Das", "email": "rahul@example.com", "message": "Order EL-2026-000123 has not come."}
    assert client.post("/contact/", data).url == "/contact/"
    [sent] = mail.outbox
    assert sent.to == ["help@examleaf.in"] and sent.extra_headers["Reply-To"] == "rahul@example.com"
    assert sent.subject == "[ExamLeaf] Contact form: Rahul Das" and data["message"] in sent.body
    for _ in range(3):
        client.post("/contact/", data)
    assert client.post("/contact/", data).status_code == 429  # five an hour from one address


def test_the_privacy_draft_names_what_the_code_keeps_and_for_how_long():
    from django.conf import settings

    from ops.sms import KEEP

    text = (settings.BASE_DIR / "pages" / "drafts" / "privacy.md").read_text()
    assert f"The record of each SMS: {KEEP.days} days." in text  # as ops.sms deletes them
    for kind in [
        "If you add a mobile number",
        "For each SMS we send",
        "If you review a book you bought",
        "email you when a book is back in stock",
        "school or bulk quotation",
        "If you use the revision course in the app",
        "If you allow the app's daily reminder",
        "we send a link to that address or number",
        "KaTeX, which this site serves itself",
    ]:
        assert kind in text, kind
