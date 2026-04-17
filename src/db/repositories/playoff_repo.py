# src/db/repositories/playoff_repo.py
from datetime import date

_WINS_NEEDED = {5: 3, 7: 4}


class PlayoffRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_series_id(self, season_id: str, name: str) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM series WHERE season_id = %s AND name = %s",
            (season_id, name),
        ).fetchone()
        return row["id"] if row else None

    def get_series_winner(self, series_id: str, best_of: int) -> str | None:
        wins_needed = _WINS_NEEDED[best_of]
        rows = self.conn.execute(
            """
            SELECT winner_id, COUNT(*) AS wins
            FROM games
            WHERE series_id = %s AND completed = 1
            GROUP BY winner_id
            """,
            (series_id,),
        ).fetchall()
        for row in rows:
            if row["wins"] >= wins_needed:
                return row["winner_id"]
        return None

    def is_decided(self, series_id: str, best_of: int) -> bool:
        return self.get_series_winner(series_id, best_of) is not None

    def series_has_games(self, series_id: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) as n FROM games WHERE series_id = %s", (series_id,)
        ).fetchone()
        return (row["n"] if row else 0) > 0

    def get_playoff_start(self, season_id: str) -> date | None:
        row = self.conn.execute(
            """SELECT g.game_date FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND s.name IN ('1v8','2v7','3v6','4v5')
               ORDER BY g.game_date LIMIT 1""",
            (season_id,),
        ).fetchone()
        return date.fromisoformat(row["game_date"]) if row else None

    def get_seeds(self, season_id: str) -> list[dict]:
        """Reconstruct original seeds from R1 series (game 1 home team = high seed)."""
        result = {}
        for name, hi, lo in [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]:
            series_id = self.get_series_id(season_id, name)
            if not series_id:
                raise ValueError(f"Series {name} not found for season {season_id}")
            game = self.conn.execute(
                "SELECT home_team_id, away_team_id FROM games WHERE series_id = %s ORDER BY game_date LIMIT 1",
                (series_id,),
            ).fetchone()
            result[hi] = game["home_team_id"]
            result[lo] = game["away_team_id"]
        return [{"team_id": result[i], "seed": i} for i in range(1, 9)]

    def create_series(self, series_id: str, season_id: str, name: str) -> None:
        self.conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (series_id, season_id, name),
        )
