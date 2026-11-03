"""
Jersey numbers (src/player/jersey_numbers.py): every player gets the list of
numbers he wants (players.jersey_prefs, made from his id the same way a new
player's is), and everyone on a team gets a number there
(team_players.jersey_number), most senior first: most seasons with the team,
then oldest. Nobody hands his number to a newcomer in the backfill.
"""

from src.db.repositories.jersey_repo import JerseyRepository
from src.player.jersey_numbers import prefs_for

VERSION = 59


def upgrade(conn):
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS jersey_prefs TEXT[]")
    conn.execute("ALTER TABLE team_players ADD COLUMN IF NOT EXISTS jersey_number TEXT")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_team_players_jersey
            ON team_players (team_id, jersey_number) WHERE jersey_number IS NOT NULL
        """
    )

    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM players WHERE jersey_prefs IS NULL"
        ).fetchall()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE players SET jersey_prefs = %s WHERE id = %s",
            [(prefs_for(pid), pid) for pid in ids],
        )

    repo = JerseyRepository(conn)
    teams = conn.execute(
        "SELECT DISTINCT team_id FROM team_players WHERE jersey_number IS NULL"
    ).fetchall()
    for t in teams:
        repo.backfill_team(t["team_id"])
