# src/game/strategy.py
import random
from typing import List

from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.count import Count
from src.game.intents.pitch import PrePitchSituation
from src.game.score import Score

# Probability constants for new events
BASE_PICKOFF_ATTEMPT_PROB = 0.02  # 2% per pitch
BASE_STEAL_SECOND_PROB = 0.08  # 8% from first
BASE_STEAL_THIRD_PROB = 0.02  # 2% from second
BASE_STEAL_HOME_PROB = 0.001  # 0.1% from third
BUNT_PROB = 0.02
BUNT_PROB_FIRST_PROB = 0.05
BUNT_PROB_SECOND_PROB = 0.08


def _get_rng(rng: random.Random | None) -> random.Random:
    """Helper to get RNG instance, creating default if needed."""
    return rng if rng is not None else random.Random()


class GameStrategy:
    """
    Handles tactical decisions during gameplay.
    Stateless - all decisions based on current game state.
    """

    @staticmethod
    def plan_pre_pitch(game, rng) -> PrePitchSituation:
        """
        Set all these variables:

        steal_attempt: Optional[int] = None
        double_steal_attempt: Optional[list[int]] = None
        bunt_attempt: bool = False
        hit_and_run: bool = False # TODO

        # Defense
        pitch_out: bool = False # TODO
        intentional_walk: bool = False # TODO
        pickoff_attempt: Optional[int] = None  # Which base?
        """
        rng = _get_rng(rng)
        steal_attempt = None
        double_steal_attempt = None
        pickoff_attempt = None
        bunt_attempt = False
        hit_and_run = False
        pitch_out = False
        intentional_walk = False

        # Do intentional walk first

        if not game.bases.is_empty:
            double_steal_bases = GameStrategy.get_double_steal_candidates(game)

            if double_steal_bases:
                runner_speeds = {}
                for base in double_steal_bases:
                    runner_speeds[base] = game.bases.runner_on(base).skills["speed"]
                if GameStrategy.should_attempt_double_steal(
                    game.inning.outs, double_steal_bases, runner_speeds, rng
                ):
                    double_steal_attempt = double_steal_bases
            if double_steal_attempt is None:
                # check lead runner first (highest base)
                occupied = sorted(game.bases.occupied_map().keys(), reverse=True)
                for base in occupied:
                    next_base = base + 1
                    # Can't steal if next base occupied
                    if next_base <= THIRD and game.bases.runner_on(next_base):
                        continue
                    runner = game.bases.runner_on(base)
                    speed = runner.skills["speed"]
                    br_skill = runner.skills["base_running"]
                    catcher = game.pitch_team.current_catcher
                    arm = catcher.skills["arm"]
                    if GameStrategy.should_attempt_steal(
                        base,
                        game.bases,
                        game.inning.outs,
                        game.count,
                        game.score,
                        speed,
                        br_skill,
                        arm,
                        rng,
                    ):
                        steal_attempt = base

        if GameStrategy.should_bunt(
            game.bases,
            game.inning.outs,
            game.current_batter.player.skills["bunting"],
            game.current_batter.player.skills["power"],
            game.score.differential,
            game.inning.number,
            rng,
        ):
            bunt_attempt = True

        # hit and run

        # pitch out

        if GameStrategy.should_attempt_pickoff(game.bases):
            target_base = GameStrategy.select_pickoff_target(game.bases)
            pickoff_attempt = target_base

        return PrePitchSituation(
            steal_attempt=steal_attempt,
            double_steal_attempt=double_steal_attempt,
            pickoff_attempt=pickoff_attempt,
            bunt_attempt=bunt_attempt,
        )

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

        # Won't bunt with 2 outs (no sac bunt value)
        if outs >= 2:
            return False

        # Base probability
        prob = BUNT_PROB  # 2% base

        # Dramatically increase if runner on first, no one on second
        if bases.runner_on(FIRST) and not bases.runner_on(SECOND):
            prob = BUNT_PROB_FIRST_PROB

        # Increase slightly if runner on second, trying to advance to third
        elif bases.runner_on(SECOND) and not bases.runner_on(THIRD):
            prob = BUNT_PROB_SECOND_PROB

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

    @staticmethod
    def get_double_steal_candidates(game) -> List[int] | None:
        """
        Get bases for potential double steal.

        When multiple double steals are possible, prioritize:
        1. 2nd and 3rd (most aggressive - runner scores)
        2. 1st and 3rd (strategic play)
        3. 1st and 2nd (most common)
        """
        # Priority 1: 2nd and 3rd (runner on 3rd can score)
        if game.bases.runner_on(SECOND) and game.bases.runner_on(THIRD):
            return [SECOND, THIRD]

        # Priority 2: 1st and 3rd (strategic, only if 2nd empty)
        if game.bases.runner_on(FIRST) and game.bases.runner_on(THIRD):
            if not game.bases.runner_on(SECOND):
                return [FIRST, THIRD]

        # Priority 3: 1st and 2nd (only if 3rd empty)
        if game.bases.runner_on(FIRST) and game.bases.runner_on(SECOND):
            if not game.bases.runner_on(THIRD):
                return [FIRST, SECOND]

        return None
