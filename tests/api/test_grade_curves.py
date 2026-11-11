"""Overall ratings are graded on a curve so they spread across A+ to F."""

import collections
import random

import pytest

from scripts.calibrate_overall_grades import prospect_scores
from src.api.grade_curves import (
    GRADES,
    OVERALL_CUTOFFS,
    ROLE_CUTOFFS,
    overall_to_grade,
    role_to_grade,
    team_grade,
)


@pytest.mark.parametrize("kind", OVERALL_CUTOFFS)
def test_cutoffs_cover_a_plus_to_d_minus_in_order(kind):
    cuts = OVERALL_CUTOFFS[kind]
    assert len(cuts) == len(GRADES) - 1
    assert cuts == sorted(cuts, reverse=True)
    assert len(set(cuts)) == len(cuts)


@pytest.mark.parametrize("kind", OVERALL_CUTOFFS)
def test_each_cutoff_starts_its_grade(kind):
    for cut, grade, below in zip(OVERALL_CUTOFFS[kind], GRADES, GRADES[1:]):
        assert overall_to_grade(cut, kind) == grade
        assert overall_to_grade(cut - 0.05, kind) == below


def test_bottom_and_missing():
    assert overall_to_grade(0, "hitter") == "F"
    assert overall_to_grade(None, "prospect") == "?"


def test_a_draft_class_spreads_across_the_grades():
    scores = prospect_scores(2, random.Random(7))
    counts = collections.Counter(overall_to_grade(s, "prospect") for s in scores)
    share = {g: counts[g] / len(scores) for g in GRADES}

    assert share["A-"] + share["A"] + share["A+"] > 0.005
    assert share["D+"] + share["D"] + share["D-"] + share["F"] > 0.10
    assert max(share.values()) < 0.25


def test_free_agents_are_graded_on_the_pro_scale():
    from types import SimpleNamespace

    from src.api.view_models.player_cards import overall_kind, overall_value

    hitter = SimpleNamespace(player_type="hitter")
    ratings = {"prospect": 70, "overall_player": 55}
    assert overall_kind("free_agent", hitter) == "hitter"
    assert overall_value("free_agent", hitter, ratings) == 55
    assert overall_kind("prospect", hitter) == "prospect"
    assert overall_value("prospect", hitter, ratings) == 70


@pytest.mark.parametrize("role", ROLE_CUTOFFS)
def test_role_cutoffs_cover_a_plus_to_d_minus_in_order(role):
    cuts = ROLE_CUTOFFS[role]
    assert len(cuts) == len(GRADES) - 1
    assert cuts == sorted(cuts, reverse=True)
    assert len(set(cuts)) == len(cuts)
    for cut, grade, below in zip(cuts, GRADES, GRADES[1:]):
        assert role_to_grade(cut, role) == grade
        assert role_to_grade(cut - 0.05, role) == below


def test_every_shown_role_has_a_curve():
    for role in (
        "sp",
        "rp",
        "cp",
        "lead_off",
        "contact_hitter",
        "power_hitter",
        "overall_offense",
        "best_def",
        "c",
        "1b",
        "2b",
        "3b",
        "ss",
        "lf",
        "cf",
        "rf",
        "if",
        "of",
    ):
        assert role in ROLE_CUTOFFS


def test_role_without_a_curve_uses_the_plain_scale():
    assert role_to_grade(80, "dh") == "A+"
    assert role_to_grade(0, "dh") == "F"
    assert role_to_grade(None, "sp") == "?"


def test_starters_spread_across_the_grades():
    from src.league.offseason.draft_strategy import ratings
    from src.team.team_factory import TeamFactory

    factory = TeamFactory(rng=random.Random(11))
    grades = []
    for i in range(40):
        team = factory.generate_team(city=f"C{i}", mascot="S", size=26)
        grades += [
            role_to_grade(ratings(p)["sp"], "sp")
            for p in team.players
            if p.position == "sp"
        ]
    share = collections.Counter(grades)
    n = len(grades)
    assert (share["A+"] + share["A"] + share["A-"]) / n > 0.01
    assert (share["D+"] + share["D"] + share["D-"] + share["F"]) / n > 0.05
    assert max(share.values()) / n < 0.25


def test_team_grades_are_curved_against_their_own_league():
    """A long-running league's talent climbs; its grades shouldn't."""
    rng = random.Random(3)
    league = [rng.gauss(60.3, 2.4) for _ in range(30)]
    inflated = [v + 5 for v in league]  # every team 5 points better
    for a, b in zip(league, inflated):
        assert team_grade(a, "lineup", league) == team_grade(b, "lineup", inflated)
    grades = [team_grade(v, "lineup", inflated) for v in inflated]
    assert sum(g.startswith("A") for g in grades) <= 6
    assert any(g[0] in "DF" or g.startswith("C") for g in grades)


def test_league_average_team_is_a_c_plus_whatever_the_talent_level():
    league = [70.0, 72.0, 74.0, 76.0, 78.0]
    assert team_grade(74.0, "lineup", league) in ("C+", "C")
    assert team_grade(78.0, "lineup", league).startswith("A")


def test_tiny_or_flat_league_falls_back_to_the_fixed_curve():
    assert team_grade(66, "lineup", [66, 60]) == overall_to_grade(66, "team_lineup")
    flat = [61.0] * 10
    assert team_grade(61.0, "lineup", flat) == overall_to_grade(61.0, "team_lineup")
