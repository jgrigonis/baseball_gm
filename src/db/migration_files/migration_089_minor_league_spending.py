# src/db/migration_files/migration_089_minor_league_spending.py
"""
Minor leaguers count against total spending (Josh, 2026-11-06): each one
never on the 40-man costs a flat minor league wage a season
(src/league/budget.py MINOR_LEAGUE_PAY), not payroll. team_budgets gets a
minor_league column for what a season's farm cost, set when it ends.

Owners' budgets now include the league's average farm, so seasons not yet
taxed get it added, the same way migration 083 added a Standard front office.
"""

VERSION = 89

PAY = 100_000
ROUNDING = 10_000
GROWTH = 0.05


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS minor_league BIGINT"
    )
    seasons = conn.execute(
        """SELECT b.league_id, b.year,
                  (SELECT MIN(f.year) FROM team_budgets f
                   WHERE f.league_id = b.league_id AND f.cap IS NOT NULL) AS first
           FROM team_budgets b
           WHERE b.luxury_tax IS NULL AND b.cap IS NOT NULL
           GROUP BY b.league_id, b.year"""
    ).fetchall()
    for s in seasons:
        teams = [
            r["team_id"]
            for r in conn.execute(
                "SELECT team_id FROM team_budgets WHERE league_id = %s AND year = %s",
                (s["league_id"], s["year"]),
            ).fetchall()
        ]
        if not teams:
            continue
        row = conn.execute(
            """SELECT COUNT(*) AS n
               FROM team_players tp
               JOIN player_status ps ON ps.player_id = tp.player_id
               WHERE tp.team_id = ANY(%s) AND ps.status = 'minors'
                 AND NOT EXISTS (
                     SELECT 1 FROM player_contracts c
                     WHERE c.player_id = tp.player_id AND c.guaranteed
                       AND c.start_year <= %s AND c.start_year + c.years > %s
                       AND (c.released_year IS NULL OR c.released_year > %s))""",
            (teams, s["year"], s["year"], s["year"]),
        ).fetchone()
        scale = (1 + GROWTH) ** max(0, s["year"] - (s["first"] or s["year"]))
        farm = round(int(row["n"]) / len(teams) * PAY * scale / ROUNDING) * ROUNDING
        if farm:
            conn.execute(
                """UPDATE team_budgets SET budget = budget + %s
                   WHERE league_id = %s AND year = %s AND luxury_tax IS NULL""",
                (farm, s["league_id"], s["year"]),
            )
