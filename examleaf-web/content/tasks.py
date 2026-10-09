"""The content module's nightly jobs (settings.CELERY_BEAT_SCHEDULE, "content-*"): the quiz items the item analysis
flags join the triage queue as reports (after insights' run), the reports set apart as spam go after 30 days, and
each published book whose legal deposits are not all recorded has its inbox item, due on the last day of the
deposit's days (CONTENT_LEGAL_DEPOSIT_DAYS), closed once the four libraries have it. Each is safe to run twice."""

from datetime import datetime, time, timedelta

from celery import shared_task
from django.utils import timezone

from staff.models import InboxItem
from staff.signals import close_items, open_item

from . import reports
from .models import Book, LegalDeposit


@shared_task
def flag_items():
    return reports.flag_items()


@shared_task
def purge_spam():
    return reports.purge_spam()


def deposit_item(book, missing):
    """A published book's inbox item while libraries miss its edition (due at the end of its last day, India time);
    closed once none does."""
    if not missing or book.published_on is None:
        close_items(book, InboxItem.Kind.LEGAL_DEPOSIT)
        return
    due = timezone.make_aware(datetime.combine(book.deposit_due_on + timedelta(days=1), time.min))
    title = f"Legal deposit: {book.title}, {book.edition or 'its edition'} ({len(missing)} of 4 libraries to send)"
    open_item(InboxItem.Kind.LEGAL_DEPOSIT, book, title, "content.add_legaldeposit", due, subject=book.subject.code)
    InboxItem.objects.filter(
        kind=InboxItem.Kind.LEGAL_DEPOSIT, target_type="content.book", target_id=str(book.pk), done_at=None
    ).update(title=title[:200], due_at=due)  # fewer libraries left, or a new edition's date


@shared_task
def check_legal_deposits():
    """Nightly: every published book's item opened, brought up to date or closed (run twice, one item a book)."""
    books = list(Book.objects.filter(published_on__isnull=False).select_related("subject"))
    missing = LegalDeposit.missing(books)
    for book in books:
        deposit_item(book, missing[book.pk])
    return sum(1 for book in books if missing[book.pk])
