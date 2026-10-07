from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from content.models import Subject
from content.tests import make_paper

from .models import Attempt


class AttemptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.paper = make_paper()
        cls.student = User.objects.create_user("student@example.com", full_name="A Student")
        cls.other = User.objects.create_user("other@example.com", full_name="Another Student")

    def setUp(self):
        self.client.force_login(self.student)

    def test_record_an_attempt_from_the_solutions_page(self):
        self.assertContains(self.client.get("/s/PHY-E01/"), reverse("attempt_add", args=["PHY-E01"]))
        response = self.client.post(reverse("attempt_add", args=["PHY-E01"]), {
            "date": "2026-10-01", "marks_obtained": "52.5", "time_taken_minutes": "170", "notes": "optics"})
        self.assertRedirects(response, reverse("record"))
        attempt = Attempt.objects.get()
        self.assertEqual((attempt.user, attempt.paper, attempt.marks_obtained), (self.student, self.paper, Decimal("52.5")))
        record = self.client.get(reverse("record"))
        self.assertContains(record, "52.5/70")
        self.assertEqual(record.context["averages"], [("Easy", 1, 75)])

    def test_marks_cannot_exceed_full_marks(self):
        response = self.client.post(reverse("attempt_add", args=["PHY-E01"]), {"date": "2026-10-01", "marks_obtained": "71"})
        self.assertIn("marks_obtained", response.context["form"].errors)
        self.assertFalse(Attempt.objects.exists())

    def test_edit_own_attempt_only(self):
        mine = Attempt.objects.create(user=self.student, paper=self.paper, marks_obtained=40)
        theirs = Attempt.objects.create(user=self.other, paper=self.paper, marks_obtained=30)
        response = self.client.post(reverse("attempt_edit", args=[mine.pk]), {"date": "2026-10-02", "marks_obtained": "45"})
        self.assertRedirects(response, reverse("record"))
        mine.refresh_from_db()
        self.assertEqual(mine.marks_obtained, 45)
        self.assertEqual(self.client.get(reverse("attempt_edit", args=[theirs.pk])).status_code, 404)

    def test_visitor_is_sent_to_log_in(self):
        self.client.logout()
        response = self.client.get(reverse("record"))
        self.assertRedirects(response, reverse("account_login") + "?next=" + reverse("record"))

    def test_my_record_queries_do_not_grow_with_the_number_of_subjects(self):
        Attempt.objects.create(user=self.student, paper=self.paper, marks_obtained=40)

        def queries():
            with CaptureQueriesContext(connection) as context:
                self.assertContains(self.client.get(reverse("record")), "PHY-E01")
            return len(context)

        before = queries()
        subject = Subject.objects.get()
        for code in ("CHE", "MAT", "BIO"):  # the subject filter prints "name (board, class)" for each of them
            Subject.objects.create(name=code, code=code, board=subject.board, class_level=subject.class_level)
        self.assertEqual(queries(), before)
