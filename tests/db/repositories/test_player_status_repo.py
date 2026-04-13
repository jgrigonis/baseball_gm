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

from datetime import date

import pytest

from src.db.repositories.player_status_repo import PlayerStatusRepository

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(db_conn):
    return PlayerStatusRepository(db_conn)


def seed_players(db_conn, *player_ids):
    """Insert minimal player rows, ignoring conflicts from prior runs."""
    for pid in player_ids:
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws)"
            " VALUES (%s, 'joe', 'blow', 'L', 'L') ON CONFLICT DO NOTHING",
            (pid,),
        )


def seed_team(db_conn, team_id, *player_ids):
    """Insert a team and associate players, ignoring conflicts."""
    db_conn.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (%s, 'City', 'Guys')"
        " ON CONFLICT DO NOTHING",
        (team_id,),
    )
    for pid in player_ids:
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, pid),
        )


@pytest.fixture
def ctx(db_conn, factory):
    """Unique players and teams per test — no cross-run collisions."""
    from types import SimpleNamespace

    p = [factory.player_row() for _ in range(6)]
    t1 = factory.team()
    t2 = factory.team()
    return SimpleNamespace(conn=db_conn, p=p, t1=t1, t2=t2)


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------


class TestSetStatus:
    def test_insert_new_player(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "26man")
        assert repo.get_status(ctx.p[0].id) == "26man"

    def test_upsert_updates_status(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[0].id, "minors")
        assert repo.get_status(ctx.p[0].id) == "minors"

    def test_upsert_updates_since(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "26man", since=date(2025, 1, 1))
        repo.set_status(ctx.p[0].id, "40man", since=date(2026, 4, 1))

        row = ctx.conn.execute(
            "SELECT since FROM player_status WHERE player_id = %s", (ctx.p[0].id,)
        ).fetchone()
        assert row["since"] == "2026-04-01"

    def test_since_defaults_to_today(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "prospect")

        row = ctx.conn.execute(
            "SELECT since FROM player_status WHERE player_id = %s", (ctx.p[0].id,)
        ).fetchone()
        assert row["since"] == date.today().isoformat()

    def test_explicit_since_date(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "minors", since=date(2025, 3, 15))

        row = ctx.conn.execute(
            "SELECT since FROM player_status WHERE player_id = %s", (ctx.p[0].id,)
        ).fetchone()
        assert row["since"] == "2025-03-15"

    def test_all_valid_statuses(self, ctx, repo):
        valid = ["unassigned", "26man", "40man", "minors", "free_agent", "prospect"]
        for i, status in enumerate(valid):
            repo.set_status(ctx.p[i].id, status)
            assert repo.get_status(ctx.p[i].id) == status


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_status_for_known_player(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "40man")
        assert repo.get_status(ctx.p[0].id) == "40man"

    def test_returns_none_for_unknown_player(self, repo):
        assert repo.get_status("nonexistent") is None

    def test_returns_latest_status_after_update(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "unassigned")
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[0].id, "minors")
        assert repo.get_status(ctx.p[0].id) == "minors"


# ---------------------------------------------------------------------------
# get_by_status
# ---------------------------------------------------------------------------


class TestGetByStatus:
    def test_returns_players_with_matching_status(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[1].id, "26man")
        repo.set_status(ctx.p[2].id, "minors")

        result = set(repo.get_by_status("26man"))
        assert {ctx.p[0].id, ctx.p[1].id}.issubset(result)
        assert ctx.p[2].id not in result

    def test_returns_empty_list_when_none_match(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "minors")
        # "prospect" not set for any of our players
        result = repo.get_by_status("prospect")
        assert ctx.p[0].id not in result

    def test_returns_all_matching_statuses(self, ctx, repo):
        for p in ctx.p[:4]:
            repo.set_status(p.id, "minors")

        result = set(repo.get_by_status("minors"))
        assert {p.id for p in ctx.p[:4]}.issubset(result)

    def test_does_not_return_other_statuses(self, ctx, repo):
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[1].id, "40man")

        result = repo.get_by_status("minors")
        assert ctx.p[0].id not in result
        assert ctx.p[1].id not in result


# ---------------------------------------------------------------------------
# get_by_team_and_status
# ---------------------------------------------------------------------------


class TestGetByTeamAndStatus:
    def test_returns_players_on_team_with_status(self, ctx, repo):
        for p in ctx.p[:3]:
            ctx.conn.execute(
                "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
                " ON CONFLICT DO NOTHING",
                (ctx.t1.id, p.id),
            )
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[1].id, "26man")
        repo.set_status(ctx.p[2].id, "minors")

        result = set(repo.get_by_team_and_status(ctx.t1.id, "26man"))
        assert result == {ctx.p[0].id, ctx.p[1].id}

    def test_does_not_return_players_from_other_teams(self, ctx, repo):
        ctx.conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (ctx.t1.id, ctx.p[0].id),
        )
        ctx.conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (ctx.t2.id, ctx.p[1].id),
        )
        repo.set_status(ctx.p[0].id, "26man")
        repo.set_status(ctx.p[1].id, "26man")

        result = repo.get_by_team_and_status(ctx.t1.id, "26man")
        assert result == [ctx.p[0].id]

    def test_returns_empty_when_no_match(self, ctx, repo):
        ctx.conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (ctx.t1.id, ctx.p[0].id),
        )
        repo.set_status(ctx.p[0].id, "minors")

        result = repo.get_by_team_and_status(ctx.t1.id, "26man")
        assert result == []

    def test_returns_empty_for_unknown_team(self, repo):
        result = repo.get_by_team_and_status("ghost_team", "26man")
        assert result == []


# ---------------------------------------------------------------------------
# bulk_set
# ---------------------------------------------------------------------------


class TestBulkSet:
    def test_inserts_all_assignments(self, ctx, repo):
        repo.bulk_set(
            {
                ctx.p[0].id: "26man",
                ctx.p[1].id: "40man",
                ctx.p[2].id: "minors",
            }
        )
        assert repo.get_status(ctx.p[0].id) == "26man"
        assert repo.get_status(ctx.p[1].id) == "40man"
        assert repo.get_status(ctx.p[2].id) == "minors"

    def test_upserts_existing_players(self, ctx, repo):
        repo.bulk_set({ctx.p[0].id: "unassigned", ctx.p[1].id: "unassigned"})
        repo.bulk_set({ctx.p[0].id: "26man", ctx.p[1].id: "minors"})
        assert repo.get_status(ctx.p[0].id) == "26man"
        assert repo.get_status(ctx.p[1].id) == "minors"

    def test_since_applied_to_all(self, ctx, repo):
        repo.bulk_set(
            {ctx.p[0].id: "26man", ctx.p[1].id: "40man"}, since=date(2025, 6, 1)
        )
        for p in ctx.p[:2]:
            row = ctx.conn.execute(
                "SELECT since FROM player_status WHERE player_id = %s", (p.id,)
            ).fetchone()
            assert row["since"] == "2025-06-01"

    def test_empty_dict_does_nothing(self, ctx, repo):
        before = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_status WHERE player_id = ANY(%s)",
            ([p.id for p in ctx.p],),
        ).fetchone()["n"]
        repo.bulk_set({})
        after = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_status WHERE player_id = ANY(%s)",
            ([p.id for p in ctx.p],),
        ).fetchone()["n"]
        assert before == after == 0

    def test_large_bulk_set(self, db_conn, repo, factory):
        players = [factory.player_row() for _ in range(160)]
        assignments = {}
        for i, p in enumerate(players):
            if i < 26:
                assignments[p.id] = "26man"
            elif i < 40:
                assignments[p.id] = "40man"
            else:
                assignments[p.id] = "minors"

        repo.bulk_set(assignments)

        all_ids = [p.id for p in players]
        assert (
            len([pid for pid in repo.get_by_status("26man") if pid in set(all_ids)])
            == 26
        )
        assert (
            len([pid for pid in repo.get_by_status("40man") if pid in set(all_ids)])
            == 14
        )
        assert (
            len([pid for pid in repo.get_by_status("minors") if pid in set(all_ids)])
            == 120
        )
