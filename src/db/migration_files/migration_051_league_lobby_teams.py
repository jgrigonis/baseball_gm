# src/db/migration_files/migration_051_league_lobby_teams.py
"""
league_lobby_teams: the teams a league in the lobby will play with, by name
(src/api/services/lobby_teams.py). They're a draw from the team pool,
balanced by region, and a person picking a team outside it swaps it in, so
they're kept instead of worked out from the league's id each time.

Leagues already in the lobby get theirs the first time the lobby asks,
keeping the teams their GMs were dealt.
"""

VERSION = 51


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS league_lobby_teams (
            league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            city      TEXT NOT NULL,
            mascot    TEXT NOT NULL,
            PRIMARY KEY (league_id, city, mascot)
        )"""
    )
