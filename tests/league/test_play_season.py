# tests/league/test_play_season.py
"""
Unit tests for play_season.py.

Testable surface:
- _pick_starter        — rich logic, mocked repos
- clear_game_data      — DB side effects
- _load_eligible_ids   — simple DB query

play_game() is too integrated (full game engine + 10+ repos) to unit test —
that belongs in integration tests.
"""

import random
from datetime import date
from unittest.mock import MagicMock

import pytest

from src.league.play_season import _pick_starter, clear_game_data, _load_eligible_ids
from src.db.repositories.pitcher_state import PitcherState, MIN_ENERGY_STARTER


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

GAME_DATE = date(2025, 4, 10)
TEAM_ID   = "team-1"
SEASON_ID = "season-1"


def _state(energy: float) -> PitcherState:
    return PitcherState(player_id="", current_energy=energy, max_energy=1.0)


def _make_rot_repo(scheduled: str | None, rotation: list[dict] | None = None):
    repo = MagicMock()
    repo.get_scheduled_starter.return_value = scheduled
    repo.get_current_rotation.return_value = rotation or []
    return repo


def _make_pitcher_repo(energy_map: dict[str, float]):
    """energy_map: player_id → current_energy"""
    repo = MagicMock()
    def _get(player_id, game_date, recovery_skill=50):
        return _state(energy_map.get(player_id, 1.0))
    repo.get_with_recovery.side_effect = _get
    return repo


def _fake_player(pid: str, stamina: int = 60, energy: float = 1.0,
                 bullpen_role: str | None = None) -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.pitcher_fatigue = MagicMock()
    p.pitcher_fatigue.energy = energy
    p.bullpen_role = bullpen_role
    skills = {"stamina": stamina, "recovery": 50}
    p.skills = MagicMock()
    p.skills.get = lambda k, d=None: skills.get(k, d)
    p.get_effective_stat.side_effect = lambda v: v  # identity
    return p


def _rotation_row(pid: str, order: int) -> dict:
    return {"player_id": pid, "rotation_order": order}


# ─────────────────────────────────────────────────────────────────────────────
# _pick_starter — no rotation
# ─────────────────────────────────────────────────────────────────────────────

class TestPickStarterNoRotation:

    def test_returns_none_when_no_scheduled_starter(self):
        rot = _make_rot_repo(scheduled=None)
        pit = _make_pitcher_repo({})
        pid, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert pid is None
        assert advance is False

    def test_returns_none_when_rotation_empty(self):
        rot = _make_rot_repo(scheduled="p1", rotation=[])
        pit = _make_pitcher_repo({"p1": 1.0})
        pid, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert pid is None
        assert advance is False


# ─────────────────────────────────────────────────────────────────────────────
# _pick_starter — healthy scheduled pitcher
# ─────────────────────────────────────────────────────────────────────────────

class TestPickStarterHealthyScheduled:

    def test_returns_scheduled_pitcher_when_rested(self):
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        pit = _make_pitcher_repo({"p1": 1.0, "p2": 1.0})
        pid, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert pid == "p1"
        assert advance is True

    def test_advance_is_true_for_normal_start(self):
        rot = _make_rot_repo(
            scheduled="p2",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        pit = _make_pitcher_repo({"p1": 1.0, "p2": 1.0})
        _, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert advance is True

    def test_skips_tired_pitcher_finds_next_rested(self):
        """Scheduled pitcher p1 is tired — should skip to p2."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        pit = _make_pitcher_repo({"p1": 0.5, "p2": 1.0})  # p1 below MIN
        pid, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert pid == "p2"
        assert advance is True

    def test_returns_most_rested_when_all_tired(self):
        """All pitchers tired — return the one with highest energy."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        # Both below MIN_ENERGY_STARTER, p2 more rested
        pit = _make_pitcher_repo({"p1": 0.3, "p2": 0.6})
        pid, advance = _pick_starter(rot, pit, TEAM_ID, SEASON_ID, GAME_DATE)
        assert pid == "p2"
        assert advance is True




# ─────────────────────────────────────────────────────────────────────────────
# _pick_starter — injured scheduled pitcher (spot start)
# ─────────────────────────────────────────────────────────────────────────────

class TestPickStarterInjuredScheduled:

    def test_spot_start_from_bullpen_when_scheduled_injured(self):
        """Scheduled p1 is injured — pick bullpen pitcher p3."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        pit = _make_pitcher_repo({"p3": 1.0})
        p3 = _fake_player("p3", stamina=60, energy=1.0)
        pid, advance = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[p3],
        )
        assert pid == "p3"
        assert advance is False  # pointer stays on injured slot

    def test_advance_false_on_spot_start(self):
        """Pointer must NOT advance when a spot starter is used."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1)],
        )
        pit = _make_pitcher_repo({"p2": 1.0})
        p2 = _fake_player("p2", stamina=60)
        _, advance = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[p2],
        )
        assert advance is False

    def test_spot_start_prefers_rested_bullpen(self):
        """When multiple bullpen options, prefer the one with higher effective stamina."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1)],
        )
        pit = _make_pitcher_repo({"p-low": 1.0, "p-high": 1.0})
        p_low  = _fake_player("p-low",  stamina=40)
        p_high = _fake_player("p-high", stamina=80)
        pid, _ = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[p_low, p_high],
        )
        assert pid == "p-high"

    def test_closer_excluded_from_spot_start(self):
        """Closers should not be used as spot starters."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1)],
        )
        pit = _make_pitcher_repo({"closer": 1.0, "middle": 1.0})
        closer = _fake_player("closer", stamina=80, bullpen_role="Closer")
        middle = _fake_player("middle", stamina=60)
        pid, _ = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[closer, middle],
        )
        assert pid == "middle"

    def test_falls_back_to_healthy_rotation_when_no_bullpen(self):
        """No bullpen available — fall back to healthy rotation pitcher."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1), _rotation_row("p2", 2)],
        )
        pit = _make_pitcher_repo({"p2": 1.0})
        # No team_players passed (empty bullpen)
        pid, advance = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[],
        )
        assert pid == "p2"
        assert advance is True

    def test_returns_none_when_entire_staff_injured(self):
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1)],
        )
        pit = _make_pitcher_repo({})
        pid, advance = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[],
        )
        assert pid is None
        assert advance is False

    def test_bullpen_pitcher_excluded_when_not_eligible(self):
        """Spot starter candidate must be in eligible_ids."""
        rot = _make_rot_repo(
            scheduled="p1",
            rotation=[_rotation_row("p1", 1)],
        )
        pit = _make_pitcher_repo({"p-ineligible": 1.0, "p-eligible": 1.0})
        p_inel = _fake_player("p-ineligible", stamina=90)
        p_el   = _fake_player("p-eligible",   stamina=60)
        pid, _ = _pick_starter(
            rot, pit, TEAM_ID, SEASON_ID, GAME_DATE,
            injured_ids={"p1"},
            team_players=[p_inel, p_el],
            eligible_ids={"p-eligible"},
        )
        assert pid == "p-eligible"


# ─────────────────────────────────────────────────────────────────────────────
# clear_game_data
# ─────────────────────────────────────────────────────────────────────────────

class TestClearGameData:

    @pytest.fixture
    def game(self, db_conn):
        db_conn.execute(
            "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
            ("s1", 2025, "Season 1"),
        )
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
            ("home", "H", "H"),
        )
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
            ("away", "A", "A"),
        )
        db_conn.execute(
            """INSERT INTO games
               (id, game_date, season_id, home_team_id, away_team_id,
                home_score, away_score, winner_id, innings_played, completed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("game-1", "2025-04-01", "s1", "home", "away", 5, 3, "home", 9, 1),
        )
        db_conn.commit()
        return db_conn

    def test_clears_game_scores(self, game):
        clear_game_data(game, "game-1")
        row = game.execute(
            "SELECT home_score, away_score FROM games WHERE id = ?", ("game-1",)
        ).fetchone()
        assert row["home_score"] is None
        assert row["away_score"] is None

    def test_clears_winner(self, game):
        clear_game_data(game, "game-1")
        row = game.execute(
            "SELECT winner_id FROM games WHERE id = ?", ("game-1",)
        ).fetchone()
        assert row["winner_id"] is None

    def test_clears_innings_played(self, game):
        clear_game_data(game, "game-1")
        row = game.execute(
            "SELECT innings_played FROM games WHERE id = ?", ("game-1",)
        ).fetchone()
        assert row["innings_played"] is None

    def test_sets_completed_to_zero(self, game):
        clear_game_data(game, "game-1")
        row = game.execute(
            "SELECT completed FROM games WHERE id = ?", ("game-1",)
        ).fetchone()
        assert row["completed"] == 0

    def test_game_row_still_exists(self, game):
        clear_game_data(game, "game-1")
        row = game.execute(
            "SELECT id FROM games WHERE id = ?", ("game-1",)
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# _load_eligible_ids
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadEligibleIds:

    @pytest.fixture
    def seeded(self, db_conn):
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES ('t1', 'C', 'M')"
        )
        for pid, status in [
            ("p-26", "26man"),
            ("p-40", "40man"),
            ("p-min", "minors"),
            ("p-fa", "free_agent"),
        ]:
            db_conn.execute(
                "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
                " VALUES (?, 'A', 'B', 'R', 'R', 'cf')", (pid,)
            )
            db_conn.execute(
                "INSERT INTO player_status (player_id, status, since) VALUES (?, ?, '2025-01-01')",
                (pid, status),
            )
            db_conn.execute(
                "INSERT INTO team_players (team_id, player_id) VALUES ('t1', ?)", (pid,)
            )
        db_conn.commit()
        return db_conn

    def test_blitz_includes_26man_and_40man(self, seeded):
        ids = _load_eligible_ids(seeded, "t1", "", blitz=True)
        assert "p-26" in ids
        assert "p-40" in ids

    def test_blitz_excludes_minors_and_free_agents(self, seeded):
        ids = _load_eligible_ids(seeded, "t1", "", blitz=True)
        assert "p-min" not in ids
        assert "p-fa" not in ids

    def test_long_form_includes_only_26man(self, seeded):
        ids = _load_eligible_ids(seeded, "t1", "", blitz=False)
        assert "p-26" in ids
        assert "p-40" not in ids

    def test_long_form_excludes_minors_and_free_agents(self, seeded):
        ids = _load_eligible_ids(seeded, "t1", "", blitz=False)
        assert "p-min" not in ids
        assert "p-fa" not in ids

    def test_returns_set(self, seeded):
        ids = _load_eligible_ids(seeded, "t1", "", blitz=True)
        assert isinstance(ids, set)

    def test_empty_roster_returns_empty_set(self, db_conn):
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES ('empty-team', 'C', 'M')"
        )
        db_conn.commit()
        ids = _load_eligible_ids(db_conn, "empty-team", "", blitz=True)
        assert ids == set()
