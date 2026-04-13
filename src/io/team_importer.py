# src/team/team_importer.py

import csv
import hashlib
from pathlib import Path
import random

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_repo import TeamRepository
from src.player.player_record import PlayerRecord
from src.player.talent_caps import generate_talent_caps
from src.team.roster_assigner import RosterAssigner
from src.team.team_record import TeamRecord
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

    def __init__(self, conn, rng=None):
        self.conn = conn
        self.rng = rng or random.Random()
        self.player_repo = PlayerRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.cap_repo = TalentCapRepository(conn)

    def import_csv(
        self,
        league_id: str,
        season_id: str,
        path: str,
        city: str,
        mascot: str,
        *,
        allow_existing=False,
        allow_roster_update=False,
        force_new=False,
    ) -> TeamRecord:
        full_path = Path(TEAM_FILES_DIR) / path
        if not full_path.exists():
            raise FileNotFoundError(full_path)
        csv_hash = self.hash_file(full_path)

        try:
            self.conn.execute("BEGIN")
            team_id = self.team_repo.find_by_city_mascot(city, mascot)
            team_record = self.team_repo.get(team_id)

            # --------------------------------------------------
            # Case 1: Team already exists
            # --------------------------------------------------
            if team_record and not force_new:
                team_id = team_record.id  # Access attribute, not dict key

                if not allow_existing:
                    raise RuntimeError(f"Team {city} {mascot} already exists")

                if not allow_roster_update:
                    if team_record.source_hash != csv_hash:  # Access attribute
                        raise RuntimeError(
                            f"CSV mismatch for team {city} {mascot} — "
                            f"refusing to import different roster"
                        )

                if self.team_repo.is_in_league(team_id, league_id, season_id):
                    raise RuntimeError(
                        f"Team {city} {mascot} already in league for this season"
                    )

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
            # Attach team to league for this season
            # --------------------------------------------------
            self.team_repo.add_to_league(league_id, season_id, team_id)

            # --------------------------------------------------
            # Import players
            # --------------------------------------------------
            players = []

            with open(full_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    player = PlayerRecord.from_csv_row(row)

                    if allow_roster_update and self.player_repo.exists(player.id):
                        self.player_repo.update_skills(player.id, player.skills)
                    else:
                        self.player_repo.insert(
                            id=player.id,
                            first_name=player.first_name,
                            last_name=player.last_name,
                            bats=player.bats,
                            throws=player.throws,
                            position=player.position,
                            skills=player.skills,
                        )
                        caps = generate_talent_caps(
                            player.skills.as_dict(), rng=self.rng
                        )
                        self.cap_repo.insert_talent_caps(player.id, caps)

                    self.team_repo.add_player(team_id, player.id)
                    players.append(player)

            # Assign roster tiers
            assignments = RosterAssigner().assign(players)
            PlayerStatusRepository(self.conn).bulk_set(assignments)

            self.conn.commit()
            # Build and return TeamRecord with all data
            return TeamRecord(
                id=team_id,
                city=city,
                mascot=mascot,
                players=tuple(players),
                source_csv=path,
                source_hash=csv_hash,
            )

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
