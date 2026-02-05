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
        Create a season or return existing season ID if already exists.
        Idempotent - safe to call multiple times with same year/name.

        Args:
            year: Season year (e.g., 2025)
            name: Season name (default: "Season{year}")

        Returns:
            Season ID (UUID hex string)

        Example:
            >>> season_id = repo.create_season(2025)
            >>> season_id = repo.create_season(2025, "Spring Season")
        """
        # Generate name if not provided
        if name is None:
            name = f"Season{year}"

        # Check if season already exists
        existing_id = self._get_season_id(year, name)
        if existing_id:
            return existing_id

        # Create new season
        season_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO seasons (id, year, name)
            VALUES (?, ?, ?)
            """,
            (season_id, year, name),
        )
        self.conn.commit()
        return season_id

    def _get_season_id(self, year: int, name: str) -> str | None:
        """Helper: Get season ID by year and name."""
        row = self.conn.execute(
            "SELECT id FROM seasons WHERE year = ? AND name = ?", (year, name)
        ).fetchone()

        return row["id"] if row else None

    def get_season(self, season_id: str) -> dict | None:
        """
        Get season information by ID.

        Args:
            season_id: Season ID

        Returns:
            Dictionary with season info, or None if not found
        """
        row = self.conn.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
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
            "SELECT * FROM seasons WHERE year = ? ORDER BY name", (year,)
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
            "SELECT * FROM seasons ORDER BY year DESC, name"
        ).fetchall()

        return [
            {"id": row["id"], "year": row["year"], "name": row["name"]} for row in rows
        ]

    def exists(self, season_id: str) -> bool:
        """
        Check if a season exists.

        Args:
            season_id: Season ID

        Returns:
            True if season exists, False otherwise
        """
        row = self.conn.execute(
            "SELECT 1 FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        return row is not None

    def delete_season(self, season_id: str) -> None:
        """
        Delete a season.

        Args:
            season_id: Season ID

        Note:
            This will cascade delete related games, stats, etc.
            depending on your foreign key constraints.
        """
        self.conn.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
        self.conn.commit()
