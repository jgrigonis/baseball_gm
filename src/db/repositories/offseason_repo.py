# src/db/repositories/offseason_repo.py


class OffseasonRepository:
    def __init__(self, conn):
        self.conn = conn

    def find_season_with_offseason_steps(
        self, league_id: str, season_id: str
    ) -> str | None:
        """Find the most recent season for this league that has deferred pipeline steps."""
        row = self.conn.execute(
            """SELECT os.season_id FROM offseason_steps os
            JOIN league_seasons ls ON ls.season_id = os.season_id
            WHERE ls.league_id = %s
                AND os.step = 'generate_draft'
                AND os.season_id != %s
                AND NOT EXISTS (
                    SELECT 1 FROM offseason_steps os2
                    WHERE os2.season_id = os.season_id AND os2.step = 'trim_rosters'
                )
            ORDER BY os.completed_at DESC LIMIT 1""",
            (league_id, season_id),
        ).fetchone()
        return row["season_id"] if row else None
