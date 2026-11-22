# src/db/migration_files/migration_152_custom_leagues.py
"""
Custom leagues (Josh, 2026-11-22): custom teams play in multiplayer leagues,
but only in a league the commissioner made a custom league when creating
it, and only paid contributors can join one (services/league_custom_teams.py).

- leagues.single_player becomes leagues.custom_league. Every league that had
  a custom team is a custom league.
- league_custom_teams.user_id: who put the custom team in. A paid person puts
  one on their own team; the commissioner also on AI teams.
"""

VERSION = 152


def _has(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            """SELECT 1 FROM information_schema.columns
               WHERE table_name = %s AND column_name = %s""",
            (table, column),
        ).fetchone()
    )


def upgrade(conn):
    old = _has(conn, "leagues", "single_player")
    new = _has(conn, "leagues", "custom_league")
    if old and not new:
        conn.execute("ALTER TABLE leagues RENAME COLUMN single_player TO custom_league")
    elif old:
        conn.execute("UPDATE leagues SET custom_league = TRUE WHERE single_player")
        conn.execute("ALTER TABLE leagues DROP COLUMN single_player")
    elif not new:
        conn.execute(
            "ALTER TABLE leagues ADD COLUMN custom_league BOOLEAN NOT NULL DEFAULT FALSE"
        )
    conn.execute(
        "ALTER TABLE league_custom_teams ADD COLUMN IF NOT EXISTS user_id TEXT"
    )
    # Custom teams already in went in by the commissioner.
    conn.execute(
        """UPDATE league_custom_teams c SET user_id = g.user_id
           FROM leagues l JOIN gms g ON g.id = l.commissioner_gm_id
           WHERE l.id = c.league_id AND c.user_id IS NULL"""
    )
