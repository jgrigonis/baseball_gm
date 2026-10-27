# src/util/weighted_choice.py

from collections.abc import Callable
from random import Random


class WeightedChoice:
    """
    Manages weighted probability distributions with support for
    dynamic updates and random selection.
    """

    def __init__(
        self,
        initial_weights: dict[str, int] | None = None,
        rng: Random | None = None,
    ):
        """
        Args:
            initial_weights: Initial probability weights as {outcome: weight}
            rng: Random number generator (defaults to Random())
        """
        self.rng = rng or Random()
        self._base_weights = initial_weights.copy() if initial_weights else {}
        self._current_weights = initial_weights.copy() if initial_weights else {}

    def set_weights(self, weights: dict[str, int]) -> None:
        """Set new base weights and reset current weights."""
        self._base_weights = weights.copy()
        self._current_weights = weights.copy()

    def reset(self) -> None:
        """Reset current weights to base weights."""
        self._current_weights = self._base_weights.copy()

    def multiply(self, outcome: str, factor: float) -> None:
        """Multiply a weight by a factor."""
        if outcome in self._current_weights:
            self._current_weights[outcome] = int(
                self._current_weights[outcome] * factor
            )

    def add(self, outcome: str, amount: int) -> None:
        """Add to a weight."""
        if outcome in self._current_weights:
            self._current_weights[outcome] += amount
        else:
            self._current_weights[outcome] = amount

    def get(self, outcome: str) -> int:
        """Get a specific current weight (0 when unset)."""
        return self._current_weights.get(outcome, 0)

    def set(self, outcome: str, value: int) -> None:
        """Set a specific weight value."""
        self._current_weights[outcome] = value

    def apply_modifier(self, modifier: Callable[[dict[str, int]], None]) -> None:
        """Apply a modifier function that updates weights in place."""
        modifier(self._current_weights)

    def choose(self) -> str:
        """
        Select a random outcome based on current weights.

        Returns:
            The selected outcome key

        Raises:
            ValueError: If weights are empty or all zero
        """
        if not self._current_weights:
            raise ValueError("No weights set")

        # Clamp all values to minimum of 0
        clamped = {k: max(0, v) for k, v in self._current_weights.items()}
        total = sum(clamped.values())

        if total == 0:
            raise ValueError("All weights are zero")

        rand_num = self.rng.random() * total

        for outcome, weight in clamped.items():
            rand_num -= weight
            if rand_num <= 0:
                return outcome

        # Fallback (shouldn't reach here due to floating point)
        return list(clamped.keys())[-1]

    def get_weights(self) -> dict[str, int]:
        """Get a copy of current weights."""
        return self._current_weights.copy()

    def get_probabilities(self) -> dict[str, float]:
        """Get normalized probabilities (0-1) for each outcome."""
        clamped = {k: max(0, v) for k, v in self._current_weights.items()}
        total = sum(clamped.values())
        if total == 0:
            return {k: 0.0 for k in clamped}
        return {k: v / total for k, v in clamped.items()}
