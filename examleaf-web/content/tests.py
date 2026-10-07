import re
import tempfile
from io import StringIO
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from content.management.commands.import_papers import SUBJECTS, import_subject
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
    @classmethod
    def setUpTestData(cls):
        cls.stats = {subject: import_subject(settings.BOOK_ROOT, subject) for subject in SUBJECTS}

    def test_four_subjects_thirty_papers_every_solution_matched(self):
        for subject, stats in self.stats.items():
            with self.subTest(subject):
                self.assertEqual(stats["papers"], 30)
                self.assertEqual(stats["unmatched"], [])
                self.assertEqual(stats["missing"], [])
                self.assertEqual(stats["solutions"], stats["questions"])
                self.assertEqual(Paper.objects.filter(book__subject__name__iexact=subject).count(), 30)
        self.assertFalse(Question.objects.filter(solution__isnull=True).exists())

    def test_labels_and_tags(self):
        self.assertTrue(Question.objects.filter(paper__code="BIO-E01", label="Z3(b)").exists())
        self.assertTrue(Question.objects.get(paper__code="PHY-E01", label="3(a) OR").is_alternative)
        self.assertIn(
            "Ch 1: Electric Charges and Fields", Question.objects.get(paper__code="PHY-E01", label="1(a)").tags.names()
        )

    def test_reimport_changes_nothing(self):
        counts = import_subject(settings.BOOK_ROOT, "physics")["counts"]
        self.assertEqual((counts["created"], counts["updated"]), (0, 0))


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


class PaperPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.paper = make_paper()
        cls.student = User.objects.create_user("student@example.com", "Brahmaputra-2027", full_name="A Student")
        EmailAddress.objects.create(user=cls.student, email=cls.student.email, verified=True, primary=True)

    def test_qr_landing_code_is_case_insensitive(self):
        self.assertRedirects(self.client.get("/s/phy-e01/"), "/s/PHY-E01/", status_code=301)

    def test_visitor_gets_register_and_login_that_return_here(self):
        response = self.client.get("/s/PHY-E01/")
        self.assertTemplateUsed(response, "landing.html")
        self.assertContains(response, "Solutions to Sample Paper E-01 — Physics")
        self.assertContains(response, reverse("account_signup") + "?next=/s/PHY-E01/")
        self.assertContains(response, reverse("account_login") + "?next=/s/PHY-E01/")
        self.assertNotContains(response, "Final answer")

    def test_login_returns_to_the_paper(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": "Student@Example.com", "password": "Brahmaputra-2027", "next": "/s/PHY-E01/"},
        )
        self.assertRedirects(response, "/s/PHY-E01/")

    def test_student_sees_the_solutions(self):
        self.client.force_login(self.student)
        response = self.client.get("/s/PHY-E01/")
        self.assertTemplateUsed(response, "solutions.html")
        self.assertContains(response, '<table class="steps">')
        self.assertContains(response, "$I = \\dfrac{\\varepsilon}{R+r}$")
        self.assertContains(response, '<p class="final"><strong>Final answer:</strong> 0.5 A</p>')

    def test_qr_image(self):
        response = self.client.get("/qr/PHY-E01.png")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertEqual(self.client.get("/qr/XYZ-E01.png").status_code, 404)

    def test_solutions_page_queries_do_not_grow_with_the_number_of_questions(self):
        self.client.force_login(self.student)

        def queries():
            with CaptureQueriesContext(connection) as context:
                self.assertEqual(self.client.get("/s/PHY-E01/").status_code, 200)
            return len(context)

        before = queries()
        for order in range(2, 12):
            question = Question.objects.create(paper=self.paper, order=order, label=str(order), text_md="Q")
            Solution.objects.create(question=question, body_md="**Final answer:** x")
        self.assertEqual(queries(), before)

    def test_the_paper_page_is_never_kept_by_a_shared_cache(self):
        self.assertIn("private", self.client.get("/s/PHY-E01/")["Cache-Control"])
        self.client.force_login(self.student)
        self.assertIn("private", self.client.get("/s/PHY-E01/")["Cache-Control"])

    def test_login_does_not_redirect_to_another_site(self):
        for url in ["https://evil.example/", "//evil.example/", "/\\evil.example", "javascript:alert(1)"]:
            with self.subTest(url):
                response = self.client.post(
                    reverse("account_login"),
                    {"login": "student@example.com", "password": "Brahmaputra-2027", "next": url},
                )
                self.assertRedirects(response, "/", fetch_redirect_response=False)
                self.client.logout()

    def test_only_this_site_and_katex_are_allowed_to_serve_files_and_nothing_runs_inline(self):
        self.client.force_login(self.student)
        response = self.client.get("/s/PHY-E01/")
        policy = (
            response.headers.get("Content-Security-Policy") or response.headers["Content-Security-Policy-Report-Only"]
        )
        self.assertIn(f"script-src 'self' {settings.KATEX_CDN};", policy)  # the folder, not all of jsDelivr
        self.assertIn("frame-ancestors 'none'", policy)
        page = response.content.decode()
        self.assertEqual(
            {u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', page) if not u.startswith(settings.KATEX_CDN)},
            set(),
        )
        self.assertNotRegex(page, r"\son[a-z]+=")  # an inline handler would need 'unsafe-inline' in script-src


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
