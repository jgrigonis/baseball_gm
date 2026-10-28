# tests/db/repositories/test_lineup_preference_repo.py
"""Saved lineups, one per hand of opposing starter (vs RHP / vs LHP)."""

import pytest

from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    players = [factory.rated_player(team, league) for _ in range(2)]
    return LineupPreferenceRepository(db_conn), league, team, gm, players


def lineup(*players):
    return [
        {"player_id": p.id, "batting_order": i + 1, "position": "c"}
        for i, p in enumerate(players)
    ]


def ids(rows):
    return [r["player_id"] for r in rows]


def test_each_hand_saves_on_its_own(setup):
    repo, league, team, gm, (a, b) = setup
    repo.save_preferences(gm.id, lineup(a, b), "R")
    repo.save_preferences(gm.id, lineup(b, a), "L")

    saved = repo.get_by_gm_id(gm.id)
    assert ids(saved["R"]) == [a.id, b.id]
    assert ids(saved["L"]) == [b.id, a.id]
    assert ids(repo.get_preferences(team.id, league.id, "L")) == [b.id, a.id]

    # Saving one hand again leaves the other alone.
    repo.save_preferences(gm.id, lineup(a), "R")
    assert ids(repo.get_by_gm_id(gm.id)["L"]) == [b.id, a.id]


def test_one_saved_lineup_is_used_against_both_hands(setup):
    repo, league, team, gm, (a, b) = setup
    repo.save_preferences(gm.id, lineup(a, b), "R")

    assert repo.get_by_gm_id(gm.id)["L"] == []
    assert ids(repo.get_preferences(team.id, league.id, "L")) == [a.id, b.id]
    assert ids(repo.get_preferences(team.id, league.id, None)) == [a.id, b.id]


def test_nothing_saved(setup):
    repo, league, team, gm, _ = setup
    assert repo.get_preferences(team.id, league.id, "R") is None
    assert repo.get_by_gm_id(gm.id) == {"R": [], "L": []}
