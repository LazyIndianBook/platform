from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import Book
from shop.models import BundleItem, Coupon, HsnCode, Product, ShippingRate, public_storage

SUBJECTS = [("PHY", "Physics"), ("CHE", "Chemistry"), ("MAT", "Mathematics"), ("BIO", "Biology")]
SAMPLE_PAPERS = (
    "30 full papers in the board's pattern for the Assam Board (ASSEB) Class 12 examination: 10 Easy, 10 Medium and "
    "10 Hard, each with its time and marks."
)
SOLUTIONS = (
    "The worked solutions of all 30 papers of the ExamLeaf {subject} Sample Papers book, step by step, with the marks "
    "each step earns as the board's marking scheme gives them."
)
RATES = [  # placeholders: change them in the admin (Shipping rates)
    ("Assam", ["AS"], 40, 499),
    ("North-East", ["AR", "MN", "ML", "MZ", "NL", "SK", "TR"], 60, 799),
    ("Rest of India", [], 80, 999),
]


class Command(BaseCommand):
    help = (
        "Create the starting catalogue: Sample Papers and Solutions for each subject (covers from static/img/, "
        "placeholder prices), a Physics bundle, the WELCOME10 coupon and shipping rates. Safe to run again: what "
        "exists is left as it is."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stock", type=int, default=0, help="copies of each new book (default 0: set it in the admin)"
        )

    @transaction.atomic
    def handle(self, *args, stock, **options):
        created = []

        def product(slug, **fields):
            obj, new = Product.objects.get_or_create(slug=slug, defaults=fields)
            if new:
                created.append(obj.title)
            return obj

        for code, name in SUBJECTS:
            book = Book.objects.filter(subject__code=code, subject__class_level__number=12).order_by("id").first()
            common = {"subject": book.subject if book else None, "book": book, "stock": stock}
            common["hsn"] = HsnCode.objects.filter(code="4901").first()  # printed books, on the master: exempt
            papers = product(
                f"{name.lower()}-sample-papers-2027",
                title=f"ExamLeaf {name} Sample Papers 2027",
                kind=Product.Kind.SAMPLE_PAPERS,
                mrp=299,
                price=299,
                weight_grams=450,
                description=SAMPLE_PAPERS,
                seo_description=f"{name} Sample Papers for the Assam Board (ASSEB) Class 12 exam: 30 papers with "
                "free online solutions.",
                **common,
            )
            solutions = product(
                f"{name.lower()}-solutions-2027",
                title=f"ExamLeaf {name} Solutions 2027",
                kind=Product.Kind.SOLUTIONS,
                mrp=249,
                price=249,
                weight_grams=400,
                description=SOLUTIONS.format(subject=name),
                seo_description=f"Worked solutions of the ExamLeaf {name} Sample Papers (ASSEB Class 12).",
                **common,
            )
            for item in [papers]:  # Solutions: no cover until its own is uploaded (static/img/ has the papers')
                if not item.cover and (path := finders.find(f"img/{name.lower()}.png")):
                    name_in_storage = f"products/{name.lower()}.png"
                    if not public_storage().exists(name_in_storage):
                        with open(path, "rb") as cover:
                            public_storage().save(name_in_storage, File(cover))
                    item.cover = name_in_storage  # reads its width and height
                    item.save(update_fields=["cover", "cover_width", "cover_height"])
                    item.cover.save_all()  # the AVIF and WebP sizes (Celery, after the commit)
            if code == "PHY":
                bundle = product(
                    "physics-bundle-2027",
                    title="ExamLeaf Physics Sample Papers + Solutions 2027",
                    kind=Product.Kind.BUNDLE,
                    mrp=548,
                    price=499,
                    weight_grams=850,
                    description="Both Physics books together: the 30 Sample Papers and their worked Solutions.",
                    subject=common["subject"],
                    book=book,
                    hsn=common["hsn"],
                    cover=papers.cover.name,
                )
                for item in (papers, solutions):
                    BundleItem.objects.get_or_create(bundle=bundle, product=item)

        coupon, new = Coupon.objects.get_or_create(
            code="WELCOME10",
            defaults={
                "value": 10,
                "min_order": 299,
                "max_uses_per_customer": 1,
                "valid_until": datetime(2027, 3, 31, 23, 59, tzinfo=ZoneInfo("Asia/Kolkata")),
            },
        )
        if new:
            created.append(f"coupon {coupon}")
        for name, states, fee, free_above in RATES:
            if ShippingRate.objects.get_or_create(
                name=name, defaults={"states": states, "fee": fee, "free_above": free_above}
            )[1]:
                created.append(f"shipping rate {name}")
        self.stdout.write(f"Created: {', '.join(created)}." if created else "Nothing to create: all there already.")
