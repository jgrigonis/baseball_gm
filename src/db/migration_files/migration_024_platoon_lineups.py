"""
Platoon lineups: a person can save one lineup for games against right-handed
starters and one against left-handers. Existing lineups become the vs RHP
lineup, which is also used against lefties until a vs LHP one is saved.
"""

VERSION = 24


def upgrade(conn):
    conn.execute(
        """
        ALTER TABLE gm_lineup_preferences
            ADD COLUMN IF NOT EXISTS vs_hand TEXT NOT NULL DEFAULT 'R'
                CHECK (vs_hand IN ('R', 'L'))
        """
    )
    conn.execute(
        """
        ALTER TABLE gm_lineup_preferences
            DROP CONSTRAINT IF EXISTS gm_lineup_preferences_pkey,
            ADD PRIMARY KEY (gm_id, vs_hand, player_id)
        """
    )
