# src/team/team_exporter.py
# this seems redundant to player_csv_exporter.py
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
                    "Name",
                    "PS",
                    "T",
                    "B",
                    "CL",
                    "SP",
                    "PO",
                    "EY",
                    "CT",
                    "BR",
                    "BU",
                    "CA",
                    "IF",
                    "OF",
                    "AR",
                    "AC",
                    "ST",
                    "RE",
                    "GB",
                    "KK",
                    "ID",
                ],
            )
            writer.writeheader()

            for player in team.players:
                row = {
                    "Name": player.name,
                    "PS": player.position,
                    "T": player.throws[0].lower(),
                    "B": player.bats[0].lower(),
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
