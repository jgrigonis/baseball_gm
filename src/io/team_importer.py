# src/io/team_importer.py

import random

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_repo import TeamRepository
from src.player.talent_caps import generate_talent_caps
from src.team.roster_assigner import RosterAssigner
from src.team.team_record import TeamRecord


class TeamImporter:
    """
    Saves a freshly generated team (TeamFactory) into a league's season:
    a new team row, its players with their talent caps, the team's roster
    and each player's roster tier. Returns the team with its new id.
    """

    def __init__(self, conn, rng=None):
        self.conn = conn
        self.rng = rng or random.Random()
        self.player_repo = PlayerRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.cap_repo = TalentCapRepository(conn)

    def import_team(
        self, team: TeamRecord, *, league_id: str, season_id: str
    ) -> TeamRecord:
        try:
            self.conn.execute("BEGIN")
            team_id = self.team_repo.create(city=team.city, mascot=team.mascot)
            self.team_repo.add_to_league(league_id, season_id, team_id)

            for player in team.players:
                self.player_repo.insert(
                    id=player.id,
                    first_name=player.first_name,
                    last_name=player.last_name,
                    bats=player.bats,
                    throws=player.throws,
                    position=player.position,
                    skills=player.skills,
                    league_id=league_id,
                )
                caps = generate_talent_caps(player.skills.as_dict(), rng=self.rng)
                self.cap_repo.insert_talent_caps(player.id, caps)
                self.team_repo.add_player(team_id, player.id)

            PlayerStatusRepository(self.conn).bulk_set(
                RosterAssigner().assign(list(team.players))
            )

            self.conn.commit()
            return TeamRecord(
                id=team_id, city=team.city, mascot=team.mascot, players=team.players
            )
        except Exception:
            self.conn.rollback()
            raise
