# src/db/repositories/games_repo.py
"""
Repository for game records and results.

Handles:
- Loading game info
- Saving game results
- Querying games by season
- Game completion status
"""

import datetime

from src.game.game import GameResult


class GameRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, game_id: str) -> dict | None:
        """Load game information from database."""
        row = self.conn.execute(
            """
            SELECT 
                id AS game_id, 
                game_date, 
                season_id, 
                series_id, 
                home_team_id, 
                away_team_id, 
                completed, 
                home_score, 
                away_score, 
                winner_id, 
                innings_played 
            FROM games WHERE id = %s
            """,
            (game_id,),
        ).fetchone()

        if not row:
            return None

        return dict(row) if row else None

        # return {
        #     "game_id": row["id"],
        #     "game_date": row["game_date"],
        #     "season_id": row["season_id"],
        #     "series_id": row["series_id"],
        #     "home_team_id": row["home_team_id"],
        #     "away_team_id": row["away_team_id"],
        #     "completed": row["completed"],
        #     "home_score": row["home_score"],
        #     "away_score": row["away_score"],
        #     "winner_id": row["winner_id"],
        #     "innings_played": row["innings_played"],
        # }

    def save_game_result(self, game_id: str, result: GameResult, winner_id: str):
        """Save game result to database."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = %s, away_score = %s, winner_id = %s, innings_played = %s, completed = 1, updated_at = %s
            WHERE id = %s
            """,
            (
                result.home_score,
                result.away_score,
                winner_id,
                result.innings_played,
                now,
                game_id,
            ),
        )
        # self.conn.commit()

    def get_season_games(
        self,
        season_id: str,
        completed_only: bool = False,
        incomplete_only: bool = False,
        regular_season_only: bool = False,
    ) -> list[dict]:
        """Get all games for a season."""
        # 1. Base query and list of columns (no SELECT *)
        query = """
            SELECT id, season_id, home_team_id, away_team_id, game_date, 
                completed, home_score, away_score, winner_id, innings_played 
            FROM games 
            WHERE season_id = %s
        """
        # conditions = ["season_id = %s"]
        params = [season_id]

        if completed_only:
            query += " AND completed = 1"
            # conditions.append("completed = 1")

        if incomplete_only:
            query += " AND completed = 0"
            # conditions.append("completed = 0")

        if regular_season_only:
            query += " AND series_id IS NULL"
            # conditions.append("series_id IS NULL")

        query += " ORDER BY game_date"

        # where = " AND ".join(conditions)

        rows = self.conn.execute(query, params).fetchall()

        # rows = self.conn.execute(
        #     f"SELECT * FROM games WHERE {where} ORDER BY game_date",
        #     params,
        # ).fetchall()

        return [
            {
                "game_id": row["id"],
                "season_id": row["season_id"],
                "home_team_id": row["home_team_id"],
                "away_team_id": row["away_team_id"],
                "game_date": row["game_date"],
                "completed": row["completed"],
                "home_score": row["home_score"],
                "away_score": row["away_score"],
                "winner_id": row["winner_id"],
                "innings_played": row["innings_played"],
            }
            for row in rows
        ]

    # Don't see this ever getting called anywhere currently
    def clear_result(self, game_id: str):
        """Clear game result (for replaying)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = NULL, away_score = NULL, winner_id = NULL, 
                innings_played = NULL, completed = 0, updated_at = %s
            WHERE id = %s
            """,
            (
                now,
                game_id,
            ),
        )
        # self.conn.commit()

    def games_remaining(self, season_id: str) -> int:
        """Returns how many unplayed games remain in a season."""
        if not season_id:
            return 0
        row = self.conn.execute(
            "SELECT COUNT(*) FROM games WHERE season_id = %s AND completed = 0",
            (season_id,),
        ).fetchone()
        return row["count"] if row else 0

    def get_team_upcoming(self, season_id: str, team_id: str, limit: int | None = None) -> list[dict]:
        """Return incomplete games for a team, with opponent team names, ordered by date."""
        query = """SELECT g.game_date, g.home_team_id, g.away_team_id,
                          ht.city as home_city, ht.mascot as home_mascot,
                          at.city as away_city, at.mascot as away_mascot
                   FROM games g
                   JOIN teams ht ON ht.id = g.home_team_id
                   JOIN teams at ON at.id = g.away_team_id
                   WHERE g.season_id = %s AND g.completed = 0
                     AND (g.home_team_id = %s OR g.away_team_id = %s)
                   ORDER BY g.game_date"""
        if limit:
            query += f" LIMIT {limit}"
        rows = self.conn.execute(query, (season_id, team_id, team_id)).fetchall()
        return [dict(r) for r in rows]

    def get_team_results(self, season_id: str, team_id: str, limit: int | None = None) -> list[dict]:
        """Return completed games for a team, with scores and team names, newest first."""
        query = """SELECT g.id as game_id, g.game_date, g.home_team_id, g.away_team_id,
                          g.home_score, g.away_score, g.innings_played,
                          ht.city as home_city, ht.mascot as home_mascot,
                          at.city as away_city, at.mascot as away_mascot
                   FROM games g
                   JOIN teams ht ON ht.id = g.home_team_id
                   JOIN teams at ON at.id = g.away_team_id
                   WHERE g.season_id = %s AND g.completed = 1
                     AND (g.home_team_id = %s OR g.away_team_id = %s)
                   ORDER BY g.game_date DESC"""
        if limit:
            query += f" LIMIT {limit}"
        rows = self.conn.execute(query, (season_id, team_id, team_id)).fetchall()
        return [dict(r) for r in rows]

    # This never gets called, except in tests
    def is_completed(self, game_id: str) -> bool:
        """Check if game is completed."""
        row = self.conn.execute(
            "SELECT completed FROM games WHERE id = %s", (game_id,)
        ).fetchone()

        if not row:
            return False

        return row["completed"] == 1
