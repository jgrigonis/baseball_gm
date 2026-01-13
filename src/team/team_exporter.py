# src/team/team_exporter.py

import csv
from pathlib import Path
from src.team.team_record import TeamRecord


class TeamCSVExporter:
    @staticmethod
    def write(team: TeamRecord, path: str | Path):
        path = Path(path)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "first_name",
                    "last_name",
                    "bats",
                    "throws",
                    "position",
                    # skill fields expanded below
                ]
                + list(team.players[0].skills.keys())
            )
            writer.writeheader()

            for player in team.players:
                row = {
                    "id": player.id,
                    "first_name": player.first_name,
                    "last_name": player.last_name,
                    "bats": player.bats,
                    "throws": player.throws,
                    "position": player.position,
                }
                row.update(player.skills.as_dict())
                writer.writerow(row)
