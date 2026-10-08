"""Route probe for the UX audit. Run with the project's venv against a COPY of the dev database:

  UXA=<this folder> DATABASE_URL=sqlite:///<copy> .venv/bin/python manage.py shell -c "exec(open('probe.py').read())"

It makes a few test people and orders in the copy, then asks every route as each kind of visitor with Django's test
client (no network, no server) and writes probe-results.json: status, redirect, templates, classes in the HTML."""

import datetime
import json
import os
import re
import shutil
import traceback
from unittest.mock import MagicMock

from django.conf import settings
from django.contrib.auth.models import Group
from django.test import Client, override_settings
from django.test.utils import setup_test_environment
from django.utils import timezone

setup_test_environment()  # response.templates, in-memory mail
UXA = os.environ["UXA"]
MEDIA = f"{UXA}/probe-media"
os.makedirs(MEDIA, exist_ok=True)
shutil.copytree(
    "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12/examleaf-web/media/products", f"{MEDIA}/products", dirs_exist_ok=True
)
CSS = json.load(open(f"{UXA}/css-classes.json"))
NEW_CSS = set(CSS["new"])
VOCAB = set(
    """btn btn-primary btn-secondary btn-ghost btn-destructive btn-accent btn-sm btn-lg btn-block field field-help
field-error input select textarea checkbox radio switch otp card card-header card-body card-footer card-interactive badge
badge-easy badge-medium badge-hard badge-gold badge-muted alert alert-info alert-success alert-warning alert-error toast
dialog tabs accordion skeleton table-wrap table breadcrumb pagination stepper step step-done step-current tile
tile-physics tile-chemistry tile-maths tile-biology band band-night stage stage-cover marker price price-now price-mrp
price-save empty timeline timeline-item qr-card nav nav-toggle nav-menu footer""".split()
)
LEGACY = set(CSS["legacy"])

CONTEXT = override_settings(
    MEDIA_ROOT=MEDIA,
    DEBUG=False,
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test-key-secret",
    RAZORPAY_WEBHOOK_SECRET_TEST="probe-webhook",
    ALLOWED_HOSTS=["testserver", "localhost"],
)
CONTEXT.enable()

from allauth.account.models import EmailAddress  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from accounts.factories import UserFactory  # noqa: E402
from accounts.models import ConsentRecord, User  # noqa: E402
from content.models import Paper  # noqa: E402
from learn.models import Chapter, Clip, Revision  # noqa: E402
from practice.models import Attempt  # noqa: E402
from shop import payments, services  # noqa: E402
from shop.factories import make_order  # noqa: E402
from shop.models import Address, Cart, Category, Collection, Order, Product  # noqa: E402


def new_order(*lines, **kw):
    Cart.objects.filter(user=kw.get('user')).delete()  # one cart per account; a new order starts from none
    return make_order(*lines, **kw)


NOW = timezone.now()


def person(email, group=None, staff=False, superuser=False, **kw):
    user = User.objects.filter(email=email).first()
    if user:
        return user
    user = UserFactory(email=email, is_staff=staff or superuser, is_superuser=superuser, **kw)
    EmailAddress.objects.get_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
    if group:
        user.groups.add(Group.objects.get(name=group))
    return user


student = person("probe-student@example.com", full_name="Probe Student", class_level=12, consent_at=NOW)
ConsentRecord.objects.get_or_create(user=student, defaults={"notice_version": "1"})
minor = person(
    "probe-minor@example.com",
    full_name="Probe Minor",
    class_level=12,
    date_of_birth=datetime.date(2012, 1, 1),
    parent_name="Parent",
    parent_contact="parent@example.com",
)
admin_user = person("probe-admin@example.com", superuser=True)
editor = person("probe-editor@example.com", group="CONTENT_EDITOR", staff=True)
sales = person("probe-sales@example.com", group="SALES", staff=True)
support = person("probe-support@example.com", group="SUPPORT", staff=True)
mfa_student = person("probe-mfa@example.com", full_name="Probe Mfa", class_level=12, consent_at=NOW)
nopass = person("probe-nopass@example.com", full_name="Probe Google", class_level=12, consent_at=NOW)
nopass.set_unusable_password()
nopass.save()
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes  # noqa: E402
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret  # noqa: E402
from allauth.mfa.models import Authenticator  # noqa: E402

if not Authenticator.objects.filter(user=mfa_student).exists():
    TOTP.activate(mfa_student, generate_totp_secret())
    RecoveryCodes.activate(mfa_student)
PERSONAS = {"student": student, "minor": minor, "admin": admin_user, "editor": editor, "sales": sales, "support": support, "mfa": mfa_student, "nopass": nopass, "reauth": student}

# shop data
rzp = MagicMock()
rzp.order.create.side_effect = lambda data, **kw: {"id": f"order_{data['receipt']}", **data}
payments.client = lambda: rzp
sample = Product.objects.get(slug="physics-sample-papers-2027")
_cod = override_settings(SHOP_COD_ENABLED=True)  # off in development: on only to make the fixtures
_cod.enable()
if not Order.objects.filter(user=student).exists():
    o_pending = new_order((sample, 1), method="razorpay", user=student, email=student.email)
    o_cod = new_order((sample, 1), method="cod", user=student, email=student.email)
    services.place_cod(o_cod)
    o_paid = new_order((sample, 2), method="razorpay", user=student, email=student.email)
    Order.objects.filter(pk=o_paid.pk).update(status="paid", placed_at=NOW)
    o_delivered = new_order((sample, 1), method="razorpay", user=student, email=student.email)
    Order.objects.filter(pk=o_delivered.pk).update(status="delivered", placed_at=NOW)
    o_cancelled = new_order((sample, 1), method="razorpay", user=student, email=student.email)
    Order.objects.filter(pk=o_cancelled.pk).update(status="cancelled")
_cod.disable()
Address.objects.get_or_create(
    user=student, pin="781001", defaults=dict(name="Probe Student", phone="+919864012345", line1="House 4", city="Guwahati", district="Kamrup Metro", state="AS", is_default=True)
)
paper = Paper.objects.get(code="PHY-E01")
Attempt.objects.get_or_create(user=student, paper=paper, defaults={"marks_obtained": 50, "notes": "Revise optics"})
category = Category.objects.filter(slug="class-12-books").first() or Category.add_root(name="Class 12 books", slug="class-12-books")
category.__class__  # noqa
sample.categories.add(category)
collection, _ = Collection.objects.get_or_create(slug="exam-week", defaults={"name": "Exam week", "is_active": True})
chapter = Chapter.objects.first()
revision, _ = Revision.objects.get_or_create(chapter=chapter, defaults={"title": "Probe revision", "status": "published"})
clip, _ = Clip.objects.get_or_create(revision=revision, title="Probe clip")
orders = {o.status + ("-cod" if o.payment_method == "cod" else ""): o for o in Order.objects.filter(user=student)}
guest_order = Order.objects.filter(user__isnull=True).first()
pending_online = Order.objects.filter(user=student, status="pending", payment_method="razorpay").first()
placed_cod = Order.objects.filter(user=student, payment_method="cod").first()
paid_order = Order.objects.filter(user=student, status="paid").first()
delivered_order = Order.objects.filter(user=student, status="delivered").first()
cancelled_order = Order.objects.filter(user=student, status="cancelled").first()
attempt = student.attempts.first()
address = student.addresses.first()
print("fixtures ok:", {k: v.number for k, v in orders.items()}, "guest", guest_order.number if guest_order else None)

RESULTS = []


def html_info(content, ctype):
    if "html" not in ctype:
        return {}
    text = content.decode("utf-8", "ignore")
    body = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S)
    tokens = set()
    for m in re.finditer(r'class="([^"]*)"', body):
        tokens.update(t for t in re.sub(r"\{\{.*?\}\}", " ", m.group(1)).split() if t)
    title = re.search(r"<title>(.*?)</title>", text, flags=re.S)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.S)
    strip = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()
    return {
        "title": strip(title.group(1)) if title else "",
        "h1": strip(h1.group(1)) if h1 else "",
        "vocab": sorted(tokens & VOCAB),
        "legacy": sorted(tokens & LEGACY),
        "other": sorted(t for t in tokens if t not in VOCAB and t not in NEW_CSS and t not in LEGACY),
        "forms": len(re.findall(r"<form\b", body)),
        "self_contained": "site.css" not in text,
        "toast": "class=\"toast\"" in text,
    }


def clients():
    out = {"anon": Client(raise_request_exception=False)}
    for name, user in PERSONAS.items():
        c = Client(raise_request_exception=False)
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        out[name] = c
    return out


CLIENTS = clients()
import time  # noqa: E402

for _name in ("reauth", "mfa", "nopass"):  # signed in a moment ago, as after a log-in or the password again
    _session = CLIENTS[_name].session
    _session["account_authentication_methods"] = [{"at": time.time(), "method": "password", "email": PERSONAS[_name].email}]
    _session.save()


def grant(client, *numbers):
    session = client.session
    session["shop_orders"] = list(numbers)
    session.save()


def probe(persona, method, path, key=None, data=None, note=""):
    client = CLIENTS[persona]
    try:
        if method == "GET":
            response = client.get(path, follow=False)
        else:
            response = client.post(path, data or {}, follow=False)
    except Exception as exc:  # the test client re-raises nothing, but a middleware might
        RESULTS.append({"persona": persona, "method": method, "path": path, "key": key or path, "status": "EXC", "error": repr(exc)[:200]})
        return None
    ctype = response.headers.get("Content-Type", "")
    templates = []
    for t in getattr(response, "templates", []) or []:
        if t.name and t.name not in templates:
            templates.append(t.name)
    row = {
        "persona": persona,
        "method": method,
        "path": path,
        "key": key or path,
        "status": response.status_code,
        "location": response.headers.get("Location", ""),
        "ctype": ctype.split(";")[0],
        "bytes": len(response.content) if not response.streaming else -1,
        "templates": templates,
        "note": note,
        **html_info(response.content if not response.streaming else b"", ctype),
    }
    RESULTS.append(row)
    return response


# ---- the website ------------------------------------------------------------------------------------------------
tok = guest_order.token
guest_n = guest_order.number
PUBLIC = [
    ("home", "/"), ("book", "/books/physics-2027/"), ("book 404", "/books/nope/"),
    ("paper", "/s/PHY-E01/"), ("paper lowercase", "/s/phy-e01/"), ("paper 404", "/s/NOPE-01/"),
    ("qr", "/qr/PHY-E01.png"), ("about", "/about/"), ("contact", "/contact/"), ("privacy", "/privacy/"),
    ("terms", "/terms/"), ("refunds", "/refunds/"), ("shipping", "/shipping/"), ("offline", "/offline/"),
    ("robots", "/robots.txt"), ("manifest", "/manifest.webmanifest"), ("sw", "/sw.js"), ("sitemap", "/sitemap.xml"),
    ("favicon", "/favicon.ico"), ("health", "/health/"), ("health web", "/health/web/"),
    ("catalogue", "/shop/"), ("catalogue kind", "/shop/?kind=bundle"), ("category", "/shop/category/class-12-books/"),
    ("category 404", "/shop/category/nope/"), ("collection", "/shop/collection/exam-week/"),
    ("product", "/shop/physics-sample-papers-2027/"), ("product out of stock", "/shop/physics-bundle-2027/"),
    ("product 404", "/shop/nope/"), ("quote", "/shop/school-orders/"), ("pin", "/shop/pin/781001/"),
    ("media", "/shop/media/products/physics.png"), ("media private", "/shop/media/invoices/x.pdf"),
    ("review GET", "/shop/physics-sample-papers-2027/review/"), ("stock alert GET", "/shop/physics-sample-papers-2027/stock-alert/"),
    ("cart", "/cart/"), ("cart add GET", f"/cart/add/{sample.pk}/"), ("checkout", "/checkout/"),
    ("lookup", "/orders/lookup/"), ("order by link", f"/orders/t/{tok}/"), ("order by link bad", "/orders/t/nope/"),
    ("order link cancel GET", f"/orders/t/{tok}/cancel/"), ("order link invoice", f"/orders/t/{tok}/invoice/"),
    ("order link credit note", f"/orders/t/{tok}/credit-notes/1/"),
    ("parent consent bad", "/c/bad.token/"), ("razorpay webhook GET", "/shop/webhooks/razorpay/"),
    ("learn hls bad", "/learn/hls/bad/master.m3u8"), ("learn preview anon", f"/learn/preview/{clip.pk}/"),
    ("account", "/account/"), ("record", "/account/record/"), ("record add", "/account/record/add/PHY-E01/"),
    ("record edit", f"/account/record/{attempt.pk}/edit/"), ("teacher", "/account/teacher/"), ("data export", "/account/data/"),
    ("delete", "/account/delete/"), ("delete cancel GET", "/account/delete/cancel/"), ("parent consent resend GET", "/account/parent-consent/"),
    ("sms updates GET", "/account/sms-updates/"), ("orders", "/account/orders/"),
    ("order mine", f"/account/orders/{pending_online.number}/"), ("order cancel GET", f"/account/orders/{pending_online.number}/cancel/"),
    ("invoice", f"/account/orders/{placed_cod.number}/invoice/"), ("credit note", f"/account/orders/{placed_cod.number}/credit-notes/1/"),
    ("address add", "/account/addresses/add/"), ("address edit", f"/account/addresses/{address.pk}/"),
    ("address delete GET", f"/account/addresses/{address.pk}/delete/"),
    ("pay", f"/checkout/{pending_online.number}/pay/"), ("pay verify GET", f"/checkout/{pending_online.number}/paid/"),
    ("done", f"/checkout/{placed_cod.number}/done/"),
    ("register redirect", "/account/register/"), ("login", "/account/login/"), ("login next", "/account/login/?next=/s/PHY-E01/"),
    ("logout page", "/account/logout/"), ("inactive", "/account/inactive/"), ("signup", "/account/signup/"),
    ("reauthenticate", "/account/reauthenticate/"), ("email", "/account/email/"), ("verification sent", "/account/confirm-email/"),
    ("password change", "/account/password/change/"), ("password set", "/account/password/set/"),
    ("password reset", "/account/password/reset/"), ("password reset done", "/account/password/reset/done/"),
    ("password reset from key", "/account/password/reset/key/abc-123/"), ("password reset key done", "/account/password/reset/key/done/"),
    ("login code confirm", "/account/login/code/confirm/"), ("login code request", "/account/login/code/"),
    ("phone verify", "/account/phone/verify/"), ("phone change", "/account/phone/change/"),
    ("2fa index", "/account/2fa/"), ("2fa authenticate", "/account/2fa/authenticate/"), ("2fa reauthenticate", "/account/2fa/reauthenticate/"),
    ("totp activate", "/account/2fa/totp/activate/"), ("totp deactivate", "/account/2fa/totp/deactivate/"),
    ("recovery codes", "/account/2fa/recovery-codes/"), ("recovery generate", "/account/2fa/recovery-codes/generate/"),
    ("recovery download", "/account/2fa/recovery-codes/download/"), ("webauthn list", "/account/2fa/webauthn/"),
    ("webauthn add", "/account/2fa/webauthn/add/"), ("webauthn reauth", "/account/2fa/webauthn/reauthenticate/"),
    ("webauthn remove", "/account/2fa/webauthn/keys/1/remove/"), ("webauthn edit", "/account/2fa/webauthn/keys/1/edit/"),
    ("webauthn login", "/account/2fa/webauthn/login/"), ("3rdparty cancelled", "/account/3rdparty/login/cancelled/"),
    ("3rdparty error", "/account/3rdparty/login/error/"), ("3rdparty signup", "/account/3rdparty/signup/"),
    ("3rdparty connections", "/account/3rdparty/"), ("social cancelled redirect", "/account/social/login/cancelled/"),
    ("social error redirect", "/account/social/login/error/"), ("social signup redirect", "/account/social/signup/"),
    ("social connections redirect", "/account/social/connections/"), ("google login", "/account/google/login/"),
    ("google callback", "/account/google/login/callback/"), ("google token", "/account/google/login/token/"),
    ("admin login redirect", "/admin/login/"), ("404 generic", "/this-page-does-not-exist/"),
]
for persona in ("anon", "student"):
    if persona == "student":
        grant(CLIENTS["student"], *[o.number for o in Order.objects.filter(user=student)])
    else:
        grant(CLIENTS["anon"], guest_n)
    for key, path in PUBLIC:
        probe(persona, "GET", path, key)

# guest order by number (session grant) and every status of a student's orders
for key, order in [("pending", pending_online), ("cod", placed_cod), ("paid", paid_order), ("delivered", delivered_order), ("cancelled", cancelled_order)]:
    probe("student", "GET", f"/account/orders/{order.number}/", f"order status {key}")
    probe("student", "GET", f"/orders/t/{order.token}/", f"order link status {key}")
    probe("student", "GET", f"/checkout/{order.number}/done/", f"done status {key}")
probe("anon", "GET", f"/account/orders/{guest_n}/", "order by session grant (guest)")
probe("anon", "GET", f"/checkout/{guest_n}/done/", "done by session grant (guest)")
probe("anon", "GET", f"/checkout/{pending_online.number}/pay/", "pay of someone else's order (anon)")
probe("student", "GET", f"/checkout/{guest_n}/pay/", "pay of a guest order (student, no grant)")

# carts
probe("student", "POST", f"/cart/add/{sample.pk}/", "cart add POST", {"quantity": 1})
probe("student", "GET", "/cart/", "cart filled")
probe("student", "GET", "/checkout/", "checkout filled")
probe("anon", "POST", f"/cart/add/{sample.pk}/", "cart add POST (anon)", {"quantity": 1})
probe("anon", "GET", "/cart/", "cart filled (anon)")
probe("anon", "GET", "/checkout/", "checkout filled (anon)")

with override_settings(SHOP_COD_ENABLED=True):
    probe("student", "GET", "/checkout/", "checkout filled (COD enabled)")
    probe("student", "GET", f"/checkout/{pending_online.number}/pay/", "pay online order (COD enabled)")
    probe("student", "GET", f"/checkout/{placed_cod.number}/pay/", "pay COD order not yet placed or placed")

# the minor, parent consent pending
with override_settings(PARENTAL_CONSENT_MODE="verified"):
    for key, path in [("account", "/account/"), ("record", "/account/record/"), ("record add", "/account/record/add/PHY-E01/"), ("paper", "/s/PHY-E01/"), ("checkout empty", "/checkout/")]:
        probe("minor", "GET", path, f"{key} (parent consent pending)")
    probe("minor", "POST", f"/cart/add/{sample.pk}/", "cart add (minor pending)", {"quantity": 1})
    probe("minor", "GET", "/checkout/", "checkout (minor pending)")
    probe("minor", "POST", "/account/record/add/PHY-E01/", "attempt save (minor pending)", {"date": "2026-10-01", "marks_obtained": "40"})

# validation states of the main forms
probe("anon", "POST", "/account/login/", "login invalid", {"login": "x@example.com", "password": "wrong"})
probe("anon", "POST", "/account/signup/", "signup invalid", {"email": "bad"})
probe("anon", "POST", "/orders/lookup/", "lookup invalid", {"number": "", "email": "bad"})
probe("anon", "POST", "/orders/lookup/", "lookup sent", {"number": guest_n, "email": "someone@example.com"})
probe("anon", "POST", "/shop/school-orders/", "quote invalid", {"school": ""})
probe("student", "POST", "/checkout/", "checkout invalid", {})
probe("student", "POST", "/account/record/add/PHY-E01/", "attempt invalid", {"date": "2026-10-01", "marks_obtained": "999"})
probe("student", "POST", "/account/addresses/add/", "address invalid", {"name": ""})
probe("student", "POST", "/account/teacher/", "teacher invalid", {"school_name": ""})
probe("student", "POST", "/account/delete/", "delete invalid", {})
probe("anon", "POST", "/cart/", "cart POST empty (anon)", {"action": "coupon", "code": "NOPE"})
probe("student", "POST", "/account/login/code/", "login code invalid", {"email": "bad"})

# allauth pages that need a recent log-in, a second factor, or an account without a password
for key, path in [("2fa index (totp on)", "/account/2fa/"), ("totp deactivate", "/account/2fa/totp/deactivate/"), ("recovery codes", "/account/2fa/recovery-codes/"),
                  ("recovery generate", "/account/2fa/recovery-codes/generate/"), ("recovery download", "/account/2fa/recovery-codes/download/"),
                  ("webauthn list", "/account/2fa/webauthn/"), ("webauthn add", "/account/2fa/webauthn/add/")]:
    probe("mfa", "GET", path, f"{key} (second factor set, just signed in)")
for key, path in [("totp activate", "/account/2fa/totp/activate/"), ("webauthn add", "/account/2fa/webauthn/add/"), ("data export", "/account/data/"),
                  ("delete", "/account/delete/"), ("email", "/account/email/"), ("password change", "/account/password/change/")]:
    probe("reauth", "GET", path, f"{key} (just signed in)")
probe("reauth", "POST", "/account/delete/", "delete invalid (just signed in)", {})
probe("nopass", "GET", "/account/password/set/", "password set (account without a password)")
probe("nopass", "GET", "/account/password/change/", "password change (account without a password)")

# ---- staff pages -------------------------------------------------------------------------------------------------
from django.contrib import admin  # noqa: E402
from django.urls import reverse  # noqa: E402

for persona in ("admin", "editor", "sales", "support", "student", "anon"):
    probe(persona, "GET", "/admin/", "admin index")
    probe(persona, "GET", f"/learn/preview/{clip.pk}/", "learn preview")
for persona in ("admin", "editor", "sales", "support"):
    probe(persona, "GET", reverse("admin:shop_customer", args=[student.pk]), "admin customer page")
    probe(persona, "GET", f"/admin/shop/order/{pending_online.pk}/change/", "admin order change")
for model, model_admin in sorted(admin.site._registry.items(), key=lambda kv: (kv[0]._meta.app_label, kv[0]._meta.model_name)):
    app, name = model._meta.app_label, model._meta.model_name
    for persona in ("admin", "editor", "sales", "support"):
        for kind in ("changelist", "add"):
            try:
                url = reverse(f"admin:{app}_{name}_{kind}")
            except Exception:
                continue
            probe(persona, "GET", url, f"admin {app}.{name} {kind}")

# ---- the API ----------------------------------------------------------------------------------------------------
API_GET = [
    "/api/v1/boards/", "/api/v1/boards/1/", "/api/v1/subjects/", "/api/v1/subjects/1/", "/api/v1/books/", "/api/v1/books/physics-2027/",
    "/api/v1/papers/", "/api/v1/papers/PHY-E01/", "/api/v1/papers/PHY-E01/solutions/", "/api/v1/qr/PHY-E01/", "/api/v1/attempts/",
    f"/api/v1/attempts/{attempt.pk}/", "/api/v1/products/", "/api/v1/products/physics-sample-papers-2027/", "/api/v1/categories/",
    "/api/v1/categories/class-12-books/", "/api/v1/collections/", "/api/v1/collections/exam-week/", "/api/v1/addresses/",
    f"/api/v1/addresses/{address.pk}/", "/api/v1/orders/", f"/api/v1/orders/{placed_cod.number}/",
    f"/api/v1/orders/{placed_cod.number}/invoice/", f"/api/v1/orders/{placed_cod.number}/credit-notes/1/", "/api/v1/cart/",
    "/api/v1/me/", "/api/v1/learn/chapters/", f"/api/v1/learn/chapters/{chapter.pk}/", f"/api/v1/learn/clips/{clip.pk}/",
    f"/api/v1/learn/quiz/?chapter={chapter.pk}", f"/api/v1/learn/flash-cards/?chapter={chapter.pk}", "/api/v1/learn/entitlements/",
    "/api/v1/learn/plan/", "/api/v1/learn/revise-again/", "/api/v1/learn/settings/", "/api/v1/devices/",
    "/api/schema/", "/api/docs/", "/api/redoc/", "/api/nope/", "/api/v1/nope/",
    "/api/v1/config/", "/api/v1/pages/", "/api/v1/pages/privacy/", "/api/v1/me/teacher/", f"/api/v1/orders/t/{guest_order.token}/",
    "/api/v1/products/physics-sample-papers-2027/reviews/",
]
API_POST = [
    "/api/v1/auth/registration/", "/api/v1/auth/registration/verify-email/", "/api/v1/auth/phone/code/", "/api/v1/auth/phone/confirm/",
    "/api/v1/auth/login/", "/api/v1/auth/logout/", "/api/v1/auth/token/refresh/", "/api/v1/auth/token/verify/",
    "/api/v1/auth/password/reset/", "/api/v1/auth/password/reset/confirm/", "/api/v1/auth/password/change/",
    "/api/v1/me/export/", "/api/v1/me/deletion/", "/api/v1/attempts/", "/api/v1/addresses/", "/api/v1/orders/",
    "/api/v1/orders/lookup/", f"/api/v1/orders/{pending_online.number}/cancel/", f"/api/v1/orders/{pending_online.number}/payment/",
    f"/api/v1/orders/{pending_online.number}/payment/confirm/", "/api/v1/cart/items/", "/api/v1/cart/coupon/",
    f"/api/v1/learn/clips/{clip.pk}/progress/", "/api/v1/learn/redeem/", "/api/v1/devices/",
    "/api/v1/auth/exchange/", "/api/v1/me/parent-consent/", "/api/v1/me/teacher/", "/api/v1/quotes/",
    "/api/v1/products/physics-sample-papers-2027/reviews/", "/api/v1/products/physics-sample-papers-2027/stock-alert/",
    "/api/v1/learn/quiz/1/attempt/", "/api/v1/learn/flash-cards/1/review/",
]
API_OTHER = [("PUT", "/api/v1/cart/items/physics-sample-papers-2027/"), ("DELETE", "/api/v1/cart/items/physics-sample-papers-2027/"),
             ("DELETE", "/api/v1/cart/coupon/"), ("DELETE", "/api/v1/devices/"), ("DELETE", "/api/v1/me/deletion/"), ("PUT", "/api/v1/learn/settings/"),
             ("PATCH", "/api/v1/me/"), ("PUT", f"/api/v1/attempts/{attempt.pk}/")]
api = {"anon": APIClient()}
for name in ("student", "admin"):
    c = APIClient()
    c.force_authenticate(user=PERSONAS[name])
    api[name] = c


def api_probe(persona, method, path):
    c = api[persona]
    try:
        response = {"GET": lambda: c.get(path), "POST": lambda: c.post(path, {}, format="json"), "PUT": lambda: c.put(path, {}, format="json"),
                    "PATCH": lambda: c.patch(path, {}, format="json"), "DELETE": lambda: c.delete(path)}[method]()
    except Exception as exc:
        RESULTS.append({"persona": persona, "method": method, "path": path, "key": path, "status": "EXC", "error": repr(exc)[:200]})
        return
    body = ""
    try:
        body = response.content.decode()[:160]
    except Exception:
        pass
    RESULTS.append({
        "persona": persona, "method": method, "path": path, "key": path, "status": response.status_code,
        "ctype": response.headers.get("Content-Type", "").split(";")[0], "bytes": len(response.content), "body": body, "api": True,
    })


for persona in ("anon", "student", "admin"):
    for path in API_GET:
        api_probe(persona, "GET", path)
    for path in API_POST:
        api_probe(persona, "POST", path)
    for method, path in API_OTHER:
        api_probe(persona, method, path)

json.dump(RESULTS, open(f"{UXA}/probe-results.json", "w"), indent=1, default=str)
print("probed", len(RESULTS), "requests")
