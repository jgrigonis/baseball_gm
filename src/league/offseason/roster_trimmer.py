# src/league/offseason/roster_trimmer.py
"""
Roster Trimmer

After the draft, each team may exceed 120 minors players.
Trim minors-only until each team has at most 120.

26man and 40man players are fully protected.
Cut players become 'free_agent' and are removed from team_players.

Roster limits:
    26man:  26
    40man:  14  (40 - 26)
    minors: 120
    total:  160
"""

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player.player_evaluator import PlayerEvaluator

MINORS_LIMIT = 120


class RosterTrimmer:
    def __init__(self, conn):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)

    def run(self, season_id: str) -> int:
        """
        Trim all teams to MINORS_LIMIT minors players.

        Args:
            season_id: Current season (used to get team list)

        Returns:
            Total number of players cut across all teams
        """
        team_rows = self.conn.execute(
            """
            SELECT DISTINCT team_id FROM league_season_teams
            WHERE season_id = %s
            """,
            (season_id,),
        ).fetchall()

        total_cut = 0
        for row in team_rows:
            cut = self._trim_team(row["team_id"])
            total_cut += cut

        self.conn.commit()
        print(f"  Trimmed {total_cut} players across {len(team_rows)} teams")
        return total_cut

    def _trim_team(self, team_id: str) -> int:
        """
        Trim a single team's minors to MINORS_LIMIT.
        Returns number of players cut.
        """
        # Load all minors players for this team
        rows = self.conn.execute(
            """
            SELECT p.id
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            JOIN player_status ps ON p.id = ps.player_id
            WHERE tp.team_id = %s
              AND ps.status = 'minors'
            """,
            (team_id,),
        ).fetchall()

        n_minors = len(rows)
        if n_minors <= MINORS_LIMIT:
            return 0

        # Load full player records and rate them
        players = []
        for row in rows:
            player = self.player_repo.look_up(row["id"])
            if player:
                rating = PlayerEvaluator.prospect_rating(player.skills)
                players.append((player, rating))

        # Sort worst first — these get cut
        players.sort(key=lambda x: x[1])

        n_to_cut = n_minors - MINORS_LIMIT
        cut_players = players[:n_to_cut]

        for player, _ in cut_players:
            # Release to free agency
            self.status_repo.set_status(player.id, "free_agent")
            # Remove from team
            self.conn.execute(
                "DELETE FROM team_players WHERE team_id = %s AND player_id = %s",
                (team_id, player.id),
            )

        return n_to_cut
