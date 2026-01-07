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

    def insert(
        self,
        id: int,
        city: int,
        mascot: int,
        league: int,
    ):
        """
        Create a team record.
        Idempotent per (id).
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO team (
                id, city, mascot, league
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                id,
                city,
                mascot,
                league,
            ),
        )

        self.conn.commit()

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
    
    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def get_or_create(self, city: int, mascot: int) -> str | None:
        """
        
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
    

    def look_up(self, team_id: int) -> Team | None:
        """
        Fetch a team
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM team
            WHERE id = ?
            """,
            (team_id,),
        ).fetchall()

        if row is None:
            return None

        return row
