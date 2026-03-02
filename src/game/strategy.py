# src/game/strategy.py
import random
from typing import List

from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.count import Count
from src.game.inning import Inning
from src.game.intents.pitch import PrePitchSituation
from src.game.score import Score
from src.player.fatigue import FatigueLevel
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_in_game import PlayerInGame
from src.team.team_in_game import TeamInGame

# Probability constants for new events
# Pickoff
BASE_PICKOFF_ATTEMPT_PROB = 0.01  # 1% per pitch

# Steal
BASE_STEAL_SECOND_PROB = 0.06  # 6% from first
BASE_STEAL_THIRD_PROB = 0.005  # 0.5% from second
BASE_STEAL_HOME_PROB = 0.00001  # 0.0001% from third
STEAL_FULL_COUNT_MOD = 1.5
STEAL_BEHIND_COUNT_MOD = 0.5
STEAL_TWO_OUT_MOD = 0.6
STEAL_CLOSE_GAME_MOD = 1.3
STEAL_BLOWOUT_MOD = 0.8
# Double Steal
DOUBLE_STEAL_FIRST_THIRD = 0.003
DOUBLE_STEAL_SECOND_THIRD = 0.00001
DOUBLE_STEAL_FIRST_SECOND = 0.001
DOUBLE_STEAL_TWO_OUT_MOD = 0.2

# Bunt
BUNT_PROB = 0.04
BUNT_ON_FIRST_MOD = 2.0
BUNT_ON_SECOND_MOD = 2.5
BUNT_CLOSE_GAME_MOD = 1.5
BUNT_LATE_INNING_MOD = 1.3

# Intentional Walk
IBB_PROB = 0.0001
IBB_POWERFUL = 0.001
IBB_POWERFUL_LATE_INNING = 0.002
IBB_TWO_OUT_MODIFIER = 1.2
IBB_STRIKES_MODIFIER = 0.01
IBB_MORE_STRIKES_MOD = 0.01

# Pitchout
PITCHOUT_PROB = 0.001
PITCHOUT_FAST_MOD = 4
PITCHOUT_BALLS_OVER_STRIKES = 0.1

# Hit and Run
HNR_PROB = 0.02
HNR_CONTACT_MOD = 1.5
HNR_SPEED_MOD = 1.5
HNR_FAVORABLE_COUNT_MOD = 1.3

# Pitcher Change
PITCH_COUNT_THRESHOLD = 100


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
        hit_and_run: bool = False

        # Defense
        pitch_out: bool = False
        intentional_walk: bool = False
        pickoff_attempt: Optional[int] = None  # Which base?
        """
        rng = _get_rng(rng)
        steal_attempt = None
        double_steal_attempt = None
        pickoff_attempt = None
        bunt_attempt = False
        hit_and_run = False
        pitch_out = False

        # Do intentional walk first
        if GameStrategy.should_intentional_walk(
            game.bases,
            game.count,
            game.inning.outs,
            game.current_batter.player.skills["power"],
            game.score.differential,
            game.inning.number,
            rng,
        ):
            return PrePitchSituation(intentional_walk=True)

        runner_speeds = {}
        if not game.bases.is_empty:
            double_steal_bases = GameStrategy.get_double_steal_candidates(game)

            if double_steal_bases:
                for base in double_steal_bases:
                    runner_speeds[base] = game.bases.runner_on(base).skills["speed"]
                if GameStrategy.should_attempt_double_steal(
                    game.inning.outs, double_steal_bases, runner_speeds, rng
                ):
                    double_steal_attempt = double_steal_bases
            else:
                for base in (THIRD, SECOND, FIRST):
                    if game.bases.runner_on(base):
                        runner_speeds[base] = game.bases.runner_on(base).skills["speed"]
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
            game.count.strikes,
            game.current_batter.player.skills["bunting"],
            game.current_batter.player.skills["power"],
            game.score.differential,
            game.inning.number,
            rng,
        ):
            bunt_attempt = True
        if not bunt_attempt:
            if GameStrategy.should_hit_and_run(
                game.bases,
                game.inning.outs,
                game.current_batter.player.skills["contact"],
                game.count.balls,
                game.count.strikes,
                rng,
            ):
                hit_and_run = True
        if runner_speeds:
            if GameStrategy.should_pitch_out(
                game.bases,
                game.inning.outs,
                runner_speeds,
                game.count.balls,
                game.count.strikes,
                rng,
            ):
                pitch_out = True

        if GameStrategy.should_attempt_pickoff(game.bases, game.score, rng):
            target_base = GameStrategy.select_pickoff_target(game.bases, rng)
            pickoff_attempt = target_base

        return PrePitchSituation(
            steal_attempt=steal_attempt,
            double_steal_attempt=double_steal_attempt,
            pickoff_attempt=pickoff_attempt,
            bunt_attempt=bunt_attempt,
            hit_and_run=hit_and_run,
            pitch_out=pitch_out,
        )

    @staticmethod
    def should_attempt_pickoff(
        bases: Bases, score: Score, rng: random.Random | None = None
    ) -> bool:
        """Decide if pitcher should attempt pickoff before this pitch."""
        rng = _get_rng(rng)

        if bases.is_empty:
            return False

        # Initialize speed with a default
        speed = 50

        if bases.one_man_on:
            base = bases.only_occupied_base()
            speed = bases.runner_on(base).skills["speed"]

        elif bases.is_loaded:
            speed = bases.runner_on(THIRD).skills["speed"]

        else:
            occupied = bases.occupied_map()
            occupied_bases = set(occupied.keys())
            if occupied_bases == {FIRST, THIRD}:
                speed = bases.runner_on(THIRD).skills["speed"]
            elif occupied_bases == {SECOND, THIRD}:
                speed = bases.runner_on(THIRD).skills["speed"]
            elif occupied_bases == {FIRST, SECOND}:
                speed = bases.runner_on(SECOND).skills["speed"]

        prob = BASE_PICKOFF_ATTEMPT_PROB
        if speed > 60:
            prob *= 1.5

        if -2 < score.differential < 2:
            prob *= 1.5

        return rng.random() < prob

    @staticmethod
    def select_pickoff_target(bases: Bases, rng: random.Random | None = None) -> int:
        """Select which base to pick off."""
        rng = _get_rng(rng)
        occupied = sorted(bases.occupied_map().keys())
        if not occupied:
            raise ValueError("Cannot select pickoff target with no runners on base")
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
            prob = BASE_STEAL_SECOND_PROB  # 8% to steal second
        elif from_base == SECOND:
            prob = BASE_STEAL_THIRD_PROB  # 2% to steal third
        elif from_base == THIRD:
            prob = BASE_STEAL_HOME_PROB  # 0.1% to steal home
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
            prob *= STEAL_FULL_COUNT_MOD  # More aggressive on full count
        elif count.balls < count.strikes:
            prob *= STEAL_BEHIND_COUNT_MOD  # Less aggressive when batter behind

        # Outs adjustment
        if outs == 2:
            prob *= STEAL_TWO_OUT_MOD  # Less aggressive with 2 outs

        # Score differential (steal more when down)
        if score.differential < -2:
            prob *= STEAL_CLOSE_GAME_MOD
        elif score.differential > 2:
            prob *= STEAL_BLOWOUT_MOD

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
            prob = DOUBLE_STEAL_FIRST_THIRD
        elif double_steal_bases == [FIRST, SECOND]:
            # 1st and 2nd - standard double steal
            prob = DOUBLE_STEAL_FIRST_SECOND
        elif double_steal_bases == [SECOND, THIRD]:
            # 2nd and 3rd
            prob = DOUBLE_STEAL_SECOND_THIRD
        else:
            return False

        # Adjust for runner speeds if provided
        if runner_speeds:
            avg_speed = sum(runner_speeds.values()) / len(runner_speeds)
            speed_factor = avg_speed / 50
            prob *= speed_factor

        # Less likely with 2 outs
        if outs == 2:
            prob *= DOUBLE_STEAL_TWO_OUT_MOD

        return rng.random() < prob

    @staticmethod
    def should_bunt(
        bases: Bases,
        outs: int,
        strikes: int,
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
        # Won't bunt with 2 strikes, risk too great
        if strikes >= 2:
            return False

        # no sac bunt without runners
        if bases.is_empty:
            return False

        # Base probability
        prob = BUNT_PROB  # base

        # Dramatically increase if runner on first, no one on second
        if bases.runner_on(FIRST) and not bases.runner_on(SECOND):
            prob *= BUNT_ON_FIRST_MOD

        # Increase slightly if runner on second, trying to advance to third
        elif bases.runner_on(SECOND) and not bases.runner_on(THIRD):
            prob *= BUNT_ON_SECOND_MOD

        # Bunting skill matters
        skill_factor = batter_bunting_skill / 50
        prob *= skill_factor

        # Power hitters don't bunt
        power_factor = 50 / max(batter_power, 30)  # Don't divide by tiny numbers
        prob *= power_factor

        # More likely in close games
        if -1 <= score_differential <= 1:
            prob *= BUNT_CLOSE_GAME_MOD

        # More likely in late innings
        if inning >= 7:
            prob *= BUNT_LATE_INNING_MOD

        return rng.random() < prob

    @staticmethod
    def should_intentional_walk(
        bases: Bases,
        count: Count,
        outs: int,
        batter_power: int = 50,
        # next_batter_power: int = 50, # No way to easily get this
        score_differential: int = 0,
        inning: int = 1,
        rng: random.Random | None = None,
    ) -> bool:
        """
        Decide if pitcher should intentionally walk batter.

        Classic scenarios:
        - First base open, dangerous hitter, TODO: less dangerous on deck
        - Late innings, close game, setting up double play
        - First base open, runner on third (avoid sac fly)
        """
        rng = _get_rng(rng)

        # Only makes sense if first base is open
        if bases.runner_on(FIRST):
            return False

        # Very rare overall
        prob = IBB_PROB

        # Much more likely if:
        # 1. Dangerous hitter (power 70+)
        # 2. Weaker hitter on deck # Can't currenty tell
        # 3. Late innings, close game

        if batter_power >= 70:
            prob = IBB_POWERFUL

            # Even more likely late/close
            if inning >= 7 and abs(score_differential) <= 2:
                prob = IBB_POWERFUL_LATE_INNING

        # Setting up double play (less than 2 outs)
        if outs < 2:
            prob *= IBB_TWO_OUT_MODIFIER

        if count.strikes > 0:
            prob *= IBB_STRIKES_MODIFIER

        # If more strikes than balls, almost never ibb
        if count.strikes > count.balls:
            prob *= IBB_MORE_STRIKES_MOD

        return rng.random() < prob

    @staticmethod
    def should_pitch_out(
        bases: Bases,
        outs: int,
        runner_speeds: dict[int, int] = None,
        count_balls: int = 0,
        count_strikes: int = 0,
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
        prob = PITCHOUT_PROB

        # Increase if runner has stolen base tendency (use speed as proxy)
        if runner_speeds:
            max_speed = max(runner_speeds.values())
            if max_speed >= 70:
                prob *= PITCHOUT_FAST_MOD

        if count_balls > count_strikes:
            prob *= PITCHOUT_BALLS_OVER_STRIKES
        # Don't pitch out on 3-0, 3-1 counts
        if count_balls >= 3:
            prob = 0

        return rng.random() < prob

    @staticmethod
    def should_hit_and_run(
        bases: Bases,
        outs: int,
        batter_contact: int = 50,
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

        # Just don't with bases loaded.
        if bases.is_loaded:
            return False

        # Can't do with 2 outs
        if outs >= 2:
            return False

        prob = HNR_PROB

        # Good contact hitter
        if batter_contact >= 60:
            prob *= HNR_CONTACT_MOD

        runner_speed = 50

        if bases.one_man_on:
            if bases.runner_on(FIRST):
                runner_speed = bases.runner_on(FIRST).skills["speed"]
            elif bases.runner_on(SECOND):
                runner_speed = bases.runner_on(SECOND).skills["speed"]
            elif bases.runner_on(THIRD):
                runner_speed = bases.runner_on(THIRD).skills["speed"]

        if bases.two_men_on:
            # Get the speed of the lead runner
            if bases.runner_on(THIRD):
                runner_speed = bases.runner_on(THIRD).skills["speed"]
            elif bases.runner_on(SECOND):
                runner_speed = bases.runner_on(SECOND).skills["speed"]

        # Fast runner
        if runner_speed >= 60:
            prob *= HNR_SPEED_MOD

        # Favorable count (1-1, 2-1, 2-2)
        if count_balls >= count_strikes:
            prob *= HNR_FAVORABLE_COUNT_MOD

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
        # Don't attempt double steal with bases loaded
        # TODO Could add a triple steal
        if game.bases.is_loaded:
            return None

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

    def set_steal(sit: PrePitchSituation) -> bool:
        if sit.double_steal_attempt:
            return True
        if sit.steal_attempt:
            return True
        if sit.hit_and_run:
            return True
        return False

    @staticmethod
    def should_consider_pitching_change(
        pitcher: PlayerInGame, inning: Inning, score_diff: int = 0
    ) -> float:
        """
        Determine if manager should consider pitching change.

        Args:
            pitcher: The current pitcher
            score_diff: Team's score minus opponent's score (positive = winning)

        Returns:
            True if should consider a change, False otherwise
        """
        if not pitcher or not pitcher.pitcher_fatigue:
            return False

        fatigue = pitcher.pitcher_fatigue
        fatigue_level = fatigue.get_level()

        # Base probabilities by fatigue level
        base_probs = {
            FatigueLevel.FRESH: 0.01,  # Almost never pull a fresh pitcher
            FatigueLevel.GOOD: 0.05,  # Rarely
            FatigueLevel.TIRED: 0.25,  # Sometimes
            FatigueLevel.EXHAUSTED: 0.60,  # Often
            FatigueLevel.ZERO: 0.95,  # Almost always
        }

        innings_pitched = pitcher.game_stats.pitching.ip_float
        prob = base_probs.get(fatigue_level, 0.5)

        # TODO PITCH_COUNT_THRESHOLD really only matters for starter
        # other pitchers should have a lower one, or a number of innings
        if pitcher.game_stats.pitching.pitch_count < PITCH_COUNT_THRESHOLD:
            if pitcher.game_stats.pitching.runs == 0:
                prob *= 0.5
            if pitcher.game_stats.pitching.hits == 0:
                prob *= 0.2

        # Modifier: Protect lead with starter (reduce probability of pulling them)
        if (
            score_diff > 0
            and innings_pitched < 5.0
            and pitcher.game_stats.pitching.game_started == 1
        ):
            # Winning and starter hasn't gone 5 innings yet
            prob *= 0.5  # Half as likely to pull

        # Modifier: Trailing badly (increase probability)
        if score_diff < -3:
            prob *= 1.3  # More likely to pull when getting blown out

        if inning.number == 9 and 0 < score_diff < 2:
            prob *= 3

        # Clamp to [0, 1]
        prob = max(0.0, min(1.0, prob))

        return prob

    @staticmethod
    def select_relief_pitcher(
        team: TeamInGame,
        current_pitcher: PlayerInGame,
        inning: Inning,
        score: Score,
    ) -> PlayerInGame | None:
        """
        Select the best available relief pitcher based on game situation.

        Priority:
        - Inning 9+, lead <= 2: best FRESH/GOOD Closer
        - Inning 7-8, lead <= 2: best FRESH/GOOD Setup
        - Inning 5-6, close game: best FRESH/GOOD Long reliever
        - Otherwise by situation: best FRESH/GOOD non-Closer reliever
        - Fallback: best TIRED non-starter, non-Closer
        - Emergency: best FRESH starter
        - Last resort: best available by fatigue
        """
        score_diff = abs(score.differential)
        inning_num = inning.number
        close_game = score_diff <= 2

        available = [
            p
            for p in team.players
            if p != current_pitcher
            and p.game_stats.pitching.pitch_count == 0
            and p.pitcher_fatigue is not None
            and p.current_position is None
        ]

        if not available:
            return None

        def best_by_rp(candidates):
            return max(
                candidates,
                key=lambda p: PlayerEvaluator.rate_player(p.record.skills).get("rp", 0),
            )

        def best_by_sp(candidates):
            return max(
                candidates,
                key=lambda p: PlayerEvaluator.rate_player(p.record.skills).get("sp", 0),
            )

        def with_fatigue(candidates, *levels):
            return [p for p in candidates if p.pitcher_fatigue.get_level() in levels]

        def with_role(candidates, role):
            return [p for p in candidates if p.bullpen_role == role]

        fresh_good = (FatigueLevel.FRESH, FatigueLevel.GOOD)
        relievers = [p for p in available if not p.is_starter]
        starters = [p for p in available if p.is_starter]

        # --- Inning 9+, save situation: go to Closer ---
        if inning_num >= 9 and close_game:
            closers = with_fatigue(with_role(available, "Closer"), *fresh_good)
            if closers:
                return best_by_rp(closers)

        # --- Inning 7-8, close game: go to Setup ---
        if 7 <= inning_num <= 8 and close_game:
            setup = with_fatigue(with_role(available, "Setup"), *fresh_good)
            if setup:
                return best_by_rp(setup)

        # --- Inning 5-6, close game: go to Long reliever ---
        if 5 <= inning_num <= 6 and close_game:
            long_men = with_fatigue(with_role(available, "Long"), *fresh_good)
            if long_men:
                return best_by_rp(long_men)

        # --- General: best FRESH/GOOD Middle or Utility reliever (not Closer) ---
        non_closer_relievers = [p for p in relievers if p.bullpen_role != "Closer"]
        middle_utility = with_fatigue(
            with_role(non_closer_relievers, "Middle")
            or with_role(non_closer_relievers, "Utility")
            or with_fatigue(non_closer_relievers, *fresh_good),
            *fresh_good,
        )
        if middle_utility:
            return best_by_rp(middle_utility)

        # --- Fallback: any FRESH/GOOD reliever ---
        fresh_good_relievers = with_fatigue(relievers, *fresh_good)
        if fresh_good_relievers:
            return best_by_rp(fresh_good_relievers)

        # --- Fallback: best TIRED non-starter, non-Closer ---
        tired_relievers = with_fatigue(
            [p for p in relievers if p.bullpen_role != "Closer"],
            FatigueLevel.TIRED,
        )
        if tired_relievers:
            return best_by_rp(tired_relievers)

        # --- Emergency: fresh starter ---
        fresh_starters = with_fatigue(starters, FatigueLevel.FRESH)
        if fresh_starters:
            return best_by_sp(fresh_starters)

        # --- Last resort: best available by any fatigue ---
        if available:
            return best_by_rp(available)

        return None
