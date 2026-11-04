"""
Starter Leash and Bullpen Shape get new choices (src/team/manager_profile.py).

starter_usage becomes three pitch targets: let-them-work -> long,
pitch-count-strict -> standard, matchup-based -> quick-hook. bullpen_pref
gains a middle step: deep-pen used to be the baseline, so it becomes
balanced, and deep-pen now goes to the pen sooner.
"""

VERSION = 68


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles"
        " DROP CONSTRAINT IF EXISTS gm_profiles_starter_usage_check,"
        " DROP CONSTRAINT IF EXISTS gm_profiles_bullpen_pref_check"
    )
    conn.execute(
        """
        UPDATE gm_profiles SET starter_usage = CASE starter_usage
            WHEN 'let-them-work' THEN 'long'
            WHEN 'matchup-based' THEN 'quick-hook'
            WHEN 'pitch-count-strict' THEN 'standard'
            ELSE starter_usage END
        """
    )
    conn.execute(
        "UPDATE gm_profiles SET bullpen_pref = 'balanced' WHERE bullpen_pref = 'deep-pen'"
    )
    conn.execute(
        """
        ALTER TABLE gm_profiles
            ALTER COLUMN starter_usage SET DEFAULT 'standard',
            ALTER COLUMN bullpen_pref SET DEFAULT 'balanced',
            ADD CONSTRAINT gm_profiles_starter_usage_check
                CHECK (starter_usage IN ('long', 'standard', 'quick-hook')),
            ADD CONSTRAINT gm_profiles_bullpen_pref_check
                CHECK (bullpen_pref IN ('starter-heavy', 'balanced', 'deep-pen'))
        """
    )
