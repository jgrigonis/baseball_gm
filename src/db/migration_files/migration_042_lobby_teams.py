# src/db/migration_files/migration_042_lobby_teams.py
"""
Teams in the lobby: every GM waiting in a league's lobby, person or AI, is
dealt one of the manifest's teams when they join or are picked, so the lobby
can show who will run which team. The team rows themselves are only made
when the league starts, so the pick is kept by name until then, and the
start hands each GM the team of that name.

- gms.lobby_city, gms.lobby_mascot: the team a GM in the lobby will run.
  Unused once the GM has a team_id.
"""

VERSION = 42


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS lobby_city TEXT")
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS lobby_mascot TEXT")
