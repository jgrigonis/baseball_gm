"""
Handles:

Player identity

Career metadata

Lookups

Not stats.

Insert player information
"""

from src.player.player_factory import Player


class PlayerRepository:
    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def insert(
        self,
        id: int,
        first_name: int,
        last_name: int,
        bats: int,
        throws: int,
    ):
        """
        Create a player record.
        Idempotent per (id).
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO players (
                id, first_name, last_name,
                bats, throws
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                id,
                first_name,
                last_name,
                bats,
                throws,
            ),
        )

        self.conn.commit()

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def look_up(self, player_id: int) -> Player | None:
        """
        Fetch a player
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM players
            WHERE id = ?
            """,
            (player_id,),
        ).fetchone()

        if row is None:
            return None

        return row
