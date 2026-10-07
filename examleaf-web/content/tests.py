from allauth.account.models import EmailAddress
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from content.management.commands.import_papers import SUBJECTS, import_subject

from .models import Board, Book, ClassLevel, Paper, Question, Solution, Subject


def make_paper():
    """One small paper (PHY-E01) with one question and its solution."""
    board = Board.objects.create(name="Assam State School Education Board", short_name="ASSEB", state="Assam")
    subject = Subject.objects.create(name="Physics", code="PHY", board=board, class_level=ClassLevel.objects.create(number=12))
    book = Book.objects.create(title="ExamLeaf Physics Sample Papers 2027", subject=subject, slug="physics-2027")
    paper = Paper.objects.create(book=book, code="PHY-E01", tier="E", number=1, title="Physics Sample Paper E-01",
                                 full_marks=70, pass_marks=21, time_text="3 hours")
    question = Question.objects.create(paper=paper, order=1, label="2(c)", marks_text="2",
                                       text_md="A cell of emf 6 V and internal resistance 1 Ω drives 11 Ω. Find the current.")
    Solution.objects.create(question=question, body_md="| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |\n"
                                                        "| $I = 0.5$ A | 1 |\n\n**Final answer:** 0.5 A")
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
        self.assertIn("Ch 1: Electric Charges and Fields", Question.objects.get(paper__code="PHY-E01", label="1(a)").tags.names())

    def test_reimport_changes_nothing(self):
        counts = import_subject(settings.BOOK_ROOT, "physics")["counts"]
        self.assertEqual((counts["created"], counts["updated"]), (0, 0))


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
        response = self.client.post(reverse("account_login"), {
            "login": "Student@Example.com", "password": "Brahmaputra-2027", "next": "/s/PHY-E01/"})
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
