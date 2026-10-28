# src/league/offseason/roster_trimmer.py
"""
Roster Trimmer

After the draft, each team may exceed 120 minors players.
Trim minors-only until each team has at most 120.

26man and 40man players are fully protected.
Cut players become 'free_agent' and are removed from team_players.

An AI team's youth tilt (src/league/front_office.py) adds age points to each
prospect's rating before the cut: a rebuilding team keeps its youngest
prospects, an all-in team its older ones.

Roster limits:
    26man:  26
    40man:  14  (40 - 26)
    minors: 120
    total:  160
"""

import logging
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.front_office import age_points
from src.player.player_evaluator import PlayerEvaluator

log = logging.getLogger(__name__)

MINORS_LIMIT = 120


class RosterTrimmer:
    def __init__(self, conn, tilts: dict[str, float] | None = None):
        """tilts: each AI team's youth tilt, by team id."""
        self.conn = conn
        self.tilts = tilts or {}
        self.player_repo = PlayerRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)
        self.team_repo = TeamRepository(conn)

    def run(self, season_id: str) -> int:
        """
        Trim all teams to MINORS_LIMIT minors players.

        Args:
            season_id: Current season (used to get team list)

        Returns:
            Total number of players cut across all teams
        """
        team_rows = self.team_repo.get_teams_in_season(season_id)

        total_cut = 0
        for row in team_rows:
            cut = self._trim_team(row["team_id"])
            total_cut += cut

        self.conn.commit()
        log.info("Trimmed %s players across %s teams", total_cut, len(team_rows))
        return total_cut

    def _trim_team(self, team_id: str) -> int:
        """
        Trim a single team's minors to MINORS_LIMIT.
        Returns number of players cut.
        """
        # Load all minors players for this team
        rows = self.status_repo.get_by_team_and_status(team_id, "minors")

        n_minors = len(rows)
        if n_minors <= MINORS_LIMIT:
            return 0

        # Load full player records and rate them
        tilt = self.tilts.get(team_id, 0.0)
        players = []
        for row in rows:
            player = self.player_repo.look_up(row)
            if player:
                rating = PlayerEvaluator.prospect_rating(player.skills)
                rating += age_points(player.age, tilt)
                players.append((player, rating))

        # Sort worst first — these get cut
        players.sort(key=lambda x: x[1])

        n_to_cut = n_minors - MINORS_LIMIT
        cut_players = players[:n_to_cut]

        for player, _ in cut_players:
            # Release to free agency
            self.status_repo.set_status(player.id, "free_agent")
            # Remove from team
            self.team_repo.remove_player(team_id, player.id)

        return n_to_cut
