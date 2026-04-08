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

TEAM_ID = "team-1"
SEASON_ID = "season-1"

OTHER_TEAM_ID = "team-2"
OTHER_SEASON_ID = "season-2"


@pytest.fixture
def conn(db_conn):
    """Seed baseline rows into the shared db_conn fixture."""
    db_conn.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        (TEAM_ID, "Springfield", "Isotopes"),
    )
    db_conn.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        (OTHER_TEAM_ID, "Shelbyville", "Sharks"),
    )
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
        (SEASON_ID, 2024, "Season1"),
    )
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
        (OTHER_SEASON_ID, 2025, "Season2"),
    )
    for pid, first, last, bats, throws in [
        ("p1", "Alice", "Smith", "R", "R"),
        ("p2", "Bob", "Jones", "L", "L"),
        ("p3", "Carol", "White", "R", "R"),
        ("p4", "Dave", "Brown", "R", "R"),
        ("p5", "Eve", "Davis", "L", "L"),
        ("starter-1", "Frank", "Miller", "R", "R"),
    ]:
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (pid, first, last, bats, throws, "rp"),
        )
    db_conn.execute(
        "INSERT INTO team_rotations"
        " (team_id, season_id, player_id, rotation_order, effective_date)"
        " VALUES (?, ?, ?, ?, ?)",
        (TEAM_ID, SEASON_ID, "starter-1", 1, "2024-04-01"),
    )
    db_conn.commit()
    yield db_conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_count(conn, team_id=TEAM_ID, season_id=SEASON_ID, active_only=True):
    """Count bullpen_roles rows, optionally filtering to active only."""
    sql = "SELECT COUNT(*) FROM bullpen_roles WHERE team_id = ? AND season_id = ?"
    params = [team_id, season_id]
    if active_only:
        sql += " AND end_date IS NULL"
    return conn.execute(sql, params).fetchone()[0]


def _seed_roles(conn, assignments, effective_date="2024-04-01"):
    set_roles(conn, TEAM_ID, SEASON_ID, assignments, effective_date=effective_date)


# ---------------------------------------------------------------------------
# set_roles
# ---------------------------------------------------------------------------


class TestSetRoles:

    def test_inserts_roles(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p2", "role": "Setup"},
            ],
        )
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == 2
        player_role_map = {r["player_id"]: r["role"] for r in roles}
        assert player_role_map["p1"] == "Closer"
        assert player_role_map["p2"] == "Setup"

    def test_replaces_existing_active_roles(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p2", "role": "Setup"},
            ],
            effective_date="2024-04-01",
        )

        # Replace with a different set
        _seed_roles(
            conn,
            [
                {"player_id": "p3", "role": "Closer"},
            ],
            effective_date="2024-05-01",
        )

        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == 1
        assert roles[0]["player_id"] == "p3"

    def test_previous_roles_are_closed_not_deleted(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p1", "role": "Closer"},
            ],
            effective_date="2024-04-01",
        )
        _seed_roles(
            conn,
            [
                {"player_id": "p2", "role": "Closer"},
            ],
            effective_date="2024-05-01",
        )

        total = _row_count(conn, active_only=False)
        active = _row_count(conn, active_only=True)
        assert total == 2
        assert active == 1

    def test_raises_on_invalid_role(self, conn):
        with pytest.raises(ValueError, match="Invalid role"):
            set_roles(
                conn,
                TEAM_ID,
                SEASON_ID,
                [
                    {"player_id": "p1", "role": "Ace"},
                ],
            )

    def test_raises_on_duplicate_player_in_list(self, conn):
        with pytest.raises(ValueError, match="appears more than once"):
            set_roles(
                conn,
                TEAM_ID,
                SEASON_ID,
                [
                    {"player_id": "p1", "role": "Closer"},
                    {"player_id": "p1", "role": "Setup"},
                ],
            )

    def test_raises_if_player_in_rotation(self, conn):
        with pytest.raises(ValueError, match="starting rotation"):
            set_roles(
                conn,
                TEAM_ID,
                SEASON_ID,
                [
                    {"player_id": "starter-1", "role": "Middle"},
                ],
            )

    def test_rotation_conflict_does_not_affect_other_team(self, conn):
        # starter-1 is only in TEAM_ID's rotation; OTHER_TEAM_ID should be fine
        set_roles(
            conn,
            OTHER_TEAM_ID,
            SEASON_ID,
            [
                {"player_id": "starter-1", "role": "Closer"},
            ],
            effective_date="2024-04-01",
        )
        roles = get_current_roles(conn, OTHER_TEAM_ID, SEASON_ID)
        assert len(roles) == 1

    def test_rotation_conflict_does_not_affect_other_season(self, conn):
        # starter-1 is only active in SEASON_ID; OTHER_SEASON_ID should be fine
        set_roles(
            conn,
            TEAM_ID,
            OTHER_SEASON_ID,
            [
                {"player_id": "starter-1", "role": "Setup"},
            ],
            effective_date="2025-04-01",
        )
        roles = get_current_roles(conn, TEAM_ID, OTHER_SEASON_ID)
        assert len(roles) == 1

    def test_accepts_all_valid_roles(self, conn):
        players = ["p1", "p2", "p3", "p4", "p5"]
        valid_roles = sorted(VALID_ROLES)
        assignments = [
            {"player_id": pid, "role": role} for pid, role in zip(players, valid_roles)
        ]
        set_roles(conn, TEAM_ID, SEASON_ID, assignments, effective_date="2024-04-01")
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == len(assignments)

    def test_empty_assignments_clears_all_roles(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        set_roles(conn, TEAM_ID, SEASON_ID, [], effective_date="2024-05-01")
        assert _row_count(conn) == 0


# ---------------------------------------------------------------------------
# get_current_roles
# ---------------------------------------------------------------------------


class TestGetCurrentRoles:

    def test_returns_empty_when_no_roles(self, conn):
        assert get_current_roles(conn, TEAM_ID, SEASON_ID) == []

    def test_returns_only_active_roles(self, conn):
        _seed_roles(
            conn, [{"player_id": "p1", "role": "Closer"}], effective_date="2024-04-01"
        )
        _seed_roles(
            conn, [{"player_id": "p2", "role": "Setup"}], effective_date="2024-05-01"
        )
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        player_ids = [r["player_id"] for r in roles]
        assert "p2" in player_ids
        assert "p1" not in player_ids

    def test_returns_correct_fields(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        role = get_current_roles(conn, TEAM_ID, SEASON_ID)[0]
        assert set(role.keys()) == {
            "team_id",
            "player_id",
            "season_id",
            "role",
            "effective_date",
        }

    def test_scoped_to_team(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        assert get_current_roles(conn, OTHER_TEAM_ID, SEASON_ID) == []

    def test_scoped_to_season(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        assert get_current_roles(conn, TEAM_ID, OTHER_SEASON_ID) == []

    def test_ordered_by_role_then_player(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p2", "role": "Closer"},
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p3", "role": "Setup"},
            ],
        )
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert roles[0]["player_id"] == "p1"
        assert roles[1]["player_id"] == "p2"
        assert roles[2]["player_id"] == "p3"


# ---------------------------------------------------------------------------
# get_closer
# ---------------------------------------------------------------------------


class TestGetCloser:

    def test_returns_none_when_no_closer(self, conn):
        assert get_closer(conn, TEAM_ID, SEASON_ID) is None

    def test_returns_none_when_only_other_roles_exist(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Setup"}])
        assert get_closer(conn, TEAM_ID, SEASON_ID) is None

    def test_returns_closer(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p2", "role": "Setup"},
            ],
        )
        closer = get_closer(conn, TEAM_ID, SEASON_ID)
        assert closer is not None
        assert closer["player_id"] == "p1"
        assert closer["role"] == "Closer"

    def test_returns_none_after_closer_replaced(self, conn):
        _seed_roles(
            conn, [{"player_id": "p1", "role": "Closer"}], effective_date="2024-04-01"
        )
        # Replace bullpen — no closer in new set
        _seed_roles(
            conn, [{"player_id": "p2", "role": "Setup"}], effective_date="2024-05-01"
        )
        assert get_closer(conn, TEAM_ID, SEASON_ID) is None

    def test_returns_correct_fields(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        closer = get_closer(conn, TEAM_ID, SEASON_ID)
        assert set(closer.keys()) == {
            "team_id",
            "player_id",
            "season_id",
            "role",
            "effective_date",
        }

    def test_scoped_to_team(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        assert get_closer(conn, OTHER_TEAM_ID, SEASON_ID) is None

    def test_scoped_to_season(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        assert get_closer(conn, TEAM_ID, OTHER_SEASON_ID) is None


# ---------------------------------------------------------------------------
# update_role
# ---------------------------------------------------------------------------


class TestUpdateRole:

    def test_updates_existing_role(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Middle"}])
        update_role(
            conn, TEAM_ID, "p1", SEASON_ID, "Closer", effective_date="2024-05-01"
        )
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == 1
        assert roles[0]["role"] == "Closer"

    def test_preserves_history_on_update(self, conn):
        _seed_roles(
            conn, [{"player_id": "p1", "role": "Middle"}], effective_date="2024-04-01"
        )
        update_role(
            conn, TEAM_ID, "p1", SEASON_ID, "Closer", effective_date="2024-05-01"
        )
        total = _row_count(conn, active_only=False)
        active = _row_count(conn, active_only=True)
        assert total == 2
        assert active == 1

    def test_assigns_role_to_player_with_no_prior_role(self, conn):
        update_role(conn, TEAM_ID, "p1", SEASON_ID, "Long", effective_date="2024-04-01")
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == 1
        assert roles[0]["player_id"] == "p1"
        assert roles[0]["role"] == "Long"

    def test_no_op_when_role_unchanged(self, conn):
        _seed_roles(
            conn, [{"player_id": "p1", "role": "Closer"}], effective_date="2024-04-01"
        )
        update_role(
            conn, TEAM_ID, "p1", SEASON_ID, "Closer", effective_date="2024-05-01"
        )
        # Should still be only one row total (no new history entry)
        total = _row_count(conn, active_only=False)
        assert total == 1

    def test_raises_on_invalid_role(self, conn):
        with pytest.raises(ValueError, match="Invalid role"):
            update_role(conn, TEAM_ID, "p1", SEASON_ID, "Ace")

    def test_raises_if_player_in_rotation(self, conn):
        with pytest.raises(ValueError, match="starting rotation"):
            update_role(conn, TEAM_ID, "starter-1", SEASON_ID, "Middle")

    def test_does_not_leave_two_active_rows(self, conn):
        _seed_roles(
            conn, [{"player_id": "p1", "role": "Middle"}], effective_date="2024-04-01"
        )
        update_role(
            conn, TEAM_ID, "p1", SEASON_ID, "Setup", effective_date="2024-05-01"
        )
        active = _row_count(conn, active_only=True)
        assert active == 1


# ---------------------------------------------------------------------------
# remove_role
# ---------------------------------------------------------------------------


class TestRemoveRole:

    def test_removes_active_role(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        result = remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01")
        assert result is True
        assert _row_count(conn) == 0

    def test_returns_false_when_no_active_role(self, conn):
        result = remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01")
        assert result is False

    def test_row_is_closed_not_deleted(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01")
        total = _row_count(conn, active_only=False)
        active = _row_count(conn, active_only=True)
        assert total == 1
        assert active == 0

    def test_only_removes_target_player(self, conn):
        _seed_roles(
            conn,
            [
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p2", "role": "Setup"},
            ],
        )
        remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01")
        roles = get_current_roles(conn, TEAM_ID, SEASON_ID)
        assert len(roles) == 1
        assert roles[0]["player_id"] == "p2"

    def test_scoped_to_team(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        # Remove for a different team — should return False, leave original intact
        result = remove_role(
            conn, OTHER_TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01"
        )
        assert result is False
        assert _row_count(conn) == 1

    def test_scoped_to_season(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        result = remove_role(
            conn, TEAM_ID, "p1", OTHER_SEASON_ID, end_date="2024-06-01"
        )
        assert result is False
        assert _row_count(conn) == 1

    def test_idempotent_second_remove(self, conn):
        _seed_roles(conn, [{"player_id": "p1", "role": "Closer"}])
        remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-01")
        result = remove_role(conn, TEAM_ID, "p1", SEASON_ID, end_date="2024-06-02")
        assert result is False
