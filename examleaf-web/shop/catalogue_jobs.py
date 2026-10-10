"""The Catalogue module's background jobs (staff.jobs: started with POST /api/v1/staff/jobs/, their progress, their
rows' errors, their file):

- coupon_codes: a school's single-use codes of a coupon (shop.add_couponcode): `count` of them with a `prefix`, the
  school's name as each code's note; its file a CSV of the codes for the school, for its starter. Above the starter's
  `bulk_rows` an approver passes it first.
- product_import: a product CSV in the admin's export format (shop/admin.py ProductResource, with the courier's
  columns), uploaded by catalogue/import/ (shop.import_product): a dry run answers what each row would do (made,
  changed, unchanged, refused, and a price that would wait for approval), then its apply names the dry run, within
  24 hours, for the same file. Each row goes through the panel's own rules (shop/staff_catalogue.py) in its own
  transaction, a price through its approval (product.price); stock is never imported (sales go on: set it by hand).
- product_export: the product list's filters as that CSV (shop.export_product), formula cells escaped; above the
  starter's `export_rows` an approver passes it first.

Nothing here is imported by staff.jobs at module level but these names; no import of staff.jobs or staff.api here at
module level (they import this)."""

import csv
import hashlib
import io
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions, serializers

from staff import approvals, audit
from staff.backends import scoped
from staff.models import ChangeRequest, Job

from . import catalogue
from .models import Coupon, Product, ProductType

Kind = Job.Kind
PERMISSIONS = {
    Kind.COUPON_CODES: "shop.add_couponcode",
    Kind.PRODUCT_IMPORT: "shop.import_product",
    Kind.PRODUCT_EXPORT: "shop.export_product",
}
LIMITS = {Kind.COUPON_CODES: "bulk_rows", Kind.PRODUCT_EXPORT: "export_rows"}  # an import: its own dry run comes first
FILE = re.compile(r"[0-9a-f]{32}")
APPLY_WITHIN = timedelta(hours=24)
# The admin's export (shop/admin.py ProductResource), in its order: what an import reads
COLUMNS = ["slug", "title", "kind", "is_active", "subject", "book", "mrp", "price", "stock", "gst_rate", "hsn_code"]
COLUMNS += ["isbn", "pages", "weight_grams", "description", "seo_title", "seo_description", "product_type"]
COLUMNS += ["categories", "length_cm", "width_cm", "height_cm", "packaging"]
NOT_IMPORTED = {"stock", "gst_rate"}  # sales go on meanwhile; the master decides the rate
TRUE, FALSE = {"1", "true", "yes", "y", "on"}, {"0", "false", "no", "n", "off"}
FORMULA = ("=", "+", "-", "@", "\t", "\r")  # a spreadsheet would run a cell starting so


def escape(value):
    """A cell for a spreadsheet: text that would start a formula gets a leading apostrophe (OWASP's CSV injection)."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA) else text


def unescape(text):
    return text[1:] if text.startswith("'") and text[1:2] in ("=", "+", "-", "@") else text


def upload_name(token):
    return f"staff/imports/products/{token}.csv"


def read_rows(text):
    """The rows of a product CSV as {column: text} (a header row first, `slug` among its columns, none unknown);
    ValueError with the words to show otherwise."""
    reader = csv.DictReader(io.StringIO(text))
    header = [name.strip() for name in reader.fieldnames or []]
    if "slug" not in header:
        raise ValueError("The first row names the columns, `slug` among them (the admin's export does).")
    if unknown := [name for name in header if name not in COLUMNS]:
        raise ValueError(f"Columns this import does not know: {', '.join(unknown[:10])}.")
    if len(set(header)) != len(header):
        raise ValueError("A column is named twice.")
    rows = []
    for row in reader:
        if None in row:
            raise ValueError(f"Row {reader.line_num} has more cells than the header.")
        rows.append({name.strip(): unescape((value or "").strip()) for name, value in row.items()})
    return rows


# ---- params, size ----


def params_for(kind, params, dry_run):
    """A job's params, checked (staff.serializers.JobStartSerializer). Raises ValidationError({"params": …})."""
    params = params if isinstance(params, dict) else {}
    if kind == Kind.COUPON_CODES:
        return codes_params(params)
    if kind == Kind.PRODUCT_EXPORT:
        filters = params.get("filters", {})
        if not isinstance(filters, dict):
            raise serializers.ValidationError({"params": {"filters": ["The list's filters, as an object."]}})
        from .staff_catalogue import ProductFilter  # (it imports staff.api, which imports staff.jobs)

        clean = {name: str(value) for name, value in filters.items() if value not in (None, "")}
        if unknown := sorted(set(clean) - set(ProductFilter.base_filters)):
            raise serializers.ValidationError({"params": {"filters": {name: ["Not a filter."] for name in unknown}}})
        if not (filterset := ProductFilter(clean, queryset=Product.objects.none())).is_valid():
            raise serializers.ValidationError({"params": {"filters": filterset.errors}})
        return {"filters": clean}
    token = str(params.get("file", ""))
    if not FILE.fullmatch(token) or not default_storage.exists(upload_name(token)):
        raise serializers.ValidationError({"params": {"file": ["Upload the file first (catalogue/import/)."]}})
    clean = {"file": token, "sha256": hashlib.sha256(read_upload(token)).hexdigest()}
    if not dry_run:
        pk = params.get("dry_run_job")
        if isinstance(pk, bool) or not str(pk).isdigit():
            raise serializers.ValidationError({"params": {"dry_run_job": ["The dry run's job, to apply it."]}})
        clean["dry_run_job"] = int(pk)
    return clean


def codes_params(params):
    problems = {}
    code = str(params.get("coupon", "")).strip().upper()
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None:
        problems["coupon"] = ["No such coupon."]
    elif not coupon.single_use:
        problems["coupon"] = ["Make it single-use first: its own code must not also work at the cart."]
    elif coupon.valid_until and coupon.valid_until < timezone.now():
        problems["coupon"] = ["It has ended: codes of it would not work."]
    count = params.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= catalogue.MAX_CODES:
        problems["count"] = [f"1 to {catalogue.MAX_CODES:,} codes."]
    prefix = str(params.get("prefix", "")).strip().upper()
    if not catalogue.PREFIX.fullmatch(prefix):
        problems["prefix"] = ["2 to 10 capitals and figures (the school's short name)."]
    note = " ".join(str(params.get("note", "")).split())
    if not note or len(note) > 200:
        problems["note"] = ["The school's name (200 characters at most)."]
    if problems:
        raise serializers.ValidationError({"params": problems})
    return {"coupon": code, "count": count, "prefix": prefix, "note": note}


def exported(user, params):
    from .staff_catalogue import ProductFilter

    products = scoped(Product.objects.all(), user, PERMISSIONS[Kind.PRODUCT_EXPORT])
    return ProductFilter(params["filters"], queryset=products).qs.order_by("pk")


def read_upload(token):
    with default_storage.open(upload_name(token), "rb") as file:
        return file.read()


def size(kind, user, params):
    """The rows a job goes through (its total, against its starter's limit)."""
    if kind == Kind.COUPON_CODES:
        return params["count"]
    if kind == Kind.PRODUCT_EXPORT:
        return exported(user, params).count()
    return len(read_rows(read_upload(params["file"]).decode("utf-8-sig")))


# ---- coupon_codes ----


def offer_words(coupon):
    return f"{coupon.value.normalize():f}% off" if coupon.kind == Coupon.Kind.PERCENT else f"₹{coupon.value:,.2f} off"


def coupon_codes(job, progress):
    """A school's batch of single-use codes, and the CSV the school gets (its starter's link, kept a week)."""
    params = job.params
    coupon = Coupon.objects.get(code=params["coupon"])
    if not coupon.single_use:
        raise ValueError("The coupon is no longer single-use: its own code would work too.")
    job.total = params["count"]
    if job.dry_run:
        return {"valid": params["count"], "coupon": coupon.code}
    made = []
    for start in range(0, params["count"], 500):
        batch = catalogue.make_codes(coupon, min(500, params["count"] - start), params["prefix"], params["note"], job)
        made += batch
        for _ in batch:
            progress.row()
    day = lambda moment: timezone.localdate(moment).isoformat() if moment else ""  # noqa: E731
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(["code", "school", "offer", "minimum order", "valid from", "valid until", "use"])
    for code in made:
        writer.writerow(
            [
                escape(code),
                escape(params["note"]),
                offer_words(coupon),
                f"{coupon.min_order.amount:.2f}",
                day(coupon.valid_from),
                day(coupon.valid_until),
                "one order",
            ]
        )
    job.result_file = default_storage.save(
        f"staff/jobs/{job.pk}/codes-{params['prefix'].lower()}-{timezone.localdate():%Y%m%d}.csv",
        ContentFile(text.getvalue().encode("utf-8-sig")),
    )
    audit.record("coupon.codes_made", actor=job.started_by, target=coupon, details={"job": job.pk, "count": len(made)})
    return {"codes": len(made), "coupon": coupon.code}


# ---- product_import ----


def decimal_of(value, name):
    try:
        return Decimal(value)
    except InvalidOperation:
        raise serializers.ValidationError({name: ["A number."]}) from None


def parsed(row):
    """A CSV row as the API's fields (shop/staff_catalogue.py CatalogueProductWriteSerializer): `subject` an id,
    `book` a slug, `product_type` by name, `categories` split on |, the code of the master as `hsn`. Stock and the GST
    rate are not imported."""
    data = {}
    for name, value in row.items():
        if name in NOT_IMPORTED or name == "slug":
            continue
        if name == "is_active":
            if value.lower() not in TRUE | FALSE:
                raise serializers.ValidationError({name: ["1 or 0 (true or false)."]})
            data[name] = value.lower() in TRUE
        elif name in ("subject", "pages", "length_cm", "width_cm", "height_cm"):
            data[name] = int(value) if value.isdigit() else None if not value else value
        elif name == "weight_grams":
            data[name] = int(value) if value.isdigit() else 0 if not value else value
        elif name in ("mrp", "price"):
            data[name] = decimal_of(value, name)
        elif name == "book":
            data[name] = value or None
        elif name == "product_type":
            kind = ProductType.objects.filter(name=value).first() if value else None
            if value and kind is None:
                raise serializers.ValidationError({name: [f"No product type “{value}”."]})
            data[name] = kind.pk if kind else None
        elif name == "categories":
            data[name] = [slug.strip() for slug in value.split("|") if slug.strip()]
        elif name == "hsn_code":
            data["hsn"] = value or None
        else:
            data[name] = value
    return data


def as_row(product):
    """A product's fields as parsed() gives a row's, to tell which of them a row changes."""
    return {
        "title": product.title,
        "kind": product.kind,
        "is_active": product.is_active,
        "subject": product.subject_id,
        "book": product.book.slug if product.book_id else None,
        "mrp": product.mrp.amount,
        "price": product.price.amount,
        "hsn": product.hsn_id or (product.hsn_code if not product.hsn_id else None),
        "isbn": product.isbn,
        "pages": product.pages,
        "weight_grams": product.weight_grams,
        "description": product.description,
        "seo_title": product.seo_title,
        "seo_description": product.seo_description,
        "product_type": product.product_type_id,
        "categories": sorted(product.categories.values_list("slug", flat=True)),
        "length_cm": product.length_cm,
        "width_cm": product.width_cm,
        "height_cm": product.height_cm,
        "packaging": product.packaging,
    }


def needed(keys, creating):
    """The permissions a row's changes need beyond the import's own (as the API's parts do)."""
    from .staff_catalogue import PRICE_FIELDS, TAX_FIELDS

    perms = ["shop.add_product"] if creating else []
    if not creating and keys - PRICE_FIELDS - TAX_FIELDS:
        perms.append("shop.change_product")
    if keys & PRICE_FIELDS:
        perms.append("staff.change_price")
    if keys & TAX_FIELDS and not creating:
        perms.append("staff.change_product_tax")
    return perms


def import_row(row, user, job):
    """One row, in its own transaction: (outcome, the fields it changes, the price's way: None, "at once", "waits").
    A dry run checks it all and changes nothing; an apply saves through the panel's own path."""
    from .staff_catalogue import CatalogueProductWriteSerializer, price_change, save_product

    slug = row["slug"]
    product = Product.objects.filter(slug=slug).first()
    if product is not None and not scoped(Product.objects.filter(pk=product.pk), user, "shop.change_product").exists():
        raise exceptions.PermissionDenied("Not a product you may change: its subject is not one of yours.")
    data = parsed(row)
    if product is not None:
        held = as_row(product)
        data = {
            name: value
            for name, value in data.items()
            if held.get(name) != (sorted(value) if name == "categories" else value)
        }
    else:
        data["slug"] = slug
    if product is not None and not data:
        return "unchanged", [], None
    keys = set(data)
    for perm in needed(keys, product is None):
        if not user.has_perm(perm):
            raise exceptions.PermissionDenied(f"Needs {perm}.")
    reason = f"Product import (job #{job.pk})"  # the versions' and a price's approval's
    asked = CatalogueProductWriteSerializer(
        data={**data, "reason": reason}, product=product, partial=product is not None, user=user
    )
    asked.is_valid(raise_exception=True)
    values = dict(asked.validated_data)
    values.pop("reason", None)
    prices = {name: values.pop(name) for name in list(values) if name in ("mrp", "price")}
    if product is not None:
        prices = {name: value for name, value in prices.items() if value != getattr(product, name).amount}
    way = None
    if product is not None and prices:
        action = approvals.ACTIONS["product.price"]
        _target, payload, _amount = action.validate(user, product.slug, {k: str(v) for k, v in prices.items()})
        way = "waits" if action.rule(user, ChangeRequest(action="product.price", payload=payload)) else "at once"
    elif product is None and prices.get("price") is not None and prices["price"] != prices["mrp"]:
        off = approvals.discount_percent(prices["mrp"], prices["price"])
        way = "waits" if approvals.over(off, approvals.limit_of(user, "discount_percent"), "{amount}") else "at once"
    outcome = "created" if product is None else "updated"
    if job.dry_run:
        return outcome, sorted(keys), way
    with transaction.atomic():
        if product is None:  # made at its MRP, its price then through its approval (as the API makes one)
            mrp = prices.pop("mrp")
            price = prices.pop("price", mrp)
            product = Product(mrp=mrp, price=mrp, is_active=values.pop("is_active", False))
            save_product(product, values, by=user, reason=reason, creating=True)
            if price != mrp:
                prices = {"price": price}
        else:
            save_product(product, values, by=user, reason=reason)
        if prices:
            prices["reason"] = reason
            change = price_change(product, prices, maker=user, key=f"job-{job.pk}-{product.pk}")
            way = None if change is None else "waits" if change.status == ChangeRequest.Status.PENDING else "at once"
            if change is not None and change.status == ChangeRequest.Status.FAILED:
                raise serializers.ValidationError({"price": [change.result.get("error", "Not changed.")]})
    return outcome, sorted(keys), way


def check_apply(job):
    """The apply's dry run: the same starter's, done, for the same file (byte for byte), within 24 hours, not applied
    already. ValueError otherwise (the job fails with it)."""
    dry = Job.objects.filter(pk=job.params["dry_run_job"], kind=Kind.PRODUCT_IMPORT, dry_run=True).first()
    if dry is None or dry.started_by_id != job.started_by_id:
        raise ValueError("No such dry run of yours: run the dry run first.")
    if dry.state != Job.State.DONE or dry.params.get("file") != job.params["file"]:
        raise ValueError("Apply a finished dry run, with its own file.")
    if dry.params.get("sha256") != job.params["sha256"]:
        raise ValueError("The file changed since its dry run: run the dry run again.")
    if not dry.finished_at or timezone.now() - dry.finished_at > APPLY_WITHIN:
        raise ValueError("Its dry run is more than 24 hours old: run it again.")
    others = Job.objects.filter(kind=Kind.PRODUCT_IMPORT, dry_run=False, params__dry_run_job=dry.pk).exclude(pk=job.pk)
    if others.exclude(state__in=[Job.State.FAILED, Job.State.CANCELLED]).exists():
        raise ValueError("This dry run has been applied already.")


def product_import(job, progress):
    """Each row through the panel's own path; the counts by outcome, and the rows that change something."""
    from collections import Counter

    from staff.jobs import message

    if not job.dry_run:
        check_apply(job)
    rows = read_rows(read_upload(job.params["file"]).decode("utf-8-sig"))
    job.total, counts, report, seen = len(rows), Counter(), [], set()
    for line, row in enumerate(rows, start=2):  # as a spreadsheet numbers them (the header is line 1)
        slug = row.get("slug", "")
        try:
            if not slug:
                raise serializers.ValidationError({"slug": ["Required: the product's address."]})
            if slug in seen:
                raise serializers.ValidationError({"slug": ["Twice in the file: once each."]})
            seen.add(slug)
            outcome, fields, way = import_row(row, job.started_by, job)
            counts[outcome] += 1
            counts["prices_waiting"] += way == "waits"
            if outcome != "unchanged" and len(report) < 500:
                report.append({"line": line, "slug": slug, "outcome": outcome, "fields": fields, "price": way})
        except (serializers.ValidationError, exceptions.APIException) as error:
            counts["errors"] += 1
            progress.error(line, slug or f"line {line}", message(error))
        progress.row()
    result = {
        "counts": {name: counts[name] for name in ("created", "updated", "unchanged", "errors", "prices_waiting")}
    }
    result["rows"] = report
    if not job.dry_run:
        details = {"job": job.pk, "dry_run_job": job.params["dry_run_job"], **result["counts"]}
        audit.record("catalogue.imported", actor=job.started_by, details=details)
        default_storage.delete(upload_name(job.params["file"]))
    return result


def purge_import_files(now=None):
    """The CSVs of dry runs never applied, deleted from the private storage once their window is well over (an
    applied import's file went at the apply): the dry runs of the last week past twice APPLY_WITHIN. Returns how
    many files went."""
    now = now or timezone.now()
    stale = Job.objects.filter(
        kind=Job.Kind.PRODUCT_IMPORT,
        dry_run=True,
        created__lt=now - 2 * APPLY_WITHIN,
        created__gte=now - timedelta(days=7),
    )
    gone = 0
    for params in stale.values_list("params", flat=True):
        name = upload_name(str((params or {}).get("file") or ""))
        if params.get("file") and default_storage.exists(name):
            default_storage.delete(name)
            gone += 1
    return gone


# ---- product_export ----


def product_export(job, progress):
    """The list's filters as the admin's export format (shop/admin.py ProductResource), formula cells escaped."""
    from .admin import ProductResource

    products = exported(job.started_by, job.params)
    job.total = products.count()
    if job.dry_run:
        return {"rows": job.total}
    dataset = ProductResource().export(queryset=products.prefetch_related("categories").select_related("book"))
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(dataset.headers)
    for row in dataset:
        writer.writerow([escape(cell) for cell in row])
        progress.row()
    job.result_file = default_storage.save(
        f"staff/jobs/{job.pk}/products-{timezone.localdate():%Y%m%d}.csv", ContentFile(text.getvalue().encode("utf-8"))
    )
    details = {"filters": job.params["filters"], "rows": job.done, "job": job.pk}
    audit.record("catalogue.exported", actor=job.started_by, change_request=job.change_request_id, details=details)
    return {"rows": job.done}


RUNNERS = {Kind.COUPON_CODES: coupon_codes, Kind.PRODUCT_IMPORT: product_import, Kind.PRODUCT_EXPORT: product_export}
