# src/game/defense/outcome.py

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DefenseOutcome:
    success: bool
    error: bool = False
    slow: bool = False
    error_type: Optional[str] = None  # "throw", "fielding", etc.

    @classmethod
    def clean_play(cls):
        return cls(success=True)

    @classmethod
    def fielding_error(cls, error_type="fielding"):
        return cls(
            success=False,
            error=True,
            error_type=error_type,
        )

    @classmethod
    def too_slow(cls):
        return cls(
            success=False,
            slow=True,
        )
