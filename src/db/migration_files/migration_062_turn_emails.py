"""
Turn emails (src/api/services/turn_alerts.py): users.turn_emails, whether a
player wants an email when a league is waiting on them; gms.seen_at, the last
time the GM had the league open; gms.alerted_at, the last turn email they got
for it.
"""

VERSION = 62


def upgrade(conn):
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS"
        " turn_emails BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS seen_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS alerted_at TIMESTAMPTZ")
