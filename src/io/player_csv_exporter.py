# src/io/player_csv_exporter.py

import csv
from pathlib import Path

from src.io.player_csv_schema import PLAYER_CSV_HEADER, PLAYER_SKILL_COLUMNS
from src.player.skill_map import SKILL_MAP
from src.team.team_record import TeamRecord
from src.util.locations import TEAM_FILES_DIR

class PlayerCSVExporter:
    @staticmethod
    def write(team: TeamRecord, filename):
        with open(Path(TEAM_FILES_DIR) / filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(PLAYER_CSV_HEADER)

            for player in team.players:
                skills = player.skills.as_dict()

                row = [
                    player.name,
                    player.position,
                    player.throws[0].lower(),  # "right" -> "r"
                    player.bats[0].lower(),    # "right" -> "r", "switch" -> "s"
                ]

                for csv_key in PLAYER_SKILL_COLUMNS:
                    skill_key = SKILL_MAP[csv_key]
                    row.append(skills[skill_key])

                row.append(player.id)
                writer.writerow(row)
