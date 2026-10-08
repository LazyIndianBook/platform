import tempfile
from io import StringIO
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User
from content.management.commands.import_papers import FIXTURES, SUBJECTS, import_subject
from content.templatetags.markdown import render

from .models import Board, Book, ClassLevel, Paper, Question, Solution, Subject


def make_paper():
    """One small paper (PHY-E01) with one question and its solution."""
    board = Board.objects.create(name="Assam State School Education Board", short_name="ASSEB", state="Assam")
    subject = Subject.objects.create(
        name="Physics", code="PHY", board=board, class_level=ClassLevel.objects.create(number=12)
    )
    book = Book.objects.create(title="ExamLeaf Physics Sample Papers 2027", subject=subject, slug="physics-2027")
    paper = Paper.objects.create(
        book=book,
        code="PHY-E01",
        tier="E",
        number=1,
        title="Physics Sample Paper E-01",
        full_marks=70,
        pass_marks=21,
        time_text="3 hours",
    )
    question = Question.objects.create(
        paper=paper,
        order=1,
        label="2(c)",
        marks_text="2",
        text_md="A cell of emf 6 V and internal resistance 1 Ω drives 11 Ω. Find the current.",
    )
    Solution.objects.create(
        question=question,
        body_md="| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |\n"
        "| $I = 0.5$ A | 1 |\n\n**Final answer:** 0.5 A",
    )
    return paper


class ImportTests(TestCase):
    """The test copies of content/fixtures/papers/ (E01, M01 and H01 of each subject, and PHY-E02); the books
    repository's 120 papers import the same way (README "Importing the papers")."""

    PAPERS = {"physics": 4, "chemistry": 3, "mathematics": 3, "biology": 3}

    @classmethod
    def setUpTestData(cls):
        cls.stats = {subject: import_subject(FIXTURES, subject) for subject in SUBJECTS}

    def test_four_subjects_every_paper_and_solution_matched(self):
        for subject, stats in self.stats.items():
            with self.subTest(subject):
                self.assertEqual(stats["papers"], self.PAPERS[subject])
                self.assertEqual(stats["unmatched"], [])
                self.assertEqual(stats["missing"], [])
                self.assertEqual(stats["solutions"], stats["questions"])
                papers = Paper.objects.filter(book__subject__name__iexact=subject)
                self.assertEqual(papers.count(), self.PAPERS[subject])
                self.assertEqual(set(papers.values_list("tier", flat=True)), {"E", "M", "H"})
        self.assertFalse(Question.objects.filter(solution__isnull=True).exists())

    def test_labels_and_tags(self):
        self.assertTrue(Question.objects.filter(paper__code="BIO-E01", label="Z3(b)").exists())
        self.assertTrue(Question.objects.get(paper__code="PHY-E01", label="3(a) OR").is_alternative)
        self.assertIn(
            "Ch 1: Electric Charges and Fields", Question.objects.get(paper__code="PHY-E01", label="1(a)").tags.names()
        )

    def test_reimport_changes_nothing(self):
        out = StringIO()
        call_command("import_papers", "--all", "--fixtures", stdout=out)
        self.assertEqual(out.getvalue().count("records created 0, updated 0,"), 4)

    @override_settings(PAPERS_ROOT="")
    def test_no_papers_root_is_said_in_words(self):
        with self.assertRaisesMessage(CommandError, "give --root a checkout of the books repository"):
            call_command("import_papers", "--all")


class MarkdownTests(SimpleTestCase):
    def test_html_and_script_links_in_content_are_escaped(self):
        for text in [
            "<script>alert(1)</script>",
            "<img src=x onerror=alert(1)>",
            "<b onmouseover=alert(1)>x</b>",
            "[x](javascript:alert(1))",
            "![x](javascript:alert(1))",
            "<javascript:alert(1)>",
        ]:
            with self.subTest(text):
                html = render(text)
                self.assertNotRegex(html, r"<(script|img|b)\b|href=\"javascript|src=\"javascript")

    def test_maths_is_left_alone_for_katex_but_escaped(self):
        html = render("| Step | Marks |\n|---|---|\n| $\\mu = \\dfrac{|v_d|}{E}$, $a_1 * b_2$, $x<y$ | 1 |")
        self.assertIn("$\\mu = \\dfrac{|v_d|}{E}$", html)
        self.assertIn("$a_1 * b_2$", html)
        self.assertIn("$x&lt;y$", html)
        self.assertIn('<table class="steps">', html)

    def test_a_quote_inside_maths_cannot_end_an_attribute(self):
        for text in [
            '[a](http://x/ "$" onmouseover="alert(1)$")',
            '[a](http://x/$" onmouseover="alert(1)$)',
            '![a](http://x/$" onerror="alert(1)$)',
            "[a](http://x/ '$' onmouseover='alert(1)$')",
        ]:
            with self.subTest(text):
                self.assertNotRegex(render(text), r"[\"'] ?on\w+=[\"']")

    def test_text_that_looks_like_a_maths_slot_is_just_text(self):
        self.assertEqual(render("MATHX5X and $a$", inline=True), "MATHX5X and $a$")
        self.assertEqual(render("\ue0005\ue001 $a$", inline=True), "5 $a$")


class PaperTests(TestCase):
    """A paper's QR code and who reads its solutions: the website's /s/<code>/ shows what the API gives (api/tests.py
    has the rest), one open sample per book."""

    @classmethod
    def setUpTestData(cls):
        cls.paper = make_paper()
        cls.student = User.objects.create_user("student@example.com", "Brahmaputra-2027", full_name="A Student")
        EmailAddress.objects.create(user=cls.student, email=cls.student.email, verified=True, primary=True)

    def test_qr_image(self):
        self.assertEqual(self.paper.landing_url(), settings.SITE_URL + "/s/PHY-E01/")  # the website's page, printed
        response = self.client.get("/qr/PHY-E01.png")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertEqual(self.client.get("/qr/XYZ-E01.png").status_code, 404)

    def test_solutions_for_students_or_for_everyone_by_setting(self):
        url = "/api/v1/papers/PHY-E01/solutions/"
        for required in (True, False):
            with self.subTest(required=required), override_settings(SOLUTIONS_REQUIRE_LOGIN=required):
                self.client.logout()
                response = self.client.get(url)
                if required:
                    self.assertEqual(response.status_code, 401)
                else:  # open: the same for every visitor, kept a few minutes by shared caches
                    self.assertEqual(sorted(response["Cache-Control"].split(", ")), ["max-age=300", "public"])
                    self.assertEqual(response.json()[0]["solution"]["markdown"][:5], "| Ste")
                self.client.force_login(self.student)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("private", response["Cache-Control"])  # never kept by a shared cache once signed in

    def test_one_open_sample_per_book(self):
        other = Paper.objects.create(
            book=self.paper.book, code="PHY-E02", tier="E", number=2, title="E-02", full_marks=70, pass_marks=21
        )
        self.paper.is_sample = True  # the data migration's choice: each book's E-01
        self.paper.save()
        other.is_sample = True
        with self.assertRaisesMessage(ValidationError, "Another paper of this book is its open sample"):
            other.full_clean()  # one per book (the admin's form says so)


class ExportQrTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_paper()

    def test_refuses_to_print_codes_for_localhost_or_plain_http(self):
        for site in ["http://localhost:8000", "http://127.0.0.1:8000", "http://examleaf.example.com"]:
            with self.subTest(site), override_settings(SITE_URL=site), tempfile.TemporaryDirectory() as out:
                with self.assertRaisesMessage(CommandError, "would not work"):
                    call_command("export_qr", out=out)
                self.assertEqual(list(Path(out).iterdir()), [])

    def test_writes_png_and_svg_for_a_public_https_address(self):
        with override_settings(SITE_URL="https://examleaf.example.com"), tempfile.TemporaryDirectory() as out:
            call_command("export_qr", out=out, stdout=StringIO())
            self.assertEqual(sorted(p.name for p in Path(out).iterdir()), ["PHY-E01.png", "PHY-E01.svg"])
