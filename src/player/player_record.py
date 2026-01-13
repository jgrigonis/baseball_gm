# src/player/player_record.py
"""
Database identity & History for a player.

PlayerFactory  →  PlayerRecord  →  PlayerInGame
        │               │               │
        │        persistent data   volatile state
        └──── RNG & rules

PlayerRecord  ── snapshot ──▶  PlayerInGame
      ▲                              │
      └────── apply results ◀────────┘

If you ever think “this changes during a game”,
it does not belong here.
"""

from dataclasses import dataclass
from typing import Any

from src.player.player_skills import PlayerSkills
from src.types.rows import CsvRow, DbRow


@dataclass(slots=True, frozen=True)
class PlayerRecord:
    """
    Persistent, authoritative player data.
    Maps 1:1 to a row in the `players` table.
    """

    id: str
    first_name: str
    last_name: str
    bats: str
    throws: str
    position: str
    skills: PlayerSkills

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"<Player {self.name}>"

    @classmethod
    def from_csv_row(cls, row: CsvRow) -> "PlayerRecord":
        first, last = row["Name"].split(" ", 1)
        return cls(
            id=row["ID"],
            first_name=first,
            last_name=last,
            bats=row["B"],
            throws=row["T"],
            skills=PlayerSkills.from_csv_row(row),
            position=row["PS"],
        )

    @classmethod
    def from_db_row(cls, row: DbRow) -> "PlayerRecord":
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            bats=row["bats"],
            throws=row["throws"],
            skills=PlayerSkills.from_db_row(row),
            position=row["position"],
        )
