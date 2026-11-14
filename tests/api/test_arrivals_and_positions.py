# tests/api/test_arrivals_and_positions.py
"""The NEW tag for a week after a player joins (src/api/services/arrivals.py)
and the player card's main and second positions
(src/api/view_models/player_detail.py)."""

from unittest.mock import patch

from src.api.services import arrivals
from src.api.view_models.player_detail import _mark_positions


def _defense(*keys):
    return [{"section": "Defense", "skills": [{"key": k} for k in keys]}]


def test_main_spot_and_a_regular_second_spot_are_marked():
    grades = _defense("c", "1b", "ss", "cf")
    starts = {
        "ss": {"season": 60, "career": 300},
        "cf": {"season": 25, "career": 40},
        "1b": {"season": 5, "career": 5},
        "dh": {"season": 30, "career": 30},
    }
    _mark_positions(grades, starts)
    by = {s["key"]: s for s in grades[0]["skills"]}
    assert by["ss"].get("main") and not by["ss"].get("second")
    assert by["cf"].get("second")  # 25 of 90 field starts
    assert not by["1b"].get("second") and not by["1b"].get("main")
    assert "starts" not in by["c"]
    assert by["ss"]["starts"] == "60 starts here this season, 300 in his career"


def test_before_he_plays_this_season_his_career_decides():
    grades = _defense("c", "lf")
    _mark_positions(
        grades,
        {"c": {"season": 0, "career": 10}, "lf": {"season": 0, "career": 200}},
    )
    by = {s["key"]: s for s in grades[0]["skills"]}
    assert by["lf"].get("main") and not by["c"].get("second")


def test_new_arrivals_are_tagged_for_a_week(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    team = factory.team()
    factory.league_season_team(league, season, team)
    fresh = factory.rated_player(team, league, 50)
    old = factory.rated_player(team, league, 50)
    db_conn.execute(
        "UPDATE team_players SET joined_on = %s WHERE player_id = %s",
        ("2025-06-01", fresh.id),
    )
    db_conn.execute(
        "UPDATE team_players SET joined_on = %s WHERE player_id = %s",
        ("2025-05-20", old.id),
    )
    cards = [{"player_id": fresh.id}, {"player_id": old.id}]
    with patch.object(arrivals, "today", return_value="2025-06-05"):
        arrivals.attach(db_conn, league.id, team.id, cards)
    assert cards[0]["arrived"] == "Joined Jun 1"
    assert "arrived" not in cards[1]


def test_mark_sets_the_league_date(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    p = factory.rated_player(team, league, 50)
    with patch.object(arrivals, "today", return_value="2025-07-04"):
        arrivals.mark(db_conn, league.id, team.id, p.id)
    row = db_conn.execute(
        "SELECT joined_on FROM team_players WHERE player_id = %s", (p.id,)
    ).fetchone()
    assert row["joined_on"] == "2025-07-04"
