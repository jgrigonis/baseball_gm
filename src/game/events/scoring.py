# src/game/events/scoring.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame

# TODO in general, we'll want to check if game is over when a run scores


@dataclass(frozen=True)
class RunScoredEvent(GameEvent):
    """
    A run has scored.
    """

    runner: PlayerInGame
    rbi_batter: PlayerInGame | None
    reason: str
    pitcher: PlayerInGame
    responsible_pitcher: PlayerInGame | None
    earned: bool = True

    def apply(self, game):
        earned = not game._inning_had_error
        game.score.score_run(
            top=game.inning.top,
            inning_number=game.inning.number,
        )
        self.runner.game_stats.batting.run()
        self.responsible_pitcher.game_stats.pitching.run()
        if earned:
            self.responsible_pitcher.game_stats.pitching.earned_run()
        if self.rbi_batter:
            self.rbi_batter.game_stats.batting.hit_rbi()

        # Track lead changes for win/loss attribution
        game._record_lead_change_if_needed(self.responsible_pitcher)
        # And whether the pitcher on the mound let the lead go (holds, saves)
        game._note_run_against_pitcher()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Run scored. Score: {game.away.name} {game.score.away} - {game.home.name} {game.score.home}"
