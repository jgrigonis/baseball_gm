# src/db/repositories/standings_repo.py
from itertools import groupby


class StandingsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_records(self, league_id: str, season_id: str) -> list[dict]:
        """W-L-RS for every team in the league, regular season only. 0-0 teams included."""
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
               GROUP BY t.id, t.city, t.mascot
               ORDER BY wins DESC, losses ASC""",
            (league_id, season_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_runs_allowed(self, season_id: str) -> dict[str, int]:
        """Return {team_id: runs_allowed} for all teams (regular season only)."""
        rows = self.conn.execute(
            """SELECT tgs.team_id, SUM(opp.runs) as runs_allowed
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
                 AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               JOIN team_game_stats opp
                 ON opp.game_id = g.id AND opp.team_id != tgs.team_id
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        return {r["team_id"]: r["runs_allowed"] or 0 for r in rows}

    def get_home_away_splits(self, season_id: str) -> dict[str, dict]:
        """Return {team_id: {hw, hl, aw, al}} for all teams (regular season only)."""
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

    def get_recent_results(self, season_id: str) -> list[dict]:
        """All completed game results newest-first, for streak/L10 calculations."""
        rows = self.conn.execute(
            """SELECT tgs.team_id, tgs.win, g.game_date
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.completed = 1
               ORDER BY g.game_date DESC""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def head_to_head_wins(self, season_id: str, team_ids: list[str]) -> dict[str, int]:
        """Return {team_id: h2h_wins} among the given teams for tiebreaking."""
        placeholders = ", ".join(["%s"] * len(team_ids))
        rows = self.conn.execute(
            f"""SELECT winner_id, COUNT(*) as wins
                FROM games
                WHERE season_id = %s
                  AND completed = 1
                  AND home_team_id IN ({placeholders})
                  AND away_team_id IN ({placeholders})
                  AND winner_id IS NOT NULL
                GROUP BY winner_id""",
            [season_id] + team_ids + team_ids,
        ).fetchall()
        result = {tid: 0 for tid in team_ids}
        for row in rows:
            if row["winner_id"] in result:
                result[row["winner_id"]] = row["wins"]
        return result

    def sort(self, season_id: str, rows: list[dict]) -> list[dict]:
        """Sort standings rows by win_pct, breaking ties with H2H wins then runs scored."""
        sorted_rows = sorted(rows, key=lambda r: -(r.get("win_pct") or 0))
        result = []
        for _, group in groupby(sorted_rows, key=lambda r: r.get("win_pct") or 0):
            group = list(group)
            if len(group) == 1:
                result.extend(group)
                continue
            tied_ids = [r["team_id"] for r in group]
            h2h = self.head_to_head_wins(season_id, tied_ids)
            group.sort(key=lambda r: (-h2h.get(r["team_id"], 0), -(r.get("runs_scored") or 0)))
            result.extend(group)
        return result

    def get_top_n(self, season_id: str, n: int = 8) -> list[dict]:
        """Return top N teams by win% (with H2H tiebreakers) for playoff seeding."""
        rows = self.conn.execute(
            """SELECT
                 t.id AS team_id,
                 t.city || ' ' || t.mascot AS team_name,
                 SUM(tgs.win)  AS wins,
                 SUM(tgs.loss) AS losses,
                 SUM(tgs.runs) AS runs_scored,
                 CAST(SUM(tgs.win) AS REAL) / (SUM(tgs.win) + SUM(tgs.loss)) AS win_pct
               FROM teams t
               JOIN team_game_stats tgs ON t.id = tgs.team_id
               JOIN games g ON tgs.game_id = g.id
               WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               GROUP BY t.id""",
            (season_id,),
        ).fetchall()

        if len(rows) < n:
            raise ValueError(f"Need at least {n} teams with completed games; found {len(rows)}")

        sorted_rows = self.sort(season_id, [dict(r) for r in rows])
        return sorted_rows[:n]
