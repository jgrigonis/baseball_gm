# src/game/strategy.py
import random

from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.count import Count
from src.game.score import Score

# Probability constants for new events
BASE_PICKOFF_ATTEMPT_PROB = 0.02  # 2% per pitch
BASE_STEAL_SECOND_PROB = 0.08  # 8% from first
BASE_STEAL_THIRD_PROB = 0.02  # 2% from second
BASE_STEAL_HOME_PROB = 0.001  # 0.1% from third

# PICKOFF_SUCCESS_PROB = 0.15  # 15% successful
# PICKOFF_ERROR_PROB = 0.05  # 5% throwing error

# STEAL_SECOND_SUCCESS_PROB = 0.75  # 75% success rate
# STEAL_THIRD_SUCCESS_PROB = 0.80  # 80% success rate
# STEAL_HOME_SUCCESS_PROB = 0.85  # 85% success rate


def _get_rng(rng: random.Random | None) -> random.Random:
    """Helper to get RNG instance, creating default if needed."""
    return rng if rng is not None else random.Random()


class GameStrategy:
    """
    Handles tactical decisions during gameplay.
    Stateless - all decisions based on current game state.
    """

    @staticmethod
    def should_attempt_pickoff(bases: Bases, rng: random.Random | None = None) -> bool:
        """Decide if pitcher should attempt pickoff before this pitch."""
        rng = _get_rng(rng)

        if bases.is_empty:
            return False

        # Simple probability - 2% chance per pitch
        # TODO: Make this smarter based on:
        # - Runner speed/steal tendency
        # - Game situation
        # - Pitcher pickoff skill
        return rng.random() < BASE_PICKOFF_ATTEMPT_PROB

    @staticmethod
    def select_pickoff_target(bases: Bases, rng: random.Random | None = None) -> int:
        """Select which base to pick off."""
        rng = _get_rng(rng)
        occupied = sorted(bases.occupied_map().keys())
        if not occupied:
            raise ValueError("Cannot select pickoff target with no runners on base")
        # TODO: Logic based on handedness of pitcher
        # Prefer third base if it's occupied
        if THIRD in occupied:
            # If both third and second occupied, sometimes pick second
            if SECOND in occupied:
                return SECOND if rng.random() < 0.1 else THIRD
            return THIRD

        if SECOND in occupied:
            return SECOND

        return FIRST

    # @staticmethod
    # def should_attempt_double_steal(
    #     bases: Bases, outs: int, rng: random.Random | None = None
    # ) -> bool:
    #     """Decide if double steal should be attempted."""
    #     rng = _get_rng(rng)
    #     # TODO need to account for runner speeds, game scenario and base_running skills
    #     # Check which scenario
    #     if bases.runner_on(FIRST) and bases.runner_on(THIRD):
    #         # 1st and 3rd is more common (strategic play)
    #         prob = 0.03  # 3% chance
    #     else:
    #         # 1st/2nd or 2nd/3rd - standard double steal
    #         prob = 0.01  # 1% chance

    #     # Less likely with 2 outs
    #     if outs == 2:
    #         prob *= 0.2

    #     return rng.random() < prob

    # @staticmethod
    # def should_attempt_steal(
    #     from_base: int, bases: Bases, outs: int, rng: random.Random | None = None
    # ) -> bool:
    #     # from_base: int, game
    #     """
    #     Decide if runner attempts to steal.

    #     Factors:
    #     - Runner speed
    #     - Pitcher delivery time
    #     - Catcher arm strength
    #     - Game situation
    #     - Count
    #     """
    #     rng = _get_rng(rng)
    #     # Can't steal if next base is occupied (in most cases)
    #     next_base = from_base + 1
    #     if next_base <= THIRD and bases.runner_on(next_base):
    #         # Exception: double steal
    #         if from_base == FIRST and bases.runner_on(SECOND):
    #             # Possible double steal - lower probability
    #             return rng.random() < (BASE_STEAL_SECOND_PROB * 0.3)
    #         return False

    #     # Base probability by base
    #     if from_base == FIRST:
    #         prob = BASE_STEAL_SECOND_PROB
    #     elif from_base == SECOND:
    #         prob = BASE_STEAL_THIRD_PROB
    #     elif from_base == THIRD:
    #         prob = BASE_STEAL_HOME_PROB
    #     else:
    #         return False

    #     # TODO: Adjust based on:
    #     # - Runner speed rating
    #     # - Pitcher delivery time
    #     # - Catcher pop time/arm strength
    #     # - Count (more on 3-2, less on 0-2)
    #     # - Score (more when down, less when up)
    #     # - Outs (rare with 2 outs)
    #     # - Pitcher handedness vs runner

    #     # Simple adjustment: less likely with 2 outs
    #     if outs == 2:
    #         prob *= 0.5

    #     return rng.random() < prob

    @staticmethod
    def should_attempt_steal(
        from_base: int,
        bases: Bases,
        outs: int,
        count: Count,
        score: Score,
        runner_speed: int = 50,
        base_running_skill: int = 50,
        catcher_arm: int = 50,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if runner should attempt to steal.

        Factors:
        - Runner speed
        - Pitcher delivery time
        - Catcher arm strength
        - Game situation (score, outs)
        - Count (more aggressive on 3-2)
        """
        rng = _get_rng(rng)

        # Can't steal if next base is occupied (except double steal)
        next_base = from_base + 1
        if next_base <= THIRD and bases.runner_on(next_base):
            return False

        # Base probability by target base
        if from_base == FIRST:
            prob = 0.08  # 8% to steal second
        elif from_base == SECOND:
            prob = 0.02  # 2% to steal third
        elif from_base == THIRD:
            prob = 0.001  # 0.1% to steal home
        else:
            return False

        # Adjust for runner speed
        speed_factor = runner_speed / 50  # 1.0 at average
        prob *= speed_factor

        # # Adjust for pitcher delivery
        # delivery_factor = 50 / pitcher_delivery  # Higher delivery = easier steal
        # prob *= delivery_factor

        # Adjust for catcher arm
        arm_factor = 50 / catcher_arm  # Weaker arm = easier steal
        prob *= arm_factor

        # Count adjustments
        if count.balls == 3 and count.strikes == 2:
            prob *= 1.5  # More aggressive on full count
        elif count.balls == 0 and count.strikes == 2:
            prob *= 0.5  # Less aggressive when batter behind

        # Outs adjustment
        if outs == 2:
            prob *= 0.5  # Less aggressive with 2 outs

        # Score differential (steal more when down)
        if score.differential < -2:
            prob *= 1.3
        elif score.differential > 2:
            prob *= 0.7

        return rng.random() < prob

    @staticmethod
    def should_attempt_double_steal(
        outs: int,
        double_steal_bases: list[int] = None,
        runner_speeds: dict[int, int] = None,  # {base: speed}
        rng: random.Random | None = None,
    ) -> bool:
        """Decide if double steal should be attempted."""
        rng = _get_rng(rng)

        # Check which scenario
        if double_steal_bases == [FIRST, THIRD]:
            # 1st and 3rd is more common (strategic play)
            prob = 0.03  # 3% chance
        elif double_steal_bases == [FIRST, SECOND]:
            # 1st and 2nd - standard double steal
            prob = 0.01  # 1% chance
        elif double_steal_bases == [SECOND, THIRD]:
            # 2nd and 3rd
            prob = 0.005  # 0.5% chance
        else:
            return False

        # Adjust for runner speeds if provided
        if runner_speeds:
            avg_speed = sum(runner_speeds.values()) / len(runner_speeds)
            speed_factor = avg_speed / 50
            prob *= speed_factor

        # Less likely with 2 outs
        if outs == 2:
            prob *= 0.2

        return rng.random() < prob

    # TODO Unused
    @staticmethod
    def should_bunt(
        bases: Bases,
        outs: int,
        batter_bunting_skill: int = 50,
        batter_power: int = 50,
        score_differential: int = 0,
        inning: int = 1,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if batter should attempt a bunt.

        More likely when:
        - Runner on first (advance to scoring position)
        - Less than 2 outs
        - Close game
        - Late innings
        - High bunting skill, low power
        """
        rng = _get_rng(rng)

        # Can't bunt with 2 outs (no sac bunt value)
        if outs >= 2:
            return False

        # Base probability
        prob = 0.02  # 2% base

        # Dramatically increase if runner on first, no one on second
        if bases.runner_on(FIRST) and not bases.runner_on(SECOND):
            prob = 0.15  # 15%

        # Increase slightly if runner on second, trying to advance to third
        elif bases.runner_on(SECOND) and not bases.runner_on(THIRD):
            prob = 0.08  # 8%

        # Bunting skill matters
        skill_factor = batter_bunting_skill / 50
        prob *= skill_factor

        # Power hitters don't bunt
        power_factor = 50 / max(batter_power, 30)  # Don't divide by tiny numbers
        prob *= power_factor

        # More likely in close games
        if -1 <= score_differential <= 1:
            prob *= 1.5

        # More likely in late innings
        if inning >= 7:
            prob *= 1.3

        return rng.random() < prob

    # TODO Unused
    @staticmethod
    def should_intentional_walk(
        bases: Bases,
        outs: int,
        batter_power: int = 50,
        next_batter_power: int = 50,
        score_differential: int = 0,
        inning: int = 1,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if pitcher should intentionally walk batter.

        Classic scenarios:
        - First base open, dangerous hitter, less dangerous on deck
        - Late innings, close game, setting up double play
        - First base open, runner on third (avoid sac fly)
        """
        rng = _get_rng(rng)

        # Only makes sense if first base is open
        if bases.runner_on(FIRST):
            return False

        # Very rare overall
        prob = 0.001

        # Much more likely if:
        # 1. Dangerous hitter (power 70+)
        # 2. Weaker hitter on deck
        # 3. Late innings, close game

        if batter_power >= 70 and next_batter_power < 60:
            prob = 0.05  # 5%

            # Even more likely late/close
            if inning >= 7 and abs(score_differential) <= 2:
                prob = 0.15  # 15%

            # Setting up double play (less than 2 outs)
            if outs < 2:
                prob *= 1.5

        return rng.random() < prob

    # TODO unused
    @staticmethod
    def should_pitch_out(
        bases: Bases,
        outs: int,
        runner_speeds: dict[int, int] = None,
        count_balls: int = 0,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if catcher/pitcher should pitch out (expecting steal).

        More likely when:
        - Fast runner on base
        - Favorable count (don't want to go 2-0, 3-1)
        - Less than 2 outs
        """
        rng = _get_rng(rng)

        if bases.is_empty:
            return False

        # Very rare
        prob = 0.01

        # Increase if runner has stolen base tendency (use speed as proxy)
        if runner_speeds:
            max_speed = max(runner_speeds.values())
            if max_speed >= 70:
                prob = 0.05

        # Don't pitch out on 3-0, 3-1 counts
        if count_balls >= 3:
            prob *= 0.1

        return rng.random() < prob

    # TODO unused
    @staticmethod
    def should_hit_and_run(
        bases: Bases,
        outs: int,
        batter_contact: int = 50,
        runner_speed: int = 50,
        count_balls: int = 0,
        count_strikes: int = 0,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if offense should call hit-and-run.

        Runner steals, batter MUST swing to protect.

        Best when:
        - Good contact hitter
        - Fast runner on first
        - Favorable count
        - Less than 2 outs
        """
        rng = _get_rng(rng)

        # Needs runner on first (typically)
        if not bases.runner_on(FIRST):
            return False

        # Can't do with 2 outs
        if outs >= 2:
            return False

        prob = 0.02  # 2% base

        # Good contact hitter
        if batter_contact >= 60:
            prob *= 1.5

        # Fast runner
        if runner_speed >= 60:
            prob *= 1.5

        # Favorable count (1-1, 2-1, 2-2)
        if count_balls >= 1 and count_strikes >= 1:
            prob *= 1.3

        return rng.random() < prob
