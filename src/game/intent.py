# src/game/intent.py
from __future__ import annotations

import uuid
from abc import ABC
from dataclasses import dataclass, field


# kw_only solves non-default argument follows default argument error
@dataclass(frozen=True, kw_only=True)
class GameIntent(ABC):
    """
    Declarative request to advance the game.

    Intents are:
    - Immutable
    - Side-effect free
    - Interpreted by a Resolver
    """

    intent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    issued_by: str | None = None
