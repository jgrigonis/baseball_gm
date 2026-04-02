# tests/api/web/test_compute_ratings.py

import pytest
from unittest.mock import patch
from src.api.routers.web import _compute_ratings


@pytest.fixture
def mock_skills_data():
    return {
        "ss": 80,
        "2b": 70,
        "3b": 60,
        "lf": 50,
        "cf": 55,
        "rf": 50,
        "c": 40,
        "1b": 45,
        "extra_field": "ignore_me",
    }


@patch("src.api.routers.web.PlayerEvaluator")
@patch("src.api.routers.web.PlayerSkills")
def test_compute_ratings_success(mock_ps_cls, mock_pe_cls, mock_skills_data):
    # Setup mock return for PlayerEvaluator.rate_player
    mock_ratings = {k: v for k, v in mock_skills_data.items() if k != "extra_field"}
    mock_pe_cls.rate_player.return_value = mock_ratings.copy()

    result = _compute_ratings(mock_skills_data, "R")

    # Verify filtering: PlayerSkills should be called without "extra_field"
    # Note: This depends on what's in your SKILLS constant
    assert "extra_field" not in mock_ps_cls.call_args[0][0]

    # Check calculated composites
    assert result["if"] == 80  # max(80, 70, 60)
    assert result["of"] == 55  # max(50, 55, 50)
    assert result["best_def"] == 80
    assert result["best_def_label"] == "IF"


@pytest.mark.parametrize(
    "high_skill, expected_label",
    [
        ({"c": 90, "ss": 10}, "CA"),
        ({"1b": 90, "ss": 10}, "1B"),
        ({"lf": 90, "ss": 10}, "OF"),
        ({"ss": 90, "c": 10}, "IF"),
    ],
)
@patch("src.api.routers.web.PlayerEvaluator")
@patch("src.api.routers.web.PlayerSkills")
def test_compute_ratings_labels(mock_ps, mock_pe, high_skill, expected_label):
    # Mocking different high scores to test the if/elif logic
    mock_pe.rate_player.return_value = {
        "2b": 0,
        "3b": 0,
        "ss": 0,
        "lf": 0,
        "cf": 0,
        "rf": 0,
        "c": 0,
        "1b": 0,
        **high_skill,
    }

    result = _compute_ratings({}, "L")
    assert result["best_def_label"] == expected_label


def test_compute_ratings_exception():
    # Test that it returns an empty dict on failure (e.g., passing None)
    result = _compute_ratings(None, "R")
    assert result == {}
