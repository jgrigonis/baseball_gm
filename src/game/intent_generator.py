from __future__ import annotations

from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent


class IntentGenerator:
    """
    Determines the next intent to attempt based on current game state.

    This is the ONLY component allowed to:
    - inspect live Game state
    - decide what action is attempted next

    It does NOT:
    - apply rules
    - decide outcomes
    """

    def __init__(self, rng):
        self.rng = rng

    def next_intent(self, game) -> GameIntent:
        """
        Return exactly one GameIntent.

        This method must not:
        - mutate game
        - raise for normal flow
        """
        # ------------------------------------------------------------
        # Core loop: if a plate appearance is active, throw a pitch
        # ------------------------------------------------------------
        if self._plate_appearance_active(game):
            return self._next_pitch_intent(game)

        # ------------------------------------------------------------
        # Fallback (should be rare): do nothing
        # ------------------------------------------------------------
        return self._noop_intent()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _plate_appearance_active(self, game) -> bool:
        """
        True if we expect a pitch to be thrown.
        """
        return game.current_batter is not None and game.current_pitcher is not None

    def _next_pitch_intent(self, game) -> PitchIntent:
        """
        Create a PitchIntent using current batter/pitcher.
        """
        return PitchIntent(
            pitcher_id=game.current_pitcher.id,
            batter_id=game.current_batter.player.id,
        )

    def _noop_intent(self) -> GameIntent:
        """
        Used only if the game is between states.
        """
        from src.game.intent import GameIntent

        return GameIntent()
