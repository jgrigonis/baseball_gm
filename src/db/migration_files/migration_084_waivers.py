"""
Waivers and the salary offset (free agency phase 2, Josh's decisions
2026-11-05; src/api/services/waivers.py).

- waivers: a released 40-man player sits on waivers for two sim periods.
  Any team can claim him; the worst record among the claimers gets him and
  takes over his whole deal. Unclaimed, he's a free agent.
- waiver_claims: who claimed him.
- player_contracts.offset_salary / offset_through: a released player who
  signs elsewhere takes his new salary off what his old team still owes,
  through the last season of the new deal.
"""

VERSION = 84


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS waivers (
            id            SERIAL PRIMARY KEY,
            league_id     TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            player_id     TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            from_team_id  TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            placed_on     TEXT NOT NULL,
            clears_on     TEXT,
            status        TEXT NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'claimed', 'cleared')),
            claimed_by    TEXT REFERENCES teams(id) ON DELETE SET NULL,
            created_at    TEXT NOT NULL DEFAULT (NOW())
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waivers_league ON waivers(league_id, status)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_waivers_player ON waivers(player_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waivers_from_team ON waivers(from_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waivers_claimed_by ON waivers(claimed_by)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS waiver_claims (
            waiver_id   INTEGER NOT NULL REFERENCES waivers(id) ON DELETE CASCADE,
            team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            created_at  TEXT NOT NULL DEFAULT (NOW()),
            PRIMARY KEY (waiver_id, team_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waiver_claims_team ON waiver_claims(team_id)"
    )
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS"
        " offset_salary INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS offset_through INTEGER"
    )
