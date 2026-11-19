# src/db/migration_files/migration_145_sac_bunt_rarely.py
"""
Sacrifice Bunt Usage gets a Rarely level between Never and Situational
(Josh, 2026-11-19; src/team/manager_profile.py SAC_BUNT, BUNT_FACTOR 0.4).
Existing settings keep their values.
"""

VERSION = 145


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles DROP CONSTRAINT IF EXISTS gm_profiles_sac_bunt_check"
    )
    conn.execute(
        "ALTER TABLE gm_profiles ADD CONSTRAINT gm_profiles_sac_bunt_check"
        " CHECK (sac_bunt IN ('never', 'rarely', 'situational', 'frequent'))"
    )
