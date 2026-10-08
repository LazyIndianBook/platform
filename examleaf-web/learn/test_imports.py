"""Chapter weights and previous-year frequencies from the production files, and quiz items from one-mark questions."""

import io
import json
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from content.models import Question, Solution
from content.tests import make_paper

from .models import Chapter, QuizItem

pytestmark = pytest.mark.django_db


def test_chapter_weights_and_frequencies(tmp_path):
    subject = make_paper().book.subject
    folder = tmp_path / "production" / "physics"
    (folder / "pyq").mkdir(parents=True)
    chapters = [
        {"ch": 1, "title": "Electric Charges and Fields", "unit": "I", "unit_marks": 9},
        {"ch": 2, "title": "Electrostatic Potential", "unit": "I", "unit_marks": 9},
        {"ch": 3, "title": "Current Electricity", "unit": "II", "unit_marks": 8},
        {"ch": 3, "title": "Current Electricity (again)", "part": "Zoology", "unit": "Z-II", "unit_marks": 1},
    ]
    (folder / "format.json").write_text(json.dumps({"code": "PHY", "full_marks": 70, "chapters": chapters}))
    rows = "| 1 | 2025 | Topic | A question? |\n| 2 | 2019 | Topic | Another one |\n"
    (folder / "pyq" / "ch01.md").write_text(
        f"# Real board questions\n\n| Marks | Year | Topic | Question |\n|---|---|---|---|\n{rows}"
    )
    call_command("import_chapter_insights", root=str(tmp_path), subject=["physics"], stdout=io.StringIO())
    got = {c.number: (c.title, c.weight, c.frequency) for c in Chapter.objects.filter(subject=subject)}
    assert got == {
        1: ("Electric Charges and Fields", Decimal("4.5"), 2),
        2: ("Electrostatic Potential", Decimal("4.5"), 0),
        3: ("Current Electricity", Decimal("9.0"), 0),
    }


def one_mark(paper, label, text, answer, options=(), chapter="Ch 1: Electric Charges and Fields"):
    question = Question.objects.create(
        paper=paper, order=Question.objects.count() + 1, label=label, text_md=text, options_json=list(options),
        marks_text="1",
    )  # fmt: skip
    question.tags.add(chapter)
    Solution.objects.create(question=question, body_md=f"**Ans.** {answer} *(1)*")
    return question


def test_a_wrong_book_root_is_said_in_words(tmp_path):
    with pytest.raises(CommandError, match=r"format\.json not found: --root \(BOOK_ROOT\)"):
        call_command("import_chapter_insights", root=str(tmp_path), stdout=io.StringIO())


def test_quiz_items_from_one_mark_questions():
    paper = make_paper()
    Chapter.objects.create(subject=paper.book.subject, number=1, title="Electric Charges and Fields")
    options = ["(i) charge", "(ii) energy", "(iii) momentum"]
    one_mark(
        paper, "1(a)", "Kirchhoff's junction rule follows from the conservation of: (Choose)", "(i) charge", options
    )
    one_mark(paper, "1(b)", "A loop feels a net force. (State True or False)", "False — only a torque.")
    one_mark(paper, "1(c)", "The SI unit of power of a lens is the ______. (Fill in the blank)", "dioptre (D)")
    one_mark(paper, "1(d)", "Pick two: (Choose)", "(i) and (iii)", options)  # two options: skipped
    one_mark(paper, "1(e)", "Define one coulomb.", "The charge that …")  # not objective: skipped
    one_mark(paper, "1(f)", "Its value is ______.", "$2\\pi$")  # maths in the blank: skipped
    out = io.StringIO()
    call_command("build_quiz_items", stdout=out)
    items = {item.source.label: (item.kind, item.answer, item.explanation) for item in QuizItem.objects.all()}
    assert items == {
        "1(a)": ("mcq", "1", ""),
        "1(b)": ("true_false", "false", "only a torque."),
        "1(c)": ("fill_blank", "dioptre|D", ""),
    }
    assert "PHY: 3 new, 0 kept" in out.getvalue() and "not one option 1" in out.getvalue()
    call_command("build_quiz_items", stdout=out)  # again: nothing new, editors' changes kept
    assert QuizItem.objects.count() == 3 and "PHY: 0 new, 3 kept" in out.getvalue()
