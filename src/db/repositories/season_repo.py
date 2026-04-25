# src/db/repositories/season_repo.py
"""
Repository for season records.

Handles:
- Creating seasons
- Querying seasons by year or league
- Season metadata management

Uses tables:
- seasons
- league_seasons (for league associations)
"""

import uuid


class SeasonRepository:
    """Repository for managing season records."""

    def __init__(self, conn):
        self.conn = conn

    def create_season(self, year: int, name: str | None = None) -> str:
        """
        Create a season in the seasons table.

        Will fail on duplicate.

        """
        if name is None:
            name = f"Season{year}"

        season_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO seasons (id, year, name) VALUES (%s, %s, %s)",
            (season_id, year, name),
        )
        # self.conn.commit()
        return season_id

    # def _get_season_id(self, year: int, name: str) -> str | None:
    #     """Helper: Get season ID by year and name."""
    #     row = self.conn.execute(
    #         "SELECT id FROM seasons WHERE year = %s AND name = %s", (year, name)
    #     ).fetchone()

    #     return row["id"] if row else None

    def has_a_completed_game(self, season_id: str) -> bool:
        """Determine if the season has a single completed game."""
        row = self.conn.execute(
            "SELECT 1 FROM games WHERE season_id = %s AND completed = 1 LIMIT 1",
            (season_id,),
        ).fetchone()
        return row is not None

    def get_year(self, season_id: str) -> dict | None:
        """Get the year of the season."""
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = %s",
            (season_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_season(self, season_id: str) -> dict | None:
        """
        Get season information by ID.

        Args:
            season_id: Season ID

        Returns:
            Dictionary with season info, or None if not found
        """
        row = self.conn.execute(
            "SELECT * FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()

        if not row:
            return None

        return {"id": row["id"], "year": row["year"], "name": row["name"]}

    def get_seasons_by_year(self, year: int) -> list[dict]:
        """
        Get all seasons for a specific year.

        Args:
            year: Season year

        Returns:
            List of season dictionaries
        """
        rows = self.conn.execute(
            "SELECT * FROM seasons WHERE year = %s ORDER BY name", (year,)
        ).fetchall()

        return [
            {"id": row["id"], "year": row["year"], "name": row["name"]} for row in rows
        ]

    def get_all_seasons(self) -> list[dict]:
        """
        Get all seasons, ordered by year (descending) then name.

        Returns:
            List of season dictionaries
        """
        rows = self.conn.execute(
            "SELECT id, year, name FROM seasons ORDER BY year DESC, name"
        ).fetchall()

        return [
            {"id": row["id"], "year": row["year"], "name": row["name"]} for row in rows
        ]

    def get_all_seasons_asc(self) -> list[dict]:
        """Return all seasons ordered by year ascending (oldest first)."""
        rows = self.conn.execute(
            "SELECT id, year, name FROM seasons ORDER BY year"
        ).fetchall()
        return [
            {"id": row["id"], "year": row["year"], "name": row["name"]} for row in rows
        ]

    # TODO Don't think this is ever called
    def exists(self, season_id: str) -> bool:
        """
        Check if a season exists.

        Args:
            season_id: Season ID

        Returns:
            True if season exists, False otherwise
        """
        row = self.conn.execute(
            "SELECT 1 FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()

        return row is not None

    # This is never called except in tests
    def delete_season(self, season_id: str) -> None:
        """
        Delete a season.

        Args:
            season_id: Season ID

        Note:
            This will cascade delete related games, stats, etc.
            depending on your foreign key constraints.
        """
        self.conn.execute("DELETE FROM seasons WHERE id = %s", (season_id,))
        # self.conn.commit()

    def get_by_league_and_year(self, league_id: str, year: int) -> dict | None:
        """Return the season row for a league and year, or None."""
        row = self.conn.execute(
            """SELECT s.* FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.year = %s""",
            (league_id, year),
        ).fetchone()
        return dict(row) if row else None

    def get_last_with_series(self, league_id: str) -> str | None:
        """Return the season_id of the most recent season that has any series records."""
        row = self.conn.execute(
            """SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (SELECT 1 FROM series sr WHERE sr.season_id = s.id)
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return row["id"] if row else None

    def get_most_recent_season_from_league(self, league_id: str) -> str | None:
        """Return the most recent season from the league."""
        row = self.conn.execute(
            """SELECT s.id FROM seasons s
                JOIN league_seasons ls ON ls.season_id = s.id
                WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return row["id"] if row else None

    def get_team_count(self, season_id: str) -> int:
        """Return the number of distinct teams in a season."""
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT team_id) as n FROM league_season_teams WHERE season_id = %s",
            (season_id,),
        ).fetchone()
        return row["n"] or 0

    def get_seasons_for_league(self, league_id: str) -> list[dict]:
        """Return all seasons for a league, newest first (id, year, name)."""
        rows = self.conn.execute(
            """SELECT s.id, s.year, s.name FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
               ORDER BY s.year DESC""",
            (league_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_oldest_incomplete_for_league(self, league_id: str) -> dict | None:
        """Return the oldest season that still has unplayed games, or None."""
        row = self.conn.execute(
            """SELECT s.id, s.year FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (
                   SELECT 1 FROM games g WHERE g.season_id = s.id AND g.completed = 0
                 )
               ORDER BY s.year ASC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_current_id_for_league(self, league_id: str) -> str | None:
        """Return the most recent season ID for a league, or None."""
        row = self.conn.execute(
            """SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return row["id"] if row else None

    def get_newest_for_league(self, league_id: str) -> dict | None:
        """Return the newest season row for a league, or None."""
        row = self.conn.execute(
            """SELECT s.id, s.year, s.name FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_last_with_completed_games(self, league_id: str) -> dict | None:
        """Return the newest season that has at least one completed game, or None."""
        row = self.conn.execute(
            """SELECT s.id, s.year, s.name FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (
                   SELECT 1 FROM games g WHERE g.season_id = s.id AND g.completed = 1
                 )
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_last_with_series_row(self, league_id: str) -> dict | None:
        """Return the newest season that has series records, or None."""
        row = self.conn.execute(
            """SELECT s.id, s.year, s.name FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (SELECT 1 FROM series sr WHERE sr.season_id = s.id)
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None
