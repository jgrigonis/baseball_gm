# src/team/team_record.py

"""The TeamRecord class.

TeamRecord   ── snapshot ──▶  TeamInGame
     ▲                               │
     └────── apply results ◀─────────┘
              ^
              |
         TeamFactory

City
Mascot
Team ID
Roster (list of PlayerRecord.ids or full PlayerRecords)

"""

from dataclasses import dataclass
from pathlib import Path

from src.player.player_record import PlayerRecord


@dataclass(slots=True, frozen=True)
class TeamRecord:
    """
    Persistent, authoritative team data.
    Maps 1:1 to a row in the `teams` table.
    """

    id: str
    city: str
    mascot: str
    players: tuple[PlayerRecord, ...]
    source_csv: Path | None = None
    source_hash: str | None = None

    @property
    def name(self) -> str:
        return f"{self.city} {self.mascot}"

    def __str__(self) -> str:
        return f"<Team {self.name} ({len(self.players)} players)>"

    def __post_init__(self):
        if not isinstance(self.players, tuple):
            raise TypeError("TeamRecord.players must be a tuple")
