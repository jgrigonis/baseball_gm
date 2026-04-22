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

    def is_done(self, season_id: str, step: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM offseason_steps WHERE season_id = %s AND step = %s",
            (season_id, step),
        ).fetchone()
        return row is not None

    def mark_done(self, season_id: str, step: str, done_time: str) -> None:
        self.conn.execute(
            "INSERT INTO offseason_steps (season_id, step, completed_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (season_id, step, done_time),
        )
