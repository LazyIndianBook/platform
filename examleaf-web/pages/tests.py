import pytest
from django.core.cache import cache
from django.urls import reverse

from accounts.factories import UserFactory
from pages.models import SLUGS, Page

pytestmark = pytest.mark.django_db


def html(client, slug):
    """What the website's page /<slug>/ shows: the API's HTML of the page."""
    return client.get(f"/api/v1/pages/{slug}/").json()["html"]


def test_every_legal_page_is_live(client):
    for slug in SLUGS:
        data = client.get(f"/api/v1/pages/{slug}/").json()
        assert data["title"] == Page.objects.get(slug=slug).title and data["web_url"] == f"http://testserver/{slug}/"
    assert "ExamLeaf LLP" in Page.objects.get(slug="contact").body_md and "[GSTIN]" in html(client, "contact")


def test_staff_edit_a_page_in_the_admin_and_every_version_is_kept(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = Page.objects.get(slug="shipping")
    response = client.post(
        reverse("admin:pages_page_change", args=[page.pk]),
        {"title": page.title, "version": "2026-11-01", "body_md": "We deliver **across India**."},
    )
    assert response.status_code == 302
    assert "<strong>across India</strong>" in html(client, "shipping")
    assert page.history.count() == 3  # the draft, the shop's rules (migration 0003) and the edit (History button)
    assert client.get(reverse("admin:pages_page_add")).status_code == 403  # pages are fixed: edited, not added


def test_placeholders_are_marked_on_the_page_and_counted_in_the_pages_list_and_on_the_dashboard(client, settings):
    contact = Page.objects.get(slug="contact")
    assert contact.placeholders[:3] == ["[registered address]", "[GSTIN]", "[email]"]
    page = html(client, "contact")
    assert '<mark class="placeholder">[email]</mark>' in page and "[10 am to 6 pm]</mark>" in page
    assert 'href="/shipping/"' in page and "[Shipping Policy]" not in page  # a link's text is not a placeholder
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert "5 legal pages with [placeholders] to fill in" in client.get(reverse("admin:index")).text
    listing = client.get(reverse("admin:pages_page_changelist")).text
    assert "[placeholders] left" in listing and f">{len(contact.placeholders)}<" in listing
    contact.body_md = "Write to **orders@examleaf.in**. See the [Shipping Policy](/shipping/)."
    contact.save()
    settings.SHOP_SELLER = {**settings.SHOP_SELLER, "email": "orders@examleaf.in"}  # the form's address too
    cache.clear()  # the API keeps a page 15 minutes
    assert "placeholder" not in html(client, "contact")
    assert "4 legal pages with [placeholders]" in client.get(reverse("admin:index")).text


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
        "Only when you press Pay, Razorpay's payment window is loaded",  # frontend review S3: what its script keeps
    ]:
        assert kind in text, kind
