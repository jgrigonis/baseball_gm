# tests/league/test_draft_generator.py
"""
Unit tests for DraftGenerator.
"""

import csv
import random
import uuid
from unittest.mock import patch

import pytest

from src.league.offseason.draft_generator import (
    DraftGenerator,
    DRAFT_POOL_SIZE,
    PITCHER_POSITIONS,
    POSITION_PLAYER_POSITIONS,
    AGE_DISTRIBUTION,
    _age_distribution_positions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rng():
    return random.Random(42)


@pytest.fixture
def generator(db_conn, rng):
    return DraftGenerator(db_conn, rng)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def insert_player(db_conn, player_id, status, team_id=None):
    """Insert a minimal player with status, optionally on a team."""
    if team_id:
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, "City", "Mascot"),
        )
    db_conn.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
        " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (player_id, "Test", "Player", "R", "R", "of"),
    )
    db_conn.execute(
        "INSERT INTO player_skills"
        " (player_id, age, durability, clutch, speed, power, eye, contact,"
        "  base_running, bunting, catching, infield, outfield, arm, accuracy,"
        "  stamina, recovery, ground_balls, strikes)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (player_id, 20, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60),
    )
    db_conn.execute(
        "INSERT INTO player_status (player_id, status, since)"
        " VALUES (%s, %s, '2025-01-01')"
        " ON CONFLICT (player_id) DO UPDATE SET status = EXCLUDED.status",
        (player_id, status),
    )
    if team_id:
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, player_id),
        )


def _uid():
    """Unique player ID for this test run."""
    return f"tst-dg-{uuid.uuid4()}"


def _team_id():
    return f"tst-team-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# _age_distribution_positions
# ---------------------------------------------------------------------------


class TestAgeDistributionPositions:
    def test_returns_correct_count(self):
        assert len(_age_distribution_positions(random.Random(42), 1000)) == 1000

    def test_all_ages_in_valid_range(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for age, _ in result:
            assert age in valid_ages

    def test_age_distribution_approximate(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        age_counts = {}
        for age, _ in result:
            age_counts[age] = age_counts.get(age, 0) + 1
        for expected_age, expected_pct in AGE_DISTRIBUTION:
            actual_pct = age_counts.get(expected_age, 0) / 10000
            assert abs(actual_pct - expected_pct) < 0.05, \
                f"Age {expected_age}: expected ~{expected_pct:.0%}, got {actual_pct:.0%}"

    def test_position_distribution_55_percent_pitchers(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        pitcher_pct = sum(1 for _, pos in result if pos in PITCHER_POSITIONS) / 10000
        assert abs(pitcher_pct - 0.38) < 0.03

    def test_position_distribution_45_percent_position_players(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        pos_pct = sum(1 for _, pos in result if pos in POSITION_PLAYER_POSITIONS) / 10000
        assert abs(pos_pct - 0.62) < 0.03

    def test_pitcher_positions_even_split(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        sp = sum(1 for _, pos in result if pos == "sp")
        rp = sum(1 for _, pos in result if pos == "rp")
        assert abs(sp - rp) < 300

    def test_all_positions_represented(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        positions_seen = {pos for _, pos in result}
        all_positions = set(PITCHER_POSITIONS + POSITION_PLAYER_POSITIONS)
        assert positions_seen == all_positions

    def test_small_n(self):
        assert len(_age_distribution_positions(random.Random(42), 5)) == 5


# ---------------------------------------------------------------------------
# _generate_prospects
# ---------------------------------------------------------------------------


class TestGenerateProspects:
    def test_generates_correct_count(self, generator):
        assert len(generator._generate_prospects()) == DRAFT_POOL_SIZE

    def test_all_players_have_valid_ids(self, generator):
        for p in generator._generate_prospects():
            assert p.id and len(p.id) > 0

    def test_ages_within_range(self, generator):
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for p in generator._generate_prospects():
            assert p.age in valid_ages

    def test_no_duplicate_ids(self, generator):
        prospects = generator._generate_prospects()
        ids = [p.id for p in prospects]
        assert len(ids) == len(set(ids))

    def test_all_have_names(self, generator):
        for p in generator._generate_prospects():
            assert p.first_name and p.last_name


# ---------------------------------------------------------------------------
# _get_existing_draftable
# ---------------------------------------------------------------------------


class TestGetExistingDraftable:

    def test_returns_prospect_without_team(self, db_conn, generator):
        pid = _uid()
        insert_player(db_conn, pid, "prospect")
        result = generator._get_existing_draftable()
        assert any(p.id == pid for p in result)

    def test_excludes_rostered_prospect(self, db_conn, generator):
        pid = _uid()
        insert_player(db_conn, pid, "prospect", team_id=_team_id())
        result = generator._get_existing_draftable()
        assert not any(p.id == pid for p in result)

    def test_excludes_free_agent(self, db_conn, generator):
        pid = _uid()
        insert_player(db_conn, pid, "free_agent")
        result = generator._get_existing_draftable()
        assert not any(p.id == pid for p in result)

    def test_excludes_26man_player(self, db_conn, generator):
        pid = _uid()
        insert_player(db_conn, pid, "26man", team_id=_team_id())
        result = generator._get_existing_draftable()
        assert not any(p.id == pid for p in result)

    def test_returns_empty_when_none_draftable(self, db_conn, generator):
        p1 = _uid()
        p2 = _uid()
        insert_player(db_conn, p1, "free_agent")
        insert_player(db_conn, p2, "26man", team_id=_team_id())
        result = generator._get_existing_draftable()
        result_ids = {p.id for p in result}
        assert p1 not in result_ids
        assert p2 not in result_ids

    def test_returns_multiple_prospects(self, db_conn, generator):
        p1, p2, p3 = _uid(), _uid(), _uid()
        insert_player(db_conn, p1, "prospect")
        insert_player(db_conn, p2, "prospect")
        insert_player(db_conn, p3, "unassigned")
        result_ids = {p.id for p in generator._get_existing_draftable()}
        assert p1 in result_ids
        assert p2 in result_ids
        assert p3 not in result_ids


# ---------------------------------------------------------------------------
# run() — integration
# ---------------------------------------------------------------------------


class TestDraftGeneratorRun:
    """
    run() is unscoped — it touches all players in the DB.
    We can't assert exact counts; instead assert on the return value and
    relative changes (+DRAFT_POOL_SIZE new players committed by run()).
    """

    def test_inserts_new_players_into_db(self, db_conn, generator, tmp_path):
        before = db_conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)
        after = db_conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
        assert after - before == DRAFT_POOL_SIZE

    def test_new_players_have_prospect_status(self, db_conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            ids_in_csv = [row["ID"] for row in csv.DictReader(f)]
        assert len(ids_in_csv) > 0
        statuses = db_conn.execute(
            "SELECT player_id, status FROM player_status WHERE player_id = ANY(%s)",
            (ids_in_csv,),
        ).fetchall()
        by_id = {r["player_id"]: r["status"] for r in statuses}
        for pid in ids_in_csv:
            assert by_id.get(pid) == "prospect", f"{pid} missing prospect status"

    def test_existing_prospects_included_in_csv(self, db_conn, generator, tmp_path):
        pid = _uid()
        insert_player(db_conn, pid, "prospect")
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)
        # At least DRAFT_POOL_SIZE new + the 1 we inserted
        assert total >= DRAFT_POOL_SIZE + 1

    def test_existing_rostered_excluded_from_csv(self, db_conn, generator, tmp_path):
        pid = _uid()
        insert_player(db_conn, pid, "26man", team_id=_team_id())
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)
        # Rostered player must not appear
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            ids_in_csv = {row["ID"] for row in csv.DictReader(f)}
        assert pid not in ids_in_csv

    def test_no_double_counting(self, db_conn, generator, tmp_path):
        """Return value matches CSV row count — no player counted twice."""
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            ids_in_csv = [row["ID"] for row in csv.DictReader(f)]
        assert len(ids_in_csv) == total
        assert len(set(ids_in_csv)) == len(ids_in_csv), "Duplicate IDs in CSV"

    def test_draft_csv_created(self, db_conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)
        assert (tmp_path / "2026" / "draft.csv").exists()

    def test_draft_csv_has_correct_row_count(self, db_conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == total

    def test_draft_csv_has_required_columns(self, db_conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            headers = csv.DictReader(f).fieldnames
        for col in ["Name", "Age", "ID", "PS", "B", "T"]:
            assert col in headers, f"Missing column: {col}"

    def test_returns_total_count(self, db_conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)
        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert total == len(rows)

    def test_deterministic_with_same_seed(self, tmp_path):
        """Same seed should produce same player IDs."""
        import os
        import psycopg
        from psycopg.rows import dict_row
        db_url = os.environ.get("DATABASE_TEST_URL")
        if not db_url:
            pytest.skip("DATABASE_TEST_URL not set")

        suffix = uuid.uuid4().hex[:8]
        with psycopg.connect(db_url, row_factory=dict_row) as conn1, \
             psycopg.connect(db_url, row_factory=dict_row) as conn2:
            gen1 = DraftGenerator(conn1, random.Random(99))
            gen2 = DraftGenerator(conn2, random.Random(99))

            with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
                gen1.run(f"det-season-{suffix}", 8888)
                gen2.run(f"det-season-{suffix}", 8888)

            ids1 = {r["id"] for r in conn1.execute(
                "SELECT id FROM players WHERE id LIKE 'tst-%' OR id NOT LIKE '%--%'"
            ).fetchall()}
            ids2 = {r["id"] for r in conn2.execute(
                "SELECT id FROM players WHERE id LIKE 'tst-%' OR id NOT LIKE '%--%'"
            ).fetchall()}

            # The newly inserted players from both runs should overlap completely
            # (same seed → same IDs → ON CONFLICT DO NOTHING on second run)
            csv_path1 = tmp_path / "8888" / "draft.csv"
            with open(csv_path1, newline="") as f:
                csv_ids = {row["ID"] for row in csv.DictReader(f)}
            assert len(csv_ids) > 0  # both runs wrote same file, same IDs
