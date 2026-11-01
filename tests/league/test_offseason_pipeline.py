# tests/league/test_offseason_pipeline.py
"""
Tests for OffseasonPipeline.

Strategy:
- Pure logic (_should_retire) — no DB needed, fast, exhaustive
- Step tracking (is_done, _mark_done) — db_conn fixture, verify DB state
- _load_season_year — db_conn, simple query
- _playoffs_complete — db_conn, test series/games state
- run() idempotency — mock the heavy steps, verify steps are skipped on re-run
- _age/_archive/_retire — mock dependencies or use minimal seeded DB
"""

import logging
import random
import uuid
from unittest.mock import MagicMock

import pytest

from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.offseason.retirement import RetirementFactors

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_pipeline(db_conn, seed=42):
    return OffseasonPipeline(db_conn, rng=random.Random(seed))


def seed_season(db_conn, season_id=None, year=2025):
    if season_id is None:
        season_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (%s, %s, %s)"
        "  ON CONFLICT DO NOTHING",
        (season_id, year, f"Season {year}"),
    )
    db_conn.commit()
    return season_id


def seed_finals_complete(db_conn, season_id):
    """Insert a completed Finals series with 4 wins for one team."""
    team_id = str(uuid.uuid4())
    team_id2 = str(uuid.uuid4())
    series_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (team_id, "Champ", "Champions"),
    )
    db_conn.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (team_id2, "Runner", "Runners"),
    )
    db_conn.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (series_id, season_id, "Finals"),
    )
    for i in range(4):
        game_id = str(uuid.uuid4())
        db_conn.execute(
            """INSERT INTO games
               (id, game_date, season_id, series_id, home_team_id, away_team_id,
                completed, winner_id)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s)""",
            (
                game_id,
                "2025-10-01",
                season_id,
                series_id,
                team_id,
                team_id2,
                team_id,
            ),
        )
    db_conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# _should_retire — pure logic, no DB
# ─────────────────────────────────────────────────────────────────────────────


class TestShouldRetire:
    """Tests for the static retirement decision. The rostered probability is
    covered in tests/league/test_retirement.py."""

    def test_rostered_young_player_never_retires(self):
        rng = random.Random(0)
        for age in range(17, 30):
            assert OffseasonPipeline._should_retire(age, False, rng) is None

    def test_unrostered_young_never_retires(self):
        rng = random.Random(0)
        for age in range(17, 18):
            assert OffseasonPipeline._should_retire(age, True, rng) is None

    def test_unrostered_old_player_likely_retires(self):
        """Age 35+ unrostered player has high probability."""
        retirements = 0
        for i in range(100):
            result = OffseasonPipeline._should_retire(35, True, random.Random(i))
            if result in ("retired", "free_agent"):
                retirements += 1
        assert retirements > 60  # high probability

    def test_rostered_regular_stays(self):
        """A 38-year-old who played every game almost never retires."""
        factors = RetirementFactors(playing_time=1.0, ovr_drop=3)
        retirements = sum(
            OffseasonPipeline._should_retire(
                38, False, random.Random(i), factors=factors
            )
            == "retired"
            for i in range(300)
        )
        assert retirements <= 10

    def test_probability_caps_at_95_percent(self):
        """Probability never exceeds 0.95."""
        mock_rng = MagicMock()
        mock_rng.random.return_value = 0.94
        # Very old unrostered player — probability should be capped at 0.95
        result = OffseasonPipeline._should_retire(99, True, mock_rng)
        assert result == "retired"  # 0.94 < 0.95 cap

    def test_rostered_unused_declining_player_usually_retires(self):
        """A declining 38-year-old who never got in usually retires."""
        factors = RetirementFactors(ovr_drop=3, below_median=5)
        retirements = sum(
            OffseasonPipeline._should_retire(
                38, False, random.Random(i), factors=factors
            )
            == "retired"
            for i in range(100)
        )
        assert retirements > 70


# ─────────────────────────────────────────────────────────────────────────────
# is_done / _mark_done
# ─────────────────────────────────────────────────────────────────────────────


class TestStepTracking:
    @pytest.mark.slow
    def test_step_not_done_initially(self, db_conn):
        season_id = seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        print(pipeline.os_repo.is_done(season_id, "archive"))
        assert pipeline.os_repo.is_done(season_id, "archive") is False

    def test_mark_done_persists(self, db_conn):
        season_id = seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done(season_id, "archive")
        assert pipeline.os_repo.is_done(season_id, "archive") is True

    def test_mark_done_is_idempotent(self, db_conn):
        season_id = seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done(season_id, "archive")
        pipeline._mark_done(season_id, "archive")  # should not raise
        assert pipeline.os_repo.is_done(season_id, "archive") is True

    def test_different_steps_tracked_independently(self, db_conn):
        season_id = seed_season(db_conn)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done(season_id, "archive")
        assert pipeline.os_repo.is_done(season_id, "archive") is True
        assert pipeline.os_repo.is_done(season_id, "age") is False

    def test_different_seasons_tracked_independently(self, db_conn):
        season_id = seed_season(db_conn, year=2025)
        season_id2 = seed_season(db_conn, year=2026)
        pipeline = make_pipeline(db_conn)
        pipeline._mark_done(season_id, "archive")
        assert pipeline.os_repo.is_done(season_id, "archive") is True
        assert pipeline.os_repo.is_done(season_id2, "archive") is False


# # ─────────────────────────────────────────────────────────────────────────────
# # _load_season_year
# # ─────────────────────────────────────────────────────────────────────────────

# This is gone

# class TestLoadSeasonYear:

#     def test_loads_year_plus_one(self, db_conn):
#         seed_season(db_conn, "s1", 2025)
#         pipeline = make_pipeline(db_conn)
#         year = pipeline._load_season_year("s1")
#         assert year == 2026
#         assert pipeline.year == 2026

#     def test_raises_on_missing_season(self, db_conn):
#         pipeline = make_pipeline(db_conn)
#         with pytest.raises(ValueError, match="Season nonexistent not found"):
#             pipeline._load_season_year("nonexistent")

#     def test_sets_year_attribute(self, db_conn):
#         seed_season(db_conn, "s1", 2030)
#         pipeline = make_pipeline(db_conn)
#         pipeline._load_season_year("s1")
#         assert pipeline.year == 2031


# ─────────────────────────────────────────────────────────────────────────────
# _playoffs_complete
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayoffsComplete:
    def test_returns_false_when_no_finals(self, db_conn):
        new_id = str(uuid.uuid4())
        seed_season(db_conn, season_id=new_id)
        pipeline = make_pipeline(db_conn)
        pipeline.year = 2026
        assert pipeline._playoffs_complete(new_id) is False

    def test_returns_false_when_finals_incomplete(self, db_conn):
        season_id = seed_season(db_conn)
        series_id = str(uuid.uuid4())
        team_a = str(uuid.uuid4())
        team_b = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (team_a, "A", "A"),
        )
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (team_b, "B", "B"),
        )
        db_conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (series_id, season_id, "Finals"),
        )
        # Only 3 wins — not enough
        for i in range(3):
            game_id = str(uuid.uuid4())
            db_conn.execute(
                """INSERT INTO games
                   (id, game_date, season_id, series_id, home_team_id, away_team_id,
                    completed, winner_id)
                   VALUES (%s, %s, %s, %s, %s, %s, 1, %s)""",
                (game_id, "2025-10-01", season_id, series_id, team_a, team_b, team_a),
            )
        db_conn.commit()
        pipeline = make_pipeline(db_conn)
        assert pipeline._playoffs_complete(season_id) is False

    def test_returns_true_when_finals_has_4_wins(self, db_conn):
        season_id = seed_season(db_conn)
        seed_finals_complete(db_conn, season_id=season_id)
        pipeline = make_pipeline(db_conn)
        assert pipeline._playoffs_complete(season_id) is True


# ─────────────────────────────────────────────────────────────────────────────
# run() — idempotency
# ─────────────────────────────────────────────────────────────────────────────


class TestRunIdempotency:
    """Verify that completed steps are skipped on re-run."""

    def _patch_all_steps(self, pipeline, season_id):
        """Pre-mark all steps done so run() skips everything."""
        steps = [
            "archive",
            "age",
            "retire",
            "clear_stale_prospects",
            "generate_draft",
            "run_draft",
            "trim_rosters",
            "reset_pitcher_state",
            "rebuild_rotations",
            "reset_player_energy",
            "build_season_stats",
        ]
        for step in steps:
            pipeline._mark_done(season_id, step)

    def test_run_skips_all_completed_steps(self, db_conn, caplog):
        season_id = seed_season(db_conn)
        seed_finals_complete(db_conn, season_id)
        pipeline = make_pipeline(db_conn)
        self._patch_all_steps(pipeline, season_id)

        with caplog.at_level(logging.INFO):
            pipeline.run(season_id, league_id=None)

        captured = caplog.text
        assert "Skipping archive" in captured
        assert "Skipping age" in captured
        assert "Skipping run draft" in captured

    def test_run_stops_early_if_playoffs_not_complete(self, db_conn, caplog):
        season_id = seed_season(db_conn)
        # No series inserted — playoffs not complete
        pipeline = make_pipeline(db_conn)

        with caplog.at_level(logging.INFO):
            pipeline.run(season_id, "l1")

        captured = caplog.text
        assert "Playoffs are not complete" in captured
        # archive should not have been marked done
        assert pipeline.os_repo.is_done(season_id, "archive") is False

    # nonsense
    # def test_second_run_skips_completed_steps(self, db_conn, capsys):
    #     """After marking archive done, second run skips it."""
    #     seed_season(db_conn)
    #     pipeline = make_pipeline(db_conn)
    #     pipeline._mark_done("s1", "archive")

    #     # Patch playoffs_complete so run() doesn't bail before archive check
    #     with patch.object(pipeline, "_playoffs_complete", return_value=True):
    #         with patch.object(pipeline, "_age"):
    #             with patch.object(pipeline, "_retire"):
    #                 with patch.object(pipeline, "_clear_stale_prospects"):
    #                     with patch.object(pipeline, "_generate_draft"):
    #                         with patch.object(pipeline, "_run_draft"):
    #                             with patch.object(pipeline, "_trim_rosters"):
    #                                 with patch.object(pipeline, "_reset_pitcher_state"):
    #                                     with patch.object(
    #                                         pipeline, "_rebuild_rotations"
    #                                     ):
    #                                         with patch.object(
    #                                             pipeline, "_reset_player_energy"
    #                                         ):
    #                                             with patch.object(
    #                                                 pipeline, "_write_csvs"
    #                                             ):
    #                                                 with patch(
    #                                                     "src.league.offseason.offseason_pipeline.build_season",
    #                                                     return_value=0,
    #                                                 ):
    #                                                     # with patch(
    #                                                     #     "src.league.offseason.offseason_pipeline.ensure_table"
    #                                                     # ):
    #                                                     pipeline.run("s1")

    #     captured = capsys.readouterr().out
    #     assert "Skipping archive" in captured
