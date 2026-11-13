# src/db/migration_files/migration_129_starter_leash_pitches.py
"""
Starter Leash in pitches (Josh, 2026-11-13): five steps, 75 to 115, with
95 the default (src/team/manager_profile.py STARTER_USAGE). Old settings
keep their place around the default: quick hook 85, standard 95, long 105.
"""

VERSION = 129


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles DROP CONSTRAINT IF EXISTS gm_profiles_starter_usage_check"
    )
    conn.execute(
        """UPDATE gm_profiles SET starter_usage = CASE starter_usage
               WHEN 'quick-hook' THEN '85' WHEN 'long' THEN '105' ELSE '95' END
           WHERE starter_usage NOT IN ('75', '85', '95', '105', '115')"""
    )
    conn.execute("ALTER TABLE gm_profiles ALTER COLUMN starter_usage SET DEFAULT '95'")
    conn.execute(
        "ALTER TABLE gm_profiles ADD CONSTRAINT gm_profiles_starter_usage_check"
        " CHECK (starter_usage IN ('75', '85', '95', '105', '115'))"
    )
