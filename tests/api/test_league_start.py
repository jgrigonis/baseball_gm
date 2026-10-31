# tests/api/test_league_start.py
"""
Tests for start_league().

start_league() has three external dependencies that touch the filesystem:
  - load_manifest / validate_manifest_* — reads a JSON file
  - create_team_files — writes CSVs
  - bootstrapper.bootstrap_from_manifest — loads CSVs and creates DB rows

These are mocked so tests run without any files on disk.
The tests verify the DB-side effects of steps 5-8:
  - GM assignment and AI GM creation
  - Draft record creation
  - Draft order written to draft_order table
  - League state transition to 'draft'
  - Return value shape
  - Guard clauses (wrong state, missing league)
"""

import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from src.api.services.league_start import start_league
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.api.services import personas as persona_service
from src.league import personas
from src.league.league_constants import LEAGUE_START_YEAR


@dataclass
class TeamRef:
    id: str
    city: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ─────────────────────────────────────────────────────────────────────────────

FAKE_MANIFEST = {
    "league_name": "Test League",
    "season_year": 2025,
    "season_start_date": "2025-04-01",
    "teams": [],
}


@pytest.fixture
def ctx(db_conn, factory):
    """
    Insert a league in lobby state with 4 teams and one human GM.
    Returns a namespace with everything tests need: conn, league, season, teams, gm.
    """
    league = factory.league(state="lobby")
    season = factory.season()
    factory.league_season(league, season)
    teams = [factory.team() for _ in range(4)]
    for t in teams:
        db_conn.execute(
            "INSERT INTO league_season_teams (league_id, season_id, team_id)"
            " VALUES (%s, %s, %s)",
            (league.id, season.id, t.id),
        )
    gm = factory.gm(team=teams[0], league=league, is_ai=False)

    from types import SimpleNamespace

    return SimpleNamespace(
        conn=db_conn,
        league=league,
        season=season,
        teams=teams,
        gm=gm,
    )


@pytest.fixture
def patched(ctx):
    """
    Patch all filesystem-touching code.
    Yields ctx so tests can access ctx.conn, ctx.league, etc.
    """

    fake_teams = [TeamRef(id=t.id) for t in ctx.teams]

    with (
        patch(
            "src.api.services.league_start.load_manifest", return_value=FAKE_MANIFEST
        ),
        patch("src.api.services.league_start.validate_manifest_structure"),
        patch("src.api.services.league_start.validate_manifest_uniqueness"),
        patch("src.api.services.league_start.create_team_files"),
        patch("src.api.services.league_start.LeagueBootstrapper") as MockBootstrapper,
        patch("src.api.services.league_start.DraftGenerator") as MockDraftGen,
        patch("src.api.services.league_start.ScheduleGenerator") as MockScheduler,
        patch("src.api.services.league_start.save_schedule_to_db"),
        patch("src.api.services.league_start.write_draft_order"),
    ):
        # --- Bootstrapper ---
        MockBootstrapper.return_value.bootstrap_from_manifest.return_value = (
            ctx.league.id,
            fake_teams,
            ctx.season.id,
        )

        # --- Draft generator ---
        MockDraftGen.return_value.run.return_value = 150

        # --- Schedule generator ---
        MockScheduler.return_value.create_schedule.return_value = ["g1", "g2", "g3"]

        yield ctx

    # with patch("src.api.services.league_start.load_manifest", return_value=FAKE_MANIFEST), \
    #      patch("src.api.services.league_start.validate_manifest_structure"), \
    #      patch("src.api.services.league_start.validate_manifest_uniqueness"), \
    #      patch("src.api.services.league_start.create_team_files"), \
    #      patch("src.api.services.league_start.LeagueBootstrapper") as MockBootstrapper, \
    #      patch("src.api.services.league_start.DraftGenerator") as MockDraftGen, \
    #      patch("src.api.services.league_start.ScheduleGenerator") as MockScheduler, \
    #      patch("src.api.services.league_start.save_schedule_to_db"), \
    #      patch("src.api.services.league_start.write_draft_order"):

    #     mock_boot = MagicMock()
    #     mock_boot.bootstrap_from_manifest.return_value = (
    #         ctx.league.id, fake_teams, ctx.season.id
    #     )
    #     MockBootstrapper.return_value = mock_boot

    #     mock_gen = MagicMock()
    #     mock_gen.run.return_value = 150
    #     MockDraftGen.return_value = mock_gen

    #     mock_sched = MagicMock()
    #     mock_sched.create_schedule.return_value = ["g1", "g2", "g3"]
    #     MockScheduler.return_value = mock_sched

    #     yield ctx


# ─────────────────────────────────────────────────────────────────────────────
# Guard clauses
# ─────────────────────────────────────────────────────────────────────────────


class TestStartLeagueGuards:
    def test_raises_if_league_not_found(self, db_conn):
        with pytest.raises(ValueError, match="not found"):
            start_league("nonexistent-league", db_conn)

    def test_raises_if_league_not_in_lobby(self, db_conn, factory):
        league = factory.league(state="draft")
        with pytest.raises(ValueError, match="already in state"):
            start_league(league.id, db_conn)

    def test_raises_if_league_in_season_state(self, db_conn, factory):
        league = factory.league(state="season")
        with pytest.raises(ValueError, match="already in state"):
            start_league(league.id, db_conn)


# ─────────────────────────────────────────────────────────────────────────────
# Return value
# ─────────────────────────────────────────────────────────────────────────────


class TestStartLeagueReturnValue:
    def test_returns_expected_keys(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert set(result.keys()) == {
            "league_id",
            "season_id",
            "draft_id",
            "team_count",
            "game_count",
            "prospect_count",
            "seed",
            "your_team",
        }

    def test_returns_correct_league_and_season_ids(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert result["league_id"] == patched.league.id
        assert result["season_id"] == patched.season.id

    def test_returns_correct_team_count(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert result["team_count"] == len(patched.teams)

    def test_returns_prospect_count_from_generator(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert result["prospect_count"] == 150

    def test_returns_game_count(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert result["game_count"] == 3

    def test_returns_seed_as_int(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert isinstance(result["seed"], int)

    def test_returns_draft_id_string(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert isinstance(result["draft_id"], str)
        assert len(result["draft_id"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# League state transition
# ─────────────────────────────────────────────────────────────────────────────


class TestLeagueStateTransition:
    def test_league_state_becomes_draft(self, patched):
        start_league(patched.league.id, patched.conn)
        row = patched.conn.execute(
            "SELECT state FROM leagues WHERE id = %s", (patched.league.id,)
        ).fetchone()
        assert row["state"] == "draft"

    def test_league_was_lobby_before(self, ctx):
        row = ctx.conn.execute(
            "SELECT state FROM leagues WHERE id = %s", (ctx.league.id,)
        ).fetchone()
        assert row["state"] == "lobby"


# ─────────────────────────────────────────────────────────────────────────────
# Draft record creation
# ─────────────────────────────────────────────────────────────────────────────


class TestDraftCreation:
    def test_draft_record_created(self, patched):
        result = start_league(patched.league.id, patched.conn)
        row = patched.conn.execute(
            "SELECT * FROM drafts WHERE id = %s", (result["draft_id"],)
        ).fetchone()
        assert row is not None
        assert row["league_id"] == patched.league.id
        assert row["season_id"] == patched.season.id
        assert row["state"] == "pending"

    def test_draft_format_is_preference_for_blitz(self, patched):
        result = start_league(patched.league.id, patched.conn)
        row = patched.conn.execute(
            "SELECT format FROM drafts WHERE id = %s", (result["draft_id"],)
        ).fetchone()
        assert row["format"] == "preference"

    def test_only_one_draft_created(self, patched):
        start_league(patched.league.id, patched.conn)
        count = patched.conn.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE league_id = %s",
            (patched.league.id,),
        ).fetchone()["n"]
        assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# GM assignment
# ─────────────────────────────────────────────────────────────────────────────


class TestGMAssignment:
    def test_human_gm_assigned_to_a_team(self, patched):
        start_league(patched.league.id, patched.conn)
        row = patched.conn.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND NOT is_ai",
            (patched.league.id,),
        ).fetchone()
        assert row["team_id"] is not None

    def test_human_gm_assigned_to_valid_team(self, patched):
        start_league(patched.league.id, patched.conn)
        row = patched.conn.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND NOT is_ai",
            (patched.league.id,),
        ).fetchone()
        team_ids = {t.id for t in patched.teams}
        assert row["team_id"] in team_ids

    def test_ai_gms_created_for_remaining_teams(self, patched):
        start_league(patched.league.id, patched.conn)
        ai_count = patched.conn.execute(
            "SELECT COUNT(*) AS n FROM gms WHERE league_id = %s AND is_ai",
            (patched.league.id,),
        ).fetchone()["n"]
        assert ai_count == len(patched.teams) - 1

    def test_every_team_has_exactly_one_gm(self, patched):
        start_league(patched.league.id, patched.conn)
        for team in patched.teams:
            count = patched.conn.execute(
                "SELECT COUNT(*) AS n FROM gms WHERE league_id = %s AND team_id = %s",
                (patched.league.id, team.id),
            ).fetchone()["n"]
            assert count == 1, f"Team {team.id} has {count} GMs, expected 1"

    def test_your_team_returned_for_human_gm(self, patched):
        result = start_league(patched.league.id, patched.conn)
        assert result["your_team"] is not None
        assert isinstance(result["your_team"], str)

    def test_ai_gms_have_profiles(self, patched):
        start_league(patched.league.id, patched.conn)
        ai_gm_ids = [
            r["id"]
            for r in patched.conn.execute(
                "SELECT id FROM gms WHERE league_id = %s AND is_ai",
                (patched.league.id,),
            ).fetchall()
        ]
        for gm_id in ai_gm_ids:
            row = patched.conn.execute(
                "SELECT gm_id FROM gm_profiles WHERE gm_id = %s", (gm_id,)
            ).fetchone()
            assert row is not None, f"AI GM {gm_id} has no gm_profiles row"

    def test_each_ai_gm_is_a_different_persona(self, patched):
        start_league(patched.league.id, patched.conn)
        rows = patched.conn.execute(
            """SELECT g.id, g.display_name, g.persona_id, p.name, p.dials
               FROM gms g JOIN gm_personas p ON p.id = g.persona_id
               WHERE g.league_id = %s AND g.is_ai""",
            (patched.league.id,),
        ).fetchall()
        assert len(rows) == len(patched.teams) - 1
        assert len({r["persona_id"] for r in rows}) == len(rows)
        for r in rows:
            assert r["display_name"] == r["name"]
            profile = patched.conn.execute(
                "SELECT * FROM gm_profiles WHERE gm_id = %s", (r["id"],)
            ).fetchone()
            for key, value in personas.profile(r["dials"]).items():
                assert profile[key] == value


class TestLobbyAiGms:
    def test_ai_gms_picked_in_the_lobby_get_the_open_teams(self, patched):
        conn, league = patched.conn, patched.league
        conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))
        conn.execute("UPDATE gms SET team_id = NULL WHERE league_id = %s", (league.id,))
        persona_service.fill_lobby(conn, league.id)
        picked = {g["id"] for g in persona_service.lobby_ai_gms(conn, league.id)}

        start_league(league.id, conn)

        rows = conn.execute(
            "SELECT id, team_id FROM gms WHERE league_id = %s AND is_ai",
            (league.id,),
        ).fetchall()
        assert {r["id"] for r in rows} == picked
        assert all(r["team_id"] for r in rows)

    def test_extra_lobby_ai_gms_are_dropped(self, patched):
        conn, league = patched.conn, patched.league
        conn.execute("UPDATE leagues SET num_teams = 6 WHERE id = %s", (league.id,))
        persona_service.fill_lobby(conn, league.id)

        start_league(league.id, conn)

        n = conn.execute(
            "SELECT COUNT(*) AS n FROM gms WHERE league_id = %s AND is_ai",
            (league.id,),
        ).fetchone()["n"]
        assert n == len(patched.teams) - 1


class TestLobbyTeams:
    def test_gms_get_the_teams_they_were_dealt_in_the_lobby(self, patched):
        conn, league, teams = patched.conn, patched.league, patched.teams
        conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))
        conn.execute("UPDATE gms SET team_id = NULL WHERE league_id = %s", (league.id,))
        for i, t in enumerate(teams):
            conn.execute(
                "UPDATE teams SET city = 'Dealt', mascot = %s WHERE id = %s",
                (f"M{i}", t.id),
            )
        persona_service.fill_lobby(conn, league.id)
        ai = persona_service.lobby_ai_gms(conn, league.id)
        dealt = {patched.gm.id: teams[2].id, ai[0]["id"]: teams[0].id}
        conn.execute(
            "UPDATE gms SET lobby_city = 'Dealt', lobby_mascot = 'M2' WHERE id = %s",
            (patched.gm.id,),
        )
        conn.execute(
            "UPDATE gms SET lobby_city = 'Dealt', lobby_mascot = 'M0' WHERE id = %s",
            (ai[0]["id"],),
        )

        start_league(league.id, conn)

        rows = conn.execute(
            "SELECT id, team_id FROM gms WHERE league_id = %s", (league.id,)
        ).fetchall()
        got = {r["id"]: r["team_id"] for r in rows}
        assert {g: got[g] for g in dealt} == dealt
        assert sorted(got.values()) == sorted(t.id for t in teams)


# ─────────────────────────────────────────────────────────────────────────────
# Backstory (src/league/backstory/)
# ─────────────────────────────────────────────────────────────────────────────


class TestBackstory:
    def _order(self, patched):
        from src.api.services import league_start

        return league_start.write_draft_order.call_args.args[4]

    def test_no_backstory_by_default_in_tests(self, patched):
        start_league(patched.league.id, patched.conn)
        rows = patched.conn.execute(
            "SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = %s",
            (patched.league.id,),
        ).fetchone()
        assert rows["n"] == 1

    def test_the_first_draft_goes_worst_first_by_last_seasons_record(self, patched):
        conn = patched.conn
        conn.execute(
            "UPDATE leagues SET backstory_years = 2 WHERE id = %s", (patched.league.id,)
        )
        start_league(patched.league.id, conn)

        last = conn.execute(
            """SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.is_backstory
               ORDER BY s.year DESC LIMIT 1""",
            (patched.league.id,),
        ).fetchone()["id"]
        pct = {
            r["team_id"]: r["wins"] / (r["wins"] + r["losses"])
            for r in TeamGameRepository(conn).get_wl_for_league(patched.league.id, last)
        }
        order = self._order(patched)
        assert sorted(order) == sorted(t.id for t in patched.teams)
        assert [pct[t] for t in order] == sorted(pct[t] for t in order)

    def test_backstory_seasons_dont_count_toward_the_league_length(self, patched):
        conn = patched.conn
        conn.execute(
            "UPDATE leagues SET backstory_years = 2 WHERE id = %s", (patched.league.id,)
        )
        start_league(patched.league.id, conn)
        assert LeagueRepository(conn).count_seasons(patched.league.id) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Start year
# ─────────────────────────────────────────────────────────────────────────────


class TestStartYear:
    """New leagues start in LEAGUE_START_YEAR, whatever year the manifest says."""

    def _boot_call(self, patched):
        from src.api.services import league_start

        return league_start.LeagueBootstrapper.return_value.bootstrap_from_manifest

    def test_start_year_is_2027(self):
        assert LEAGUE_START_YEAR == 2027

    def test_first_season_gets_the_start_year(self, patched):
        start_league(patched.league.id, patched.conn)
        manifest, start_date = self._boot_call(patched).call_args.args[:2]
        assert FAKE_MANIFEST["season_year"] != LEAGUE_START_YEAR
        assert manifest["season_year"] == LEAGUE_START_YEAR
        assert start_date == datetime.date(LEAGUE_START_YEAR, 4, 1)

    def test_team_files_are_made_for_the_start_year(self, patched):
        from src.api.services import league_start

        start_league(patched.league.id, patched.conn)
        assert league_start.create_team_files.call_args.args[1] == LEAGUE_START_YEAR

    def test_schedule_starts_in_the_start_year(self, patched):
        from src.api.services import league_start

        start_league(patched.league.id, patched.conn)
        kwargs = (
            league_start.ScheduleGenerator.return_value.create_schedule.call_args.kwargs
        )
        assert kwargs["start_date"].year == LEAGUE_START_YEAR


class TestDivisions:
    def test_the_teams_are_drawn_into_leagues_and_divisions(self, patched):
        start_league(patched.league.id, patched.conn)
        rows = patched.conn.execute(
            "SELECT team_id, conference, division FROM team_divisions WHERE league_id = %s",
            (patched.league.id,),
        ).fetchall()
        assert {r["team_id"] for r in rows} == {t.id for t in patched.teams}
        assert len({r["conference"] for r in rows}) == 2
        assert len({(r["conference"], r["division"]) for r in rows}) == 4

    def test_a_weighted_league_hands_the_divisions_to_the_schedule(self, patched):
        patched.conn.execute(
            "UPDATE leagues SET weighted_schedule = TRUE WHERE id = %s",
            (patched.league.id,),
        )
        with patch("src.api.services.league_start.ScheduleGenerator") as gen:
            gen.return_value.create_schedule.return_value = []
            start_league(patched.league.id, patched.conn)
        leagues = gen.return_value.create_schedule.call_args.kwargs["leagues"]
        assert sorted(t for lg in leagues for d in lg for t in d) == sorted(
            t.id for t in patched.teams
        )

    def test_a_balanced_league_doesnt(self, patched):
        start_league(patched.league.id, patched.conn)
        from src.api.services import league_start as ls

        kwargs = ls.ScheduleGenerator.return_value.create_schedule.call_args.kwargs
        assert kwargs["leagues"] is None
