# tests/util/test_team_resolver.py
"""
Unit tests for src/util/team_resolver.py
"""

import pytest

from src.util.team_resolver import resolve_team, list_teams, TeamResolverError

# ── Fixtures ──────────────────────────────────────────────────────────────────

_TEST_TEAMS = [
    ("uuid-tstvienna",    "Tstvienna",    "Tmaestros"),
    ("uuid-tsttokyo",     "Tsttokyo",     "Tsamurai"),
    ("uuid-tstdubai",     "Tstdubai",     "Tfalcons"),
    ("uuid-tstlondon",    "Tstlondon",    "Tlions"),
    ("uuid-tstberlin",    "Tstberlin",    "Teagles"),   # \
    ("uuid-tstfrankfurt", "Tstfrankfurt", "Teagles"),   # / same mascot — ambiguity tests
]


@pytest.fixture
def conn(db_conn):
    """
    Inserts the 6 test teams inside the current savepoint.
    The savepoint rollback in db_conn cleans them up automatically.
    """
    with db_conn.cursor() as cur:
        for team in _TEST_TEAMS:
            cur.execute(
                "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s)", team
            )
    return db_conn


# ── Helpers ───────────────────────────────────────────────────────────────────


def assert_team(result, expected_id, expected_city, expected_mascot):
    assert result["id"] == expected_id
    assert result["city"] == expected_city
    assert result["mascot"] == expected_mascot
    assert result["name"] == f"{expected_city} {expected_mascot}"


# ── UUID lookup ───────────────────────────────────────────────────────────────


def test_resolve_by_exact_uuid(conn):
    result = resolve_team(conn, "uuid-tstvienna")
    assert_team(result, "uuid-tstvienna", "Tstvienna", "Tmaestros")


def test_resolve_by_uuid_unknown(conn):
    with pytest.raises(TeamResolverError, match="No team found"):
        resolve_team(conn, "uuid-does-not-exist")


# ── Full name lookup ──────────────────────────────────────────────────────────


def test_resolve_by_full_name(conn):
    result = resolve_team(conn, "Tstvienna Tmaestros")
    assert_team(result, "uuid-tstvienna", "Tstvienna", "Tmaestros")


def test_resolve_by_full_name_case_insensitive(conn):
    result = resolve_team(conn, "tstvienna tmaestros")
    assert_team(result, "uuid-tstvienna", "Tstvienna", "Tmaestros")


def test_resolve_by_full_name_mixed_case(conn):
    result = resolve_team(conn, "TSTTOKYO TSAMURAI")
    assert_team(result, "uuid-tsttokyo", "Tsttokyo", "Tsamurai")


# ── City-only lookup ──────────────────────────────────────────────────────────


def test_resolve_by_city(conn):
    result = resolve_team(conn, "Tsttokyo")
    assert_team(result, "uuid-tsttokyo", "Tsttokyo", "Tsamurai")


def test_resolve_by_city_case_insensitive(conn):
    result = resolve_team(conn, "tstlondon")
    assert_team(result, "uuid-tstlondon", "Tstlondon", "Tlions")


# ── Mascot-only lookup ────────────────────────────────────────────────────────


def test_resolve_by_mascot(conn):
    result = resolve_team(conn, "Tfalcons")
    assert_team(result, "uuid-tstdubai", "Tstdubai", "Tfalcons")


def test_resolve_by_mascot_case_insensitive(conn):
    result = resolve_team(conn, "tsamurai")
    assert_team(result, "uuid-tsttokyo", "Tsttokyo", "Tsamurai")


def test_resolve_by_mascot_ambiguous(conn):
    """Berlin Eagles and Frankfurt Eagles — mascot alone is ambiguous."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "Teagles")


# ── Partial match ─────────────────────────────────────────────────────────────


def test_resolve_by_partial_city(conn):
    result = resolve_team(conn, "Tstv")
    assert_team(result, "uuid-tstvienna", "Tstvienna", "Tmaestros")


def test_resolve_by_partial_mascot(conn):
    result = resolve_team(conn, "Tsam")
    assert_team(result, "uuid-tsttokyo", "Tsttokyo", "Tsamurai")


def test_resolve_by_partial_ambiguous(conn):
    """'Tst' is a prefix of every test city — always ambiguous within this fixture."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "Tst")


# ── No match ──────────────────────────────────────────────────────────────────


def test_resolve_no_match(conn):
    with pytest.raises(TeamResolverError, match="No team found"):
        resolve_team(conn, "Tstxyz_nomatch")


def test_resolve_empty_string(conn):
    """Empty string after strip — partial LIKE '%%' would match everything."""
    with pytest.raises(TeamResolverError, match="Ambiguous"):
        resolve_team(conn, "   ")


# ── Return shape ──────────────────────────────────────────────────────────────


def test_result_has_all_keys(conn):
    result = resolve_team(conn, "Tstdubai")
    assert set(result.keys()) == {"id", "city", "mascot", "name"}


def test_name_is_city_space_mascot(conn):
    result = resolve_team(conn, "Tstlondon Tlions")
    assert result["name"] == "Tstlondon Tlions"


# ── list_teams ────────────────────────────────────────────────────────────────


def test_list_teams_contains_test_teams(conn):
    teams = list_teams(conn)
    ids = {t["id"] for t in teams}
    assert {t[0] for t in _TEST_TEAMS}.issubset(ids)


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
    result = resolve_team(conn, "  Tstvienna  ")
    assert_team(result, "uuid-tstvienna", "Tstvienna", "Tmaestros")


def test_resolve_full_name_with_extra_spaces(conn):
    # Extra internal spaces won't match the full-name query — falls through
    # to partial match, which should still find a unique team
    result = resolve_team(conn, "  Tsttokyo  ")
    assert_team(result, "uuid-tsttokyo", "Tsttokyo", "Tsamurai")
