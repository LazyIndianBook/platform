"""Who may watch what (entitlements, free previews, book codes), and the hooks the shop calls for digital products."""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone

from .models import CODE_ALPHABET, CODE_LENGTH, BookCode, Chapter, Entitlement, clean_code, code_digest

logger = logging.getLogger(__name__)


class Every:
    """Every subject (staff, or an entitlement without a subject)."""

    def __contains__(self, subject_id):
        return True


def entitled_subjects(user):
    """The ids of the subjects the user's entitlements open today, or Every()."""
    if not user.is_authenticated:
        return set()
    if user.is_staff:  # editors check the course in the app
        return Every()
    today = timezone.localdate()
    ids = set(
        user.entitlements.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)).values_list(
            "subject_id", flat=True
        )
    )
    return Every() if None in ids else ids


def is_free_clip(clip):
    """The first clip of every revision (and any clip marked as a free preview), while LEARN_FREE_PREVIEW is on."""
    first = clip.revision.clips.order_by("order", "pk").values_list("pk", flat=True).first()
    return settings.LEARN_FREE_PREVIEW and (clip.is_free_preview or clip.pk == first)


def is_free_chapter(chapter):
    """All flash cards of a subject's first chapter are free, while LEARN_FREE_PREVIEW is on."""
    first = Chapter.objects.filter(subject=chapter.subject_id).aggregate(first=Min("number"))["first"]
    return settings.LEARN_FREE_PREVIEW and chapter.number == first


class CodeError(Exception):
    pass


def make_codes(subject, count, batch):
    """`count` new book codes for `subject` (None: all subjects); only their digests are kept, so the list returned
    (XXXX-XXXX-XXXX) is the only copy of the codes."""
    codes = set()
    while len(codes) < count:
        codes.add("".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)))
    BookCode.objects.bulk_create(BookCode(digest=code_digest(c), subject=subject, batch=batch) for c in codes)
    return sorted(f"{c[:4]}-{c[4:8]}-{c[8:]}" for c in codes)


def redeem(user, code):
    """A book code typed in the app: an entitlement for LEARN_ACCESS_DAYS, once per code (again for the same user it
    returns the same entitlement). Raises CodeError with the reason to show. Rate-limited by the API (5 an hour per
    user and per address); every attempt is logged, without the code."""
    code = clean_code(code)
    if len(code) != CODE_LENGTH or set(code) - set(CODE_ALPHABET):
        raise CodeError("A book code has 12 letters and digits, like 7KQM-3XPA-9TRW.")
    with transaction.atomic():
        book_code = BookCode.objects.select_for_update().filter(digest=code_digest(code)).first()
        if book_code is None:
            logger.warning("book code refused for user %s: unknown", user.pk)
            raise CodeError("This code is not valid. Check it against the one printed in your book.")
        reference = f"code #{book_code.pk}"
        if book_code.redeemed_by_id == user.pk:
            return Entitlement.objects.filter(user=user, reference=reference).first()
        if book_code.redeemed_at:
            logger.warning("book code #%s refused for user %s: used already", book_code.pk, user.pk)
            raise CodeError("This code has been used already.")
        book_code.redeemed_by, book_code.redeemed_at = user, timezone.now()
        book_code.save(update_fields=["redeemed_by", "redeemed_at"])
        entitlement = Entitlement.objects.create(
            user=user,
            subject=book_code.subject,
            source=Entitlement.Source.BOOK_CODE,
            reference=reference,
            valid_until=timezone.localdate() + timedelta(days=settings.LEARN_ACCESS_DAYS),
        )
    logger.info("book code #%s redeemed by user %s", book_code.pk, user.pk)
    return entitlement


def grant_for_order(order):
    """For the shop to call once an order is paid (or placed): each digital product in it ("digital" kind, alone or in
    a bundle) opens its subject (all subjects without one) for LEARN_ACCESS_DAYS to the order's account. Guest orders
    get nothing (no account to open it for). Calling it again changes nothing. Returns the entitlements."""
    if order.user_id is None:
        return []
    until = timezone.localdate() + timedelta(days=settings.LEARN_ACCESS_DAYS)
    granted = []
    for item in order.items.select_related("product"):
        for product in [item.product, *(bundled.product for bundled in item.product.bundle_items.all())]:
            if product.kind == "digital":
                entitlement, _ = Entitlement.objects.get_or_create(
                    user_id=order.user_id,
                    source=Entitlement.Source.PURCHASE,
                    reference=order.number,
                    subject_id=product.subject_id,
                    defaults={"valid_until": until},
                )
                granted.append(entitlement)
    return granted


def revoke_for_order(order):
    """For the shop to call when a paid order is cancelled or refunded: what it opened closes. Returns how many."""
    return Entitlement.objects.filter(source=Entitlement.Source.PURCHASE, reference=order.number).delete()[0]
