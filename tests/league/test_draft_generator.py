# tests/league/test_draft_generator.py
"""
Unit tests for DraftGenerator.

Tests cover:
- Age distribution of generated prospects
- Position distribution (55% pitchers, 45% position players)
- New players inserted into DB with 'prospect' status
- Existing unattached prospects included in draft pool
- Retired/rostered players excluded from draft pool
- draft.csv written with correct format
- No double-counting of existing vs new prospects
"""

import csv
import random
import sqlite3
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
# Schema
# ---------------------------------------------------------------------------

MINIMAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    bats TEXT NOT NULL,
    throws TEXT NOT NULL,
    position TEXT
);

CREATE TABLE IF NOT EXISTS player_skills (
    player_id TEXT PRIMARY KEY,
    age INTEGER NOT NULL DEFAULT 17,
    clutch INTEGER NOT NULL DEFAULT 50,
    speed INTEGER NOT NULL DEFAULT 50,
    power INTEGER NOT NULL DEFAULT 50,
    eye INTEGER NOT NULL DEFAULT 50,
    contact INTEGER NOT NULL DEFAULT 50,
    base_running INTEGER NOT NULL DEFAULT 50,
    bunting INTEGER NOT NULL DEFAULT 50,
    catching INTEGER NOT NULL DEFAULT 50,
    infield INTEGER NOT NULL DEFAULT 50,
    outfield INTEGER NOT NULL DEFAULT 50,
    arm INTEGER NOT NULL DEFAULT 50,
    accuracy INTEGER NOT NULL DEFAULT 50,
    stamina INTEGER NOT NULL DEFAULT 50,
    recovery INTEGER NOT NULL DEFAULT 50,
    ground_balls INTEGER NOT NULL DEFAULT 50,
    strikes INTEGER NOT NULL DEFAULT 50,
    updated_at TEXT,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_talent_caps (
    player_id    TEXT PRIMARY KEY,
    clutch       INTEGER NOT NULL DEFAULT 100,
    speed        INTEGER NOT NULL DEFAULT 100,
    durability   INTEGER NOT NULL DEFAULT 100,
    power        INTEGER NOT NULL DEFAULT 100,
    eye          INTEGER NOT NULL DEFAULT 100,
    contact      INTEGER NOT NULL DEFAULT 100,
    base_running INTEGER NOT NULL DEFAULT 100,
    bunting      INTEGER NOT NULL DEFAULT 100,
    catching     INTEGER NOT NULL DEFAULT 100,
    infield      INTEGER NOT NULL DEFAULT 100,
    outfield     INTEGER NOT NULL DEFAULT 100,
    arm          INTEGER NOT NULL DEFAULT 100,
    accuracy     INTEGER NOT NULL DEFAULT 100,
    stamina      INTEGER NOT NULL DEFAULT 100,
    recovery     INTEGER NOT NULL DEFAULT 100,
    ground_balls INTEGER NOT NULL DEFAULT 100,
    strikes      INTEGER NOT NULL DEFAULT 100,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_status (
    player_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect'
    )),
    since TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS team_players (
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    PRIMARY KEY (team_id, player_id)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(MINIMAL_SCHEMA)
    yield connection
    connection.close()


@pytest.fixture
def rng():
    return random.Random(42)


@pytest.fixture
def generator(conn, rng):
    return DraftGenerator(conn, rng)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def insert_player(conn, player_id, status, team_id=None):
    """Insert a minimal player with status, optionally on a team."""
    conn.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position) VALUES (?,?,?,?,?,?)",
        (player_id, "Test", "Player", "R", "R", "of"),
    )
    conn.execute(
        "INSERT INTO player_skills (player_id, age) VALUES (?, ?)",
        (player_id, 20),
    )
    conn.execute(
        "INSERT INTO player_status (player_id, status, since) VALUES (?, ?, '2025-01-01')",
        (player_id, status),
    )
    if team_id:
        conn.execute("INSERT OR IGNORE INTO teams (id) VALUES (?)", (team_id,))
        conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
            (team_id, player_id),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# _age_distribution_positions
# ---------------------------------------------------------------------------


class TestAgeDistributionPositions:
    def test_returns_correct_count(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        assert len(result) == 1000

    def test_all_ages_in_valid_range(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for age, _ in result:
            assert age in valid_ages

    def test_age_distribution_approximate(self):
        """Age distribution should be roughly correct within 5%."""
        result = _age_distribution_positions(random.Random(42), 10000)
        age_counts = {}
        for age, _ in result:
            age_counts[age] = age_counts.get(age, 0) + 1

        for expected_age, expected_pct in AGE_DISTRIBUTION:
            actual_pct = age_counts.get(expected_age, 0) / 10000
            assert (
                abs(actual_pct - expected_pct) < 0.05
            ), f"Age {expected_age}: expected ~{expected_pct:.0%}, got {actual_pct:.0%}"

    def test_position_distribution_55_percent_pitchers(self):
        """Roughly 55% of positions should be pitchers."""
        result = _age_distribution_positions(random.Random(42), 10000)
        pitcher_count = sum(1 for _, pos in result if pos in PITCHER_POSITIONS)
        pitcher_pct = pitcher_count / 10000
        assert abs(pitcher_pct - 0.55) < 0.03

    def test_position_distribution_45_percent_position_players(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        pos_player_count = sum(
            1 for _, pos in result if pos in POSITION_PLAYER_POSITIONS
        )
        pos_pct = pos_player_count / 10000
        assert abs(pos_pct - 0.45) < 0.03

    def test_pitcher_positions_even_split(self):
        """sp and rp should be roughly equal."""
        result = _age_distribution_positions(random.Random(42), 10000)
        sp_count = sum(1 for _, pos in result if pos == "sp")
        rp_count = sum(1 for _, pos in result if pos == "rp")
        assert abs(sp_count - rp_count) < 300  # within 3% of 10000

    def test_all_positions_represented(self):
        """All 13 positions should appear."""
        result = _age_distribution_positions(random.Random(42), 1000)
        positions_seen = {pos for _, pos in result}
        all_positions = set(PITCHER_POSITIONS + POSITION_PLAYER_POSITIONS)
        assert positions_seen == all_positions

    def test_small_n(self):
        """Should handle small counts without crashing."""
        result = _age_distribution_positions(random.Random(42), 5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _generate_prospects
# ---------------------------------------------------------------------------


class TestGenerateProspects:
    def test_generates_correct_count(self, generator):
        prospects = generator._generate_prospects()
        assert len(prospects) == DRAFT_POOL_SIZE

    def test_all_players_have_valid_ids(self, generator):
        prospects = generator._generate_prospects()
        for p in prospects:
            assert p.id and len(p.id) > 0

    def test_ages_within_range(self, generator):
        prospects = generator._generate_prospects()
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for p in prospects:
            assert p.age in valid_ages, f"Invalid age {p.age}"

    def test_no_duplicate_ids(self, generator):
        prospects = generator._generate_prospects()
        ids = [p.id for p in prospects]
        assert len(ids) == len(set(ids))

    def test_all_have_names(self, generator):
        prospects = generator._generate_prospects()
        for p in prospects:
            assert p.first_name and p.last_name


# ---------------------------------------------------------------------------
# _get_existing_draftable
# ---------------------------------------------------------------------------


class TestGetExistingDraftable:
    def test_returns_prospect_without_team(self, conn, generator):
        insert_player(conn, "p1", "prospect")
        result = generator._get_existing_draftable()
        assert any(p.id == "p1" for p in result)

    def test_returns_unassigned_without_team(self, conn, generator):
        insert_player(conn, "p1", "unassigned")
        result = generator._get_existing_draftable()
        assert any(p.id == "p1" for p in result)

    def test_excludes_rostered_prospect(self, conn, generator):
        """A prospect on a team should not appear."""
        insert_player(conn, "p1", "prospect", team_id="team1")
        result = generator._get_existing_draftable()
        assert not any(p.id == "p1" for p in result)

    def test_excludes_free_agent(self, conn, generator):
        """Free agents (retired) should not appear."""
        insert_player(conn, "p1", "free_agent")
        result = generator._get_existing_draftable()
        assert not any(p.id == "p1" for p in result)

    def test_excludes_26man_player(self, conn, generator):
        insert_player(conn, "p1", "26man", team_id="team1")
        result = generator._get_existing_draftable()
        assert not any(p.id == "p1" for p in result)

    def test_returns_empty_when_none_draftable(self, conn, generator):
        insert_player(conn, "p1", "free_agent")
        insert_player(conn, "p2", "26man", team_id="team1")
        result = generator._get_existing_draftable()
        assert result == []

    def test_returns_multiple_prospects(self, conn, generator):
        insert_player(conn, "p1", "prospect")
        insert_player(conn, "p2", "prospect")
        insert_player(conn, "p3", "unassigned")
        result = generator._get_existing_draftable()
        ids = {p.id for p in result}
        assert ids == {"p1", "p2", "p3"}


# ---------------------------------------------------------------------------
# run() — integration
# ---------------------------------------------------------------------------


class TestDraftGeneratorRun:
    def test_inserts_new_players_into_db(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)

        count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        assert count == DRAFT_POOL_SIZE

    def test_new_players_have_prospect_status(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)

        count = conn.execute(
            "SELECT COUNT(*) FROM player_status WHERE status = 'prospect'"
        ).fetchone()[0]
        assert count == DRAFT_POOL_SIZE

    def test_existing_prospects_included_in_csv(self, conn, generator, tmp_path):
        insert_player(conn, "existing-p1", "prospect")

        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)

        assert total == DRAFT_POOL_SIZE + 1

    def test_existing_rostered_excluded_from_csv(self, conn, generator, tmp_path):
        insert_player(conn, "rostered-p1", "26man", team_id="team1")

        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)

        assert total == DRAFT_POOL_SIZE

    def test_no_double_counting(self, conn, generator, tmp_path):
        """New players inserted before existing query — no overlap."""
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)

        # Should be exactly DRAFT_POOL_SIZE with no existing players
        assert total == DRAFT_POOL_SIZE

    def test_draft_csv_created(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)

        csv_path = tmp_path / "2026" / "draft.csv"
        assert csv_path.exists()

    def test_draft_csv_has_correct_row_count(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)

        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == total

    def test_draft_csv_has_required_columns(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            generator.run("season-1", 2026)

        csv_path = tmp_path / "2026" / "draft.csv"
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        for col in ["Name", "Age", "ID", "PS", "B", "T"]:
            assert col in headers, f"Missing column: {col}"

    def test_returns_total_count(self, conn, generator, tmp_path):
        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            total = generator.run("season-1", 2026)

        assert total == DRAFT_POOL_SIZE

    def test_deterministic_with_same_seed(self, conn, tmp_path):
        """Same seed should produce same player IDs."""
        conn2 = sqlite3.connect(":memory:")
        conn2.row_factory = sqlite3.Row
        conn2.execute("PRAGMA foreign_keys = ON")
        conn2.executescript(MINIMAL_SCHEMA)

        gen1 = DraftGenerator(conn, random.Random(99))
        gen2 = DraftGenerator(conn2, random.Random(99))

        with patch("src.league.offseason.draft_generator.TEAM_FILES_DIR", tmp_path):
            gen1.run("season-1", 2026)
            gen2.run("season-1", 2026)

        ids1 = {r["id"] for r in conn.execute("SELECT id FROM players").fetchall()}
        ids2 = {r["id"] for r in conn2.execute("SELECT id FROM players").fetchall()}
        assert ids1 == ids2

        conn2.close()
