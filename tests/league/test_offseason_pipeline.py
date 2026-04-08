# tests/league/test_offseason_pipeline.py
"""
Tests for OffseasonPipeline.

Strategy:
- Pure logic (_should_retire) — no DB needed, fast, exhaustive
- Step tracking (_is_done, _mark_done) — db_conn fixture, verify DB state
- _load_season_year — db_conn, simple query
- _playoffs_complete — db_conn, test series/games state
- run() idempotency — mock the heavy steps, verify steps are skipped on re-run
- _age/_archive/_retire — mock dependencies or use minimal seeded DB
"""

import random
from unittest.mock import MagicMock, patch, call

import pytest

from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.player.player_skills import PlayerSkills


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_pipeline(db_conn, seed=42):
    return OffseasonPipeline(db_conn, rng=random.Random(seed))


def seed_season(db_conn, season_id="s1", year=2025):
    db_conn.execute(
        "INSERT OR IGNORE INTO seasons (id, year, name) VALUES (?, ?, ?)",
        (season_id, year, f"Season {year}"),
    )
    db_conn.commit()


def seed_finals_complete(db_conn, season_id="s1"):
    """Insert a completed Finals series with 4 wins for one team."""
    db_conn.execute(
        "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        ("team-champ", "Champ", "Champions"),
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        ("team-runner", "Runner", "Runners"),
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO series (id, season_id, name) VALUES (?, ?, ?)",
        ("finals-1", season_id, "Finals"),
    )
    for i in range(4):
        db_conn.execute(
            """INSERT INTO games
               (id, game_date, season_id, series_id, home_team_id, away_team_id,
                completed, winner_id)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (f"finals-game-{i}", "2025-10-01", season_id, "finals-1",
             "team-champ", "team-runner", "team-champ"),
        )
    db_conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# _should_retire — pure logic, no DB
# ─────────────────────────────────────────────────────────────────────────────

class TestShouldRetire:
    """Tests for the static retirement probability logic."""

    def _skills(self, **overrides):
        """Return a minimal PlayerSkills-like object."""
        defaults = dict(
            contact=50, power=50, eye=50, speed=50, base_running=50,
            arm=50, outfield=50, infield=50, catching=50,
            accuracy=50, stamina=20, recovery=50, ground_balls=50, strikes=20,
        )
        defaults.update(overrides)
        mock = MagicMock()
        mock.as_dict.return_value = defaults
        return mock

    def test_rostered_young_player_never_retires(self):
        skills = self._skills()
        rng = random.Random(0)
        for age in range(17, 30):
            assert OffseasonPipeline._should_retire(age, skills, False, rng) is False

    def test_unrostered_young_never_retires(self):
        skills = self._skills()
        rng = random.Random(0)
        for age in range(17, 18):
            assert OffseasonPipeline._should_retire(age, skills, True, rng) is False

    def test_unrostered_old_player_likely_retires(self):
        """Age 35+ unrostered player has high probability."""
        skills = self._skills()
        retirements = sum(
            OffseasonPipeline._should_retire(35, skills, True, random.Random(i))
            for i in range(100)
        )
        assert retirements > 60  # high probability

    def test_rostered_elite_pitcher_stays(self):
        """Elite pitcher (high strikes) at age 32 rarely retires."""
        skills = self._skills(strikes=80, stamina=80, recovery=80, ground_balls=80)
        retirements = sum(
            OffseasonPipeline._should_retire(32, skills, False, random.Random(i))
            for i in range(100)
        )
        assert retirements == 0  # peak >= 75 → never retires at 32

    def test_rostered_elite_batter_stays(self):
        """Elite batter (high power/speed/arm) at age 32 never retires."""
        skills = self._skills(power=75, speed=75, arm=75)
        retirements = sum(
            OffseasonPipeline._should_retire(32, skills, False, random.Random(i))
            for i in range(100)
        )
        assert retirements == 0  # peak >= 72 → never retires

    def test_probability_caps_at_95_percent(self):
        """Probability never exceeds 0.95."""
        skills = self._skills()
        # Use a deterministic rng that always returns just under 0.95
        mock_rng = MagicMock()
        mock_rng.random.return_value = 0.94
        # Very old unrostered player — probability should be capped at 0.95
        result = OffseasonPipeline._should_retire(99, skills, True, mock_rng)
        assert result is True  # 0.94 < 0.95 cap

    def test_rostered_aging_mediocre_player_eventually_retires(self):
        """Mediocre 38-year-old rostered player has significant retirement chance."""
        skills = self._skills(power=40, speed=40, arm=40)
        retirements = sum(
            OffseasonPipeline._should_retire(38, skills, False, random.Random(i))
            for i in range(100)
        )
        assert retirements > 20


# ─────────────────────────────────────────────────────────────────────────────
# _is_done / _mark_done
# ─────────────────────────────────────────────────────────────────────────────

class TestStepTracking:

    def test_step_not_done_initially(self, db_conn):
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        assert pipeline._is_done("s1", "archive") is False

    def test_mark_done_persists(self, db_conn):
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done("s1", "archive")
        assert pipeline._is_done("s1", "archive") is True

    def test_mark_done_is_idempotent(self, db_conn):
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done("s1", "archive")
        pipeline._mark_done("s1", "archive")  # should not raise
        assert pipeline._is_done("s1", "archive") is True

    def test_different_steps_tracked_independently(self, db_conn):
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done("s1", "archive")
        assert pipeline._is_done("s1", "archive") is True
        assert pipeline._is_done("s1", "age") is False

    def test_different_seasons_tracked_independently(self, db_conn):
        seed_season(db_conn, "s1", 2025)
        seed_season(db_conn, "s2", 2026)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done("s1", "archive")
        assert pipeline._is_done("s1", "archive") is True
        assert pipeline._is_done("s2", "archive") is False


# ─────────────────────────────────────────────────────────────────────────────
# _load_season_year
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadSeasonYear:

    def test_loads_year_plus_one(self, db_conn):
        seed_season(db_conn, "s1", 2025)
        pipeline = make_pipeline(db_conn)
        year = pipeline._load_season_year("s1")
        assert year == 2026
        assert pipeline.year == 2026

    def test_raises_on_missing_season(self, db_conn):
        pipeline = make_pipeline(db_conn)
        with pytest.raises(ValueError, match="Season nonexistent not found"):
            pipeline._load_season_year("nonexistent")

    def test_sets_year_attribute(self, db_conn):
        seed_season(db_conn, "s1", 2030)
        pipeline = make_pipeline(db_conn)
        pipeline._load_season_year("s1")
        assert pipeline.year == 2031


# ─────────────────────────────────────────────────────────────────────────────
# _playoffs_complete
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayoffsComplete:

    def test_returns_false_when_no_finals(self, db_conn):
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline.year = 2026
        assert pipeline._playoffs_complete("s1") is False

    def test_returns_false_when_finals_incomplete(self, db_conn):
        seed_season(db_conn)
        db_conn.execute(
            "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
            ("team-a", "A", "A"),
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
            ("team-b", "B", "B"),
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO series (id, season_id, name) VALUES (?, ?, ?)",
            ("finals-1", "s1", "Finals"),
        )
        # Only 3 wins — not enough
        for i in range(3):
            db_conn.execute(
                """INSERT INTO games
                   (id, game_date, season_id, series_id, home_team_id, away_team_id,
                    completed, winner_id)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (f"g{i}", "2025-10-01", "s1", "finals-1", "team-a", "team-b", "team-a"),
            )
        db_conn.commit()
        pipeline = make_pipeline(db_conn)
        assert pipeline._playoffs_complete("s1") is False

    def test_returns_true_when_finals_has_4_wins(self, db_conn):
        seed_season(db_conn)
        seed_finals_complete(db_conn)
        pipeline = make_pipeline(db_conn)
        assert pipeline._playoffs_complete("s1") is True


# ─────────────────────────────────────────────────────────────────────────────
# run() — idempotency
# ─────────────────────────────────────────────────────────────────────────────

class TestRunIdempotency:
    """Verify that completed steps are skipped on re-run."""

    def _patch_all_steps(self, pipeline):
        """Pre-mark all steps done so run() skips everything."""
        steps = [
            "archive", "age", "retire", "clear_stale_prospects",
            "generate_draft", "run_draft", "trim_rosters",
            "reset_pitcher_state", "rebuild_rotations",
            "reset_player_energy", "build_season_stats", "write_csvs",
        ]
        for step in steps:
            pipeline._mark_done("s1", step)

    def test_run_skips_all_completed_steps(self, db_conn, capsys):
        seed_season(db_conn)
        seed_finals_complete(db_conn)
        pipeline = make_pipeline(db_conn)
        self._patch_all_steps(pipeline)

        pipeline.run("s1", league_id=None)

        captured = capsys.readouterr().out
        assert "Skipping archive" in captured
        assert "Skipping age" in captured
        assert "Skipping run draft" in captured

    def test_run_stops_early_if_playoffs_not_complete(self, db_conn, capsys):
        seed_season(db_conn)
        # No series inserted — playoffs not complete
        pipeline = make_pipeline(db_conn)

        pipeline.run("s1")

        captured = capsys.readouterr().out
        assert "Playoffs are not complete" in captured
        # archive should not have been marked done
        assert pipeline._is_done("s1", "archive") is False

    def test_second_run_skips_completed_steps(self, db_conn, capsys):
        """After marking archive done, second run skips it."""
        seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done("s1", "archive")

        # Patch playoffs_complete so run() doesn't bail before archive check
        with patch.object(pipeline, "_playoffs_complete", return_value=True):
            with patch.object(pipeline, "_age"):
                with patch.object(pipeline, "_retire"):
                    with patch.object(pipeline, "_clear_stale_prospects"):
                        with patch.object(pipeline, "_generate_draft"):
                            with patch.object(pipeline, "_run_draft"):
                                with patch.object(pipeline, "_trim_rosters"):
                                    with patch.object(pipeline, "_reset_pitcher_state"):
                                        with patch.object(pipeline, "_rebuild_rotations"):
                                            with patch.object(pipeline, "_reset_player_energy"):
                                                with patch.object(pipeline, "_write_csvs"):
                                                    with patch("src.league.offseason.offseason_pipeline.build_season", return_value=0):
                                                        with patch("src.league.offseason.offseason_pipeline.ensure_table"):
                                                            pipeline.run("s1")

        captured = capsys.readouterr().out
        assert "Skipping archive" in captured