# src/db/repositories/season_repo.py
import uuid


class SeasonRepository:
    def __init__(self, conn):
        self.conn = conn

    def create_season(self, year: int, name: str = None) -> str:
        """
        Create a season.

        If you try to create an existing name/year combo, it will
        just return the id of that existing season.
        """
        # Generate name if not provided
        if name is None:
            name = f"Season{year}"

        row = self.conn.execute(
            "SELECT id FROM seasons WHERE year = ? AND name = ?",
            (year, name),
        ).fetchone()

        if row:
            return row["id"]

        season_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT OR REPLACE INTO seasons (
                id, year, name
            )
            VALUES(?, ?, ?)
            """,
            (
                season_id,
                year,
                name,
            ),
        )
        self.conn.commit()
        return season_id
