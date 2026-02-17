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
from src.player.player_evaluator import PlayerEvaluator


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

    def assign_starting_rotation(self) -> list[str]:
        """Return player IDs of top 5 pitchers by SP rating, ordered best to worst."""
        pitchers = [p for p in self.players if p.is_pitcher()]
        pitchers.sort(key=lambda p: PlayerEvaluator.rate_player(p.skills).get("sp", 0), reverse=True)
        return [p.id for p in pitchers[:5]]
