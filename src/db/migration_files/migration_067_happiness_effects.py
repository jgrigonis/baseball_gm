"""
What player happiness does (plans/player-happiness.md, phase 2): player_moods
counts weeks in a row a player has been unhappy, remembers when he asked to
be traded (while he's still on that team), and when a miserable player who
benched himself plays again.
"""

VERSION = 67


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_moods ADD COLUMN IF NOT EXISTS"
        " unhappy_weeks INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE player_moods ADD COLUMN IF NOT EXISTS trade_request_on TEXT"
    )
    conn.execute(
        "ALTER TABLE player_moods ADD COLUMN IF NOT EXISTS refusing_until TEXT"
    )
