"""Phase 5 B: the two storages, responsive pictures, link-preview pictures, the static covers and the PIN code
table."""

import importlib
import io
import shutil

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from PIL import Image
from rest_framework.test import APIClient
from storages.backends.s3 import S3Storage

from accounts.factories import UserFactory
from content.management.commands.build_covers import COVERS, build_covers
from shop.factories import ADDRESS, ProductFactory, picture
from shop.forms import AddressForm
from shop.models import PinCode, public_storage
from shop.test_api import customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def reload_settings(monkeypatch):
    """The settings module run again with the environment a test sets (Django's own settings do not change)."""
    module = importlib.import_module("examleaf.settings")
    yield lambda: importlib.reload(module)
    monkeypatch.undo()
    importlib.reload(module)


def test_buckets_private_signed_for_five_minutes_public_on_the_media_domain(monkeypatch, reload_settings):
    for name, value in {
        "MEDIA_BUCKET": "examleaf-private",
        "PUBLIC_MEDIA_BUCKET": "examleaf-public",
        "PUBLIC_MEDIA_DOMAIN": "media.examleaf.in",
        "S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        "S3_ACCESS_KEY_ID": "key",
        "S3_SECRET_ACCESS_KEY": "secret",
    }.items():
        monkeypatch.setenv(name, value)
    settings = reload_settings()
    private, public = (settings.STORAGES[alias]["OPTIONS"] for alias in ("default", "public"))
    assert private["default_acl"] is None and private["file_overwrite"] is False
    assert "X-Amz-Expires=300" in S3Storage(**private).url("invoices/EL-2026-27-00001.pdf")
    assert S3Storage(**public).url("products/a.jpg") == "https://media.examleaf.in/products/a.jpg"
    assert public["object_parameters"]["CacheControl"] == "public, max-age=31536000, immutable"
    assert "https://media.examleaf.in" in settings.CONTENT_SECURITY_POLICY["img-src"]
    monkeypatch.setenv("PUBLIC_S3_ENDPOINT_URL", "https://r2.example")  # the private bucket in Mumbai, the public on R2
    monkeypatch.setenv("S3_REGION", "ap-south-1")
    monkeypatch.delenv("S3_ENDPOINT_URL")
    settings = reload_settings()
    private, public = (settings.STORAGES[alias]["OPTIONS"] for alias in ("default", "public"))
    assert (private["endpoint_url"], private["region_name"]) == (None, "ap-south-1")
    assert public["endpoint_url"] == "https://r2.example" and public["access_key"] == "key"


def test_without_buckets_only_the_public_folders_are_served(client, settings):
    public_storage().save("products/cover.png", ContentFile(b"png"))
    public_storage().save("invoices/EL-1.pdf", ContentFile(b"%PDF"))
    assert public_storage().url("products/cover.png") == "/shop/media/products/cover.png"
    response = client.get("/shop/media/products/cover.png")
    assert response.status_code == 200 and response["Cache-Control"] == "public, max-age=31536000, immutable"
    for name in ["invoices/EL-1.pdf", "products/../invoices/EL-1.pdf", "products/missing.png"]:
        assert client.get(f"/shop/media/{name}").status_code == 404


def test_a_new_cover_is_shown_in_avif_and_webp_sizes(client, commit):
    product = ProductFactory()
    with commit():  # the sizes are made by the Celery task queued after the commit
        upload = ContentFile(public_storage().open(picture(size=(800, 1200))).read(), name="cover.png")
        product.cover.save("cover.png", upload)
    assert (product.cover_width, product.cover_height) == (800, 1200)
    cover = client.get(f"/api/v1/products/{product.slug}/").json()["cover"]  # the website's <picture>
    assert set(cover["sources"]) == {"image/avif", "image/webp"}
    assert client.get("/shop/media/products/cover/2_3/400w.avif").status_code == 200


def test_static_covers_have_avif_and_webp_sizes(tmp_path, settings):
    """The website's book covers (examleaf-frontend, cover.tsx) are these static files: the API's Book.cover, its
    -320 and -480 AVIF and WebP sizes, and the default link-preview picture."""
    for name in COVERS:
        shutil.copy(settings.BASE_DIR / "static" / "img" / f"{name}.png", tmp_path)
    build_covers(tmp_path)
    with Image.open(tmp_path / "physics-320.avif") as image:
        assert image.size == (320, 452)
    sizes = ["physics-320.avif", "physics-320.webp", "physics-480.avif", "physics-480.webp"]
    assert sorted(path.name for path in tmp_path.glob("physics-*")) == sizes
    assert all(finders.find(f"img/{size}") for size in sizes) and finders.find("img/og-default.jpg")


def test_a_picture_saved_while_the_broker_is_down_gets_its_sizes_made_in_the_request(broker, closed_port, commit):
    """The product is saved, the member of staff sees no server error, and the sizes are there (the Celery processor
    of django-pictures would have raised once the transaction was committed)."""
    broker(f"redis://127.0.0.1:{closed_port}/0")
    product = ProductFactory()
    with commit():
        upload = ContentFile(public_storage().open(picture(size=(800, 1200))).read(), name="cover.png")
        product.cover.save("cover.png", upload)
    assert public_storage().exists(product.cover.name) and public_storage().exists("products/cover/2_3/400w.avif")


def test_the_product_admin_says_while_the_picture_sizes_are_being_made(client, commit):
    product = ProductFactory(cover=picture(size=(400, 600)))  # its sizes are queued for after the commit
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    url = f"/admin/shop/product/{product.pk}/change/"
    assert "smaller sizes are still being made" in client.get(url).text
    with commit():
        product.cover.save_all()  # the sizes queued, then made (eager Celery in the tests)
    assert "smaller sizes are still being made" not in client.get(url).text


def test_each_product_gets_its_own_link_preview_picture(client, commit):
    with commit():
        product = ProductFactory(cover=picture(size=(400, 600)))
    product.refresh_from_db()
    first = product.og_image.name
    with public_storage().open(first) as file, Image.open(file) as image:
        assert (image.format, image.size) == ("JPEG", (1200, 630))
    data = client.get(f"/api/v1/products/{product.slug}/").json()  # the website's og:image
    assert data["og_image"] == f"http://testserver/shop/media/{first}"
    with commit():
        product.title = "New title"
        product.save()
    product.refresh_from_db()
    assert product.og_image.name != first and not public_storage().exists(first)


SAMPLE_PINS = settings.BASE_DIR / "shop" / "fixtures" / "pincodes-sample.csv"  # 20 rows in data.gov.in's format


def test_pin_directory_import_lookup_and_state_check(client, tmp_path):
    out = io.StringIO()
    call_command("import_pincodes", str(SAMPLE_PINS), stdout=out)
    call_command("import_pincodes", str(SAMPLE_PINS), stdout=out)  # again: replaces, no duplicates
    assert PinCode.objects.count() == 18 and "18 PIN codes loaded." in out.getvalue()
    assert PinCode.objects.get(pin="781001").districts == ["Kamrup Metro"]
    assert PinCode.objects.get(pin="396230").states == ["DH", "GJ"]  # a PIN across a border
    assert [PinCode.objects.get(pin=p).states for p in ["492001", "190001", "605001"]] == [["CT"], ["JK"], ["PY"]]
    bad = tmp_path / "bad.csv"
    bad.write_text("pincode,district,statename\n781001,Kamrup,ATLANTIS\n")
    with pytest.raises(CommandError, match="ATLANTIS"):
        call_command("import_pincodes", str(bad))

    quote = client.get("/api/v1/shipping/quote/?pin=781001").json()  # the checkout fills in the address with it
    assert (quote["states"], quote["districts"], quote["state"]) == (["AS"], ["Kamrup Metro"], "AS")
    assert client.get("/api/v1/shipping/quote/?pin=999999").json()["states"] == []
    address = {**ADDRESS, "phone": "98640 12345", "pin": "781 001"}
    form = AddressForm({**address, "state": "WB"})  # the admin's (a staff order's address)
    assert not form.is_valid() and form.errors["state"] == ["PIN code 781001 is in Assam."]
    assert AddressForm({**address, "state": "AS"}).is_valid()
    assert AddressForm({**address, "pin": "123456", "state": "WB"}).is_valid()  # not in the directory: not checked
    api = APIClient()
    customer(api)
    answer = api.post("/api/v1/addresses/", {**address, "pin": "781001", "state": "WB"})
    assert answer.status_code == 400 and answer.json()["state"] == ["PIN code 781001 is in Assam."]
