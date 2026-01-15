"""
Handles:

Team identity

Career metadata

Lookups

Not stats.

Insert player information

Know how to persist teams

Know how to associate teams

Know how to answer safety questions

NOT create domain Team objects
"""

import uuid
import sqlite3

from src.team.team_record import TeamRecord


class TeamRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------
    # TEAM CREATION
    # ------------------------------------------------------------

    def create(
        self,
        city: str,
        mascot: str,
        *,
        source_csv: str | None = None,
        source_hash: str | None = None,
    ) -> str:
        """
        Create a new team record.
        Caller must ensure this is safe.
        """
        team_id = uuid.uuid4().hex

        self.conn.execute(
            """
            INSERT INTO teams (
                id, city, mascot, source_csv, source_hash
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (team_id, city, mascot, source_csv, source_hash),
        )

        return team_id

    def add_to_league(self, league_id: str, team_id: str):
        """
        Attach a team to a league.
        Idempotent.
        """
        self.conn.execute(
            """
            INSERT OR IGNORE INTO league_teams (league_id, team_id)
            VALUES (?, ?)
            """,
            (league_id, team_id),
        )

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

    def get(self, team_id: str) -> TeamRecord | None:
        """
        Fetch a team by ID.
        """
        return self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE id = ?
            """,
            (team_id,),
        ).fetchone()

    def find_by_city_mascot(self, city: str, mascot: str):
        """
        Fetch a team based on city and mascot
        """
        return self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE city = ? AND mascot = ?
            """,
            (city, mascot),
        ).fetchone()

    def is_in_league(self, team_id: str, league_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM league_teams
            WHERE league_id = ? AND team_id = ?
            """,
            (league_id, team_id),
        ).fetchone()

        return row is not None

    def has_players(self, team_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM team_players
            WHERE team_id = ?
            LIMIT 1
            """,
            (team_id,),
        ).fetchone()

        return row is not None

    def load_for_game(self, team_id) -> TeamRecord:
        team_row = self.get_team(team_id)
        players = self.get_roster(team_id)

        return TeamRecord.from_records(team_row, players)
