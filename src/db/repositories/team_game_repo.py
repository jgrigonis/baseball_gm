"""
Repository for team game statistics.

Handles:
- Saving team stats for a game
- Loading team stats
- Aggregating team stats by season
"""

from src.team.team_in_game import TeamInGame


class TeamGameRepository:
    def __init__(self, conn):
        self.conn = conn

    def save_stats(
        self,
        game_id: str,
        team_id: str,
        opponent_id: str,
        runs: int,
        hits: int,
        errors: int,
        won: bool,
    ):
        """Save team stats for a game."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO team_game_stats (
                game_id, team_id, runs, hits, errors, win, loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (game_id, team_id, runs, hits, errors, 1 if won else 0, 0 if won else 1),
        )
        self.conn.commit()

    def save_game_stats(
        self,
        game_id: str,
        home_team_id: str,
        away_team_id: str,
        home_team: TeamInGame,
        away_team: TeamInGame,
        home_score: int,
        away_score: int,
    ):
        """Save stats for both teams in a game."""
        # Calculate team totals
        home_hits = sum(p.game_stats.batting.hits for p in home_team.players)
        away_hits = sum(p.game_stats.batting.hits for p in away_team.players)

        home_errors = sum(p.game_stats.fielding.errors for p in home_team.players)
        away_errors = sum(p.game_stats.fielding.errors for p in away_team.players)

        # Determine winners
        home_won = home_score > away_score

        # Save both teams
        self.save_stats(
            game_id,
            home_team_id,
            away_team_id,
            home_score,
            home_hits,
            home_errors,
            home_won,
        )
        self.save_stats(
            game_id,
            away_team_id,
            home_team_id,
            away_score,
            away_hits,
            away_errors,
            not home_won,
        )

    def get_team_stats(self, game_id: str, team_id: str) -> dict | None:
        """Get team stats for a specific game."""
        row = self.conn.execute(
            """
            SELECT * FROM team_game_stats
            WHERE game_id = ? AND team_id = ?
            """,
            (game_id, team_id),
        ).fetchone()

        if not row:
            return None

        return {
            "game_id": row["game_id"],
            "team_id": row["team_id"],
            "runs": row["runs"],
            "hits": row["hits"],
            "errors": row["errors"],
            "win": row["win"],
            "loss": row["loss"],
        }

    def get_season_stats(self, season_id: str, team_id: str) -> dict:
        """Get aggregated stats for a team in a season."""
        row = self.conn.execute(
            """
            SELECT 
                COUNT(*) as games_played,
                SUM(win) as wins,
                SUM(loss) as losses,
                SUM(runs) as runs_scored,
                SUM(hits) as hits,
                SUM(errors) as errors
            FROM team_game_stats tgs
            JOIN games g ON tgs.game_id = g.id
            WHERE g.season_id = ? AND tgs.team_id = ?
            """,
            (season_id, team_id),
        ).fetchone()

        return {
            "games_played": row["games_played"] or 0,
            "wins": row["wins"] or 0,
            "losses": row["losses"] or 0,
            "runs_scored": row["runs_scored"] or 0,
            "hits": row["hits"] or 0,
            "errors": row["errors"] or 0,
        }

    def clear_stats(self, game_id: str):
        """Clear team stats for a game (for replaying)."""
        self.conn.execute("DELETE FROM team_game_stats WHERE game_id = ?", (game_id,))
        self.conn.commit()

    def get_standings(self, season_id: str) -> list[dict]:
        """Get season standings."""
        rows = self.conn.execute(
            """
            SELECT 
                t.id as team_id,
                t.city || ' ' || t.mascot as team_name,
                SUM(tgs.win) as wins,
                SUM(tgs.loss) as losses,
                SUM(tgs.runs) as runs_scored,
                ROUND(CAST(SUM(tgs.win) AS FLOAT) / (SUM(tgs.win) + SUM(tgs.loss)), 3) as win_pct
            FROM teams t
            JOIN team_game_stats tgs ON t.id = tgs.team_id
            JOIN games g ON tgs.game_id = g.id
            WHERE g.season_id = ? AND g.completed = 1
            GROUP BY t.id
            ORDER BY win_pct DESC, wins DESC
            """,
            (season_id,),
        ).fetchall()

        return [
            {
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "wins": row["wins"],
                "losses": row["losses"],
                "runs_scored": row["runs_scored"],
                "win_pct": row["win_pct"],
            }
            for row in rows
        ]
