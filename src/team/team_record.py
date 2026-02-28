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

from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.player.player_record import PlayerRecord, VALID_ROLES
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
        pitchers.sort(
            key=lambda p: PlayerEvaluator.rate_player(p.skills).get("sp", 0),
            reverse=True,
        )
        return [p.id for p in pitchers[:5]]

    def set_bullpen_roles(self, rotation) -> list[dict]:
        """
        rotation: list of the starting pitchers.

        Return a list of dicts, with keys:

        player_id (str)
        role      (str)  -- one of VALID_ROLES
        VALID_ROLES = "Closer", "Setup", "Middle", "Long", "Specialist", "Utility"

        """
        roles = []
        # TODO ASAP
        pitchers = [p for p in self.players if p.is_pitcher()]
        # remove the starters in rotation from contention
        # set a closer first, best "stuff"
        # stuff = (strikes * 0.5) + (accuracy * 0.2) + (clutch * 0.2) + (ground_balls * 0.1)
        # set a setup, next best stuff
        # set a long, best stamina + recovery, should combine over 140 or skip
        # set a middle, next best stuff
        # 2 middles if you skip long
        # rest of pitchers, up to 8 total relievers are utility

        for player_role in roles:
            if player_role["role"] not in VALID_ROLES:
                raise(f"Invalid role type: {player_role["role"]}")
        return roles
