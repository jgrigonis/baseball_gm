# src/db/migration_files/migration_149_starter_leash_tens.py
"""
Starter Leash on round 10s, centered on the default (Josh, 2026-11-20):
70/80/90/100/110 with 90 the default, was 75/85/95/105/115 with 85.
Starters were pulled at a hard pitch count wall, so quality starts ran
about 10 points short of MLB; a starter who's dealing now also goes a few
pitches past his leash and one getting hit comes out early
(src/team/manager_profile.py DEALING_EXTRA, SHELLED_PULL).

Every setting, team and per-pitcher, moves one step longer so it keeps its
place around the new default: 75 -> 80, 85 -> 90, 95 -> 100, 105 and 115
-> 110. The new shortest step, 70, starts empty.
"""

VERSION = 149

STEPS = "('70', '80', '90', '100', '110')"
MOVE = """CASE {col} WHEN '75' THEN '80' WHEN '85' THEN '90' WHEN '95' THEN '100'
          WHEN '105' THEN '110' WHEN '115' THEN '110' ELSE {col} END"""


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles DROP CONSTRAINT IF EXISTS gm_profiles_starter_usage_check"
    )
    conn.execute(
        f"UPDATE gm_profiles SET starter_usage = {MOVE.format(col='starter_usage')}"
    )
    conn.execute("ALTER TABLE gm_profiles ALTER COLUMN starter_usage SET DEFAULT '90'")
    conn.execute(
        "ALTER TABLE gm_profiles ADD CONSTRAINT gm_profiles_starter_usage_check"
        f" CHECK (starter_usage IN {STEPS})"
    )
    conn.execute(
        "ALTER TABLE pitcher_leashes DROP CONSTRAINT IF EXISTS pitcher_leashes_pitches_check"
    )
    conn.execute(f"UPDATE pitcher_leashes SET pitches = {MOVE.format(col='pitches')}")
    conn.execute(
        "ALTER TABLE pitcher_leashes ADD CONSTRAINT pitcher_leashes_pitches_check"
        f" CHECK (pitches IN {STEPS})"
    )
