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
            SELECT * FROM games WHERE id = ?
            """,
            (game_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "game_id": row["id"],
            "game_date": row["date"],
            "season_id": row["season_id"],
            "series_id": row["series_id"],
            "home_team_id": row["home_team_id"],
            "away_team_id": row["away_team_id"],
            "completed": row["completed"],
            "home_score": row["home_score"],
            "away_score": row["away_score"],
            "winner_id": row["winner_id"],
            "innings_played": row["innings_played"],
        }

    def save_result(self, game_id: str, result: GameResult, winner_id: str):
        """Save game result to database."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = ?, away_score = ?, winner_id = ?, innings_played = ?, completed = 1, updated_at = ?
            WHERE id = ?
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
        self.conn.commit()

    def get_season_games(
        self,
        season_id: str,
        completed_only: bool = False,
        incomplete_only: bool = False,
        regular_season_only: bool = False,
    ) -> list[dict]:
        """Get all games for a season."""
        conditions = ["season_id = ?"]
        params = [season_id]

        if incomplete_only:
            conditions.append("completed = 0")
        
        if regular_season_only:
            conditions.append("series_id IS NULL")

        where = " AND ".join(conditions)

        rows = self.conn.execute(
            f"SELECT * FROM games WHERE {where} ORDER BY date",
            params,
        ).fetchall()
    

        return [
            {
                "game_id": row["id"],
                "season_id": row["season_id"],
                "home_team_id": row["home_team_id"],
                "away_team_id": row["away_team_id"],
                "game_date": row["date"],
                "completed": row["completed"],
                "home_score": row["home_score"],
                "away_score": row["away_score"],
                "winner_id": row["winner_id"],
                "innings_played": row["innings_played"],
            }
            for row in rows
        ]

    def clear_result(self, game_id: str):
        """Clear game result (for replaying)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = NULL, away_score = NULL, winner_id = NULL, 
                innings_played = NULL, completed = 0, updated_at = ?
            WHERE id = ?
            """,
            (
                now,
                game_id,
            ),
        )
        self.conn.commit()

    def is_completed(self, game_id: str) -> bool:
        """Check if game is completed."""
        row = self.conn.execute(
            "SELECT completed FROM games WHERE id = ?", (game_id,)
        ).fetchone()

        if not row:
            return False

        return row["completed"] == 1
