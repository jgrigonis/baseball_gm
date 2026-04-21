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
        rows = self.get_win_count(series_id)
        # rows = self.conn.execute(
        #     """
        #     SELECT winner_id, COUNT(*) AS wins
        #     FROM games
        #     WHERE series_id = %s AND completed = 1
        #     GROUP BY winner_id
        #     """,
        #     (series_id,),
        # ).fetchall()
        for row in rows:
            if row["wins"] >= wins_needed:
                return row["winner_id"]
        return None

    def get_win_count(self, series_id: str) -> dict:
        rows = self.conn.execute(
            """
            SELECT winner_id, COUNT(*) AS wins
            FROM games
            WHERE series_id = %s AND completed = 1
            # GROUP BY winner_id
            """,
            (series_id,),
        ).fetchall()
        return rows

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

    def get_teams_in_series(self, series_id: str) -> dict:
        teams = self.conn.execute(
            "SELECT home_team_id, away_team_id FROM games WHERE series_id = %s LIMIT 1",
            (series_id,),
        ).fetchone()
        return teams

    def get_seeds(self, season_id: str) -> list[dict]:
        """Reconstruct original seeds from R1 series (game 1 home team = high seed)."""
        result = {}
        for name, hi, lo in [
            ("1v8", 1, 8),
            ("2v7", 2, 7),
            ("3v6", 3, 6),
            ("4v5", 4, 5),
        ]:
            series_id = self.get_series_id(season_id, name)
            if not series_id:
                raise ValueError(f"Series {name} not found for season {season_id}")
            game = self.get_teams_in_series(series_id)
            # game = self.conn.execute(
            #     "SELECT home_team_id, away_team_id FROM games WHERE series_id = %s ORDER BY game_date LIMIT 1",
            #     (series_id,),
            # ).fetchone()
            result[hi] = game["home_team_id"]
            result[lo] = game["away_team_id"]
        return [{"team_id": result[i], "seed": i} for i in range(1, 9)]

    def create_series(self, series_id: str, season_id: str, name: str) -> None:
        self.conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (series_id, season_id, name),
        )

    def existing_series_exist(self, season_id: str) -> bool:
        """Return True is there is already an existing series, else False."""
        existing_series = self.conn.execute(
            "SELECT COUNT(*) FROM series WHERE season_id = %s",
            (season_id,),
        ).fetchone()["count"]
        if existing_series:
            return True
        return False

    def get_earliest_unplayed_date(self, season_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT MIN(g.game_date) as next_date
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.completed = 0""",
            (season_id,),
        ).fetchone()
        return dict(row)

    def get_days_playoff_games(self, season_id: str, next_date) -> list[dict]:
        rows = self.conn.execute(
            """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id,
                      g.completed, s.name as series_name, g.series_id
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.game_date = %s AND g.completed = 0
               ORDER BY s.name""",
            (season_id, next_date),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_games_after_date(self, season_id: str, next_date) -> list[dict]:
        rows = self.conn.execute(
            """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id,
                      g.completed, s.name as series_name, g.series_id
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.completed = 0 AND g.game_date::date > %s
               ORDER BY g.game_date, s.name""",
            (season_id, next_date),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_first_game(self, season_id: str) -> dict:
        """Infer playoff start date from first R1 game"""
        game = self.conn.execute(
            """
            SELECT g.game_date FROM games g
            JOIN series s ON g.series_id = s.id
            WHERE s.season_id = %s AND s.name IN ('1v8','2v7','3v6','4v5')
            ORDER BY g.game_date LIMIT 1
            """,
            (season_id,),
        ).fetchone()
        return game

    def get_series_name(self, series_id: str) -> str:
        series = self.conn.execute(
            "SELECT name FROM series WHERE id = %s", (series_id,)
        ).fetchone()
        return series
