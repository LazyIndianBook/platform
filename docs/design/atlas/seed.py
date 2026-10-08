"""The atlas's Django side: the temporary accounts and the rows that make the pages worth photographing.

Run from examleaf-web, with the atlas environment, one phase at a time (capture.mjs does it for you):

    ATLAS_PHASE=base       ATLAS_CREDS=creds.json .venv/bin/python manage.py shell < seed.py
    ATLAS_PHASE=catalogue  ...  shelves, collections, pictures, reviews, an offer, PIN codes, the course's clips, the
                                other roles (sales, editor, support, a teacher, a minor, a reviewer)
    ATLAS_PHASE=filled     ...  the student's orders in every state, marks, learning rows, staff notes
    ATLAS_PHASE=cleanup    ...  deletes every account (and what it made) whose email starts with "atlas-"

Passwords and the TOTP secret are made in `base` and written to ATLAS_CREDS (mode 600); nothing prints them.
Every phase can be run again: what exists is left alone.
"""

import datetime
import json
import os
import secrets
import sys
from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.utils import timezone

from accounts.models import ConsentRecord, TeacherProfile, User
from content.models import Board, Paper, Subject
from pages.models import Page

PHASE = os.environ["ATLAS_PHASE"]
CREDS = os.environ.get("ATLAS_CREDS", "creds.json")
STUDENT, STAFF, MINOR = "atlas-student@example.com", "atlas-staff@example.com", "atlas-minor@example.com"
PREFIX = "atlas-"


def say(*parts):
    print("ATLAS", *parts, file=sys.stderr)


def creds():
    try:
        with open(CREDS) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def save_creds(data):
    with open(os.open(CREDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        json.dump(data, handle)


def make_user(email, full_name, group, password=None, **extra):
    defaults = dict(
        full_name=full_name,
        class_level=12,
        board=Board.objects.first(),
        district="Kamrup Metro",
        date_of_birth=datetime.date(2008, 3, 14),
        consent_at=timezone.now(),
    )
    defaults.update(extra)
    user, created = User.objects.get_or_create(email=email, defaults=defaults)
    if created:
        user.set_password(password) if password else user.set_unusable_password()
        user.save()
        notice = Page.objects.filter(slug="privacy").values_list("version", flat=True).first() or ""
        ConsentRecord.objects.create(user=user, notice_version=notice)
    user.groups.add(Group.objects.get(name=group))
    EmailAddress.objects.update_or_create(user=user, email=email, defaults=dict(verified=True, primary=True))
    return user


def pay_online(order, method="upi"):
    """What Razorpay's capture does (services.record_capture): the payment gets its ids, the order is paid, the
    invoice is queued, the confirmation is printed in the log."""
    from shop import services
    from shop.models import INR, Payment, paise

    payment = order.payments.get()
    Payment.objects.filter(pk=payment.pk).update(razorpay_order_id=f"order_ATLAS{order.pk:06d}")
    services.record_capture(
        {
            "id": f"pay_ATLAS{order.pk:06d}",
            "order_id": f"order_ATLAS{order.pk:06d}",
            "amount": paise(payment.amount),
            "currency": INR,
            "method": method,
        }
    )
    order.refresh_from_db()
    return order


def make_order(user, products, coupon=None, address=None):
    """A pending order of `(product slug, copies)` for the user at today's prices, as the checkout makes it."""
    from shop import services
    from shop.cart import Line, price
    from shop.models import Coupon, Order, Product

    address = address or user.addresses.get(is_default=True)
    lines = [Line(Product.objects.get(slug=slug), quantity) for slug, quantity in products]
    coupon = Coupon.objects.get(code=coupon) if coupon else None
    result = price(lines, coupon, state=address.state, user=user, email=user.email)
    return services.save_order(
        result, user=user, email=user.email, shipping_address=address.snapshot(), payment_method=Order.Method.RAZORPAY
    )


def backdate(order, days):
    """Move an order's whole history to `days` ago (each step a few hours or a day after the last), so that the pages
    show a believable fortnight: the timeline reads the history rows, the lists read `created`."""
    from shop.models import Order, Payment, Shipment

    base = timezone.now() - timedelta(days=days, hours=2)
    steps = [timedelta(0), timedelta(minutes=3), timedelta(hours=22), timedelta(days=1, hours=18), timedelta(days=3, hours=5)]
    order.refresh_from_db()
    seen = []
    for record in Order.history.filter(id=order.pk).order_by("history_date", "history_id"):
        if record.status not in seen:
            seen.append(record.status)
        when = base + steps[min(seen.index(record.status), len(steps) - 1)]
        Order.history.filter(history_id=record.history_id).update(history_date=when)
    fields = {"created": base}
    if order.placed_at:
        fields["placed_at"] = base + steps[1]
    Order.objects.filter(pk=order.pk).update(**fields)
    Payment.objects.filter(order=order).update(created=base)
    Shipment.objects.filter(order=order).update(shipped_at=base + steps[3])
    Shipment.objects.filter(order=order, delivered_at__isnull=False).update(delivered_at=base + steps[4])


if PHASE == "base":
    password, staff_password = secrets.token_urlsafe(15), secrets.token_urlsafe(15)
    student = make_user(STUDENT, "Atlas Student", "STUDENT", password)
    staff = make_user(STAFF, "Atlas Staff", "ADMIN", staff_password, is_staff=True, is_superuser=True)
    for user, new_password in [(student, password), (staff, staff_password)]:  # a second run: new passwords
        user.set_password(new_password)
        user.save()
    Authenticator.objects.filter(user=staff, type=Authenticator.Type.TOTP).delete()
    secret = generate_totp_secret()
    TOTP.activate(staff, secret)
    save_creds(
        {
            "student": {"email": STUDENT, "password": password},
            "staff": {"email": STAFF, "password": staff_password, "totp_secret": secret},
        }
    )
    # one open sample a book: every other paper's solutions ask for an account
    Paper.objects.filter(code="PHY-E01").update(is_sample=True)
    say("base:", student.email, staff.email, "is_staff", staff.is_staff)

elif PHASE == "catalogue":
    from content.models import Book
    from learn.models import Chapter, Clip, FlashCard, Revision
    from shop.models import (
        Category,
        Collection,
        CollectionItem,
        Offer,
        PinCode,
        Product,
        ProductImage,
        Review,
    )

    # the other roles, for the users page and the reviews
    for email, name, group in [
        ("atlas-sales@example.com", "Atlas Sales", "SALES"),
        ("atlas-editor@example.com", "Atlas Editor", "CONTENT_EDITOR"),
        ("atlas-support@example.com", "Atlas Support", "SUPPORT"),
    ]:
        make_user(email, name, group, is_staff=True)
    teacher = make_user("atlas-teacher@example.com", "Atlas Teacher", "TEACHER", date_of_birth=datetime.date(1985, 6, 1))
    TeacherProfile.objects.get_or_create(
        user=teacher,
        defaults=dict(
            school_name="Demo Higher Secondary School",
            district="Kamrup Metro",
            subject="Physics",
            verified=True,
            verified_at=timezone.now(),
            verification_note="Checked with the school office (atlas demo account).",
        ),
    )
    today = timezone.localdate()
    minor = make_user(
        MINOR,
        "Atlas Minor",
        "STUDENT",
        class_level=10,
        date_of_birth=datetime.date(today.year - 15, 5, 2),
        parent_name="Atlas Parent",
        parent_contact="atlas-parent@example.com",
    )
    reviewer = make_user("atlas-reviewer@example.com", "Atlas Reviewer", "STUDENT")

    # shelves: Books > Class 12 > Sample Papers, Solutions, Bundles
    if not Category.objects.filter(slug="books").exists():
        books = Category.add_root(name="Books", slug="books", description="Printed books for the ASSEB Class 12 examination.")
        class12 = books.add_child(name="Class 12", slug="class-12", description="Assam Board (ASSEB) Class 12, 2027.")
        shelves = {
            "sample-papers": class12.add_child(name="Sample Papers", slug="sample-papers", description="Thirty full papers a subject."),
            "solutions": class12.add_child(name="Solutions", slug="solutions", description="Every step, with its marks."),
            "bundle": class12.add_child(name="Bundles", slug="bundles", description="Both books of a subject together."),
        }
        for product in Product.objects.all():
            if product.kind in shelves:
                product.categories.add(Category.objects.get(pk=shelves[product.kind].pk))
    # hand-picked lists
    physics, _ = Collection.objects.get_or_create(
        slug="physics", defaults=dict(name="Physics", description="Everything for Class 12 Physics.", position=1)
    )
    papers, _ = Collection.objects.get_or_create(
        slug="all-sample-papers",
        defaults=dict(name="All Sample Papers", description="One book for each of the four subjects.", position=2),
    )
    for position, slug in enumerate(["physics-bundle-2027", "physics-sample-papers-2027", "physics-solutions-2027"]):
        CollectionItem.objects.get_or_create(collection=physics, product=Product.objects.get(slug=slug), defaults=dict(position=position))
    for position, subject in enumerate(["physics", "chemistry", "mathematics", "biology"]):
        CollectionItem.objects.get_or_create(
            collection=papers, product=Product.objects.get(slug=f"{subject}-sample-papers-2027"), defaults=dict(position=position)
        )
    # an automatic offer, so that the cart shows a saving line
    Offer.objects.get_or_create(
        name="Board 2027 offer",
        defaults=dict(kind="percent", value=5, scope="cart", min_value=600, combinable=True, is_active=True),
    )
    # a few PIN codes of Assam (the directory is India Post's; this is what the checkout looks up)
    from shop.models import PinCode

    for pin, district in [("781001", "Kamrup Metro"), ("781005", "Kamrup Metro"), ("786001", "Dibrugarh"), ("785001", "Jorhat"),
                          ("788001", "Cachar"), ("782001", "Nagaon"), ("784001", "Sonitpur")]:
        PinCode.objects.update_or_create(pin=pin, defaults=dict(states=["AS"], districts=[district]))
    # pictures: the cover, and two crops of it, as a gallery
    from django.contrib.staticfiles import finders
    from PIL import Image
    import io

    def crop_bytes(path, box):
        with Image.open(path) as image:
            width, height = image.size
            part = image.crop((int(box[0] * width), int(box[1] * height), int(box[2] * width), int(box[3] * height)))
            out = io.BytesIO()
            part.convert("RGB").save(out, "JPEG", quality=88)
            return out.getvalue()

    for subject in ["physics", "chemistry"]:
        product = Product.objects.get(slug=f"{subject}-sample-papers-2027")
        if not product.images.exists():
            source = finders.find(f"img/{subject}.png")
            title = product.title
            for position, (box, alt) in enumerate(
                [
                    ((0, 0, 1, 1), f"Cover of {title}"),
                    ((0.05, 0.05, 0.95, 0.5), f"The title and the count of papers on the cover of {title}"),
                    ((0.05, 0.5, 0.95, 0.97), f"The lower half of the cover of {title}: the papers and the QR code"),
                ]
            ):
                if subject == "chemistry" and position == 2:
                    continue
                ProductImage.objects.create(
                    product=product, alt=alt, position=position,
                    image=ContentFile(crop_bytes(source, box), name=f"{subject}-{position}.jpg"),
                )
    # reviews: two shown, one waiting, one rejected
    physics_papers, chem_papers, chem_solutions = (Product.objects.get(slug=s) for s in ["physics-sample-papers-2027", "chemistry-sample-papers-2027", "chemistry-solutions-2027"])
    for product, user, rating, text, status in [
        (physics_papers, reviewer, 5, "Every answer is step by step, with the marks for each step. It showed me where I was losing marks.", "approved"),
        (physics_papers, minor, 4, "Good papers. I would like a few more Hard ones in the first set.", "approved"),
        (chem_papers, teacher, 5, "I give the Medium papers to my class as a weekly test.", "pending"),
        (chem_solutions, reviewer, 1, "Click here to win a free phone", "rejected"),
    ]:
        Review.objects.get_or_create(product=product, user=user, defaults=dict(rating=rating, text=text, status=status))

    # the course: Physics chapters 1 to 3 revised, Chemistry's first still a draft with clips in every state
    phy, che = Subject.objects.get(code="PHY"), Subject.objects.get(code="CHE")
    chapters = {(c.subject.code, c.number): c for c in Chapter.objects.select_related("subject")}

    def revision(key, title, status, clips, minutes):
        chapter = chapters[key]
        rev, new = Revision.objects.get_or_create(chapter=chapter, defaults=dict(title=title, status=status, target_minutes=minutes))
        if new:
            for order, (clip_title, kind, seconds, processing, error) in enumerate(clips, 1):
                Clip.objects.create(
                    revision=rev, order=order, title=clip_title, kind=kind, duration=seconds, processing=processing,
                    processing_error=error, is_free_preview=order == 1,
                    hls_path=f"learn/hls/atlas-{chapter.pk}-{order}/v1/master.m3u8" if processing == "ready" else "",
                    notes="Coulomb's law in one picture, and the three questions the Board repeats." if order == 1 else "",
                )
        return rev

    ready = "ready"
    revision(("PHY", 1), "Electric charges and fields in 13 minutes", "published", [
        ("Coulomb's law in one picture", "concept", 140, ready, ""), ("The field of a dipole: the one formula", "formula", 165, ready, ""),
        ("Gauss's law: choose the surface", "trick", 190, ready, ""), ("Where marks are lost: signs and directions", "mistake", 120, ready, ""),
        ("The Board's questions on charges, 2019 to 2025", "pyq", 175, ready, ""),
    ], 13)
    revision(("PHY", 2), "Potential and capacitance in 12 minutes", "published", [
        ("Potential energy of two charges", "concept", 150, ready, ""), ("Capacitors in series and parallel", "formula", 170, ready, ""),
        ("The dielectric shortcut", "shortcut", 130, ready, ""),
    ], 12)
    revision(("PHY", 3), "Current electricity in 15 minutes", "published", [
        ("Drift velocity and current", "concept", 160, ready, ""), ("Kirchhoff's rules without tears", "trick", 200, ready, ""),
        ("The Wheatstone bridge in 40 seconds", "shortcut", 95, ready, ""), ("Potentiometer: what the Board asks", "pyq", 180, ready, ""),
    ], 15)
    revision(("CHE", 1), "Solutions in 12 minutes", "draft", [
        ("Colligative properties: the four formulas", "formula", 0, "uploaded", ""),
        ("Raoult's law, step by step", "concept", 0, "processing", ""),
        ("Van't Hoff factor", "trick", 0, "failed", "ffmpeg is not installed: the video was kept; process it again once it is."),
    ], 12)
    for number, (front, back) in enumerate([
        ("State Coulomb's law", "F = k q1 q2 / r^2, along the line joining the charges"),
        ("Unit of electric field", "Newton per coulomb, or volt per metre"),
        ("Field inside a charged conductor", "Zero: the charge sits on the surface"),
        ("Flux through a closed surface", "q(enclosed) / epsilon-naught: Gauss's law"),
        ("Electric dipole moment", "p = q x 2a, from the negative to the positive charge"),
        ("Torque on a dipole in a uniform field", "p E sin(theta), and no net force"),
    ], 1):
        FlashCard.objects.get_or_create(chapter=chapters[("PHY", 1)], order=number, defaults=dict(front=front, back=back))
    say("catalogue: categories", Category.objects.count(), "collections", Collection.objects.count(), "images", ProductImage.objects.count(),
        "reviews", Review.objects.count(), "revisions", Revision.objects.count(), "clips", Clip.objects.count())

elif PHASE == "filled":
    from learn.models import Clip, Learner, Progress, QuizAttempt, QuizItem
    from practice.models import Attempt
    from shop import services
    from shop.models import Address, Order, OrderNote, Product, Shipment

    student, staff = User.objects.get(email=STUDENT), User.objects.get(email=STAFF)
    today = timezone.localdate()
    address = student.addresses.filter(is_default=True).first() or Address.objects.create(
        user=student, name="Atlas Student", phone="+919864012345", line1="12 Demo Road", line2="Near the park",
        city="Guwahati", district="Kamrup Metro", state="AS", pin="781001", is_default=True,
    )
    def once(status, build):
        """One order of this status (besides the two the browser placed, which wait for payment)."""
        if not student.orders.filter(status=status).exists():
            build()

    def build_delivered():  # twelve days ago, with the welcome coupon and an invoice
        order = make_order(student, [("physics-sample-papers-2027", 1), ("chemistry-sample-papers-2027", 1)], coupon="WELCOME10")
        pay_online(order)
        services.pack_order(order)
        services.ship_order(order, "India Post", "EL482916305IN")
        services.deliver_order(order)
        backdate(order, 12)
        OrderNote.objects.create(order=order, author=staff, text="Asked for the school's name on the invoice: a corrected copy sent by email.")

    def build_shipped():  # four days ago
        order = make_order(student, [("mathematics-sample-papers-2027", 1), ("mathematics-solutions-2027", 1)])
        pay_online(order)
        services.pack_order(order)
        services.ship_order(order, "Delhivery", "DLV7710093244")
        backdate(order, 4)
        OrderNote.objects.create(order=order, author=staff, text="Handed to Delhivery at the Guwahati hub; the customer was texted the tracking number.")

    def build_packed():  # two days ago, waiting for the courier
        order = make_order(student, [("chemistry-solutions-2027", 1)])
        pay_online(order)
        services.pack_order(order)
        backdate(order, 2)

    def build_paid():  # yesterday, not yet packed
        order = make_order(student, [("physics-bundle-2027", 1)])
        pay_online(order)
        backdate(order, 1)

    def build_cancelled():  # by the student before it was paid, six days ago
        order = make_order(student, [("biology-sample-papers-2027", 2)])
        services.cancel_order(order, "Cancelled by you.", email=False)
        backdate(order, 6)

    for status, build in [("delivered", build_delivered), ("shipped", build_shipped), ("packed", build_packed), ("paid", build_paid), ("cancelled", build_cancelled)]:
        once(status, build)
    # marks: the paper saved in the browser is the fifth
    for code, marks, ago, minutes, notes in [
        ("PHY-E01", 61, 20, 175, "Optics: ray diagrams and the mirror formula"),
        ("CHE-E01", 48.5, 14, 160, "Named reactions in organic chemistry"),
        ("MAT-M01", 52, 9, 178, ""),
        ("PHY-M01", 41, 3, 180, "Alternating current: resonance and power factor"),
    ]:
        Attempt.objects.get_or_create(
            user=student, paper=Paper.objects.get(code=code), date=today - timedelta(days=ago),
            defaults=dict(marks_obtained=marks, time_taken_minutes=minutes, notes=notes),
        )
    # the course, once a book code has opened Physics (done in the browser): clips watched, quiz answers
    clips = list(Clip.objects.filter(revision__chapter__subject__code="PHY", processing="ready").order_by("revision__chapter__number", "order"))
    for clip, watched, done in zip(clips[:5], [clips[0].duration, clips[1].duration, clips[2].duration, 90, 40], [True, True, True, False, False], strict=False):
        Progress.objects.update_or_create(user=student, clip=clip, defaults=dict(seconds_watched=watched, completed=done))
    items = list(QuizItem.objects.filter(chapter__subject__code="PHY").order_by("pk")[:8])
    for index, item in enumerate(items):
        QuizAttempt.objects.get_or_create(
            user=student, item=item, defaults=dict(correct=index % 3 != 0, created=timezone.now() - timedelta(days=index % 3))
        )
    Learner.objects.update_or_create(user=student, defaults=dict(minutes_per_day=45))
    say("filled: orders", student.orders.count(), "attempts", student.attempts.count(), "progress", Progress.objects.filter(user=student).count())

elif PHASE == "cleanup":
    from django.contrib.sessions.models import Session

    from shop import services
    from shop.models import CreditNote, Invoice, Order, OrderNote, Payment, Refund, Review, StockAlert

    users = User.objects.filter(email__startswith=PREFIX)
    emails = list(users.values_list("email", flat=True))
    orders = Order.objects.filter(email__in=emails)
    for order in orders.filter(status="pending", placed_at__isnull=True):
        try:
            services.cancel_order(order, "atlas clean-up", email=False)
        except Exception as error:  # noqa: BLE001
            say("not cancelled", order, error)
    CreditNote.objects.filter(invoice__order__in=orders).delete()
    Refund.objects.filter(order__in=orders).delete()
    Invoice.objects.filter(order__in=orders).delete()
    ids = list(orders.values_list("pk", flat=True))
    Payment.objects.filter(order__in=orders).delete()
    OrderNote.objects.filter(order__in=orders).delete()
    orders.delete()
    Order.history.filter(id__in=ids).delete()
    Review.objects.filter(user__email__in=emails).delete()
    StockAlert.objects.filter(email__in=emails).delete()
    pks = {str(pk) for pk in users.values_list("pk", flat=True)}
    gone = [s.pk for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") in pks]
    Session.objects.filter(pk__in=gone).delete()
    say("cleanup: users", users.delete(), "orders", len(ids), "sessions", len(gone))
    say("left:", User.objects.filter(email__startswith=PREFIX).count(), "accounts,", Order.objects.filter(email__in=emails).count(), "orders")

else:
    raise SystemExit(f"ATLAS_PHASE={PHASE}: base, catalogue, filled or cleanup")
