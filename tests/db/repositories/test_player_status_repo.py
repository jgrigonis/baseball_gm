# tests/db/repositories/test_player_status_repo.py
"""
Unit tests for PlayerStatusRepository.

Tests cover:
- set_status: insert and upsert behavior
- get_status: found and not found
- get_by_status: filtering by status
- get_by_team_and_status: join with team_players
- bulk_set: mass insert and upsert
"""

import sqlite3
from datetime import date

import pytest

from src.db.repositories.player_status_repo import PlayerStatusRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory SQLite DB with minimal schema."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE players (
            id TEXT PRIMARY KEY
        );

        CREATE TABLE teams (
            id TEXT PRIMARY KEY
        );

        CREATE TABLE team_players (
            team_id   TEXT NOT NULL,
            player_id TEXT NOT NULL,
            PRIMARY KEY (team_id, player_id)
        );

        CREATE TABLE player_status (
            player_id TEXT PRIMARY KEY,
            status    TEXT NOT NULL CHECK (status IN (
                'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect'
            )),
            since     TEXT NOT NULL
        );
    """
    )
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return PlayerStatusRepository(conn)


def seed_players(conn, *player_ids):
    """Insert minimal player rows."""
    conn.executemany(
        "INSERT INTO players (id) VALUES (?)",
        [(pid,) for pid in player_ids],
    )
    conn.commit()


def seed_team(conn, team_id, *player_ids):
    """Insert a team and associate players."""
    conn.execute("INSERT INTO teams (id) VALUES (?)", (team_id,))
    conn.executemany(
        "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
        [(team_id, pid) for pid in player_ids],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------


class TestSetStatus:
    def test_insert_new_player(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "26man")
        assert repo.get_status("p1") == "26man"

    def test_upsert_updates_status(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "26man")
        repo.set_status("p1", "minors")
        assert repo.get_status("p1") == "minors"

    def test_upsert_updates_since(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "26man", since=date(2025, 1, 1))
        repo.set_status("p1", "40man", since=date(2026, 4, 1))

        row = conn.execute(
            "SELECT since FROM player_status WHERE player_id = ?", ("p1",)
        ).fetchone()
        assert row["since"] == "2026-04-01"

    def test_since_defaults_to_today(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "prospect")

        row = conn.execute(
            "SELECT since FROM player_status WHERE player_id = ?", ("p1",)
        ).fetchone()
        assert row["since"] == date.today().isoformat()

    def test_explicit_since_date(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "minors", since=date(2025, 3, 15))

        row = conn.execute(
            "SELECT since FROM player_status WHERE player_id = ?", ("p1",)
        ).fetchone()
        assert row["since"] == "2025-03-15"

    def test_all_valid_statuses(self, conn, repo):
        valid = ["unassigned", "26man", "40man", "minors", "free_agent", "prospect"]
        for i, status in enumerate(valid):
            pid = f"p{i}"
            seed_players(conn, pid)
            repo.set_status(pid, status)
            assert repo.get_status(pid) == status


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_status_for_known_player(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "40man")
        assert repo.get_status("p1") == "40man"

    def test_returns_none_for_unknown_player(self, repo):
        assert repo.get_status("nonexistent") is None

    def test_returns_latest_status_after_update(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "unassigned")
        repo.set_status("p1", "26man")
        repo.set_status("p1", "minors")
        assert repo.get_status("p1") == "minors"


# ---------------------------------------------------------------------------
# get_by_status
# ---------------------------------------------------------------------------


class TestGetByStatus:
    def test_returns_players_with_matching_status(self, conn, repo):
        seed_players(conn, "p1", "p2", "p3")
        repo.set_status("p1", "26man")
        repo.set_status("p2", "26man")
        repo.set_status("p3", "minors")

        result = repo.get_by_status("26man")
        assert set(result) == {"p1", "p2"}

    def test_returns_empty_list_when_none_match(self, conn, repo):
        seed_players(conn, "p1")
        repo.set_status("p1", "minors")

        result = repo.get_by_status("prospect")
        assert result == []

    def test_returns_all_matching_statuses(self, conn, repo):
        seed_players(conn, "p1", "p2", "p3", "p4")
        for pid in ["p1", "p2", "p3", "p4"]:
            repo.set_status(pid, "minors")

        result = repo.get_by_status("minors")
        assert set(result) == {"p1", "p2", "p3", "p4"}

    def test_does_not_return_other_statuses(self, conn, repo):
        seed_players(conn, "p1", "p2")
        repo.set_status("p1", "26man")
        repo.set_status("p2", "40man")

        result = repo.get_by_status("minors")
        assert result == []


# ---------------------------------------------------------------------------
# get_by_team_and_status
# ---------------------------------------------------------------------------


class TestGetByTeamAndStatus:
    def test_returns_players_on_team_with_status(self, conn, repo):
        seed_players(conn, "p1", "p2", "p3")
        seed_team(conn, "teamA", "p1", "p2", "p3")
        repo.set_status("p1", "26man")
        repo.set_status("p2", "26man")
        repo.set_status("p3", "minors")

        result = repo.get_by_team_and_status("teamA", "26man")
        assert set(result) == {"p1", "p2"}

    def test_does_not_return_players_from_other_teams(self, conn, repo):
        seed_players(conn, "p1", "p2")
        seed_team(conn, "teamA", "p1")
        seed_team(conn, "teamB", "p2")
        repo.set_status("p1", "26man")
        repo.set_status("p2", "26man")

        result = repo.get_by_team_and_status("teamA", "26man")
        assert result == ["p1"]

    def test_returns_empty_when_no_match(self, conn, repo):
        seed_players(conn, "p1")
        seed_team(conn, "teamA", "p1")
        repo.set_status("p1", "minors")

        result = repo.get_by_team_and_status("teamA", "26man")
        assert result == []

    def test_returns_empty_for_unknown_team(self, conn, repo):
        result = repo.get_by_team_and_status("ghost_team", "26man")
        assert result == []


# ---------------------------------------------------------------------------
# bulk_set
# ---------------------------------------------------------------------------


class TestBulkSet:
    def test_inserts_all_assignments(self, conn, repo):
        seed_players(conn, "p1", "p2", "p3")
        repo.bulk_set({"p1": "26man", "p2": "40man", "p3": "minors"})

        assert repo.get_status("p1") == "26man"
        assert repo.get_status("p2") == "40man"
        assert repo.get_status("p3") == "minors"

    def test_upserts_existing_players(self, conn, repo):
        seed_players(conn, "p1", "p2")
        repo.bulk_set({"p1": "unassigned", "p2": "unassigned"})
        repo.bulk_set({"p1": "26man", "p2": "minors"})

        assert repo.get_status("p1") == "26man"
        assert repo.get_status("p2") == "minors"

    def test_since_applied_to_all(self, conn, repo):
        seed_players(conn, "p1", "p2")
        repo.bulk_set({"p1": "26man", "p2": "40man"}, since=date(2025, 6, 1))

        for pid in ["p1", "p2"]:
            row = conn.execute(
                "SELECT since FROM player_status WHERE player_id = ?", (pid,)
            ).fetchone()
            assert row["since"] == "2025-06-01"

    def test_empty_dict_does_nothing(self, conn, repo):
        repo.bulk_set({})
        rows = conn.execute("SELECT COUNT(*) as n FROM player_status").fetchone()
        assert rows["n"] == 0

    def test_large_bulk_set(self, conn, repo):
        player_ids = [f"p{i:04d}" for i in range(160)]
        seed_players(conn, *player_ids)

        assignments = {}
        for i, pid in enumerate(player_ids):
            if i < 26:
                assignments[pid] = "26man"
            elif i < 40:
                assignments[pid] = "40man"
            else:
                assignments[pid] = "minors"

        repo.bulk_set(assignments)

        assert len(repo.get_by_status("26man")) == 26
        assert len(repo.get_by_status("40man")) == 14
        assert len(repo.get_by_status("minors")) == 120
