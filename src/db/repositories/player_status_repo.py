# src/db/repositories/player_status_repo.py

from datetime import date

from src.db.repositories.jersey_repo import JerseyRepository


def _guarantee(conn, player_ids: list[str]) -> None:
    """Joining the 40-man guarantees a player's deal (contract_repo)."""
    # Imported here: contract_repo -> player_value -> ... is a long chain.
    from src.db.repositories.contract_repo import ContractRepository

    ContractRepository(conn).guarantee(player_ids)


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
            VALUES (%s, %s, %s)
            ON CONFLICT(player_id) DO UPDATE SET
                status = excluded.status,
                since  = excluded.since
            """,
            (player_id, status, since_str),
        )
        # Joining or leaving the 40-man gives or takes a jersey number.
        JerseyRepository(self.conn).sync([player_id])
        _guarantee(self.conn, [player_id])

    def get_status(self, player_id: str) -> str | None:
        """Return the current status for a player, or None if not found."""
        row = self.conn.execute(
            "SELECT status FROM player_status WHERE player_id = %s",
            (player_id,),
        ).fetchone()
        return row["status"] if row else None

    def get_by_status(self, status: str) -> list[str]:
        """Return all player_ids with a given status."""
        rows = self.conn.execute(
            "SELECT player_id FROM player_status WHERE status = %s",
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
            WHERE tp.team_id = %s AND ps.status = %s
            """,
            (team_id, status),
        ).fetchall()
        return [r["player_id"] for r in rows]

    # def get_by_team_and_statuses(self, team_id: str, statuses: list) -> list[str]:
    #     """Return player_ids on a specific team with a given status."""
    #     rows = self.conn.execute(
    #         f"""
    #         SELECT tp.player_id
    #         FROM team_players tp
    #         JOIN player_status ps ON tp.player_id = ps.player_id
    #         WHERE tp.team_id = %s AND ps.status IN ({statuses})
    #         """,
    #         (team_id,),
    #     ).fetchall()
    #     return [r["player_id"] for r in rows]

    # Use get_player_ids_from_team_players
    # def get_player_ids_for_team(self, team_id: str) -> set[str]:
    #     """Return all player_ids on a team (from team_players)."""
    #     rows = self.conn.execute(
    #         "SELECT player_id FROM team_players WHERE team_id = %s", (team_id,)
    #     ).fetchall()
    #     return {r["player_id"] for r in rows}

    def set_40man_roster(
        self, team_player_ids: set[str], forty_man_ids: list[str]
    ) -> None:
        """Set 40-man/minors status for every player on a team."""
        forty_set = set(forty_man_ids)
        assignments = {
            pid: ("40man" if pid in forty_set else "minors") for pid in team_player_ids
        }
        self.bulk_set(assignments)

    def bulk_set(self, assignments: dict[str, str], since: date | None = None) -> None:
        """
        Set status for many players at once.

        Args:
            assignments: Dict of player_id -> status
            since: Date to use for all assignments (default: today)
        """
        since_str = (since or date.today()).isoformat()
        self.conn.cursor().executemany(
            """
            INSERT INTO player_status (player_id, status, since)
            VALUES (%s, %s, %s)
            ON CONFLICT(player_id) DO UPDATE SET
                status = excluded.status,
                since  = excluded.since
            """,
            [
                (player_id, status, since_str)
                for player_id, status in assignments.items()
            ],
        )
        JerseyRepository(self.conn).sync(assignments)
        _guarantee(self.conn, list(assignments))
