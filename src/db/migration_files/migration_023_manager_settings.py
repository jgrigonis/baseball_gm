"""
Manager settings the game engine reads (src/team/manager_profile.py).

baserunning replaces steal_aggression with five steps; existing choices map
conservative / standard / aggressive to the 2nd, 3rd and 4th. Adds the
rotation settings and rest days. steal_aggression stays, unread.
"""

VERSION = 23


def upgrade(conn):
    conn.execute(
        """
        ALTER TABLE gm_profiles
            ADD COLUMN IF NOT EXISTS baserunning TEXT NOT NULL DEFAULT 'standard'
                CHECK (baserunning IN ('very-conservative', 'conservative', 'standard',
                                       'aggressive', 'very-aggressive')),
            ADD COLUMN IF NOT EXISTS rest_days TEXT NOT NULL DEFAULT 'standard'
                CHECK (rest_days IN ('iron-man', 'standard', 'rest-often')),
            ADD COLUMN IF NOT EXISTS rotation_size INTEGER NOT NULL DEFAULT 5
                CHECK (rotation_size IN (4, 5, 6)),
            ADD COLUMN IF NOT EXISTS skip_fifth_starter BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS playoff_rotation TEXT NOT NULL DEFAULT 'same'
                CHECK (playoff_rotation IN ('3', '4', 'same')),
            ADD COLUMN IF NOT EXISTS tired_starters TEXT NOT NULL DEFAULT 'standard'
                CHECK (tired_starters IN ('push', 'standard', 'protect'))
        """
    )
    conn.execute(
        "UPDATE gm_profiles SET baserunning = steal_aggression"
        " WHERE steal_aggression IN ('conservative', 'aggressive')"
    )
