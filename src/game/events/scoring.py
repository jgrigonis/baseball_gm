# src/game/events/run.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class RunScoredEvent(GameEvent):
    """
    A run has scored.
    """

    runner_id: str
    rbi_batter_id: str | None
    reason: str

    def apply(self, game):
        game.score.score_run(
            top=game.inning.top,
            inning_number=game.inning.number,
        )

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Run scored. Score: {game.away.name} {game.score.away} - {game.home.name} {game.score.home}"
