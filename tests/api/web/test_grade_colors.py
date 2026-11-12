"""Every letter grade has its own color rule, and templates build the class
name the stylesheet expects."""

from pathlib import Path

import pytest

from src.web.utils import grade_class, grade_tier

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


# Single skills shown as numbers (SKILLS_AS_NUMBERS) keep their letter's color.
@pytest.mark.parametrize(
    "shown,cls,tier",
    [
        ("85", "A-plus", "elite"),
        ("56", "B-minus", "good"),
        ("50", "C-plus", "good"),
        ("39", "D-plus", "poor"),
        ("12", "F", "poor"),
        ("C", "C", ""),
    ],
)
def test_skill_numbers_keep_letter_colors(shown, cls, tier):
    assert grade_class(shown) == cls
    assert grade_tier(shown) == tier


def test_skill_to_grade_shows_number_or_letter(monkeypatch):
    import src.api.schemas as schemas

    monkeypatch.setattr(schemas, "SKILLS_AS_NUMBERS", True)
    assert schemas.skill_to_grade(56) == "56"
    assert schemas.skill_to_grade(140) == "100"
    assert schemas.skill_to_grade(None) == "?"
    monkeypatch.setattr(schemas, "SKILLS_AS_NUMBERS", False)
    assert schemas.skill_to_grade(56) == "B-"
