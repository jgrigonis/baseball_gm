# src/db/repositories/league_repo.py
import uuid


class LeagueRepository:
    """
    Call create_league_season() before assign_to_league() to ensure
    the foreign key constraint is satisfied.
    """

    def __init__(self, conn):
        self.conn = conn

    def create_league(self, name: str):
        """
        Create The League

        If you try to re-use a league name, it will just
        return the id of that existing league.
        """
        row = self.conn.execute(
            "SELECT id FROM leagues WHERE name = ?",
            (name,),
        ).fetchone()

        if row:
            return row["id"]

        id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT OR REPLACE INTO leagues (
                id, name
            )
            VALUES(?, ?)
            """,
            (
                id,
                name,
            ),
        )
        self.conn.commit()
        return id

    def assign_season_to_league(self, league_id: str, season_id: str):
        """Register that a league is active for a given season"""
        self.conn.execute(
            """
            INSERT OR IGNORE INTO league_seasons (league_id, season_id)
            VALUES (?, ?)
            """,
            (league_id, season_id),
        )
        self.conn.commit()

    def assign_to_league(self, league_id: str, season_id: str, team_id: str):
        self.conn.execute(
            """
            INSERT OR IGNORE INTO league_season_teams (league_id, season_id, team_id)
            VALUES (?, ?, ?)
            """,
            (league_id, season_id, team_id),
        )
        self.conn.commit()

    def has_season(self, league_id: str, season_id: str) -> bool:
        """Check if a season is already assigned to a league"""
        row = self.conn.execute(
            """
            SELECT 1
            FROM league_seasons
            WHERE league_id = ? AND season_id = ?
            """,
            (league_id, season_id),
        ).fetchone()

        return row is not None
