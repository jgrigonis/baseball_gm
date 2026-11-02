"""Every letter grade has its own color rule, and templates build the class
name the stylesheet expects."""

from pathlib import Path

import pytest

from src.web.utils import grade_class

GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
CSS = (Path(__file__).parents[3] / "src/web/static/css/main.css").read_text()


@pytest.mark.parametrize(
    "grade,cls",
    [("A+", "A-plus"), ("A", "A"), ("B-", "B-minus"), ("F", "F"), (None, "?")],
)
def test_grade_class(grade, cls):
    assert grade_class(grade) == cls


@pytest.mark.parametrize("grade", GRADES)
def test_every_grade_has_a_color_rule(grade):
    assert f".grade-{grade_class(grade)} " in CSS
