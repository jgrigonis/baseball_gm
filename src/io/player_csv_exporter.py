# src/io/player_csv_exporter.py
# Consider renaming this to team_csv_exporter.py

import csv
from pathlib import Path

from src.io.player_csv_schema import PLAYER_CSV_HEADER, PLAYER_SKILL_COLUMNS
from src.player.skill_map import SKILL_MAP
from src.team.team_record import TeamRecord
from src.util.locations import TEAM_FILES_DIR


class PlayerCSVExporter:
    @staticmethod
    def write(
        team: TeamRecord,
        year,
        filename,
        force_overwrite=False,
        league_id: str | None = None,
    ):
        """
        Write team players to CSV file.

        Args:
            team: TeamRecord to export
            filename: Name of file to write
            force_overwrite: If True, skip confirmation dialog
            league_id: If provided, scope output to a league-specific subdirectory
                       so multiple leagues don't overwrite each other's CSVs.

        Returns:
            bool: True if file was written, False if user cancelled
        """
        base = Path(TEAM_FILES_DIR) / league_id if league_id else Path(TEAM_FILES_DIR)
        out_dir = base / str(year)
        filepath = out_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists and prompt user
        if filepath.exists() and not force_overwrite:
            response = input(
                f"File '{filename}' already exists. Overwrite? (y/n): "
            ).lower()
            if response not in ("y", "yes"):
                print("Export cancelled.")
                return False

        # Write the file
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(PLAYER_CSV_HEADER)

            for player in team.players:
                skills = player.skills.as_dict()

                row = [
                    player.name,
                    player.age,
                    player.position,
                    player.throws[0].upper(),  # "right" -> "R"
                    player.bats[0].upper(),  # "right" -> "R", "switch" -> "S"
                ]

                for csv_key in PLAYER_SKILL_COLUMNS:
                    skill_key = SKILL_MAP[csv_key]
                    row.append(skills[skill_key])

                row.append(player.id)
                writer.writerow(row)

        print(f"Successfully wrote {len(team.players)} players to {filename}")
        return True
