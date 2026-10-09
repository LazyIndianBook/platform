"""The content module's test helpers: papers of a subject with their questions and solutions, members of staff
narrowed to a subject, and the staff tests' sign-in (staff/tests/conftest.py)."""

import pytest

from accounts import roles
from staff.models import StaffScope
from staff.tests.conftest import STAFF, events, make_staff, signed_in  # noqa: F401  (the content tests' helpers)

from .models import Board, Book, ClassLevel, Paper, Question, Solution, Subject

CONTENT = STAFF + "content/"
NAMES = {"PHY": "Physics", "CHE": "Chemistry", "MAT": "Mathematics", "BIO": "Biology"}
SOLUTION = (
    "| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |\n| $I = 0.5$ A | 1 |\n\n"
    "**Final answer:** 0.5 A"
)


@pytest.fixture(autouse=True)
def quick_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # many users per test


def make_paper(subject="PHY", code=None, labels=("2(c)",), number=1):
    """A paper of `subject` (its book made once) with a question and a solution per label."""
    board, _ = Board.objects.get_or_create(
        short_name="ASSEB", defaults={"name": "Assam State School Education Board", "state": "Assam"}
    )
    level, _ = ClassLevel.objects.get_or_create(number=12)
    subject, _ = Subject.objects.get_or_create(
        board=board, class_level=level, code=subject, defaults={"name": NAMES[subject]}
    )
    book, _ = Book.objects.get_or_create(
        slug=f"{subject.name.lower()}-2027",
        defaults={
            "title": f"ExamLeaf {subject.name} Sample Papers 2027",
            "subject": subject,
            "edition": "First edition, 2026",
        },
    )
    paper = Paper.objects.create(
        book=book,
        code=code or f"{subject.code}-E{number:02d}",
        tier="E",
        number=number,
        title=f"{subject.name} Sample Paper E-{number:02d}",
        full_marks=70,
        pass_marks=21,
        time_text="3 hours",
    )
    for order, label in enumerate(labels, 1):
        question = Question.objects.create(
            paper=paper, order=order, label=label, marks_text="2", text_md=f"A cell drives a current ({label})."
        )
        Solution.objects.create(question=question, body_md=SOLUTION)
    return paper


def narrowed(role, *subjects):
    """A member of staff of `role`, narrowed to these subjects (StaffScope)."""
    user = make_staff(role)
    for code in subjects:
        StaffScope.objects.create(user=user, kind=StaffScope.Kind.SUBJECT, value=code)
    return type(user).objects.get(pk=user.pk)


@pytest.fixture
def editor():
    return narrowed(roles.CONTENT_EDITOR, "PHY")


@pytest.fixture
def reviewer():
    return narrowed(roles.REVIEWER, "PHY")
