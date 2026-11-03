"""
Only the 40-man roster wears jersey numbers. Databases that ran migration 59
before that rule gave numbers to minor leaguers and prospects too: take
those back, then number any 40-man player still without one.
"""

from src.db.repositories.jersey_repo import JerseyRepository
from src.player.jersey_numbers import NUMBERED_STATUSES

VERSION = 60


def upgrade(conn):
    statuses = list(NUMBERED_STATUSES)
    conn.execute(
        """
        UPDATE team_players tp SET jersey_number = NULL
        WHERE tp.jersey_number IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM player_status ps
              WHERE ps.player_id = tp.player_id AND ps.status = ANY(%s)
          )
        """,
        (statuses,),
    )
    repo = JerseyRepository(conn)
    teams = conn.execute(
        """
        SELECT DISTINCT tp.team_id FROM team_players tp
        JOIN player_status ps ON ps.player_id = tp.player_id
        WHERE tp.jersey_number IS NULL AND ps.status = ANY(%s)
        """,
        (statuses,),
    ).fetchall()
    for t in teams:
        repo.backfill_team(t["team_id"])
