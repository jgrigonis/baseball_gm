# tests/league/test_setup_playoffs.py
"""Playoff rotation setup: trimming to a short rotation and resetting to sp1."""

from datetime import date

import pytest

from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.playoffs.setup_playoffs import (
    demote_extra_starters,
    reset_playoff_rotation_pointers,
)

PLAYOFF_START = date(2024, 10, 5)


@pytest.fixture
def rot(db_conn, factory):
    from types import SimpleNamespace

    season = factory.season(year=2024)
    team = factory.team(city="Boston", mascot="Red Sox")
    players = []
    for i in range(1, 6):
        pid = f"{team.id[:8]}-p{i:03d}"
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (pid, f"First{i}", f"Last{i}", "R", "R", "sp"),
        )
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (team.id, pid),
        )
        players.append(pid)
    repo = TeamRotationsRepository(db_conn, league_id="test")
    repo.set_rotation(team.id, season.id, players, "2024-04-01")
    return SimpleNamespace(season_id=season.id, team_id=team.id, p=players, repo=repo)


def test_demotions_take_effect_on_playoff_start_date(db_conn, rot):
    teams = [{"team_id": rot.team_id, "team_name": "Boston Red Sox"}]

    demote_extra_starters(
        db_conn,
        rot.season_id,
        teams,
        keep=4,
        league_id="test",
        effective_date=PLAYOFF_START,
    )

    rotation = rot.repo.get_current_rotation(rot.team_id, rot.season_id, PLAYOFF_START)
    assert [r["player_id"] for r in rotation] == rot.p[:4]


def test_reset_puts_sp1_next_after_regular_season(db_conn, rot):
    rot.repo.assign_rotation_pointer(rot.team_id, rot.season_id, 3)

    reset_playoff_rotation_pointers(db_conn, rot.season_id, "test")

    assert rot.repo.get_scheduled_starter(rot.team_id, rot.season_id) == rot.p[0]
