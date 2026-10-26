# src/db/migration_files/migration_011_skill_fractions.py
"""
Fractional skill progress.

player_skills stores whole numbers, and yearly aging used to drop whatever
a player gained below one point, so slow development never showed up.
player_skill_fractions keeps the part each skill is above or below its
whole number (-0.5 to 0.5), and aging adds it back before the next year.

Existing players start at 0 for every skill.
"""

VERSION = 11

SKILLS = (
    "clutch",
    "speed",
    "durability",
    "power",
    "eye",
    "contact",
    "base_running",
    "bunting",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "stamina",
    "recovery",
    "ground_balls",
    "strikes",
)


def upgrade(conn):
    columns = ",\n".join(f"{skill} REAL NOT NULL DEFAULT 0" for skill in SKILLS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS player_skill_fractions (
            player_id TEXT PRIMARY KEY,
            {columns},
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
        """)
