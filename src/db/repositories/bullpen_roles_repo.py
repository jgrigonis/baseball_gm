# src/db/repositories/bullpen_roles_repo.py
"""
This script can:

Set bullpen roles for a team in a given season
Return current bullpen roles for a team
Get the current closer
Update a pitcher's bullpen role
Remove a pitcher from the bullpen

Enforces:
- A pitcher cannot hold more than one simultaneously active bullpen role (two open-ended rows) per team/season
- A pitcher currently in the starting rotation cannot be assigned a bullpen role
"""

from datetime import date
from typing import Optional

from src.player.player_constants import VALID_ROLES

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today() -> str:
    return date.today().isoformat()


def _validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise ValueError(
            f"Invalid role '{role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}"
        )


def _get_active_rotation_player_ids(conn, team_id: str, season_id: str) -> set[str]:
    """Return the set of player_ids currently in the starting rotation."""
    cursor = conn.execute(
        """
        SELECT player_id
        FROM team_rotations
        WHERE team_id = %s
          AND season_id = %s
          AND end_date IS NULL
        """,
        (team_id, season_id),
    )
    return {row["player_id"] for row in cursor.fetchall()}


# Unused
def _get_active_bullpen_player_ids(conn, team_id: str, season_id: str) -> set[str]:
    """Return the set of player_ids with an active bullpen role."""
    cursor = conn.execute(
        """
        SELECT player_id
        FROM bullpen_roles
        WHERE team_id = %s
          AND season_id = %s
          AND end_date IS NULL
        """,
        (team_id, season_id),
    )
    return {row["player_id"] for row in cursor.fetchall()}


def _close_active_role(
    conn, team_id: str, player_id: str, season_id: str, end_date: str
) -> None:
    """Set end_date on any active bullpen role for this player."""
    conn.execute(
        """
        UPDATE bullpen_roles
        SET end_date = %s
        WHERE team_id = %s
          AND player_id = %s
          AND season_id = %s
          AND end_date IS NULL
        """,
        (end_date, team_id, player_id, season_id),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class BullpenRepository:
    def __init__(self, conn):
        self.conn = conn

    def set_roles(
        self,
        team_id: str,
        season_id: str,
        assignments: list[dict],
        effective_date: Optional[str] = None,
    ) -> None:
        """
        Bulk-assign bullpen roles for a team, replacing all current active roles.

        `assignments` is a list of dicts with keys:
            player_id (str)
            role      (str)  -- one of VALID_ROLES

        Example:
            set_roles("team-1", "season-1", [
                {"player_id": "p1", "role": "Closer"},
                {"player_id": "p2", "role": "Setup"},
            ])

        Raises ValueError if:
            - Any role value is invalid
            - Any player is in the starting rotation
            - Any player_id appears more than once in the assignments list
        """
        if effective_date is None:
            effective_date = _today()

        # Validate roles and check for duplicates within the provided list
        seen_player_ids: set[str] = set()
        for entry in assignments:
            _validate_role(entry["role"])
            if entry["player_id"] in seen_player_ids:
                raise ValueError(
                    f"Player '{entry['player_id']}' appears more than once in the assignment list."
                )
            seen_player_ids.add(entry["player_id"])

        # Check no one is in the starting rotation
        rotation_ids = _get_active_rotation_player_ids(self.conn, team_id, season_id)
        conflicts = seen_player_ids & rotation_ids
        if conflicts:
            raise ValueError(
                f"The following players are in the starting rotation and cannot be assigned bullpen roles: "
                f"{', '.join(sorted(conflicts))}"
            )

        with self.conn.cursor() as cur:
            # Close all current active roles for this team/season
            cur.execute(
                """
                UPDATE bullpen_roles
                SET end_date = %s
                WHERE team_id = %s
                AND season_id = %s
                AND end_date IS NULL
                """,
                (effective_date, team_id, season_id),
            )

            # Insert new roles
            cur.executemany(
                # """
                # INSERT INTO bullpen_roles (team_id, player_id, season_id, role, effective_date, end_date)
                # VALUES (%s, %s, %s, %s, %s, NULL)
                # """,
                """
                INSERT INTO bullpen_roles (team_id, player_id, season_id, role, effective_date, end_date)
                VALUES (%s, %s, %s, %s, %s, NULL)
                ON CONFLICT (team_id, player_id, season_id, effective_date) 
                DO UPDATE SET 
                    role = EXCLUDED.role,
                    end_date = NULL
                """,
                [
                    (
                        team_id,
                        entry["player_id"],
                        season_id,
                        entry["role"],
                        effective_date,
                    )
                    for entry in assignments
                ],
            )

    def get_current_roles(self, team_id: str, season_id: str) -> list[dict]:
        """
        Return all active bullpen role assignments for a team in a given season,
        ordered by role then player_id.

        Returns a list of dicts:
            team_id, player_id, season_id, role, effective_date
        """
        cursor = self.conn.execute(
            """
            SELECT team_id, player_id, season_id, role, effective_date
            FROM bullpen_roles
            WHERE team_id = %s
            AND season_id = %s
            AND end_date IS NULL
            ORDER BY role, player_id
            """,
            (team_id, season_id),
        )
        # columns = [col[0] for col in cursor.description]
        return [dict(row) for row in cursor.fetchall()]

    def get_roles_map(self, team_id: str, season_id: str) -> dict[str, str]:
        """Return {player_id: role} for all active bullpen roles for a team."""
        rows = self.conn.execute(
            """SELECT player_id, role FROM bullpen_roles
               WHERE team_id = %s AND season_id = %s AND end_date IS NULL""",
            (team_id, season_id),
        ).fetchall()
        return {r["player_id"]: r["role"] for r in rows}

    def get_closer(self, team_id: str, season_id: str) -> Optional[dict]:
        """
        Return the active Closer for a team in a given season, or None if unassigned.

        Returns a dict:
            team_id, player_id, season_id, role, effective_date
        """
        cursor = self.conn.execute(
            """
            SELECT team_id, player_id, season_id, role, effective_date
            FROM bullpen_roles
            WHERE team_id = %s
            AND season_id = %s
            AND role = 'Closer'
            AND end_date IS NULL
            LIMIT 1
            """,
            (team_id, season_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def update_role(
        self,
        team_id: str,
        player_id: str,
        season_id: str,
        new_role: str,
        effective_date: Optional[str] = None,
    ) -> None:
        """
        Change a pitcher's active bullpen role.

        Closes their current role (if any) and inserts a new one.

        Raises ValueError if:
            - new_role is invalid
            - The player is in the starting rotation
            - The player already holds new_role (no-op guard)
        """
        if effective_date is None:
            effective_date = _today()

        _validate_role(new_role)

        # Rotation conflict check
        rotation_ids = _get_active_rotation_player_ids(self.conn, team_id, season_id)
        if player_id in rotation_ids:
            raise ValueError(
                f"Player '{player_id}' is in the starting rotation and cannot be assigned a bullpen role."
            )

        # Check current role — skip if already set to new_role
        cursor = self.conn.execute(
            """
            SELECT role FROM bullpen_roles
            WHERE team_id = %s
            AND player_id = %s
            AND season_id = %s
            AND end_date IS NULL
            LIMIT 1
            """,
            (team_id, player_id, season_id),
        )
        row = cursor.fetchone()
        if row and row["role"] == new_role:
            return  # Already assigned this role; nothing to do

        # Close existing active role
        _close_active_role(self.conn, team_id, player_id, season_id, effective_date)

        # Insert updated role
        self.conn.execute(
            """
            INSERT INTO bullpen_roles (team_id, player_id, season_id, role, effective_date, end_date)
            VALUES (%s, %s, %s, %s, %s, NULL)
            """,
            (team_id, player_id, season_id, new_role, effective_date),
        )

    def remove_role(
        self,
        team_id: str,
        player_id: str,
        season_id: str,
        end_date: Optional[str] = None,
    ) -> None:
        """
        Remove a pitcher from the bullpen by closing their active role.
        """
        if end_date is None:
            end_date = _today()

        _close_active_role(self.conn, team_id, player_id, season_id, end_date)

        # cursor = self.conn.execute(
        #     """
        #     UPDATE bullpen_roles
        #     SET end_date = %s
        #     WHERE team_id = %s
        #     AND player_id = %s
        #     AND season_id = %s
        #     AND end_date IS NULL
        #     """,
        #     (end_date, team_id, player_id, season_id),
        # )
        # return cursor.rowcount > 0
