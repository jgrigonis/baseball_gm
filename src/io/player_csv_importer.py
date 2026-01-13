# src/io/player_csv_importer.py

import csv
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.skill_map import SKILL_MAP
from src.io.player_csv_schema import PLAYER_SKILL_COLUMNS

CSV_TO_THROWS = {
    "r": "right",
    "l": "left",
}

CSV_TO_BATS = {
    "r": "right",
    "l": "left",
    "s": "switch",
}


class PlayerCSVImporter:
    @staticmethod
    def read(path: str) -> list[PlayerRecord]:
        players = []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                first, last = row["Name"].split(" ", 1)

                skills = {
                    SKILL_MAP[csv_key]: int(row[csv_key])
                    for csv_key in PLAYER_SKILL_COLUMNS
                }

                players.append(
                    PlayerRecord(
                        id=row["ID"],
                        first_name=first,
                        last_name=last,
                        position=row["PS"],
                        throws = CSV_TO_THROWS[row["T"].lower()],
                        bats = CSV_TO_BATS[row["B"].lower()],

                        # bats={"r": "right", "l": "left", "s": "switch"}[row["B"]],
                        skills=PlayerSkills(skills),
                    )
                )

        return players
