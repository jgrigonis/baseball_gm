# src/game/event_outcome.py
"""
✅ Simple
✅ Explicit
✅ Serializable
✅ Test-friendly
✅ Free of game logic

EventGenerator decides
Resolver applies
Outcome describes

“The authoritative description of what happened at this layer.”
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EventOutcome:
    # category of outcome
    type: str
    # "pitch", "in_play", "walk", "strikeout"

    # contact info (only if in_play)
    contact: str | None = None
    # "ground", "fly", "line", "popup"

    # batter result
    # bases: int | None = None
    # 0, 1, 2, 3, 4

    # outs recorded on the play
    outs: int = 0

    # misc flags
    double_play: bool = False
    description: str = ""
