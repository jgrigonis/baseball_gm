# src/db/repositories/hr_derby_repo.py
#
# The Home Run Derby (src/league/hr_derby.py): every hitter's line in every
# matchup of a season's derby.

from __future__ import annotations


class HRDerbyRepository:
    def __init__(self, conn):
        self.conn = conn

    def played(self, season_id: str | None) -> bool:
        if not season_id:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM hr_derby_results WHERE season_id = %s LIMIT 1",
            (season_id,),
        ).fetchone()
        return row is not None

    def save(self, season_id: str, lines: list[dict]) -> None:
        for r in lines:
            self.conn.execute(
                """INSERT INTO hr_derby_results
                       (season_id, round, match, player_id, team_id, seed,
                        homers, swingoff, longest, won)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    season_id,
                    r["round"],
                    r["match"],
                    r["player_id"],
                    r.get("team_id"),
                    r["seed"],
                    r["homers"],
                    r["swingoff"],
                    r["longest"],
                    r["won"],
                ),
            )

    def results(self, season_id: str) -> list[dict]:
        """Every line of the season's derby, with names and teams, by round,
        match and seed."""
        rows = self.conn.execute(
            """SELECT d.*, p.first_name || ' ' || p.last_name AS name,
                      t.city, t.mascot
               FROM hr_derby_results d
               JOIN players p ON p.id = d.player_id
               LEFT JOIN teams t ON t.id = d.team_id
               WHERE d.season_id = %s
               ORDER BY d.round, d.match, d.seed""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def career(self, player_id: str) -> list[dict]:
        """A player's derbies, oldest first: the year, how far he got
        (rounds), his home runs in all, his longest and whether he won it."""
        rows = self.conn.execute(
            """SELECT y.year, d.season_id, MAX(d.round) AS rounds,
                      SUM(d.homers + COALESCE(d.swingoff, 0)) AS homers,
                      MAX(d.longest) AS longest,
                      BOOL_OR(d.won AND d.round = (
                          SELECT MAX(round) FROM hr_derby_results x
                          WHERE x.season_id = d.season_id)) AS champion,
                      (SELECT MAX(round) FROM hr_derby_results x
                       WHERE x.season_id = d.season_id) AS last_round,
                      (SELECT COUNT(*) FROM hr_derby_results x
                       WHERE x.season_id = d.season_id AND x.round = 1) AS field
               FROM hr_derby_results d
               JOIN seasons y ON y.id = d.season_id
               WHERE d.player_id = %s
               GROUP BY y.year, d.season_id
               ORDER BY y.year""",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]
