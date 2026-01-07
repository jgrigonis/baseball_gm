"""
Handles:

Team identity

Career metadata

Lookups

Not stats.

Insert player information
"""

import uuid

from src.team.team import Team


class TeamRepository:
    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def add_player(self, team_id: str, player_id: str):
        """
        Add player to team roster.
        Idempotent.
        """
        self.conn.execute(
            """
            INSERT OR IGNORE INTO team_players (team_id, player_id)
            VALUES (?, ?)
            """,
            (team_id, player_id),
        )
        self.conn.commit()

    def get_or_create(self, city: int, mascot: int) -> str | None:
        """
        Inputs:
        city and mascot

        It will return the id for the team if that combo exists.

        Otherwise it will create the id, insert that combo and
        then return the team id

        Outputs:
        team_id

        Notably, this doesn't set the league.
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE city = ? AND mascot = ?
            """,
            (city, mascot),
        ).fetchone()
        if row:
            return row["id"]
        # Create a new ID if that city/mascot combo doesn't exist
        team_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT OR REPLACE INTO teams (
                id, city, mascot
            )
            VALUES(?, ?, ?)
            """,
            (
                team_id,
                city,
                mascot,
            ),
        )
        self.conn.commit()
        return team_id

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def look_up(self, team_id: int) -> Team | None:
        """
        Fetch a team based on id
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE id = ?
            """,
            (team_id,),
        ).fetchall()

        if row is None:
            return None

        return row
