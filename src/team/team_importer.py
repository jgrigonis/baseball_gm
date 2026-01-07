import csv
import os

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.team_repo import TeamRepository
from src.player.player import Player
from src.team.team import Team
from src.util.locations import TEAM_FILES_DIR

class TeamImporter:
    """
    Imports a team from a CSV into the League DB
    Read a team CSV
    Create Player objects
    Insert players into players table (idempotent)
    Create or lookup team record
    Associate players with the team
    Return a fully populated Team object
    """
    def __init__(self, conn):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.team_repo = TeamRepository(conn)

    def import_csv(self, path: str, city: str, mascot: str) -> Team:
        team = Team(city, mascot)

        team_id = self.team_repo.get_or_create(city, mascot)
        with open(TEAM_FILES_DIR + os.sep + path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                print(row)
                player = Player.from_row(row)

                self.player_repo.insert(
                    id=player.id,
                    first_name=player.first_name,
                    last_name=player.last_name,
                    bats=player.bats,
                    throws=player.throws,
                )

                team.players.append(player)

                self.team_repo.add_player(team_id, player.id)

        team.id = team_id
        return team
