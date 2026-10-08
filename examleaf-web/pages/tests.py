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


def test_placeholders_are_marked_on_the_page_and_counted_in_the_pages_list_and_on_the_dashboard(client):
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
    assert "placeholder" not in client.get("/contact/").text
    assert "4 legal pages with [placeholders]" in client.get(reverse("admin:index")).text
