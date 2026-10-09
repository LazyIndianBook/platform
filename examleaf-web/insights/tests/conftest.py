"""The insights tests' fixtures: Physics of the Assam board with three exam seasons (two past, one ahead) and two PIN
codes of the directory. Helpers to make sales and learners: helpers.py."""

from datetime import timedelta

import pytest

from content.models import Board, ClassLevel, Subject
from insights.models import ExamSeason
from shop.models import PinCode

from .helpers import EXAMS


@pytest.fixture
def physics(db):
    board = Board.objects.create(name="Assam State School Education Board", short_name="ASSEB", state="Assam")
    level = ClassLevel.objects.create(number=12)
    return Subject.objects.create(name="Physics", code="PHY", board=board, class_level=level)


@pytest.fixture
def seasons(physics):
    """(before, last, this): the seasons of 2024-25, 2025-26 and 2026-27."""
    return [
        ExamSeason.objects.create(
            board=physics.board,
            class_level=physics.class_level,
            academic_year=year,
            exam_start=start,
            exam_end=start + timedelta(days=30),
        )
        for year, start in EXAMS.items()
    ]


@pytest.fixture
def directory(db):
    PinCode.objects.create(pin="781001", states=["AS"], districts=["Kamrup Metro"])
    PinCode.objects.create(pin="785001", states=["AS"], districts=["Jorhat"])
