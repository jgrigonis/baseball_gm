# src/team/team_exporter.py
# this seems redundant to player_csv_exporter.py
import csv
from pathlib import Path

from src.io.player_csv_schema import PLAYER_CSV_HEADER
from src.team.team_record import TeamRecord


class TeamCSVExporter:
    @staticmethod
    def write(team: TeamRecord, path: str | Path):
        path = Path(path)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PLAYER_CSV_HEADER)
            writer.writeheader()

            for player in team.players:
                row = {
                    "Name": player.name,
                    "PS": player.position,
                    "T": player.throws[0].upper(),
                    "B": player.bats[0].upper(),
                    "CL": player.clutch,
                    "SP": player.speed,
                    "PO": player.power,
                    "EY": player.eye,
                    "CT": player.contact,
                    "BR": player.base_running,
                    "BU": player.bunting,
                    "CA": player.catching,
                    "IF": player.infield,
                    "OF": player.outfield,
                    "AR": player.arm,
                    "AC": player.accuracy,
                    "ST": player.stamina,
                    "RE": player.recovery,
                    "GB": player.ground_balls,
                    "KK": player.strikes,
                    "ID": player.id,
                }
                writer.writerow(row)
