# src/db/migration_files/migration_073_undrafted_free_agents.py
"""
Undrafted prospects become free agents when the draft ends (PR #514,
PlayerRepository.release_undrafted). Leagues whose draft finished before
that shipped still hold last draft's leftovers as prospects, so they never
show on the Free Agents tab. Make them free agents now.

A league in its draft (or still in its lobby) is left alone: its prospects
are the pool being drafted from.
"""

VERSION = 73


def upgrade(conn):
    conn.execute(
        """
        UPDATE player_status ps SET status = 'free_agent'
        FROM players p
        JOIN leagues l ON l.id = p.league_id
        WHERE p.id = ps.player_id
          AND ps.status = 'prospect'
          AND l.state NOT IN ('lobby', 'draft')
          AND NOT EXISTS (SELECT 1 FROM team_players tp WHERE tp.player_id = p.id)
        """
    )
