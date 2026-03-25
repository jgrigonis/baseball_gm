# tests/util/test_team_resolver.py
"""
Unit tests for src/util/team_resolver.py

Uses an in-memory SQLite database with a minimal teams table.
"""

import sqlite3
import pytest

from src.util.team_resolver import resolve_team, list_teams, TeamResolverError

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conn():
    """In-memory DB with a small teams table."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE teams (
            id      TEXT PRIMARY KEY,
            city    TEXT NOT NULL,
            mascot  TEXT NOT NULL
        )
    """)
    db.executemany(
        "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        [
            ("uuid-vienna", "Vienna", "Maestros"),
            ("uuid-tokyo", "Tokyo", "Samurai"),
            ("uuid-dubai", "Dubai", "Falcons"),
            ("uuid-london", "London", "Lions"),
            # Two teams sharing a mascot — for ambiguity tests
            ("uuid-berlin", "Berlin", "Eagles"),
            ("uuid-frankfurt", "Frankfurt", "Eagles"),
        ],
    )
    db.commit()
    yield db
    db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────


def assert_team(result, expected_id, expected_city, expected_mascot):
    assert result["id"] == expected_id
    assert result["city"] == expected_city
    assert result["mascot"] == expected_mascot
    assert result["name"] == f"{expected_city} {expected_mascot}"


# ── UUID lookup ───────────────────────────────────────────────────────────────


def test_resolve_by_exact_uuid(conn):
    result = resolve_team(conn, "uuid-vienna")
    assert_team(result, "uuid-vienna", "Vienna", "Maestros")


def test_resolve_by_uuid_unknown(conn):
    with pytest.raises(TeamResolverError, match="No team found"):
        resolve_team(conn, "uuid-does-not-exist")


# ── Full name lookup ──────────────────────────────────────────────────────────


def test_resolve_by_full_name(conn):
    result = resolve_team(conn, "Vienna Maestros")
    assert_team(result, "uuid-vienna", "Vienna", "Maestros")


def test_resolve_by_full_name_case_insensitive(conn):
    result = resolve_team(conn, "vienna maestros")
    assert_team(result, "uuid-vienna", "Vienna", "Maestros")


def test_resolve_by_full_name_mixed_case(conn):
    result = resolve_team(conn, "TOKYO SAMURAI")
    assert_team(result, "uuid-tokyo", "Tokyo", "Samurai")


# ── City-only lookup ──────────────────────────────────────────────────────────


def test_resolve_by_city(conn):
    result = resolve_team(conn, "Tokyo")
    assert_team(result, "uuid-tokyo", "Tokyo", "Samurai")


def test_resolve_by_city_case_insensitive(conn):
    result = resolve_team(conn, "london")
    assert_team(result, "uuid-london", "London", "Lions")


# ── Mascot-only lookup ────────────────────────────────────────────────────────


def test_resolve_by_mascot(conn):
    result = resolve_team(conn, "Falcons")
    assert_team(result, "uuid-dubai", "Dubai", "Falcons")


def test_resolve_by_mascot_case_insensitive(conn):
    result = resolve_team(conn, "samurai")
    assert_team(result, "uuid-tokyo", "Tokyo", "Samurai")


def test_resolve_by_mascot_ambiguous(conn):
    """Berlin Eagles and Frankfurt Eagles — mascot alone is ambiguous."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "Eagles")


# ── Partial match ─────────────────────────────────────────────────────────────


def test_resolve_by_partial_city(conn):
    result = resolve_team(conn, "Vien")
    assert_team(result, "uuid-vienna", "Vienna", "Maestros")


def test_resolve_by_partial_mascot(conn):
    result = resolve_team(conn, "Samur")
    assert_team(result, "uuid-tokyo", "Tokyo", "Samurai")


def test_resolve_by_partial_ambiguous(conn):
    """'a' matches multiple cities/mascots."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "a")


# ── No match ──────────────────────────────────────────────────────────────────


def test_resolve_no_match(conn):
    with pytest.raises(TeamResolverError, match="No team found"):
        resolve_team(conn, "Sydney")


def test_resolve_empty_string(conn):
    """Empty string after strip — partial LIKE '%%' would match everything."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "   ")


# ── Return shape ──────────────────────────────────────────────────────────────


def test_result_has_all_keys(conn):
    result = resolve_team(conn, "Dubai")
    assert set(result.keys()) == {"id", "city", "mascot", "name"}


def test_name_is_city_space_mascot(conn):
    result = resolve_team(conn, "London Lions")
    assert result["name"] == "London Lions"


# ── list_teams ────────────────────────────────────────────────────────────────


def test_list_teams_returns_all(conn):
    teams = list_teams(conn)
    assert len(teams) == 6


def test_list_teams_sorted_by_city(conn):
    teams = list_teams(conn)
    cities = [t["city"] for t in teams]
    assert cities == sorted(cities)


def test_list_teams_have_name_key(conn):
    teams = list_teams(conn)
    for t in teams:
        assert t["name"] == f"{t['city']} {t['mascot']}"


# ── Whitespace handling ───────────────────────────────────────────────────────


def test_resolve_strips_whitespace(conn):
    result = resolve_team(conn, "  Vienna  ")
    assert_team(result, "uuid-vienna", "Vienna", "Maestros")


def test_resolve_full_name_with_extra_spaces(conn):
    # Extra internal spaces won't match the full-name query — falls through
    # to partial match, which should still find a unique team
    result = resolve_team(conn, "  Tokyo  ")
    assert_team(result, "uuid-tokyo", "Tokyo", "Samurai")
