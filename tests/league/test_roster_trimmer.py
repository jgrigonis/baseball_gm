# tests/league/test_roster_trimmer.py
"""
Unit tests for RosterTrimmer.

Tests cover:
- Teams under limit: no cuts made
- Teams at limit: no cuts made
- Teams over limit: worst-rated minors cut first
- 26man and 40man players always protected
- Cut players become free_agent and removed from team_players
- Multiple teams trimmed independently
- Total cut count returned correctly
"""

import sqlite3

import pytest

from src.league.offseason.roster_trimmer import RosterTrimmer, MINORS_LIMIT

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

MINIMAL_SCHEMA = """
PRAGMA foreign_keys = ON;

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
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS player_status (
    player_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect'
    )),
    since TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    mascot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    PRIMARY KEY (team_id, player_id)
);

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    year INTEGER
);

CREATE TABLE IF NOT EXISTS leagues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS league_season_teams (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    PRIMARY KEY (league_id, season_id, team_id)
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
def trimmer(conn):
    return RosterTrimmer(conn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _next_id():
    global _counter
    _counter += 1
    return f"player-{_counter:04d}"


def setup_season(conn, season_id="s1", team_ids=("t1",)):
    conn.execute(
        "INSERT OR IGNORE INTO seasons (id, year) VALUES (?, 2026)", (season_id,)
    )
    conn.execute(
        "INSERT OR IGNORE INTO leagues (id, name) VALUES ('lg1', 'Test League')"
    )
    for team_id in team_ids:
        conn.execute(
            "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, 'Test', 'Team')",
            (team_id,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO league_season_teams (league_id, season_id, team_id) VALUES ('lg1', ?, ?)",
            (season_id, team_id),
        )
    conn.commit()


def insert_player(conn, team_id, status, strikes=50, speed=50, player_id=None):
    """Insert a player with given status and key skills that affect prospect_rating."""
    pid = player_id or _next_id()
    conn.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position) VALUES (?,?,?,?,?,?)",
        (pid, "Test", "Player", "R", "R", "of"),
    )
    conn.execute(
        """INSERT INTO player_skills
           (player_id, age, strikes, stamina, recovery, accuracy, clutch,
            speed, power, arm, eye, contact, base_running,
            bunting, catching, infield, outfield, ground_balls)
           VALUES (?,20,?,50,50,50,50,?,50,50,50,50,50,50,50,50,50,50)""",
        (pid, strikes, speed),
    )
    conn.execute(
        "INSERT INTO player_status (player_id, status, since) VALUES (?, ?, '2026-01-01')",
        (pid, status),
    )
    conn.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
        (team_id, pid),
    )
    conn.commit()
    return pid


def insert_n_minors(conn, team_id, n, base_strikes=50):
    """Insert n minors players, each with slightly different ratings."""
    ids = []
    for i in range(n):
        pid = insert_player(
            conn, team_id, "minors", strikes=max(1, min(99, base_strikes + i))
        )
        ids.append(pid)
    return ids


def count_team_players(conn, team_id, status=None):
    if status:
        return conn.execute(
            """SELECT COUNT(*) FROM team_players tp
               JOIN player_status ps ON tp.player_id = ps.player_id
               WHERE tp.team_id = ? AND ps.status = ?""",
            (team_id, status),
        ).fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM team_players WHERE team_id = ?", (team_id,)
    ).fetchone()[0]


def get_status(conn, player_id):
    row = conn.execute(
        "SELECT status FROM player_status WHERE player_id = ?", (player_id,)
    ).fetchone()
    return row["status"] if row else None


def in_team(conn, team_id, player_id):
    return (
        conn.execute(
            "SELECT 1 FROM team_players WHERE team_id = ? AND player_id = ?",
            (team_id, player_id),
        ).fetchone()
        is not None
    )


# ---------------------------------------------------------------------------
# _trim_team
# ---------------------------------------------------------------------------


class TestTrimTeam:
    def test_no_cut_when_under_limit(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT - 10)
        cut = trimmer._trim_team("t1")
        assert cut == 0

    def test_no_cut_when_at_limit(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT)
        cut = trimmer._trim_team("t1")
        assert cut == 0

    def test_cuts_correct_number_over_limit(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 15)
        cut = trimmer._trim_team("t1")
        assert cut == 15

    def test_minors_count_after_trim(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 20)
        trimmer._trim_team("t1")
        remaining = count_team_players(conn, "t1", status="minors")
        assert remaining == MINORS_LIMIT

    def test_cut_players_become_free_agent(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 5)
        trimmer._trim_team("t1")
        conn.commit()

        fa_count = conn.execute(
            "SELECT COUNT(*) FROM player_status WHERE status = 'free_agent'"
        ).fetchone()[0]
        assert fa_count == 5

    def test_cut_players_removed_from_team_players(self, conn, trimmer):
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 5)
        trimmer._trim_team("t1")
        conn.commit()

        remaining = count_team_players(conn, "t1")
        assert remaining == MINORS_LIMIT

    def test_worst_rated_cut_first(self, conn, trimmer):
        """Players with lowest prospect_rating should be cut."""
        setup_season(conn, team_ids=["t1"])

        # Insert MINORS_LIMIT average players
        insert_n_minors(conn, "t1", MINORS_LIMIT, base_strikes=50)

        # Insert 3 clearly bad players (should be cut)
        bad_ids = [
            insert_player(conn, "t1", "minors", strikes=1, speed=1),
            insert_player(conn, "t1", "minors", strikes=1, speed=1),
            insert_player(conn, "t1", "minors", strikes=1, speed=1),
        ]

        trimmer._trim_team("t1")
        conn.commit()

        for pid in bad_ids:
            assert get_status(conn, pid) == "free_agent", f"{pid} should be cut"
            assert not in_team(conn, "t1", pid), f"{pid} should not be on team"

    def test_best_rated_kept(self, conn, trimmer):
        """Players with highest prospect_rating should survive cuts."""
        setup_season(conn, team_ids=["t1"])

        insert_n_minors(conn, "t1", MINORS_LIMIT, base_strikes=30)

        # Insert 5 elite players (should survive)
        elite_ids = [
            insert_player(conn, "t1", "minors", strikes=99, speed=99),
            insert_player(conn, "t1", "minors", strikes=99, speed=99),
            insert_player(conn, "t1", "minors", strikes=99, speed=99),
            insert_player(conn, "t1", "minors", strikes=99, speed=99),
            insert_player(conn, "t1", "minors", strikes=99, speed=99),
        ]

        trimmer._trim_team("t1")
        conn.commit()

        for pid in elite_ids:
            assert get_status(conn, pid) == "minors", f"{pid} should be kept"
            assert in_team(conn, "t1", pid), f"{pid} should still be on team"

    def test_26man_players_never_cut(self, conn, trimmer):
        """26man players must not be touched even when over minors limit."""
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 5)

        protected_ids = [
            insert_player(conn, "t1", "26man", strikes=1, speed=1),
            insert_player(conn, "t1", "26man", strikes=1, speed=1),
        ]

        trimmer._trim_team("t1")
        conn.commit()

        for pid in protected_ids:
            assert (
                get_status(conn, pid) == "26man"
            ), f"26man player {pid} should be protected"
            assert in_team(conn, "t1", pid)

    def test_40man_players_never_cut(self, conn, trimmer):
        """40man players must not be touched."""
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 5)

        protected_ids = [
            insert_player(conn, "t1", "40man", strikes=1, speed=1),
            insert_player(conn, "t1", "40man", strikes=1, speed=1),
        ]

        trimmer._trim_team("t1")
        conn.commit()

        for pid in protected_ids:
            assert (
                get_status(conn, pid) == "40man"
            ), f"40man player {pid} should be protected"
            assert in_team(conn, "t1", pid)

    def test_no_minors_no_cut(self, conn, trimmer):
        """Team with only 26man/40man players and no minors: no cuts."""
        setup_season(conn, team_ids=["t1"])
        for _ in range(26):
            insert_player(conn, "t1", "26man")
        for _ in range(14):
            insert_player(conn, "t1", "40man")

        cut = trimmer._trim_team("t1")
        assert cut == 0


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRosterTrimmerRun:
    def test_trims_all_teams(self, conn, trimmer):
        setup_season(conn, team_ids=["t1", "t2"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 10)
        insert_n_minors(conn, "t2", MINORS_LIMIT + 20)

        total = trimmer.run("s1")
        assert total == 30

    def test_returns_total_cut_count(self, conn, trimmer):
        setup_season(conn, team_ids=["t1", "t2", "t3"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 5)
        insert_n_minors(conn, "t2", MINORS_LIMIT)  # at limit, no cuts
        insert_n_minors(conn, "t3", MINORS_LIMIT + 8)

        total = trimmer.run("s1")
        assert total == 13

    def test_teams_under_limit_unaffected(self, conn, trimmer):
        setup_season(conn, team_ids=["t1", "t2"])
        insert_n_minors(conn, "t1", MINORS_LIMIT - 5)
        insert_n_minors(conn, "t2", MINORS_LIMIT + 10)

        trimmer.run("s1")

        # t1 should be untouched
        assert count_team_players(conn, "t1", status="minors") == MINORS_LIMIT - 5
        # t2 should be trimmed
        assert count_team_players(conn, "t2", status="minors") == MINORS_LIMIT

    def test_no_teams_in_season(self, conn, trimmer):
        """Should handle a season with no teams gracefully."""
        conn.execute("INSERT INTO seasons (id, year) VALUES ('s1', 2026)")
        conn.execute("INSERT INTO leagues (id, name) VALUES ('lg1', 'Test')")
        conn.commit()
        total = trimmer.run("s1")
        assert total == 0

    def test_commits_changes(self, conn, trimmer):
        """Changes should be committed so a new connection sees them."""
        setup_season(conn, team_ids=["t1"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 10)

        trimmer.run("s1")

        # Verify via a fresh query
        remaining = conn.execute(
            """SELECT COUNT(*) FROM team_players tp
               JOIN player_status ps ON tp.player_id = ps.player_id
               WHERE tp.team_id = 't1' AND ps.status = 'minors'"""
        ).fetchone()[0]
        assert remaining == MINORS_LIMIT

    def test_each_team_trimmed_independently(self, conn, trimmer):
        """One team being over limit shouldn't affect another team's roster."""
        setup_season(conn, team_ids=["t1", "t2"])
        insert_n_minors(conn, "t1", MINORS_LIMIT + 15)
        insert_n_minors(conn, "t2", 50)  # well under limit

        trimmer.run("s1")

        assert count_team_players(conn, "t1", status="minors") == MINORS_LIMIT
        assert count_team_players(conn, "t2", status="minors") == 50
