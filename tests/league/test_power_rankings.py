# tests/league/test_power_rankings.py
"""Team strength for the Power Rankings: what each area weighs, where the
starting nine play, and how results take over from ratings."""

import pytest

from src.api.view_models.power_rankings import (
    expected_wins,
    rank_grade,
    ranks,
    records,
)
from src.league.offseason.draft_strategy import ratings
from src.league.power_rankings import (
    RESULTS_HALF,
    power_scores,
    results_weight,
    starting_nine,
    team_strength,
)
from src.player.player_skills import PlayerSkills
from tests.factories.player_record_factory import make_player_record


def hitter(position="2b", **skills):
    base = dict(contact=50, power=50, eye=50, speed=50, base_running=50, arm=50)
    base.update(skills)
    p = make_player_record(position=position, skills=PlayerSkills(base))
    return p, ratings(p)


def pitcher(position="sp", **skills):
    base = dict(accuracy=50, strikes=50, stamina=50, ground_balls=50, recovery=50)
    base.update(skills)
    p = make_player_record(position=position, skills=PlayerSkills(base))
    return p, ratings(p)


def staff(sp, rp):
    groups = {p.id: "sp" for p, _ in sp}
    groups.update({p.id: "rp" for p, _ in rp})
    return groups


class TestTeamStrength:
    def test_control_counts_more_than_stamina(self):
        # The engine: +10 control saves far more runs than +10 stamina.
        control = [pitcher(accuracy=70) for _ in range(5)]
        workhorse = [pitcher(stamina=70) for _ in range(5)]
        a = team_strength(control, staff(control, []))
        b = team_strength(workhorse, staff(workhorse, []))
        assert a["pitching"] > b["pitching"]

    def test_defense_is_the_glove_at_the_position_played(self):
        # A great glove at a position he doesn't play doesn't help.
        catcher = hitter("c", catching=90, infield=10, outfield=10)
        fielders = [
            hitter("2b", infield=60, outfield=60, catching=10) for _ in range(9)
        ]
        with_c = team_strength([catcher] + fielders, {})
        without = team_strength(fielders, {})
        assert with_c["defense"] > without["defense"]

    def test_empty_roster_scores_zero(self):
        assert team_strength([], {}) == {"hitting": 0, "pitching": 0, "defense": 0}


class TestStartingNine:
    def test_fills_every_spot_once(self):
        hitters = [hitter("c", catching=80)] + [
            hitter("cf", outfield=70) for _ in range(10)
        ]
        nine = starting_nine(hitters)
        positions = sorted(pos for _, pos in nine)
        assert positions == sorted(
            ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]
        )
        assert dict((pos, p) for p, pos in nine)["c"] is hitters[0][0]


class TestBlend:
    def test_no_games_is_ratings_only(self):
        strength = {
            "a": {"hitting": 60, "pitching": 60, "defense": 60},
            "b": {"hitting": 40, "pitching": 40, "defense": 40},
        }
        scores = power_scores(strength, {})
        assert scores["a"]["power"] > scores["b"]["power"]

    def test_results_take_over(self):
        strength = {
            "a": {"hitting": 60, "pitching": 60, "defense": 60},
            "b": {"hitting": 40, "pitching": 40, "defense": 40},
        }
        # The weaker roster has outscored the stronger one all season.
        recs = {
            "a": {"g": 150, "rs": 600, "ra": 700},
            "b": {"g": 150, "rs": 700, "ra": 600},
        }
        scores = power_scores(strength, recs)
        assert scores["b"]["power"] > scores["a"]["power"]
        # Defense stays ratings only.
        assert scores["a"]["defense"] > scores["b"]["defense"]

    def test_half_and_half_at_results_half(self):
        assert results_weight(0) == 0
        assert results_weight(RESULTS_HALF) == pytest.approx(0.5)
        assert results_weight(162) > 0.8


class TestPageHelpers:
    def test_records_and_cutoff(self):
        games = [
            {
                "game_date": "2025-04-01",
                "home_team_id": "a",
                "away_team_id": "b",
                "home_score": 5,
                "away_score": 3,
            },
            {
                "game_date": "2025-04-09",
                "home_team_id": "b",
                "away_team_id": "a",
                "home_score": 2,
                "away_score": 1,
            },
        ]
        now = records(games)
        assert now["a"]["w"] == 1 and now["a"]["l"] == 1
        assert now["a"]["rs"] == 6 and now["a"]["ra"] == 5
        assert now["a"]["results"] == [False, True]  # most recent first
        assert records(games, before="2025-04-05")["b"]["g"] == 1

    def test_ranks_and_grades(self):
        assert ranks({"a": 1.0, "b": 3.0, "c": 2.0}) == {"b": 1, "c": 2, "a": 3}
        assert rank_grade(1, 30) == "A"
        assert rank_grade(30, 30) == "F"

    def test_expected_wins_even_when_runs_even(self):
        assert expected_wins({"g": 100, "rs": 450, "ra": 450}) == pytest.approx(50)
