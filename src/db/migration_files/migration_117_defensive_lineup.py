"""
Defensive lineup style (Josh, 2026-11-11): a fifth Lineup Construction
style that weighs gloves more, most of all at C, 2B, SS and CF
(src/team/lineup_optimizer.py STYLE_DEFENSE). gm_profiles.lineup_style's
check lets it in.
"""

VERSION = 117


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles DROP CONSTRAINT IF EXISTS gm_profiles_lineup_style_check"
    )
    conn.execute(
        "ALTER TABLE gm_profiles ADD CONSTRAINT gm_profiles_lineup_style_check"
        " CHECK (lineup_style IN ('traditional', 'analytics', 'speed-first',"
        " 'power-first', 'defensive'))"
    )
