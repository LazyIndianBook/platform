"""The content module's staff API beyond the review and the triage: the person's subjects narrowing every list and
hiding another subject's record (404), lists read with a fixed number of queries, the ISBN checked (on the book and on
the product), legal deposits with their inbox item (once, and closed when the four libraries have it), the module's
home per role, and a paper's QR code (refused on a plain-http or local address)."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts import roles
from shop.factories import ProductFactory
from staff.models import InboxItem

from .conftest import CONTENT, events, make_paper, make_staff, narrowed, signed_in
from .models import Book, ErrorReport, LegalDeposit, Paper, Question, ReviewTask, Solution
from .tasks import check_legal_deposits

pytestmark = pytest.mark.django_db
ISBN = "978-0-306-40615-7"  # a valid ISBN-13 (its check digit right)


def queries(client, path):
    client.get(path)  # (the site's switches, read once into the cache)
    with CaptureQueriesContext(connection) as captured:
        assert client.get(path).status_code == 200
    return len(captured)


def test_a_subject_narrows_every_list_and_another_subjects_record_is_not_found(editor):
    physics, chemistry = make_paper(), make_paper("CHE")
    client = signed_in(editor)
    assert [row["code"] for row in client.get(f"{CONTENT}papers/").json()["results"]] == ["PHY-E01"]
    assert [row["subject_code"] for row in client.get(f"{CONTENT}books/").json()["results"]] == ["PHY"]
    assert {row["paper_code"] for row in client.get(f"{CONTENT}questions/").json()["results"]} == {"PHY-E01"}
    assert {row["paper_code"] for row in client.get(f"{CONTENT}solutions/").json()["results"]} == {"PHY-E01"}
    other = Solution.objects.get(question__paper=chemistry)
    assert client.get(f"{CONTENT}papers/{chemistry.pk}/").status_code == 404
    assert client.get(f"{CONTENT}solutions/{other.pk}/").status_code == 404
    assert client.patch(f"{CONTENT}solutions/{other.pk}/", {"body_md": "x"}, format="json").status_code == 404
    assert client.get(f"{CONTENT}papers/{physics.pk}/").json()["tree"][0]["label"] == "2(c)"
    # filters by board, class and subject, in the address
    owner = signed_in(make_staff(roles.OWNER))
    assert len(owner.get(f"{CONTENT}papers/?subject=CHE").json()["results"]) == 1
    assert len(owner.get(f"{CONTENT}papers/?board=ASSEB&class_level=12").json()["results"]) == 2
    assert owner.get(f"{CONTENT}papers/?q=phy-e").json()["results"][0]["code"] == "PHY-E01"


def test_the_lists_read_with_a_fixed_number_of_queries(editor):
    client = signed_in(make_staff(roles.OWNER))
    make_paper(labels=("1", "2"))
    Book.objects.update(published_on=date(2026, 10, 1))  # (a book whose deposits are due: the home reads them)
    paths = ["books/", "papers/", "questions/", "solutions/", "reviews/", "reports/", "errata/", "legal-deposits/",
             "imports/", "summary/"]  # fmt: skip
    one = {path: queries(client, CONTENT + path) for path in paths}
    for number in (2, 3, 4):
        paper = make_paper(code=f"PHY-E{number:02d}", number=number, labels=("1", "2", "3"))
        solution = Solution.objects.filter(question__paper=paper).first()
        signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": "$x$"}, format="json")
        signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json")
        ErrorReport.objects.create(target=solution, subject=paper.book.subject, paper=paper, question=solution.question,
                                   category="typo", state="confirmed")  # fmt: skip
    LegalDeposit.objects.create(book=Book.objects.get(), edition="First edition, 2026", library="connemara",
                                sent_on=date(2026, 10, 5), proof="Speed Post EA1IN")  # fmt: skip
    assert ReviewTask.objects.count() == 3 and ErrorReport.objects.count() == 3
    assert {path: queries(client, CONTENT + path) for path in paths} == one


def test_an_isbn_is_checked_on_the_book_and_on_the_product(editor):
    paper = make_paper()
    client = signed_in(editor)
    url = f"{CONTENT}books/{paper.book.pk}/"
    assert client.patch(url, {"isbn": "978-0-306-40615-8"}, format="json").json()["isbn"] == [
        "Not a valid ISBN-13: 13 digits starting 978 or 979, the last one its check digit (hyphens may stay)."
    ]
    assert client.patch(url, {"isbn": "0-306-40615-2"}, format="json").status_code == 400  # an ISBN-10
    saved = client.patch(url, {"isbn": ISBN, "format": "print"}, format="json")
    assert saved.status_code == 200 and saved.json()["isbn"] == "9780306406157"
    assert events("content.book_changed").get().changes == {"isbn": ["", "9780306406157"]}
    made = client.post(
        f"{CONTENT}books/",
        {"title": "ExamLeaf Physics (e-book)", "subject": paper.book.subject_id, "slug": "physics-ebook",
         "format": "ebook", "isbn": ISBN},
        format="json",
    )  # fmt: skip
    assert made.status_code == 400 and made.json()["isbn"] == [
        "Another book has this ISBN: each format and edition has its own."
    ]
    product = ProductFactory(isbn="978-0-306-40615-8")  # saved before the check: left alone until changed
    product.full_clean()
    product.isbn = "978-0-306-40615-9"
    with pytest.raises(ValidationError) as refused:
        product.full_clean()
    assert "isbn" in refused.value.message_dict
    product.isbn = ISBN
    product.full_clean()


def test_legal_deposits_open_one_inbox_item_and_close_it_with_the_fourth_library(editor, settings):
    paper = make_paper()
    book = paper.book
    Book.objects.filter(pk=book.pk).update(published_on=timezone.localdate() - timedelta(days=31))
    assert check_legal_deposits() == 1 and check_legal_deposits() == 1  # run twice: one item
    item = InboxItem.objects.get(kind=InboxItem.Kind.LEGAL_DEPOSIT, done_at=None)
    assert item.title.endswith("(4 of 4 libraries to send)") and item.due_at < timezone.now()  # overdue
    assert (item.permission, item.data["subject"]) == ("content.add_legaldeposit", "PHY")
    client = signed_in(editor)
    missing = client.get(f"{CONTENT}legal-deposits/missing/").json()
    assert missing[0]["book"] == book.pk and missing[0]["overdue"] is True and len(missing[0]["missing"]) == 4
    scan = SimpleUploadedFile("proof.pdf", b"%PDF-1.4 proof", content_type="application/pdf")
    first = client.post(
        f"{CONTENT}legal-deposits/",
        {"book": book.pk, "library": "national_library", "sent_on": "2026-10-02", "proof": "Speed Post EA1IN",
         "proof_file": scan},
        format="multipart",
    )  # fmt: skip
    assert first.status_code == 201, first.content
    assert first.json()["edition"] == "First edition, 2026" and first.json()["has_file"] is True
    assert client.get(f"{CONTENT}legal-deposits/{first.json()['id']}/proof/").status_code == 200
    again = client.post(f"{CONTENT}legal-deposits/", {"book": book.pk, "library": "national_library",
                                                     "sent_on": "2026-10-02", "proof": "x"}, format="json")  # fmt: skip
    assert again.json() == {"library": ["This library has this edition already."]}
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    later = client.post(f"{CONTENT}legal-deposits/", {"book": book.pk, "library": "connemara", "sent_on": tomorrow,
                                                     "proof": "x"}, format="json")  # fmt: skip
    assert "sent_on" in later.json()
    for library in ["connemara", "asiatic_society", "delhi_public_library"]:
        deposit = {"book": book.pk, "library": library, "sent_on": "2026-10-03", "proof": "Speed Post"}
        answer = client.post(f"{CONTENT}legal-deposits/", deposit, format="json")
        assert answer.status_code == 201
    assert not InboxItem.objects.filter(kind=InboxItem.Kind.LEGAL_DEPOSIT, done_at=None).exists()
    assert client.get(f"{CONTENT}legal-deposits/missing/").json() == []
    assert events("content.legal_deposit_recorded").count() == 4
    # a new edition needs its own four
    client.patch(f"{CONTENT}books/{book.pk}/", {"edition": "Second edition, 2027"}, format="json")
    assert InboxItem.objects.filter(kind=InboxItem.Kind.LEGAL_DEPOSIT, done_at=None).count() == 1
    reviewer = signed_in(narrowed(roles.REVIEWER, "PHY"))
    assert reviewer.post(f"{CONTENT}legal-deposits/", {}, format="json").status_code == 403


def test_the_modules_home_counts_for_each_role(editor):
    paper = make_paper(labels=("1", "2"))
    solution = Solution.objects.filter(question__paper=paper).first()
    signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": "$y$"}, format="json")
    signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json")
    ErrorReport.objects.create(target=solution, subject=paper.book.subject, category="typo")
    ErrorReport.objects.create(target=solution, subject=paper.book.subject, category="typo", spam=True)
    Book.objects.update(published_on=date(2026, 10, 1))
    mine = signed_in(editor).get(f"{CONTENT}summary/").json()
    assert mine["reports_open"] == {"total": 1, "by_category": {"typo": 1}} and mine["drafts"] == 1
    assert mine["reviews_waiting"] == 1 and mine["reviews_mine"] is None  # an editor publishes nothing
    assert len(mine["legal_deposits_missing"]) == 1
    reviewer = signed_in(narrowed(roles.REVIEWER, "PHY")).get(f"{CONTENT}summary/").json()
    assert reviewer["reviews_mine"] == 1
    support = signed_in(make_staff(roles.SUPPORT)).get(f"{CONTENT}summary/").json()
    assert support["reports_open"]["total"] == 1 and support["drafts"] is None and support["reviews_waiting"] is None
    assert signed_in(narrowed(roles.CONTENT_EDITOR, "CHE")).get(f"{CONTENT}summary/").json()["reports_open"] == {
        "total": 0,
        "by_category": {},
    }


def test_a_papers_qr_code_prints_an_address_we_control_and_never_a_local_one(settings, editor):
    paper = make_paper()
    client = signed_in(editor)
    settings.SITE_URL = "http://localhost:8000"
    refused = client.get(f"{CONTENT}papers/{paper.pk}/qr/")
    assert refused.status_code == 400 and refused.json()["code"] == "site_url_not_public"
    settings.SITE_URL = "https://examleaf.in"
    code = client.get(f"{CONTENT}papers/{paper.pk}/qr/").json()
    assert code["url"] == "https://examleaf.in/s/PHY-E01/" and code["png"].startswith("data:image/png;base64,iVBOR")


def test_a_question_no_longer_in_the_books_leaves_the_site_but_not_the_panel(editor):
    paper = make_paper(labels=("1", "2"))
    Question.objects.filter(label="2").update(is_published=False)
    from rest_framework.test import APIClient

    from content.views import cache_solutions  # noqa: F401  (the public page reads the same API)

    open_api = APIClient()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("django.conf.settings.SOLUTIONS_REQUIRE_LOGIN", False)
        labels = [row["label"] for row in open_api.get(f"/api/v1/papers/{paper.code}/solutions/").json()]
    assert labels == ["1"]
    tree = signed_in(editor).get(f"{CONTENT}papers/{paper.pk}/").json()["tree"]
    assert [(row["label"], row["is_published"]) for row in tree] == [("1", True), ("2", False)]
    assert Paper.objects.get().questions.count() == 2
