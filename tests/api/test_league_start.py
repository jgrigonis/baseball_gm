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

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.api.services.league_start import start_league


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ─────────────────────────────────────────────────────────────────────────────

LEAGUE_ID = "league-test"
SEASON_ID = "season-test"


def _fake_team(team_id: str):
    t = MagicMock()
    t.id = team_id
    return t


FAKE_TEAMS = [_fake_team(f"team-{i}") for i in range(4)]
FAKE_MANIFEST = {
    "league_name": "Test League",
    "season_year": 2025,
    "season_start_date": "2025-04-01",
    "teams": [],
}


@pytest.fixture
def league(db_conn):
    """Insert a league in lobby state and a human GM."""
    db_conn.execute(
        "INSERT INTO leagues (id, name, state, mode) VALUES (?, ?, 'lobby', 'blitz')",
        (LEAGUE_ID, "Test League"),
    )
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
        (SEASON_ID, 2025, "Season 2025"),
    )
    db_conn.execute(
        "INSERT INTO league_seasons (league_id, season_id) VALUES (?, ?)",
        (LEAGUE_ID, SEASON_ID),
    )
    for t in FAKE_TEAMS:
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
            (t.id, f"City {t.id}", "Team"),
        )
        db_conn.execute(
            "INSERT INTO league_season_teams (league_id, season_id, team_id) VALUES (?, ?, ?)",
            (LEAGUE_ID, SEASON_ID, t.id),
        )
    # One human GM, no team assigned yet
    gm_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO gms (id, league_id, display_name, is_ai) VALUES (?, ?, 'Human GM', 0)",
        (gm_id, LEAGUE_ID),
    )
    db_conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (?)", (gm_id,))
    db_conn.commit()
    return db_conn


@pytest.fixture
def patched_start(league):
    """
    Patch all filesystem-touching code. Returns (db_conn, call_start_league).
    Tests call start_league(LEAGUE_ID, db_conn) themselves.
    """
    with patch("src.api.services.league_start.load_manifest", return_value=FAKE_MANIFEST), \
         patch("src.api.services.league_start.validate_manifest_structure"), \
         patch("src.api.services.league_start.validate_manifest_uniqueness"), \
         patch("src.api.services.league_start.create_team_files"), \
         patch("src.api.services.league_start.LeagueBootstrapper") as MockBootstrapper, \
         patch("src.api.services.league_start.DraftGenerator") as MockDraftGen, \
         patch("src.api.services.league_start.ScheduleGenerator") as MockScheduler, \
         patch("src.api.services.league_start.save_schedule_to_db"), \
         patch("src.api.services.league_start.write_draft_order"):

        # Bootstrap returns (league_id, teams, season_id)
        mock_boot = MagicMock()
        mock_boot.bootstrap_from_manifest.return_value = (LEAGUE_ID, FAKE_TEAMS, SEASON_ID)
        MockBootstrapper.return_value = mock_boot

        # Draft generator returns prospect count
        mock_gen = MagicMock()
        mock_gen.run.return_value = 150
        MockDraftGen.return_value = mock_gen

        # Schedule generator returns a list of fake games
        mock_sched = MagicMock()
        mock_sched.create_schedule.return_value = ["g1", "g2", "g3"]
        MockScheduler.return_value = mock_sched

        yield league


# ─────────────────────────────────────────────────────────────────────────────
# Guard clauses
# ─────────────────────────────────────────────────────────────────────────────

class TestStartLeagueGuards:

    def test_raises_if_league_not_found(self, db_conn):
        with pytest.raises(ValueError, match="not found"):
            start_league("nonexistent-league", db_conn)

    def test_raises_if_league_not_in_lobby(self, db_conn):
        db_conn.execute(
            "INSERT INTO leagues (id, name, state, mode) VALUES (?, ?, 'draft', 'blitz')",
            ("league-wrong-state", "Test"),
        )
        db_conn.commit()
        with pytest.raises(ValueError, match="already in state"):
            start_league("league-wrong-state", db_conn)

    def test_raises_if_league_in_season_state(self, db_conn):
        db_conn.execute(
            "INSERT INTO leagues (id, name, state, mode) VALUES (?, ?, 'season', 'blitz')",
            ("league-season", "Test"),
        )
        db_conn.commit()
        with pytest.raises(ValueError, match="already in state"):
            start_league("league-season", db_conn)


# ─────────────────────────────────────────────────────────────────────────────
# Return value
# ─────────────────────────────────────────────────────────────────────────────

class TestStartLeagueReturnValue:

    def test_returns_expected_keys(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert set(result.keys()) == {
            "league_id", "season_id", "draft_id", "team_count",
            "game_count", "prospect_count", "seed", "your_team",
        }

    def test_returns_correct_league_and_season_ids(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert result["league_id"] == LEAGUE_ID
        assert result["season_id"] == SEASON_ID

    def test_returns_correct_team_count(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert result["team_count"] == len(FAKE_TEAMS)

    def test_returns_prospect_count_from_generator(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert result["prospect_count"] == 150

    def test_returns_game_count(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert result["game_count"] == 3  # len of fake schedule

    def test_returns_seed_as_int(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert isinstance(result["seed"], int)

    def test_returns_draft_id_string(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert isinstance(result["draft_id"], str)
        assert len(result["draft_id"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# League state transition
# ─────────────────────────────────────────────────────────────────────────────

class TestLeagueStateTransition:

    def test_league_state_becomes_draft(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        row = patched_start.execute(
            "SELECT state FROM leagues WHERE id = ?", (LEAGUE_ID,)
        ).fetchone()
        assert row["state"] == "draft"

    def test_league_was_lobby_before(self, league):
        row = league.execute(
            "SELECT state FROM leagues WHERE id = ?", (LEAGUE_ID,)
        ).fetchone()
        assert row["state"] == "lobby"


# ─────────────────────────────────────────────────────────────────────────────
# Draft record creation
# ─────────────────────────────────────────────────────────────────────────────

class TestDraftCreation:

    def test_draft_record_created(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        row = patched_start.execute(
            "SELECT * FROM drafts WHERE id = ?", (result["draft_id"],)
        ).fetchone()
        assert row is not None
        assert row["league_id"] == LEAGUE_ID
        assert row["season_id"] == SEASON_ID
        assert row["state"] == "pending"

    def test_draft_format_is_preference_for_blitz(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        row = patched_start.execute(
            "SELECT format FROM drafts WHERE id = ?", (result["draft_id"],)
        ).fetchone()
        assert row["format"] == "preference"

    def test_only_one_draft_created(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        count = patched_start.execute(
            "SELECT COUNT(*) FROM drafts WHERE league_id = ?", (LEAGUE_ID,)
        ).fetchone()[0]
        assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# GM assignment
# ─────────────────────────────────────────────────────────────────────────────

class TestGMAssignment:

    def test_human_gm_assigned_to_a_team(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        row = patched_start.execute(
            "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0",
            (LEAGUE_ID,),
        ).fetchone()
        assert row["team_id"] is not None

    def test_human_gm_assigned_to_valid_team(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        row = patched_start.execute(
            "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0",
            (LEAGUE_ID,),
        ).fetchone()
        team_ids = {t.id for t in FAKE_TEAMS}
        assert row["team_id"] in team_ids

    def test_ai_gms_created_for_remaining_teams(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        ai_count = patched_start.execute(
            "SELECT COUNT(*) FROM gms WHERE league_id = ? AND is_ai = 1",
            (LEAGUE_ID,),
        ).fetchone()[0]
        # 4 teams, 1 human GM → 3 AI GMs
        assert ai_count == len(FAKE_TEAMS) - 1

    def test_every_team_has_exactly_one_gm(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        for team in FAKE_TEAMS:
            count = patched_start.execute(
                "SELECT COUNT(*) FROM gms WHERE league_id = ? AND team_id = ?",
                (LEAGUE_ID, team.id),
            ).fetchone()[0]
            assert count == 1, f"Team {team.id} has {count} GMs, expected 1"

    def test_your_team_returned_for_human_gm(self, patched_start):
        result = start_league(LEAGUE_ID, patched_start)
        assert result["your_team"] is not None
        # Should be "City team-X Team" format
        assert "Team" in result["your_team"]

    def test_ai_gms_have_profiles(self, patched_start):
        start_league(LEAGUE_ID, patched_start)
        ai_gm_ids = [
            r["id"] for r in patched_start.execute(
                "SELECT id FROM gms WHERE league_id = ? AND is_ai = 1", (LEAGUE_ID,)
            ).fetchall()
        ]
        for gm_id in ai_gm_ids:
            row = patched_start.execute(
                "SELECT gm_id FROM gm_profiles WHERE gm_id = ?", (gm_id,)
            ).fetchone()
            assert row is not None, f"AI GM {gm_id} has no gm_profiles row"