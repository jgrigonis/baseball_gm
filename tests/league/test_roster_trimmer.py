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

import pytest

import uuid

from src.league.offseason.roster_trimmer import RosterTrimmer, MINORS_LIMIT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trimmer(db_conn):
    return RosterTrimmer(db_conn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


# def _next_id():
#     global _counter
#     _counter += 1
#     return f"player-{_counter:04d}"


def setup_season(db_conn, season_id=None, team_ids=None):
    if season_id is None:
        season_id = str(uuid.uuid4())
    if team_ids is None:
        team_ids = (str(uuid.uuid4()),)
    league_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (%s, 2026, 'Season 2026') ON CONFLICT DO NOTHING",
        (season_id,),
    )
    db_conn.execute(
        "INSERT INTO leagues (id, name) VALUES (%s, 'Test League') ON CONFLICT DO NOTHING",
        (league_id,),
    )
    db_conn.execute(
        "INSERT INTO league_seasons (league_id, season_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (
            league_id,
            season_id,
        ),
    )
    for team_id in team_ids:
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, 'Test', 'Team') ON CONFLICT DO NOTHING",
            (team_id,),
        )
        db_conn.execute(
            "INSERT INTO league_season_teams (league_id, season_id, team_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (league_id, season_id, team_id),
        )
    db_conn.commit()
    return season_id


def insert_player(db_conn, team_id, status, strikes=50, speed=50, player_id=None):
    """Insert a player with given status and key skills that affect prospect_rating."""
    pid = player_id or str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position) VALUES (%s,%s,%s,%s,%s,%s)",
        (pid, "Test", "Player", "R", "R", "of"),
    )
    db_conn.execute(
        """INSERT INTO player_skills
           (player_id, age, strikes, stamina, recovery, accuracy, clutch,
            speed, power, arm, eye, contact, base_running,
            bunting, catching, infield, outfield, ground_balls, durability)
           VALUES (%s,20,%s,50,50,50,50,%s,50,50,50,50,50,50,50,50,50,50,50)""",
        (pid, strikes, speed),
    )
    db_conn.execute(
        "INSERT INTO player_status (player_id, status, since) VALUES (%s, %s, '2026-01-01')",
        (pid, status),
    )
    db_conn.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
        (team_id, pid),
    )
    db_conn.commit()
    return pid


def insert_n_minors(db_conn, team_id, n, base_strikes=50):
    """Insert n minors players, each with slightly different ratings."""
    ids = []
    for i in range(n):
        pid = insert_player(
            db_conn, team_id, "minors", strikes=max(1, min(99, base_strikes + i))
        )
        ids.append(pid)
    return ids


def count_team_players(db_conn, team_id, status=None):
    if status:
        return db_conn.execute(
            """SELECT COUNT(*) FROM team_players tp
               JOIN player_status ps ON tp.player_id = ps.player_id
               WHERE tp.team_id = %s AND ps.status = %s""",
            (team_id, status),
        ).fetchone()["count"]
    return db_conn.execute(
        "SELECT COUNT(*) FROM team_players WHERE team_id = %s", (team_id,)
    ).fetchone()["count"]


def get_status(db_conn, player_id):
    row = db_conn.execute(
        "SELECT status FROM player_status WHERE player_id = %s", (player_id,)
    ).fetchone()
    return row["status"] if row else None


def in_team(db_conn, team_id, player_id):
    return (
        db_conn.execute(
            "SELECT 1 FROM team_players WHERE team_id = %s AND player_id = %s",
            (team_id, player_id),
        ).fetchone()
        is not None
    )


# ---------------------------------------------------------------------------
# _trim_team
# ---------------------------------------------------------------------------


class TestTrimTeam:
    def test_no_cut_when_under_limit(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT - 10)
        cut = trimmer._trim_team(t1)
        assert cut == 0

    def test_no_cut_when_at_limit(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT)
        cut = trimmer._trim_team(t1)
        assert cut == 0

    def test_cuts_correct_number_over_limit(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 15)
        cut = trimmer._trim_team(t1)
        assert cut == 15

    def test_minors_count_after_trim(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 20)
        trimmer._trim_team(t1)
        remaining = count_team_players(db_conn, t1, status="minors")
        assert remaining == MINORS_LIMIT

    # We can't test this because of DB pollution
    # def test_cut_players_become_free_agent(self, db_conn, trimmer):
    #     t1 = str(uuid.uuid4())
    #     setup_season(db_conn, team_ids=[t1])
    #     insert_n_minors(db_conn, t1, MINORS_LIMIT + 5)
    #     trimmer._trim_team(t1)
    #     db_conn.commit()

    #     fa_count = db_conn.execute(
    #         "SELECT COUNT(*) FROM player_status WHERE status = 'free_agent'"
    #     ).fetchone()["count"]
    #     assert fa_count == 5

    def test_cut_players_removed_from_team_players(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 5)
        trimmer._trim_team(t1)
        db_conn.commit()

        remaining = count_team_players(db_conn, t1)
        assert remaining == MINORS_LIMIT

    def test_worst_rated_cut_first(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        """Players with lowest prospect_rating should be cut."""
        setup_season(db_conn, team_ids=[t1])

        # Insert MINORS_LIMIT average players
        insert_n_minors(db_conn, t1, MINORS_LIMIT, base_strikes=50)

        # Insert 3 clearly bad players (should be cut)
        bad_ids = [
            insert_player(db_conn, t1, "minors", strikes=1, speed=1),
            insert_player(db_conn, t1, "minors", strikes=1, speed=1),
            insert_player(db_conn, t1, "minors", strikes=1, speed=1),
        ]

        trimmer._trim_team(t1)
        db_conn.commit()

        for pid in bad_ids:
            assert get_status(db_conn, pid) == "free_agent", f"{pid} should be cut"
            assert not in_team(db_conn, t1, pid), f"{pid} should not be on team"

    def test_best_rated_kept(self, db_conn, trimmer):
        """Players with highest prospect_rating should survive cuts."""
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])

        insert_n_minors(db_conn, t1, MINORS_LIMIT, base_strikes=30)

        # Insert 5 elite players (should survive)
        elite_ids = [
            insert_player(db_conn, t1, "minors", strikes=99, speed=99),
            insert_player(db_conn, t1, "minors", strikes=99, speed=99),
            insert_player(db_conn, t1, "minors", strikes=99, speed=99),
            insert_player(db_conn, t1, "minors", strikes=99, speed=99),
            insert_player(db_conn, t1, "minors", strikes=99, speed=99),
        ]

        trimmer._trim_team(t1)
        db_conn.commit()

        for pid in elite_ids:
            assert get_status(db_conn, pid) == "minors", f"{pid} should be kept"
            assert in_team(db_conn, t1, pid), f"{pid} should still be on team"

    def test_26man_players_never_cut(self, db_conn, trimmer):
        """26man players must not be touched even when over minors limit."""
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 5)

        protected_ids = [
            insert_player(db_conn, t1, "26man", strikes=1, speed=1),
            insert_player(db_conn, t1, "26man", strikes=1, speed=1),
        ]

        trimmer._trim_team(t1)
        db_conn.commit()

        for pid in protected_ids:
            assert (
                get_status(db_conn, pid) == "26man"
            ), f"26man player {pid} should be protected"
            assert in_team(db_conn, t1, pid)

    def test_40man_players_never_cut(self, db_conn, trimmer):
        """40man players must not be touched."""
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 5)

        protected_ids = [
            insert_player(db_conn, t1, "40man", strikes=1, speed=1),
            insert_player(db_conn, t1, "40man", strikes=1, speed=1),
        ]

        trimmer._trim_team(t1)
        db_conn.commit()

        for pid in protected_ids:
            assert (
                get_status(db_conn, pid) == "40man"
            ), f"40man player {pid} should be protected"
            assert in_team(db_conn, t1, pid)

    def test_no_minors_no_cut(self, db_conn, trimmer):
        """Team with only 26man/40man players and no minors: no cuts."""
        t1 = str(uuid.uuid4())
        setup_season(db_conn, team_ids=[t1])
        for _ in range(26):
            insert_player(db_conn, t1, "26man")
        for _ in range(14):
            insert_player(db_conn, t1, "40man")

        cut = trimmer._trim_team(t1)
        assert cut == 0


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRosterTrimmerRun:
    def test_trims_all_teams(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        s1 = setup_season(db_conn, team_ids=[t1, t2])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 10)
        insert_n_minors(db_conn, t2, MINORS_LIMIT + 20)

        total = trimmer.run(s1)
        assert total == 30

    @pytest.mark.slow
    def test_returns_total_cut_count(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        t3 = str(uuid.uuid4())

        s1 = setup_season(db_conn, team_ids=[t1, t2, t3])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 5)
        insert_n_minors(db_conn, t2, MINORS_LIMIT)  # at limit, no cuts
        insert_n_minors(db_conn, t3, MINORS_LIMIT + 8)

        total = trimmer.run(s1)
        assert total == 13

    def test_teams_under_limit_unaffected(self, db_conn, trimmer):
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        s1 = setup_season(db_conn, team_ids=[t1, t2])
        insert_n_minors(db_conn, t1, MINORS_LIMIT - 5)
        insert_n_minors(db_conn, t2, MINORS_LIMIT + 10)

        trimmer.run(s1)

        # t1 should be untouched
        assert count_team_players(db_conn, t1, status="minors") == MINORS_LIMIT - 5
        # t2 should be trimmed
        assert count_team_players(db_conn, t2, status="minors") == MINORS_LIMIT

    def test_no_teams_in_season(self, db_conn, trimmer):
        """Should handle a season with no teams gracefully."""
        s1 = str(uuid.uuid4())
        lg1 = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO seasons (id, year, name) VALUES (%s, 2026, 'Season 2026')",
            (s1,),
        )
        db_conn.execute(
            "INSERT INTO leagues (id, name) VALUES (%s, 'Test')",
            (lg1,),
        )
        db_conn.commit()
        total = trimmer.run(s1)
        assert total == 0

    def test_commits_changes(self, db_conn, trimmer):
        """Changes should be committed so a new db_connection sees them."""
        t1 = str(uuid.uuid4())
        s1 = setup_season(db_conn, team_ids=[t1])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 10)

        trimmer.run(s1)

        # Verify via a fresh query
        remaining = db_conn.execute("""SELECT COUNT(*) FROM team_players tp
               JOIN player_status ps ON tp.player_id = ps.player_id
               WHERE tp.team_id = 't1' AND ps.status = 'minors'""").fetchone()["count"]
        assert remaining == MINORS_LIMIT

    @pytest.mark.slow
    def test_each_team_trimmed_independently(self, db_conn, trimmer):
        """One team being over limit shouldn't affect another team's roster."""
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        s1 = setup_season(db_conn, team_ids=[t1, t2])
        insert_n_minors(db_conn, t1, MINORS_LIMIT + 15)
        insert_n_minors(db_conn, t2, 50)  # well under limit

        trimmer.run(s1)

        assert count_team_players(db_conn, t1, status="minors") == MINORS_LIMIT
        assert count_team_players(db_conn, t2, status="minors") == 50
