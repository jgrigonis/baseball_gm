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

from src.player.player_constants import VALID_ROLES
from src.player.player_record import PlayerRecord
from src.player.player_evaluator import PlayerEvaluator


@dataclass(frozen=True)
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

    def set_bullpen_roles(
        self, rotation: list[str], relievers: list | None = None
    ) -> list[dict]:
        """
        rotation: list of player IDs of the starting pitchers.
        relievers: optional pre-filtered list of reliever PlayerRecords. If None,
                   derived from self.players excluding rotation.

        Return a list of dicts, with keys:
            player_id (str)
            role      (str)  -- one of VALID_ROLES

        VALID_ROLES = "Closer", "Setup", "Middle", "Long", "Specialist", "Utility"

        Assignment logic:
        - Closer:  best "stuff" score
        - Setup:   second best stuff
        - Long:    best stamina + recovery (combined >= 140), skipped if no one qualifies
        - Middle:  next best stuff (2 middles if long was skipped)
        - Utility: remaining relievers up to 8 total
        """
        roles = []

        # All pitchers not in the starting rotation
        if relievers is None:
            relievers = [
                p for p in self.players if p.is_pitcher() and p.id not in rotation
            ]

        def stuff(p: PlayerRecord) -> float:
            s = p.skills
            return (
                (s["strikes"] * 0.5)
                + (s["accuracy"] * 0.2)
                + (s["clutch"] * 0.2)
                + (s["ground_balls"] * 0.1)
            )

        # Sort relievers by stuff descending — we'll pull from this ordered list
        relievers.sort(key=stuff, reverse=True)
        remaining = list(relievers)

        # --- Closer: best stuff ---
        if remaining:
            roles.append({"player_id": remaining.pop(0).id, "role": "Closer"})

        # --- Setup: second best stuff ---
        if remaining:
            roles.append({"player_id": remaining.pop(0).id, "role": "Setup"})

        # --- Long: best stamina + recovery >= 140, pulled from remaining ---
        long_candidate = next(
            (
                p
                for p in remaining
                if (p.skills["stamina"] + p.skills["recovery"]) >= 140
            ),
            None,
        )
        skip_long = long_candidate is None
        if long_candidate:
            remaining.remove(long_candidate)
            roles.append({"player_id": long_candidate.id, "role": "Long"})

        # --- Middle: next 1 or 2 best stuff (2 if long was skipped) ---
        middle_slots = 2 if skip_long else 1
        for _ in range(middle_slots):
            if remaining:
                roles.append({"player_id": remaining.pop(0).id, "role": "Middle"})

        # --- Utility: fill up to 8 total relievers ---
        max_relievers = 8
        for p in remaining:
            if len(roles) >= max_relievers:
                break
            roles.append({"player_id": p.id, "role": "Utility"})

        for player_role in roles:
            if player_role["role"] not in VALID_ROLES:
                raise ValueError(f"Invalid role type: {player_role['role']}")

        return roles
