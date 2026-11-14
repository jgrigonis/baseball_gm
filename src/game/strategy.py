# src/game/strategy.py
from datetime import date
import random

from src.db.repositories.pitcher_state import PitcherState, availability_weight
from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.count import Count
from src.game.inning import Inning
from src.game.intents.pitch import PrePitchSituation
from src.game.probabilities import (
    BASE_PICKOFF_ATTEMPT_PROB,
    BASE_STEAL_SECOND_PROB,
    BASE_STEAL_THIRD_PROB,
    BASE_STEAL_HOME_PROB,
    STEAL_FULL_COUNT_MOD,
    STEAL_BEHIND_COUNT_MOD,
    STEAL_TWO_OUT_MOD,
    STEAL_CLOSE_GAME_MOD,
    STEAL_BLOWOUT_MOD,
    DOUBLE_STEAL_FIRST_THIRD,
    DOUBLE_STEAL_SECOND_THIRD,
    DOUBLE_STEAL_FIRST_SECOND,
    DOUBLE_STEAL_TWO_OUT_MOD,
    BUNT_PROB,
    BUNT_ON_FIRST_MOD,
    BUNT_ON_SECOND_MOD,
    BUNT_CLOSE_GAME_MOD,
    BUNT_LATE_INNING_MOD,
    IBB_PROB,
    IBB_POWERFUL,
    IBB_POWERFUL_LATE_INNING,
    IBB_TWO_OUT_MODIFIER,
    IBB_STRIKES_MODIFIER,
    IBB_MORE_STRIKES_MOD,
    PITCHOUT_PROB,
    PITCHOUT_FAST_MOD,
    PITCHOUT_BALLS_OVER_STRIKES,
    HNR_PROB,
    HNR_CONTACT_MOD,
    HNR_SPEED_MOD,
    HNR_SLOW_SPEED,
    HNR_SLOW_MOD,
    HNR_FAVORABLE_COUNT_MOD,
    STARTER_LEAD_HOOK,
    STARTER_LEAD_OUTS,
    CLOSER_ENTRANCE_PROB,
    PITCHER_CHANGE_PROB,
    PITCHER_CHANGE_MULTIPLIERS,
)
from src.game.score import Score
from src.league import budget as bg
from src.player.fatigue import FatigueLevel
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_in_game import PlayerInGame
from src.team.manager_profile import DEFAULT_PROFILE, ManagerProfile, profile_of
from src.team.team_in_game import TeamInGame


def _get_rng(rng: random.Random | None) -> random.Random:
    """Helper to get RNG instance, creating default if needed."""
    return rng if rng is not None else random.Random()


def _analytics_level(game) -> int:
    """The batting team's Analytics level (Standard when not set)."""
    levels = getattr(game, "analytics_levels", None) or {}
    record = getattr(getattr(game, "bat_team", None), "record", None)
    return levels.get(getattr(record, "id", None), bg.STANDARD)


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
        offense = profile_of(getattr(game, "bat_team", None))
        analytics = _analytics_level(game)
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
                    game.inning.outs,
                    double_steal_bases,
                    runner_speeds,
                    rng,
                    aggression=offense.steal_factor,
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
                        aggression=offense.steal_factor,
                        analytics=analytics,
                    ):
                        steal_attempt = base

        if GameStrategy.should_bunt(
            game.bases,
            game.inning.outs,
            game.count.strikes,
            game.count.balls,
            game.current_batter.player.skills["bunting"],
            game.current_batter.player.skills["power"],
            game.score.differential,
            game.inning.number,
            rng,
            bunt_factor=offense.bunt_factor,
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
                aggression=offense.steal_factor,
                analytics=analytics,
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
        aggression: float = 1.0,
        analytics: int = bg.STANDARD,
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
            prob = BASE_STEAL_SECOND_PROB  # % to steal second
        elif from_base == SECOND:
            prob = BASE_STEAL_THIRD_PROB  # 2% to steal third
        elif from_base == THIRD:
            prob = BASE_STEAL_HOME_PROB  # 0.1% to steal home
        else:
            return False

        # Adjust for runner speed. Speed counts double: good reads and jumps
        # help, but they can't make a slow runner a threat to steal.
        speed_factor = (2 * runner_speed + base_running_skill) / 150  # 1.0 at average
        prob *= speed_factor * speed_factor
        # Elite speed runners should steal much more often
        if speed_factor > 1.5:
            prob *= speed_factor * speed_factor

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

        # The manager's baserunning setting, aimed by his analytics staff
        prob *= aggression
        prob *= bg.analytics_aim(analytics, speed_factor * arm_factor)

        return rng.random() < prob

    @staticmethod
    def should_attempt_double_steal(
        outs: int,
        double_steal_bases: list[int] = None,
        runner_speeds: dict[int, int] = None,  # {base: speed}
        rng: random.Random | None = None,
        aggression: float = 1.0,
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

        prob *= aggression

        return rng.random() < prob

    @staticmethod
    def should_bunt(
        bases: Bases,
        outs: int,
        strikes: int,
        balls: int,
        batter_bunting_skill: int = 50,
        batter_power: int = 50,
        score_differential: int = 0,
        inning: int = 1,
        rng: random.Random | None = None,
        bunt_factor: float = 1.0,
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
        # Won't bunt with 2 strikes or 3 balls, risk too great
        if strikes >= 2 or balls >= 3:
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

        # The manager's sac bunt setting
        prob *= bunt_factor

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
        aggression: float = 1.0,
        analytics: int = bg.STANDARD,
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
        # Slow runner: the runner is going on the pitch, so a slow one
        # usually just gets thrown out
        elif runner_speed < HNR_SLOW_SPEED:
            prob *= HNR_SLOW_MOD

        # Favorable count (1-1, 2-1, 2-2)
        if count_balls >= count_strikes:
            prob *= HNR_FAVORABLE_COUNT_MOD

        prob *= aggression
        prob *= bg.analytics_aim(analytics, (batter_contact / 50) * (runner_speed / 50))

        return rng.random() < prob

    @staticmethod
    def get_double_steal_candidates(game) -> list[int] | None:
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
        pitcher: PlayerInGame,
        inning: Inning,
        score_differential: int,
        profile: ManagerProfile = DEFAULT_PROFILE,
        inning_start: bool = False,
    ) -> float:
        """
        Determine if manager should consider pitching change.

        Args:
            pitcher: The current pitcher
            score_differential: Team's score minus opponent's score (positive = winning)
            inning: The current inning
            profile: The pitching team's manager: starter usage and bullpen
                settings set how long a starter's leash is.
            inning_start: True for the check before a half-inning begins,
                when a reliever who has finished his inning usually sits.

        Returns:
            1.0 if should consider a change, 0.0 if not, or some value in between
        """
        if not pitcher or not pitcher.pitcher_fatigue:
            return 0.0

        fatigue = pitcher.pitcher_fatigue
        fatigue_level = fatigue.get_level().value  # .value gives the plain string key

        prob = PITCHER_CHANGE_PROB.get(fatigue_level, 0.5)

        stats = pitcher.game_stats.pitching

        if pitcher.is_starter:
            threshold = profile.leash_pitches
            if stats.runs == 0:
                prob *= PITCHER_CHANGE_MULTIPLIERS.get("runs_0", 0.21)
            elif stats.runs == 1:
                prob *= PITCHER_CHANGE_MULTIPLIERS.get("runs_1", 0.52)
            elif stats.runs == 2 and score_differential > 0:
                prob *= PITCHER_CHANGE_MULTIPLIERS.get("runs_2_positive_diff", 0.61)
            if pitcher.game_stats.pitching.pitch_count < threshold:
                if stats.hits == 0:
                    prob *= PITCHER_CHANGE_MULTIPLIERS.get("no_hits", 0.11)

            # Modifier: Protect lead with starter (reduce probability of pulling them)
            if score_differential > 0 and stats.outs < STARTER_LEAD_OUTS:
                # Winning and the starter hasn't gone far yet: less likely to pull
                prob *= STARTER_LEAD_HOOK
            if stats.pitch_count >= threshold:
                prob = max(prob, profile.at_target_pull)
            else:
                # Short of his pitch count: the bullpen shape decides how
                # quickly a starter who's getting hit comes out.
                prob *= profile.trouble_hook
            batters_faced = stats.outs + stats.hits + stats.walks + stats.hb
            prob = min(1.0, prob * profile.starter_hook(batters_faced))

        elif pitcher.bullpen_role == "Closer":
            outs = stats.outs
            if outs >= 9 or stats.runs >= 3:
                return 1.0  # 3 innings or 3 runs is the max
            elif outs >= 6 or stats.runs >= 2:
                return min(1.0, prob + 0.3)  # getting long for a closer
            elif outs >= 3:  # done his job, but manager may want him back
                return min(0.35, max(0.19, prob))  # at least some chance of pulling him
            return 0.0

        else:  # RELIEVER / SETUP / LONG / SHORT
            outs = stats.outs
            # Most relievers get an inning and sit, as in MLB. Long men can
            # go two or three.
            if inning_start:
                is_long = pitcher.bullpen_role == "Long"
                if outs >= (6 if is_long else 3):
                    return profile.reliever_done
            if outs >= 6 or stats.runs >= 2:
                return min(1, prob + 0.3)
            elif outs >= 3 or stats.runs >= 1:
                return min(1.0, prob + 0.15)
            return 0.0

        return prob

    @staticmethod
    def is_save_situation(inning_num: int, score_diff: int) -> bool:
        """Inning 9 or later with the pitching team ahead by 1-3 runs."""
        return inning_num >= 9 and 1 <= score_diff <= 3

    @staticmethod
    def find_closer(
        current_pitcher: PlayerInGame,
        team: TeamInGame,
        inning: Inning,
        score_diff: int,  # positive = pitching team is winning
        rng: random.Random | None = None,
    ) -> PlayerInGame | None:
        """
        Return the closer to bring in if this is a closer situation, else None.

        The team's closer usage setting decides what that means:
        - saves-only: inning 9 or later, leading by 1-3 (a save situation)
        - high-leverage: also a tie or a lead of 1-2 in the 8th or later
        - best-available: save situations, but the best fresh reliever by
          closer rating comes in, whatever his bullpen role

        A fresh/good pitcher must be available, and the current pitcher must
        not already be the Closer. Returns the closer with probability
        CLOSER_ENTRANCE_PROB so the manager almost always makes the move, but
        not robotically 100%.
        """
        rng = _get_rng(rng)
        usage = profile_of(team).closer_usage

        save_situation = GameStrategy.is_save_situation(inning.number, score_diff)
        late_and_close = inning.number >= 8 and 0 <= score_diff <= 2
        if not (save_situation or (usage == "high-leverage" and late_and_close)):
            return None
        if getattr(current_pitcher, "bullpen_role", None) == "Closer":
            return None

        def _fresh(p: PlayerInGame) -> bool:
            return (
                p != current_pitcher
                and p.game_stats.pitching.pitch_count == 0
                and p.pitcher_fatigue is not None
                and p.pitcher_fatigue.get_level()
                in (FatigueLevel.FRESH, FatigueLevel.GOOD)
                and p.current_position is None
            )

        if usage == "best-available":

            def _cp(p: PlayerInGame) -> int:
                return (getattr(p, "ratings", None) or {}).get("cp", 0)

            relievers = [
                p
                for p in team.players
                if getattr(p, "bullpen_role", None) and _fresh(p)
            ]
            best = max(relievers, key=_cp, default=None)
            # Already have the best arm in? Leave him.
            if best is None or _cp(best) <= _cp(current_pitcher):
                return None
            available_closers = [best]
        else:
            available_closers = [
                p
                for p in team.players
                if getattr(p, "bullpen_role", None) == "Closer" and _fresh(p)
            ]

        if not available_closers:
            return None

        if rng.random() >= CLOSER_ENTRANCE_PROB:
            return None

        return available_closers[0]

    @staticmethod
    def should_bring_in_closer(
        current_pitcher: PlayerInGame,
        team: TeamInGame,
        inning: Inning,
        score_diff: int,
        rng: random.Random | None = None,
    ) -> bool:
        """Thin wrapper around find_closer for backwards compatibility."""
        return (
            GameStrategy.find_closer(current_pitcher, team, inning, score_diff, rng)
            is not None
        )

    @staticmethod
    def select_relief_pitcher(
        team: TeamInGame,
        current_pitcher: PlayerInGame,
        inning: Inning,
        score: Score,
        pitcher_states: dict[str, PitcherState] | None = None,
        game_date: date | None = None,
        eligible_ids: set[str] | None = None,
        rng: random.Random | None = None,
    ) -> PlayerInGame | None:
        """
        Select the best available relief pitcher based on game situation,
        weighted by days of rest since last appearance.

        Role priority:
        - Inning 9+, lead <= 2: Closer
        - Inning 7-8, lead <= 2: Setup
        - Inning 5-6, close game: Long reliever
        - Otherwise: Middle/Utility reliever
        - Fallback: any fresh/good reliever
        - Emergency: fresh starter
        - Last resort: best available
        """
        rng = _get_rng(rng)
        score_diff = abs(score.differential)
        inning_num = inning.number
        close_game = score_diff <= 2

        def _is_available(p: PlayerInGame) -> bool:
            state = (pitcher_states or {}).get(p.id)
            if not state or not state.last_game_date or not game_date:
                return True  # no history, assume rested

            days_rest = (game_date - state.last_game_date).days

            # Pitched today in a previous game (shouldn't happen but guard it)
            if days_rest == 0:
                return False

            # Had two days off — always available
            if days_rest >= 3:
                return True

            # Pitched yesterday — check workload
            # Heavy outing (18+ pitches) needs at least 2 days rest
            if days_rest <= 2 and getattr(state, "last_pitch_count", 0) >= 18:
                return False

            # Check consecutive days streak
            consecutive = getattr(state, "consecutive_days", 0)

            # 3 consecutive days is the hard cap regardless of workload
            if consecutive >= 3:
                return False

            # 2 consecutive days + decent outing (9+ pitches) yesterday = needs rest
            if consecutive >= 2 and getattr(state, "last_pitch_count", 0) >= 9:
                return False

            return True

        available = [
            p
            for p in team.players
            if p != current_pitcher
            and p.game_stats.pitching.pitch_count == 0
            and p.pitcher_fatigue is not None
            and p.current_position is None
            and not p.is_injured
            and _is_available(p)
            and (eligible_ids is None or p.id in eligible_ids)
        ]

        if not available:
            return None

        def _weight(p: PlayerInGame) -> float:
            """Combined weight: rest days x in-game energy."""
            state = (pitcher_states or {}).get(
                p.id if hasattr(p, "id") else p.player.id
            )
            rest_w = availability_weight(state, game_date) if game_date else 1.0
            energy_w = p.pitcher_fatigue.energy if p.pitcher_fatigue else 1.0
            return rest_w * energy_w

        def _weighted_choice(candidates: list) -> PlayerInGame | None:
            if not candidates:
                return None
            weights = [max(_weight(p), 1e-6) for p in candidates]
            total = sum(weights)
            r = rng.random() * total
            cumulative = 0.0
            for p, w in zip(candidates, weights):
                cumulative += w
                if r <= cumulative:
                    return p
            return candidates[-1]

        # unused function
        # def best_by_rp(candidates):
        #     return max(
        #         candidates,
        #         key=lambda p: PlayerEvaluator.rate_player(p.record.skills).get("rp", 0),
        #     )

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
                # Closer situation: still use weighted choice but bias heavily
                # toward best closer — pick best by rating, weighted by rest
                return _weighted_choice(
                    sorted(
                        closers,
                        key=lambda p: PlayerEvaluator.rate_player(p.record.skills).get(
                            "rp", 0
                        ),
                        reverse=True,
                    )[:3]
                )  # top 3 closers by rating, weighted by rest

        # --- Inning 7-8, close game: Setup ---
        if 7 <= inning_num <= 8 and close_game:
            setup = with_fatigue(with_role(available, "Setup"), *fresh_good)
            if setup:
                return _weighted_choice(setup)

        # --- Inning 5-6, close game: Long reliever ---
        if 5 <= inning_num <= 6 and close_game:
            long_men = with_fatigue(with_role(available, "Long"), *fresh_good)
            if long_men:
                return _weighted_choice(long_men)

        # --- General: Middle/Utility non-Closer relievers ---
        non_closer_relievers = [p for p in relievers if p.bullpen_role != "Closer"]
        middle_utility = with_fatigue(
            with_role(non_closer_relievers, "Middle")
            or with_role(non_closer_relievers, "Utility")
            or with_fatigue(non_closer_relievers, *fresh_good),
            *fresh_good,
        )
        if middle_utility:
            return _weighted_choice(middle_utility)

        # --- Fallback: any fresh/good reliever ---
        fresh_good_relievers = with_fatigue(relievers, *fresh_good)
        if fresh_good_relievers:
            return _weighted_choice(fresh_good_relievers)

        # --- Fallback: tired non-Closer reliever ---
        tired_relievers = with_fatigue(
            [p for p in relievers if p.bullpen_role != "Closer"],
            FatigueLevel.TIRED,
        )
        if tired_relievers:
            return _weighted_choice(tired_relievers)

        # --- Emergency: fresh starter ---
        fresh_starters = with_fatigue(starters, FatigueLevel.FRESH)
        if fresh_starters:
            return best_by_sp(fresh_starters)

        # --- Last resort ---
        return _weighted_choice(available)
