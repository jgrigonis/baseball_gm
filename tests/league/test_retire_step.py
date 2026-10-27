# tests/league/test_retire_step.py
"""
DB tests for the offseason retirement step and the data it reads.

Tests cover:
- Already-retired players are not checked (or recorded) again
- A regular who played every game stays; an unused veteran retires
- Season totals add up a traded player's games across teams
- Skill history for many players at once
- Draft prospects never take an existing player's id
"""

import random
import uuid

import pytest

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.player.player_factory import PlayerFactory


class FixedRng(random.Random):
    """random() always returns value; everything else is a normal Random."""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


@pytest.fixture
def league_setup(db_conn, factory):
    league = factory.league()
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    factory.league_season_team(league, season, team)
    return league, season, team


def add_player(db_conn, factory, league, team, *, age, status):
    player = factory.prospect(league.id)
    db_conn.execute(
        "UPDATE player_skills SET age = %s WHERE player_id = %s", (age, player.id)
    )
    db_conn.execute(
        "UPDATE player_status SET status = %s WHERE player_id = %s",
        (status, player.id),
    )
    if team is not None:
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
            (team.id, player.id),
        )
    return player


def add_games(db_conn, player, season, team, games):
    db_conn.execute(
        """INSERT INTO player_season_stats
           (player_id, season_id, team_id, is_postseason, bat_games_played)
           VALUES (%s, %s, %s, FALSE, %s)""",
        (player.id, season.id, team.id, games),
    )


def run_retire(db_conn, league, season, rng_value):
    pipeline = OffseasonPipeline(db_conn, rng=FixedRng(rng_value))
    pipeline.league_id = league.id
    pipeline._current_season_id = season.id
    pipeline.year = season.year + 1
    pipeline._retire(pipeline.rng)


def retirement_rows(db_conn, player):
    return db_conn.execute(
        "SELECT COUNT(*) AS n FROM player_retirements WHERE player_id = %s",
        (player.id,),
    ).fetchone()["n"]


def status_of(db_conn, player):
    return db_conn.execute(
        "SELECT status FROM player_status WHERE player_id = %s", (player.id,)
    ).fetchone()["status"]


class TestRetireStep:
    def test_already_retired_player_is_not_retired_again(
        self, db_conn, factory, league_setup
    ):
        league, season, _ = league_setup
        player = add_player(db_conn, factory, league, None, age=41, status="retired")

        # rng 0.0 retires anyone with a chance above zero
        run_retire(db_conn, league, season, 0.0)

        assert retirement_rows(db_conn, player) == 0
        assert status_of(db_conn, player) == "retired"

    def test_regular_stays_and_unused_veteran_retires(
        self, db_conn, factory, league_setup, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "src.league.offseason.offseason_pipeline.TEAM_FILES_DIR", tmp_path
        )
        league, season, team = league_setup
        regular = add_player(db_conn, factory, league, team, age=38, status="26man")
        unused = add_player(db_conn, factory, league, team, age=38, status="40man")
        add_games(db_conn, regular, season, team, 162)

        # 0.05: above a regular's 1% cap, far below an unused 38-year-old's chance
        run_retire(db_conn, league, season, 0.05)

        assert status_of(db_conn, regular) == "26man"
        assert status_of(db_conn, unused) == "retired"
        assert retirement_rows(db_conn, unused) == 1


class TestSeasonTotals:
    def test_traded_player_games_add_up(self, db_conn, factory, league_setup):
        league, season, team = league_setup
        other_team = factory.team()
        player = add_player(db_conn, factory, league, team, age=32, status="26man")
        add_games(db_conn, player, season, team, 90)
        add_games(db_conn, player, season, other_team, 60)

        totals = PlayerSeasonStatsRepository(db_conn).get_player_season_totals(
            season.id
        )

        assert totals[player.id]["bat_games_played"] == 150
        assert totals[player.id]["pitch_games_started"] == 0


class TestSkillHistoryMany:
    def test_groups_snapshots_by_player_oldest_first(self, db_conn, factory):
        league = factory.league()
        early, late = factory.season(year=2025), factory.season(year=2026)
        p1, p2 = factory.prospect(league.id), factory.prospect(league.id)
        repo = PlayerRepository(db_conn)
        for season in (late, early):
            repo.snapshot_skills(p1.id, season.id)
        repo.snapshot_skills(p2.id, early.id)

        history = repo.get_skill_history_many([p1.id, p2.id, "nobody"])

        assert [row["season_id"] for row in history[p1.id]] == [early.id, late.id]
        assert len(history[p2.id]) == 1
        assert "nobody" not in history

    def test_no_players(self, db_conn):
        assert PlayerRepository(db_conn).get_skill_history_many([]) == {}


class TestDraftProspectIds:
    def test_taken_id_gets_replaced(self, db_conn, factory):
        league = factory.league()
        existing = factory.prospect(league.id)
        generator = DraftGenerator(db_conn, random.Random(1))
        prospect = PlayerFactory(rng=random.Random(1)).create(position="ss")
        clash = prospect.__class__(**{**prospect.__dict__, "id": existing.id})

        replaced = generator._with_unused_id(clash)

        assert replaced.id != existing.id
        assert replaced.first_name == clash.first_name

    def test_free_id_is_kept(self, db_conn):
        generator = DraftGenerator(db_conn, random.Random(1))
        prospect = PlayerFactory(rng=random.Random(uuid.uuid4().int)).create(
            position="ss"
        )
        assert generator._with_unused_id(prospect).id == prospect.id
