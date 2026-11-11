# src/db/repositories/games_repo.py
"""
Repository for game records and results.

Handles:
- Loading game info
- Saving game results
- Querying games by season
- Game completion status
"""

# needed for < python 3.14 for type hinting ScheduledGame without quotes
from __future__ import annotations
import datetime
from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb

from src.game.game import GameResult

if TYPE_CHECKING:
    from src.league.schedule import ScheduledGame


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

        # if not row:
        #     return None

        return dict(row) if row else None

    def save_game_result(
        self, game_id: str, result: GameResult, winner_id: str
    ) -> None:
        """Save game result to database."""
        now = datetime.datetime.now(datetime.UTC).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = %s, away_score = %s, winner_id = %s, innings_played = %s,
                line_score = %s, completed = 1, updated_at = %s
            WHERE id = %s
            """,
            (
                result.home_score,
                result.away_score,
                winner_id,
                result.innings_played,
                Jsonb(
                    {
                        "away": list(result.away_innings),
                        "home": list(result.home_innings),
                    }
                ),
                now,
                game_id,
            ),
        )

    def insert_schedule(self, schedule: list[ScheduledGame]) -> None:
        cursor = self.conn.cursor()

        for game in schedule:
            cursor.execute(
                """
                INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    game.id,
                    game.game_date,
                    game.season_id,
                    game.series_id,
                    game.home_team_id,
                    game.away_team_id,
                ),
            )

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

        rows = self.conn.execute(query, params).fetchall()

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

    def get_days_games(self, season_id: str, game_date) -> list[dict] | None:
        """Get the season's games for a particular date."""
        games = self.conn.execute(
            """
            SELECT id as game_id, home_team_id, away_team_id, completed,
                season_id, game_date
            FROM games
            WHERE season_id = %s AND game_date = %s AND completed = 0
            """,
            (season_id, game_date),
        ).fetchall()
        return games

    def clear_result(self, game_id: str):
        """Clear game result (for replaying)."""
        now = datetime.datetime.now(datetime.UTC).isoformat()

        self.conn.execute(
            """
            UPDATE games 
            SET home_score = NULL, away_score = NULL, winner_id = NULL, 
                innings_played = NULL, line_score = NULL, completed = 0, updated_at = %s
            WHERE id = %s
            """,
            (
                now,
                game_id,
            ),
        )
        # self.conn.commit()

    def get_completed_regular_season_count(self, season_id: str) -> int:
        """Return the number of completed regular season games."""
        row = self.conn.execute(
            "SELECT COUNT(*) as g FROM games WHERE season_id = %s AND completed = 1 AND series_id IS NULL",
            (season_id,),
        ).fetchone()
        return row["g"] or 0

    def get_with_teams(self, game_id: str) -> dict | None:
        """Return game row with home/away team city and mascot joined in."""
        row = self.conn.execute(
            """SELECT g.*, ht.city as home_city, ht.mascot as home_mascot,
                      at.city as away_city, at.mascot as away_mascot
               FROM games g
               JOIN teams ht ON ht.id = g.home_team_id
               JOIN teams at ON at.id = g.away_team_id
               WHERE g.id = %s""",
            (game_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_events(self, game_id: str) -> list[dict]:
        """Return all event log entries for a game in order."""
        rows = self.conn.execute(
            """SELECT event_type, inning, half, reason, detail, team_id,
                      player_id, player_id_2
               FROM game_events
               WHERE game_id = %s
               ORDER BY id""",
            (game_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_plays(self, game_id: str, season_id: str, plays: list[dict]) -> None:
        """Keep a game's play-by-play (src/game/play_log.py) for the panel."""
        self.conn.execute(
            """INSERT INTO game_plays (game_id, season_id, plays)
               VALUES (%s, %s, %s)
               ON CONFLICT (game_id) DO UPDATE SET plays = EXCLUDED.plays""",
            (game_id, season_id, Jsonb(plays)),
        )

    def get_plays(self, game_id: str) -> list[dict] | None:
        """A game's play-by-play, or None when it was never kept or has
        been cleared (only the current season's are kept)."""
        row = self.conn.execute(
            "SELECT plays FROM game_plays WHERE game_id = %s", (game_id,)
        ).fetchone()
        return row["plays"] if row else None

    def clear_old_plays(self, league_id: str, keep_season_id: str) -> int:
        """Delete the league's play-by-play from every season but this one."""
        cur = self.conn.execute(
            """DELETE FROM game_plays
               WHERE season_id <> %s
                 AND season_id IN (
                     SELECT season_id FROM league_seasons WHERE league_id = %s
                 )""",
            (keep_season_id, league_id),
        )
        return cur.rowcount

    def get_series_games(self, series_id: str) -> list[dict]:
        """Return all games for a playoff series, ordered by date."""
        rows = self.conn.execute(
            """SELECT id, game_date, home_team_id, away_team_id,
                      completed, home_score, away_score, winner_id
               FROM games WHERE series_id = %s ORDER BY game_date""",
            (series_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def games_remaining(self, season_id: str) -> int:
        """Returns how many unplayed games remain in a season."""
        if not season_id:
            return 0
        row = self.conn.execute(
            "SELECT COUNT(*) FROM games WHERE season_id = %s AND completed = 0",
            (season_id,),
        ).fetchone()
        return row["count"] if row else 0

    def get_team_upcoming(
        self, season_id: str, team_id: str, limit: int | None = None
    ) -> list[dict]:
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

    def get_team_results(
        self, season_id: str, team_id: str, limit: int | None = None
    ) -> list[dict]:
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

    def void_remaining_series_games(self, series_id: str) -> int:
        """Mark unplayed games in a decided series as voided (-1). Returns count voided."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE games SET completed = -1 WHERE series_id = %s AND completed = 0",
            (series_id,),
        )
        return cursor.rowcount

    def get_next_unplayed_date(self, season_id: str) -> dict | None:
        """Get the next unplayed date row."""
        row = self.conn.execute(
            """
            SELECT game_date FROM games
            WHERE season_id = %s AND completed = 0
            ORDER BY game_date ASC
            LIMIT 1
            """,
            (season_id,),
        ).fetchone()
        if row:
            return dict(row)

    def opening_game(self, season_id: str, team_id: str) -> dict | None:
        """The team's first regular season game, with both teams' names."""
        row = self.conn.execute(
            """SELECT g.game_date, g.home_team_id, g.away_team_id,
                      h.city AS home_city, h.mascot AS home_mascot,
                      a.city AS away_city, a.mascot AS away_mascot
               FROM games g
               JOIN teams h ON h.id = g.home_team_id
               JOIN teams a ON a.id = g.away_team_id
               WHERE g.season_id = %s AND g.series_id IS NULL
                 AND %s IN (g.home_team_id, g.away_team_id)
               ORDER BY g.game_date LIMIT 1""",
            (season_id, team_id),
        ).fetchone()
        return dict(row) if row else None

    def last_scheduled_date(self, season_id: str) -> str | None:
        """The regular season's last scheduled day, played or not (playoff
        series games aren't counted)."""
        row = self.conn.execute(
            """SELECT MAX(game_date) as d FROM games
                WHERE season_id = %s AND series_id IS NULL""",
            (season_id,),
        ).fetchone()
        return row["d"] if row and row.get("d") is not None else None

    def last_game_date(self, season_id: str) -> dict | None:
        last_game = self.conn.execute(
            """SELECT MAX(game_date) as d FROM games
                WHERE season_id = %s AND completed = 1""",
            (season_id,),
        ).fetchone()
        if last_game and last_game.get("d") is not None:
            return last_game
        return None

    def last_series_game_date(self, season_id: str) -> dict | None:
        last_game = self.conn.execute(
            """SELECT MAX(game_date) as d FROM games g
                JOIN series s ON g.series_id = s.id
                WHERE s.season_id = %s AND g.completed = 1""",
            (season_id,),
        ).fetchone()
        if last_game and last_game.get("d") is not None:
            return last_game["d"]
        return None

    def delete_season_games(self, season_id: str) -> None:
        self.conn.execute("DELETE FROM games WHERE season_id = %s", (season_id,))
