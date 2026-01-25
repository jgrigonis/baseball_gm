# src/game/rules/force_advancement.py
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class ForcedAdvance:
    runner: str
    from_base: int
    to_base: int
    reason: str = "force"
    rbi_batter: Optional[PlayerInGame] = None


def force_advance_chain(
    occupied_bases: Dict[int, PlayerInGame],
    start_base: int,
    rbi_batter: Optional[PlayerInGame] = None,
) -> List[ForcedAdvance]:
    """
    Compute forced runner movement as a pure function.

    Definition:
        A runner is forced if a new runner is awarded their current base
        and the runner has no legal option to remain.

    Rules:
        - Only runners on contiguous occupied bases are forced
        - Forced runners advance exactly one base
        - Chain stops at first empty base
        - Events are returned in collision-safe order
          (highest base → lowest base)
        - No RNG, no Game, no side effects

    Example:
        occupied = {1: "r1", 2: "r2", 3: "r3"}
        start_base = 1

        returns:
        [
            ForcedAdvance("r3", 3, 4),
            ForcedAdvance("r2", 2, 3),
            ForcedAdvance("r1", 1, 2),
        ]
    """

    advances: List[ForcedAdvance] = []

    # Walk forward to find contiguous occupied chain
    base = start_base
    while base in occupied_bases:
        base += 1

    # Now walk backward to produce collision-safe order
    for b in range(base - 1, start_base - 1, -1):
        advances.append(
            ForcedAdvance(
                runner=occupied_bases[b],
                from_base=b,
                to_base=b + 1,
                rbi_batter=rbi_batter,
            )
        )

    return advances
