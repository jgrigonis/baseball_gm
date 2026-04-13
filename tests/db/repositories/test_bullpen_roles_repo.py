# tests/db/repositories/test_bullpen_roles_repo.py

import pytest

from src.db.repositories.bullpen_roles_repo import (
    set_roles,
    get_current_roles,
    get_closer,
    update_role,
    remove_role,
)
from src.player.player_constants import VALID_ROLES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx(db_conn, factory):
    """
    Seed two teams, two seasons, 6 players, and one starter in the rotation.
    Returns a namespace so tests can reference everything by name.
    """
    from types import SimpleNamespace

    team        = factory.team(city="Springfield", mascot="Isotopes")
    other_team  = factory.team(city="Shelbyville", mascot="Sharks")
    season      = factory.season(year=2024)
    other_season = factory.season(year=2025)

    player_data = [
        ("Alice", "Smith",  "R", "R"),
        ("Bob",   "Jones",  "L", "L"),
        ("Carol", "White",  "R", "R"),
        ("Dave",  "Brown",  "R", "R"),
        ("Eve",   "Davis",  "L", "L"),
        ("Frank", "Miller", "R", "R"),  # index 5 — used as starter
    ]
    players = []
    for i, (first, last, bats, throws) in enumerate(player_data):
        pid = f"{team.id[:8]}-p{i+1}"
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (pid, first, last, bats, throws, "rp"),
        )
        players.append(pid)

    starter_id = players[5]
    db_conn.execute(
        "INSERT INTO team_rotations"
        " (team_id, season_id, player_id, rotation_order, effective_date)"
        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (team.id, season.id, starter_id, 1, "2024-04-01"),
    )

    return SimpleNamespace(
        conn=db_conn,
        team=team,
        other_team=other_team,
        season=season,
        other_season=other_season,
        p=players,          # p[0]..p[4] are relievers, p[5] is the starter
        starter=starter_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_count(conn, team_id, season_id, active_only=True):
    sql = "SELECT COUNT(*) AS n FROM bullpen_roles WHERE team_id = %s AND season_id = %s"
    params = [team_id, season_id]
    if active_only:
        sql += " AND end_date IS NULL"
    return conn.execute(sql, params).fetchone()["n"]


def _seed_roles(ctx, assignments, effective_date="2024-04-01"):
    set_roles(ctx.conn, ctx.team.id, ctx.season.id, assignments, effective_date=effective_date)


# ---------------------------------------------------------------------------
# set_roles
# ---------------------------------------------------------------------------


class TestSetRoles:

    def test_inserts_roles(self, ctx):
        _seed_roles(ctx, [
            {"player_id": ctx.p[0], "role": "Closer"},
            {"player_id": ctx.p[1], "role": "Setup"},
        ])
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == 2
        player_role_map = {r["player_id"]: r["role"] for r in roles}
        assert player_role_map[ctx.p[0]] == "Closer"
        assert player_role_map[ctx.p[1]] == "Setup"

    def test_replaces_existing_active_roles(self, ctx):
        _seed_roles(ctx, [
            {"player_id": ctx.p[0], "role": "Closer"},
            {"player_id": ctx.p[1], "role": "Setup"},
        ], effective_date="2024-04-01")

        _seed_roles(ctx, [
            {"player_id": ctx.p[2], "role": "Closer"},
        ], effective_date="2024-05-01")

        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == 1
        assert roles[0]["player_id"] == ctx.p[2]

    def test_previous_roles_are_closed_not_deleted(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}], effective_date="2024-04-01")
        _seed_roles(ctx, [{"player_id": ctx.p[1], "role": "Closer"}], effective_date="2024-05-01")

        total  = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=False)
        active = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=True)
        assert total == 2
        assert active == 1

    def test_raises_on_invalid_role(self, ctx):
        with pytest.raises(ValueError, match="Invalid role"):
            set_roles(ctx.conn, ctx.team.id, ctx.season.id, [
                {"player_id": ctx.p[0], "role": "Ace"},
            ])

    def test_raises_on_duplicate_player_in_list(self, ctx):
        with pytest.raises(ValueError, match="appears more than once"):
            set_roles(ctx.conn, ctx.team.id, ctx.season.id, [
                {"player_id": ctx.p[0], "role": "Closer"},
                {"player_id": ctx.p[0], "role": "Setup"},
            ])

    def test_raises_if_player_in_rotation(self, ctx):
        with pytest.raises(ValueError, match="starting rotation"):
            set_roles(ctx.conn, ctx.team.id, ctx.season.id, [
                {"player_id": ctx.starter, "role": "Middle"},
            ])

    def test_rotation_conflict_does_not_affect_other_team(self, ctx):
        set_roles(ctx.conn, ctx.other_team.id, ctx.season.id, [
            {"player_id": ctx.starter, "role": "Closer"},
        ], effective_date="2024-04-01")
        roles = get_current_roles(ctx.conn, ctx.other_team.id, ctx.season.id)
        assert len(roles) == 1

    def test_rotation_conflict_does_not_affect_other_season(self, ctx):
        set_roles(ctx.conn, ctx.team.id, ctx.other_season.id, [
            {"player_id": ctx.starter, "role": "Setup"},
        ], effective_date="2025-04-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.other_season.id)
        assert len(roles) == 1

    def test_accepts_all_valid_roles(self, ctx):
        valid_roles = sorted(VALID_ROLES)
        assignments = [
            {"player_id": pid, "role": role}
            for pid, role in zip(ctx.p[:5], valid_roles)
        ]
        set_roles(ctx.conn, ctx.team.id, ctx.season.id, assignments, effective_date="2024-04-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == len(assignments)

    def test_empty_assignments_clears_all_roles(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        set_roles(ctx.conn, ctx.team.id, ctx.season.id, [], effective_date="2024-05-01")
        assert _row_count(ctx.conn, ctx.team.id, ctx.season.id) == 0


# ---------------------------------------------------------------------------
# get_current_roles
# ---------------------------------------------------------------------------


class TestGetCurrentRoles:

    def test_returns_empty_when_no_roles(self, ctx):
        assert get_current_roles(ctx.conn, ctx.team.id, ctx.season.id) == []

    def test_returns_only_active_roles(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}], effective_date="2024-04-01")
        _seed_roles(ctx, [{"player_id": ctx.p[1], "role": "Setup"}],  effective_date="2024-05-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        player_ids = [r["player_id"] for r in roles]
        assert ctx.p[1] in player_ids
        assert ctx.p[0] not in player_ids

    def test_returns_correct_fields(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        role = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)[0]
        assert set(role.keys()) == {"team_id", "player_id", "season_id", "role", "effective_date"}

    def test_scoped_to_team(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        assert get_current_roles(ctx.conn, ctx.other_team.id, ctx.season.id) == []

    def test_scoped_to_season(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        assert get_current_roles(ctx.conn, ctx.team.id, ctx.other_season.id) == []

    def test_ordered_by_role_then_player(self, ctx):
        _seed_roles(ctx, [
            {"player_id": ctx.p[1], "role": "Closer"},
            {"player_id": ctx.p[0], "role": "Closer"},
            {"player_id": ctx.p[2], "role": "Setup"},
        ])
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert roles[0]["player_id"] == ctx.p[0]
        assert roles[1]["player_id"] == ctx.p[1]
        assert roles[2]["player_id"] == ctx.p[2]


# ---------------------------------------------------------------------------
# get_closer
# ---------------------------------------------------------------------------


class TestGetCloser:

    def test_returns_none_when_no_closer(self, ctx):
        assert get_closer(ctx.conn, ctx.team.id, ctx.season.id) is None

    def test_returns_none_when_only_other_roles_exist(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Setup"}])
        assert get_closer(ctx.conn, ctx.team.id, ctx.season.id) is None

    def test_returns_closer(self, ctx):
        _seed_roles(ctx, [
            {"player_id": ctx.p[0], "role": "Closer"},
            {"player_id": ctx.p[1], "role": "Setup"},
        ])
        closer = get_closer(ctx.conn, ctx.team.id, ctx.season.id)
        assert closer is not None
        assert closer["player_id"] == ctx.p[0]
        assert closer["role"] == "Closer"

    def test_returns_none_after_closer_replaced(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}], effective_date="2024-04-01")
        _seed_roles(ctx, [{"player_id": ctx.p[1], "role": "Setup"}],  effective_date="2024-05-01")
        assert get_closer(ctx.conn, ctx.team.id, ctx.season.id) is None

    def test_returns_correct_fields(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        closer = get_closer(ctx.conn, ctx.team.id, ctx.season.id)
        assert set(closer.keys()) == {"team_id", "player_id", "season_id", "role", "effective_date"}

    def test_scoped_to_team(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        assert get_closer(ctx.conn, ctx.other_team.id, ctx.season.id) is None

    def test_scoped_to_season(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        assert get_closer(ctx.conn, ctx.team.id, ctx.other_season.id) is None


# ---------------------------------------------------------------------------
# update_role
# ---------------------------------------------------------------------------


class TestUpdateRole:

    def test_updates_existing_role(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Middle"}])
        update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Closer", effective_date="2024-05-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == 1
        assert roles[0]["role"] == "Closer"

    def test_preserves_history_on_update(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Middle"}], effective_date="2024-04-01")
        update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Closer", effective_date="2024-05-01")
        total  = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=False)
        active = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=True)
        assert total == 2
        assert active == 1

    def test_assigns_role_to_player_with_no_prior_role(self, ctx):
        update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Long", effective_date="2024-04-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == 1
        assert roles[0]["player_id"] == ctx.p[0]
        assert roles[0]["role"] == "Long"

    def test_no_op_when_role_unchanged(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}], effective_date="2024-04-01")
        update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Closer", effective_date="2024-05-01")
        total = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=False)
        assert total == 1

    def test_raises_on_invalid_role(self, ctx):
        with pytest.raises(ValueError, match="Invalid role"):
            update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Ace")

    def test_raises_if_player_in_rotation(self, ctx):
        with pytest.raises(ValueError, match="starting rotation"):
            update_role(ctx.conn, ctx.team.id, ctx.starter, ctx.season.id, "Middle")

    def test_does_not_leave_two_active_rows(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Middle"}], effective_date="2024-04-01")
        update_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, "Setup", effective_date="2024-05-01")
        assert _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=True) == 1


# ---------------------------------------------------------------------------
# remove_role
# ---------------------------------------------------------------------------


class TestRemoveRole:

    def test_removes_active_role(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        result = remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        assert result is True
        assert _row_count(ctx.conn, ctx.team.id, ctx.season.id) == 0

    def test_returns_false_when_no_active_role(self, ctx):
        result = remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        assert result is False

    def test_row_is_closed_not_deleted(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        total  = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=False)
        active = _row_count(ctx.conn, ctx.team.id, ctx.season.id, active_only=True)
        assert total == 1
        assert active == 0

    def test_only_removes_target_player(self, ctx):
        _seed_roles(ctx, [
            {"player_id": ctx.p[0], "role": "Closer"},
            {"player_id": ctx.p[1], "role": "Setup"},
        ])
        remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        roles = get_current_roles(ctx.conn, ctx.team.id, ctx.season.id)
        assert len(roles) == 1
        assert roles[0]["player_id"] == ctx.p[1]

    def test_scoped_to_team(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        result = remove_role(ctx.conn, ctx.other_team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        assert result is False
        assert _row_count(ctx.conn, ctx.team.id, ctx.season.id) == 1

    def test_scoped_to_season(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        result = remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.other_season.id, end_date="2024-06-01")
        assert result is False
        assert _row_count(ctx.conn, ctx.team.id, ctx.season.id) == 1

    def test_idempotent_second_remove(self, ctx):
        _seed_roles(ctx, [{"player_id": ctx.p[0], "role": "Closer"}])
        remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-01")
        result = remove_role(ctx.conn, ctx.team.id, ctx.p[0], ctx.season.id, end_date="2024-06-02")
        assert result is False
