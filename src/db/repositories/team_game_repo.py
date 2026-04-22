# src/db/repositories/team_game_repo.py
"""
Repository for team game statistics.

Handles:
- Saving team stats for a game
- Loading team stats
- Aggregating team stats by season
- Generating standings

Uses tables:
- team_game_stats
- games
- teams
"""

from src.team.team_in_game import TeamInGame


class TeamGameRepository:
    """Repository for managing team game statistics."""

    def __init__(self, conn):
        self.conn = conn

    def save_stats(
        self,
        game_id: str,
        team_id: str,
        runs: int,
        hits: int,
        errors: int,
        won: bool,
    ) -> None:
        """
        Save team stats for a game.
        Idempotent - calling multiple times updates the record.

        Args:
            game_id: Game ID
            team_id: Team ID
            runs: Runs scored
            hits: Team hits
            errors: Team errors
            won: Whether team won (True) or lost (False)
        """
        self.conn.execute(
            """
            INSERT INTO team_game_stats (
                game_id, team_id, runs, hits, errors, win, loss
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, team_id) DO UPDATE SET
                runs = EXCLUDED.runs, hits = EXCLUDED.hits,
                errors = EXCLUDED.errors, win = EXCLUDED.win, loss = EXCLUDED.loss
            """,
            (game_id, team_id, runs, hits, errors, 1 if won else 0, 0 if won else 1),
        )
        # self.conn.commit()

    def save_game_stats(
        self,
        game_id: str,
        home_team_id: str,
        away_team_id: str,
        home_team: TeamInGame,
        away_team: TeamInGame,
        home_score: int,
        away_score: int,
    ) -> None:
        """
        Save stats for both teams in a game.
        Convenience method that calculates team totals and saves both teams.

        Args:
            game_id: Game ID
            home_team_id: Home team ID
            away_team_id: Away team ID
            home_team: Home TeamInGame object (for calculating stats)
            away_team: Away TeamInGame object (for calculating stats)
            home_score: Home team runs scored
            away_score: Away team runs scored
        """
        # Calculate team totals
        home_hits = sum(p.game_stats.batting.hits for p in home_team.players)
        away_hits = sum(p.game_stats.batting.hits for p in away_team.players)

        home_errors = sum(p.game_stats.fielding.errors for p in home_team.players)
        away_errors = sum(p.game_stats.fielding.errors for p in away_team.players)

        # Determine winners
        home_won = home_score > away_score

        # Save both teams
        self.save_stats(
            game_id, home_team_id, home_score, home_hits, home_errors, home_won
        )
        self.save_stats(
            game_id, away_team_id, away_score, away_hits, away_errors, not home_won
        )

    def get_team_stats(self, game_id: str, team_id: str) -> dict | None:
        """
        Get team stats for a specific game.

        Args:
            game_id: Game ID
            team_id: Team ID

        Returns:
            Dictionary with team stats, or None if not found
        """
        row = self.conn.execute(
            """
            SELECT * FROM team_game_stats
            WHERE game_id = %s AND team_id = %s
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

    def get_game_stats(self, game_id: str) -> list[dict]:
        """
        Get stats for both teams in a game.

        Args:
            game_id: Game ID

        Returns:
            List of team stat dictionaries (typically 2 - home and away)
        """
        rows = self.conn.execute(
            """
            SELECT * FROM team_game_stats
            WHERE game_id = %s
            ORDER BY win DESC
            """,
            (game_id,),
        ).fetchall()

        return [
            {
                "game_id": row["game_id"],
                "team_id": row["team_id"],
                "runs": row["runs"],
                "hits": row["hits"],
                "errors": row["errors"],
                "win": row["win"],
                "loss": row["loss"],
            }
            for row in rows
        ]

    def get_season_stats(self, season_id: str, team_id: str) -> dict:
        """
        Get aggregated stats for a team in a season.

        Args:
            season_id: Season ID
            team_id: Team ID

        Returns:
            Dictionary with aggregated season stats
        """
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
            WHERE g.season_id = %s AND tgs.team_id = %s AND g.completed = 1
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
            "win_pct": self._calculate_win_pct(row["wins"] or 0, row["losses"] or 0),
        }

    def clear_stats(self, game_id: str) -> None:
        """
        Clear team stats for a game (for replaying games).

        Args:
            game_id: Game ID
        """
        self.conn.execute("DELETE FROM team_game_stats WHERE game_id = %s", (game_id,))

    def get_standings(self, season_id: str) -> list[dict]:
        """
        Get season standings ordered by winning percentage.

        Args:
            season_id: Season ID

        Returns:
            List of team standings dictionaries, ordered by win_pct DESC
        """
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
            WHERE g.season_id = %s AND g.completed = 1
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

    def get_team_record(self, season_id: str, team_id: str) -> tuple[int, int]:
        """
        Get team's win-loss record for a season.

        Args:
            season_id: Season ID
            team_id: Team ID

        Returns:
            Tuple of (wins, losses)
        """
        stats = self.get_season_stats(season_id, team_id)
        return (stats["wins"], stats["losses"])

    def get_runs_differential(self, season_id: str, team_id: str) -> int:
        """
        Get team's run differential for a season.

        Args:
            season_id: Season ID
            team_id: Team ID

        Returns:
            Run differential (runs scored - runs allowed)
        """
        row = self.conn.execute(
            """
            SELECT 
                SUM(CASE WHEN tgs.team_id = %s THEN tgs.runs ELSE 0 END) as runs_scored,
                SUM(CASE WHEN tgs.team_id != %s THEN tgs.runs ELSE 0 END) as runs_allowed
            FROM team_game_stats tgs
            JOIN games g ON tgs.game_id = g.id
            WHERE g.season_id = %s AND g.completed = 1 
                AND g.id IN (
                    SELECT game_id FROM team_game_stats WHERE team_id = %s
                )
            """,
            (team_id, team_id, season_id, team_id),
        ).fetchone()

        runs_scored = row["runs_scored"] or 0
        runs_allowed = row["runs_allowed"] or 0
        return runs_scored - runs_allowed

    def get_team_wl(self, team_id: str, season_id: str) -> dict | None:
        """Return {w, l} for a team in a season (regular season only), or None if no games."""
        row = self.conn.execute(
            """SELECT SUM(tgs.win) as w, SUM(tgs.loss) as l
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE tgs.team_id = %s AND g.season_id = %s AND g.series_id IS NULL""",
            (team_id, season_id),
        ).fetchone()
        if not row or (row["w"] is None and row["l"] is None):
            return None
        return {"w": row["w"] or 0, "l": row["l"] or 0}

    def get_wl_for_league(self, league_id: str, season_id: str) -> list[dict]:
        """Return W-L-RS per team for a league/season (regular season only, all teams included)."""
        rows = self.conn.execute(
            """SELECT
                 t.id as team_id, t.city, t.mascot,
                 COALESCE(SUM(tgs.win),  0) as wins,
                 COALESCE(SUM(tgs.loss), 0) as losses,
                 COALESCE(SUM(tgs.runs), 0) as runs_scored
               FROM teams t
               JOIN league_season_teams lst
                 ON lst.team_id = t.id
                 AND lst.league_id = %s
                 AND lst.season_id = %s
               LEFT JOIN (
                 SELECT tgs2.team_id, tgs2.win, tgs2.loss, tgs2.runs
                 FROM team_game_stats tgs2
                 JOIN games g2
                   ON g2.id = tgs2.game_id
                   AND g2.season_id = %s
                   AND g2.completed = 1
                   AND g2.series_id IS NULL
               ) tgs ON tgs.team_id = t.id
               GROUP BY t.id
               ORDER BY wins DESC, losses ASC""",
            (league_id, season_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_runs_allowed(self, season_id: str) -> dict[str, int]:
        """Return {team_id: runs_allowed} for all teams in a season (regular season only)."""
        rows = self.conn.execute(
            """SELECT tgs.team_id, SUM(opp.runs) as runs_allowed
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               JOIN team_game_stats opp
                 ON opp.game_id = g.id AND opp.team_id != tgs.team_id
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        return {r["team_id"]: r["runs_allowed"] or 0 for r in rows}

    def get_home_away_splits(self, season_id: str) -> dict[str, dict]:
        """Return {team_id: {hw, hl, aw, al}} for all teams in a season (regular season only)."""
        rows = self.conn.execute(
            """SELECT
                 tgs.team_id,
                 SUM(CASE WHEN g.home_team_id = tgs.team_id AND tgs.win  = 1 THEN 1 ELSE 0 END) as home_wins,
                 SUM(CASE WHEN g.home_team_id = tgs.team_id AND tgs.loss = 1 THEN 1 ELSE 0 END) as home_losses,
                 SUM(CASE WHEN g.away_team_id = tgs.team_id AND tgs.win  = 1 THEN 1 ELSE 0 END) as away_wins,
                 SUM(CASE WHEN g.away_team_id = tgs.team_id AND tgs.loss = 1 THEN 1 ELSE 0 END) as away_losses
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
                 AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        return {
            r["team_id"]: {
                "hw": r["home_wins"] or 0,
                "hl": r["home_losses"] or 0,
                "aw": r["away_wins"] or 0,
                "al": r["away_losses"] or 0,
            }
            for r in rows
        }

    def get_records_for_teams(
        self, season_id: str, team_ids: set[str]
    ) -> dict[str, str]:
        """Return {team_id: 'W-L'} for a set of teams in a season (regular season only)."""
        if not team_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(team_ids))
        rows = self.conn.execute(
            f"""SELECT tgs.team_id,
                       COALESCE(SUM(tgs.win),  0) as wins,
                       COALESCE(SUM(tgs.loss), 0) as losses
                FROM team_game_stats tgs
                JOIN games g ON g.id = tgs.game_id
                  AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
                WHERE tgs.team_id IN ({placeholders})
                GROUP BY tgs.team_id""",
            (season_id, *team_ids),
        ).fetchall()
        return {r["team_id"]: f"{r['wins']}-{r['losses']}" for r in rows}

    @staticmethod
    def _calculate_win_pct(wins: int, losses: int) -> float:
        """
        Calculate winning percentage.

        Args:
            wins: Number of wins
            losses: Number of losses

        Returns:
            Winning percentage (0.0 to 1.0), or 0.0 if no games played
        """
        total_games = wins + losses
        if total_games == 0:
            return 0.0
        return round(wins / total_games, 3)
