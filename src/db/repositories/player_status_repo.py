# src/db/repositories/player_status_repo.py

from datetime import date

# ------------------------------------------------------------------
# Repository
# ------------------------------------------------------------------


class PlayerStatusRepository:
    """Repository for managing player roster status."""

    def __init__(self, conn):
        self.conn = conn

    def set_status(
        self, player_id: str, status: str, since: date | None = None
    ) -> None:
        """Insert or update a player's roster status."""
        since_str = (since or date.today()).isoformat()
        self.conn.execute(
            """
            INSERT INTO player_status (player_id, status, since)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                status = excluded.status,
                since  = excluded.since
            """,
            (player_id, status, since_str),
        )
        self.conn.commit()

    def get_status(self, player_id: str) -> str | None:
        """Return the current status for a player, or None if not found."""
        row = self.conn.execute(
            "SELECT status FROM player_status WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return row["status"] if row else None

    def get_by_status(self, status: str) -> list[str]:
        """Return all player_ids with a given status."""
        rows = self.conn.execute(
            "SELECT player_id FROM player_status WHERE status = ?",
            (status,),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def get_by_team_and_status(self, team_id: str, status: str) -> list[str]:
        """Return player_ids on a specific team with a given status."""
        rows = self.conn.execute(
            """
            SELECT tp.player_id
            FROM team_players tp
            JOIN player_status ps ON tp.player_id = ps.player_id
            WHERE tp.team_id = ? AND ps.status = ?
            """,
            (team_id, status),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def bulk_set(self, assignments: dict[str, str], since: date | None = None) -> None:
        """
        Set status for many players at once.

        Args:
            assignments: Dict of player_id -> status
            since: Date to use for all assignments (default: today)
        """
        since_str = (since or date.today()).isoformat()
        self.conn.executemany(
            """
            INSERT INTO player_status (player_id, status, since)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                status = excluded.status,
                since  = excluded.since
            """,
            [
                (player_id, status, since_str)
                for player_id, status in assignments.items()
            ],
        )
        self.conn.commit()
