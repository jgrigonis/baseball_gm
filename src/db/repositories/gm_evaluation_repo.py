# src/db/repositories/gm_evaluation_repo.py


class GMEvaluationRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, gm_id: str, season_id: str) -> dict | None:
        """Return the evaluation row for a GM in a season, or None."""
        row = self.conn.execute(
            "SELECT * FROM gm_season_evaluations WHERE gm_id = %s AND season_id = %s",
            (gm_id, season_id),
        ).fetchone()
        return dict(row) if row else None
