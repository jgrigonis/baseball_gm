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
from src.player.player_skills import PlayerSkills


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
    skills: PlayerSkills

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"<Player {self.name}>"

    @classmethod
    def from_row(cls, row) -> "PlayerRecord":
        return cls(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            bats=row["bats"],
            throws=row["throws"],
            skills=PlayerSkills.from_row(row),
        )
