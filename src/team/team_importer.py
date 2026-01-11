# This code is all borken

import csv
import hashlib
from pathlib import Path

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.team_repo import TeamRepository
from src.player.player_factory import PlayerFactory
from src.team.team_factory import TeamFactory
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

    def import_csv(
        self, league_id: str, path: str, city: str, mascot: str, *, allow_existing=False
    ) -> Team:
        full_path = Path(TEAM_FILES_DIR) / path
        if not full_path.exists():
            raise FileNotFoundError(full_path)
        csv_hash = self.hash_file(full_path)
        try:
            self.conn.execute("BEGIN")
            team_row = self.team_repo.find_by_city_mascot(city, mascot)
            # --------------------------------------------------
            # Case 1: Team already exists
            # --------------------------------------------------
            if team_row:
                team_id = team_row["id"]

                if not allow_existing:
                    raise RuntimeError(f"Team {city} {mascot} already exists")

                if team_row["source_hash"] != csv_hash:
                    raise RuntimeError(
                        f"CSV mismatch for team {city} {mascot} — "
                        f"refusing to import different roster"
                    )

                if self.team_repo.is_in_league(team_id, league_id):
                    raise RuntimeError(f"Team {city} {mascot} already in league")
            # --------------------------------------------------
            # Case 2: Create new team
            # --------------------------------------------------
            else:
                team_id = self.team_repo.create(
                    city=city,
                    mascot=mascot,
                    source_csv=path,
                    source_hash=csv_hash,
                )
            # --------------------------------------------------
            # Attach team to league
            # --------------------------------------------------
            self.team_repo.add_to_league(league_id, team_id)

            # --------------------------------------------------
            # Import players
            # --------------------------------------------------
            team = TeamFactory()
            team.id = team_id

            with open(full_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    player = Player.from_row(row)

                    self.player_repo.insert(
                        id=player.id,
                        first_name=player.first_name,
                        last_name=player.last_name,
                        bats=player.bats,
                        throws=player.throws,
                    )

                    self.team_repo.add_player(team_id, player.id)
                    team.players.append(player)
            self.conn.commit()
            return team
        except Exception:
            self.conn.rollback()
            raise

    @staticmethod
    def hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

        # team_id = self.team_repo.get_or_create(city, mascot)
        # team = Team(city, mascot, team_id)
        # with open(full_path, newline="", encoding="utf-8") as csvfile:
        #     reader = csv.DictReader(csvfile)
        #     for row in reader:
        #         player = Player.from_row(row)
        #         self.player_repo.insert(
        #             id=player.id,
        #             first_name=player.first_name,
        #             last_name=player.last_name,
        #             bats=player.bats,
        #             throws=player.throws,
        #         )

        #         team.players.append(player)

        #         self.team_repo.add_player(team_id, player.id)

        # return team
