"""Phase 5 B: the two storages, responsive pictures, SEO tags, the PWA files and the PIN code table."""

import importlib
import io
import json
import math
import re
import shutil

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.template import Context, Template
from PIL import Image
from rest_framework.test import APIClient
from storages.backends.s3 import S3Storage

from accounts.factories import UserFactory
from content.management.commands.build_covers import COVERS, build_covers
from examleaf.images import app_icon
from shop.factories import ADDRESS, ProductFactory, picture
from shop.forms import AddressBookForm
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
    assert client.get("/shop/media/products/cover.png").status_code == 200
    for name in ["invoices/EL-1.pdf", "products/../invoices/EL-1.pdf", "products/missing.png"]:
        assert client.get(f"/shop/media/{name}").status_code == 404


def test_a_new_cover_is_shown_in_avif_and_webp_sizes(client, commit):
    product = ProductFactory()
    with commit():  # the sizes are made by the Celery task queued after the commit
        upload = ContentFile(public_storage().open(picture(size=(800, 1200))).read(), name="cover.png")
        product.cover.save("cover.png", upload)
    assert (product.cover_width, product.cover_height) == (800, 1200)
    page = client.get(product.get_absolute_url()).content.decode()
    assert '<source type="image/avif"' in page and '<source type="image/webp"' in page
    assert client.get("/shop/media/products/cover/2_3/400w.avif").status_code == 200


def test_static_covers_have_avif_and_webp_sizes(tmp_path, settings):
    for name in COVERS:
        shutil.copy(settings.BASE_DIR / "static" / "img" / f"{name}.png", tmp_path)
    build_covers(tmp_path)
    with Image.open(tmp_path / "physics-320.avif") as image:
        assert image.size == (320, 452)
    assert len(list(tmp_path.glob("*-[34][28]0.*"))) == 16
    html = Template('{% load web %}{% static_cover "img/physics.png" "Cover" %}').render(Context())
    srcset = "/static/img/physics-320.avif 320w, /static/img/physics-480.avif 480w"
    assert f'<source type="image/avif" srcset="{srcset}"' in html
    assert '<img src="/static/img/physics.png" alt="Cover"' in html
    assert "<source" not in Template('{% load web %}{% static_cover "img/favicon-32.png" %}').render(Context())


def ld_blocks(page):
    return [json.loads(block) for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page)]


def test_product_page_has_canonical_open_graph_and_product_json_ld(client):
    product = ProductFactory(title="Physics </script><b>", isbn="978-81-123456-7-8", pages=180, slug="physics")
    page = client.get(product.get_absolute_url()).content.decode()
    assert '<link rel="canonical" href="http://localhost:8000/shop/physics/">' in page
    assert '<meta property="og:type" content="product">' in page
    assert '<meta property="og:image" content="http://localhost:8000/static/img/og-default.jpg">' in page
    assert "</script><b>" not in page and "\\u003c/script\\u003e\\u003cb\\u003e" in page
    item, crumbs = ld_blocks(page)
    assert item["@type"] == ["Product", "Book"] and item["gtin13"] == "9788112345678" and item["numberOfPages"] == 180
    offer = item["offers"]
    assert (offer["price"], offer["priceCurrency"], offer["availability"]) == (
        "299.00",
        "INR",
        "https://schema.org/InStock",
    )
    assert offer["hasMerchantReturnPolicy"]["merchantReturnLink"] == "http://localhost:8000/refunds/"
    assert "aggregateRating" not in item  # no approved reviews
    assert [c["name"] for c in crumbs["itemListElement"]] == ["Home", "Shop", "Physics </script><b>"]


def test_each_product_gets_its_own_link_preview_picture(client, commit):
    with commit():
        product = ProductFactory(cover=picture(size=(400, 600)))
    product.refresh_from_db()
    first = product.og_image.name
    with public_storage().open(first) as file, Image.open(file) as image:
        assert (image.format, image.size) == ("JPEG", (1200, 630))
    page = client.get(product.get_absolute_url()).content.decode()
    assert f'<meta property="og:image" content="http://localhost:8000/shop/media/{first}">' in page
    with commit():
        product.title = "New title"
        product.save()
    product.refresh_from_db()
    assert product.og_image.name != first and not public_storage().exists(first)


def test_home_page_names_the_publisher(client, real_seller):
    organization = ld_blocks(client.get("/").content.decode())[0]
    assert organization["@type"] == "Organization" and organization["legalName"] == "ExamLeaf LLP"
    assert organization["email"] == "orders@examleaf.in" and organization["logo"].endswith("/static/img/icon-512.png")


def test_web_app_manifest_icons_and_offline_page(client):
    response = client.get("/manifest.webmanifest")
    data = response.json()
    assert response["Content-Type"] == "application/manifest+json"
    assert (data["start_url"], data["display"], data["scope"]) == ("/?source=pwa", "standalone", "/")
    assert [(i["sizes"], i["purpose"]) for i in data["icons"]] == [
        ("192x192", "any"),
        ("512x512", "any"),
        ("512x512", "maskable"),
    ]
    with Image.open(io.BytesIO(app_icon(192))) as icon:  # maskable: only the navy background outside the safe circle
        ring = {
            icon.getpixel((round(96 + 82 * math.cos(a / 10)), round(96 + 82 * math.sin(a / 10)))) for a in range(63)
        }
        assert ring == {(11, 42, 91)} and icon.getpixel((96, 70)) == (76, 194, 101)
    client.force_login(UserFactory())
    offline = client.get("/offline/").content.decode()
    assert "You are offline" in offline and "csrfmiddlewaretoken" not in offline and "Log out" not in offline
    page = client.get("/")
    assert '<link rel="manifest" href="/manifest.webmanifest">' in page.content.decode()
    policy = page.headers.get("Content-Security-Policy") or page.headers["Content-Security-Policy-Report-Only"]
    assert "manifest-src 'self'" in policy and "worker-src 'self'" in policy


def test_service_worker_keeps_static_files_and_the_offline_page_never_pages(client):
    response = client.get("/sw.js")
    worker = response.content.decode()
    assert response["Content-Type"].startswith("text/javascript") and response["Cache-Control"] == "no-cache"
    precache = json.loads(re.search(r"const PRECACHE = (.*);", worker).group(1))
    assert precache[0] == "/offline/" and all(p.startswith("/static/") for p in precache[1:])
    assert re.search(r'const CACHE = "examleaf-[0-9a-f]{12}";', worker)
    assert 'if (request.mode === "navigate")' in worker and "/account/" not in worker


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

    assert client.get("/shop/pin/781001/").json() == {"pin": "781001", "states": ["AS"], "districts": ["Kamrup Metro"]}
    assert client.get("/shop/pin/999999/").status_code == 404
    address = {**ADDRESS, "phone": "98640 12345", "pin": "781 001"}
    form = AddressBookForm({**address, "state": "WB"})
    assert not form.is_valid() and form.errors["state"] == ["PIN code 781001 is in Assam."]
    assert AddressBookForm({**address, "state": "AS"}).is_valid()
    assert AddressBookForm({**address, "pin": "123456", "state": "WB"}).is_valid()  # not in the directory: not checked
    api = APIClient()
    customer(api)
    answer = api.post("/api/v1/addresses/", {**address, "pin": "781001", "state": "WB"})
    assert answer.status_code == 400 and answer.json()["state"] == ["PIN code 781001 is in Assam."]
