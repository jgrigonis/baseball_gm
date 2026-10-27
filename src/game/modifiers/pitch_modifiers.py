# src/game/modifiers/pitch_modifiers.py
from src.game.bases import Bases, SECOND, THIRD
from src.game.count import Count
from src.game.intents.pitch import PrePitchSituation
from src.player.player_in_game import PlayerInGame
from src.game.modifiers.count_modifiers import (
    CALLED_STRIKE_MIX_BY_COUNT,
    PITCH_COUNT_MODIFIERS,
)

CALLED = "called_strike"
SWINGING = "swinging_strike"


def multiply_strikes(resolver, factor: float) -> None:
    """Scale both kinds of strike by the same factor."""
    resolver.pitch_outcome.multiply(CALLED, factor)
    resolver.pitch_outcome.multiply(SWINGING, factor)


def add_strikes(resolver, amount: float, called_share: float) -> None:
    """
    Add (or remove) strike weight, giving called_share of it to called
    strikes and the rest to swinging strikes. When one kind would drop
    below zero the shortfall comes out of the other, so the combined
    strike weight moves by exactly `amount` (as the old single weight did).
    """
    po = resolver.pitch_outcome
    called = po.get(CALLED) + amount * called_share
    swinging = po.get(SWINGING) + amount * (1 - called_share)
    if called < 0:
        swinging += called
        called = 0
    elif swinging < 0:
        called += swinging
        swinging = 0
    po.set(CALLED, int(called))
    po.set(SWINGING, int(swinging))


def shift_strike_mix(resolver, called_factor: float) -> None:
    """
    Scale called strikes by called_factor and move the difference to or
    from swinging strikes, leaving the combined strike weight unchanged.
    """
    po = resolver.pitch_outcome
    called, swinging = max(0, po.get(CALLED)), max(0, po.get(SWINGING))
    total = called + swinging
    new_called = min(total, int(called * called_factor))
    po.set(CALLED, new_called)
    po.set(SWINGING, total - new_called)


class PitchModifiers:
    """Modifies pitch outcome probabilities based on game state."""

    @staticmethod
    def apply_all(resolver, game) -> None:
        """Apply all pitch probability modifiers based on game state."""
        batter = game.current_batter.player
        pitcher = game.pos("p")
        catcher = game.pos("c")
        PitchModifiers.modify_for_bases(resolver, game.bases)
        PitchModifiers.modify_for_situation(resolver, game.situation, batter)
        PitchModifiers.modify_for_count(resolver, game.count)
        PitchModifiers.modify_for_batter(resolver, batter)
        PitchModifiers.modify_for_pitcher(resolver, pitcher)
        PitchModifiers.modify_for_catcher(resolver, catcher)
        PitchModifiers.modify_for_platoon(resolver, batter, pitcher)
        PitchModifiers.modify_for_clutch(resolver, batter, pitcher, game)
        PitchModifiers.modify_strike_mix_for_count(resolver, game.count)

    @staticmethod
    def modify_for_bases(resolver, bases: Bases) -> None:
        """Modify probabilities based on base state."""
        if bases.is_empty:
            resolver.pitch_outcome.set("illegal_pitch", 10)
        else:
            resolver.pitch_outcome.set("balk", 22)
            resolver.pitch_outcome.multiply("ball", 1.03)
            multiply_strikes(resolver, 0.97)
            resolver.pitch_outcome.multiply("foul", 0.94)
            resolver.pitch_outcome.multiply("in_play", 1.18)
            resolver.pitch_outcome.multiply("home_run", 1.18)

    @staticmethod
    def modify_for_situation(
        resolver, situation: PrePitchSituation, batter: PlayerInGame
    ) -> None:
        """Modify probabilities based on game situation."""
        bunting = batter.get_effective_stat(batter.skills["bunting"])
        contact = batter.get_effective_stat(batter.skills["contact"])

        if situation.bunt_attempt:
            add_strikes(resolver, -25 * bunting, called_share=0.0)
            resolver.pitch_outcome.add("foul", 25 * (100 - bunting))
            resolver.pitch_outcome.set("home_run", 0)
            resolver.pitch_outcome.add("in_play", 25 * (100 - bunting))

        if situation.hit_and_run:
            add_strikes(resolver, -90 * contact, called_share=0.0)
            resolver.pitch_outcome.set("ball", 10)
            resolver.pitch_outcome.add("foul", 4 * (100 - contact))
            resolver.pitch_outcome.add("home_run", 2 * (contact - 60))
            resolver.pitch_outcome.multiply("balk", 1.2)
            resolver.pitch_outcome.multiply("catcher_interference", 1.2)
            resolver.pitch_outcome.add("in_play", 90 * contact)

        if situation.pitch_out:
            multiply_strikes(resolver, 0.05)
            resolver.pitch_outcome.multiply("ball", 2.0)
            resolver.pitch_outcome.multiply("foul", 0.05)
            resolver.pitch_outcome.multiply("home_run", 0.01)
            resolver.pitch_outcome.multiply("hit_by_pitch", 0.01)
            resolver.pitch_outcome.multiply("catcher_interference", 1.2)
            resolver.pitch_outcome.multiply("wild_pitch", 0.35)
            resolver.pitch_outcome.multiply("in_play", 0.001)

        if situation.hit_and_run and situation.pitch_out:
            multiply_strikes(resolver, 25)
            resolver.pitch_outcome.multiply("foul", 10)
            resolver.pitch_outcome.multiply("in_play", 50)

    @staticmethod
    def modify_for_count(resolver, count: Count) -> None:
        """Apply count-based probability modifiers."""
        modifiers = PITCH_COUNT_MODIFIERS.get((count.balls, count.strikes))
        if modifiers:
            for outcome, factor in modifiers.items():
                if outcome == "strike":
                    multiply_strikes(resolver, factor)
                else:
                    resolver.pitch_outcome.multiply(outcome, factor)

    @staticmethod
    def modify_strike_mix_for_count(resolver, count: Count) -> None:
        """
        Hitters take early and in hitter's counts and protect with two
        strikes. Runs last so it splits all of the strike weight.
        """
        key = (count.balls, count.strikes)
        shift_strike_mix(resolver, CALLED_STRIKE_MIX_BY_COUNT.get(key, 1.0))

    @staticmethod
    def modify_for_batter(resolver, batter: PlayerInGame) -> None:
        """Modify probabilities based on batter skills."""
        # Strike weight split: eye mostly cuts chases (swinging strikes),
        # contact cuts whiffs, power hitters swing through more pitches.
        eye = batter.get_effective_stat(batter.skills["eye"])
        add_strikes(resolver, -21 * (eye - 50), called_share=0.25)
        resolver.pitch_outcome.add("foul", 8 * (eye - 50))
        resolver.pitch_outcome.add("ball", 12 * (eye - 50))
        if eye > 75:
            elite_bonus = (eye - 75) ** 1.6
            resolver.pitch_outcome.add("ball", int(6 * elite_bonus))
            add_strikes(resolver, int(-9.0 * elite_bonus), called_share=0.25)

        contact = batter.get_effective_stat(batter.skills["contact"])
        add_strikes(resolver, -19 * (contact - 50), called_share=0.1)
        resolver.pitch_outcome.add("foul", int(2 * (contact - 50)))
        resolver.pitch_outcome.add("in_play", int(3.6 * (contact - 50)))
        if contact > 75:
            elite_bonus = (contact - 75) ** 1.6
            resolver.pitch_outcome.add("in_play", int(3.5 * elite_bonus))
            add_strikes(resolver, int(-11.5 * elite_bonus), called_share=0.1)

        power = batter.get_effective_stat(batter.skills["power"])
        resolver.pitch_outcome.add("home_run", int(3.1 * (power - 50)))
        if power > 75:
            elite_bonus = (power - 75) ** 1.6
            resolver.pitch_outcome.add("home_run", int(0.6 * elite_bonus))
        shift_strike_mix(resolver, 1.0 - 0.004 * (power - 50))

    @staticmethod
    def modify_for_catcher(resolver, catcher: PlayerInGame) -> None:
        """Modify passed balls and wild pitches for catcher."""
        catching = catcher.get_effective_stat(catcher.skills["catching"])
        resolver.pitch_outcome.add("wild_pitch", -(catching))
        resolver.pitch_outcome.add("passed_ball", -(catching - 50))

    @staticmethod
    def modify_for_pitcher(resolver, pitcher: PlayerInGame) -> None:
        """Modify probabilities based on pitcher skills."""
        accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
        resolver.pitch_outcome.add("ball", -30 * (accuracy - 50))
        # Strike weight split: control paints corners (called strikes),
        # stuff misses bats (swinging strikes).
        add_strikes(resolver, 18 * (accuracy - 50), called_share=0.7)
        resolver.pitch_outcome.add("hit_by_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("wild_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("passed_ball", int(-0.7 * (accuracy - 50)))
        if accuracy > 75:
            elite_bonus = (accuracy - 75) ** 1.6
            add_strikes(resolver, 2.2 * elite_bonus, called_share=0.7)
            resolver.pitch_outcome.add("ball", -2.2 * (elite_bonus))

        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        resolver.pitch_outcome.add("home_run", -3 * (ground_balls - 40))

        strikes = pitcher.get_effective_stat(pitcher.skills["strikes"])
        resolver.pitch_outcome.add("ball", -12.5 * (strikes - 50))
        add_strikes(resolver, 19.5 * (strikes - 50), called_share=0.25)
        resolver.pitch_outcome.add("foul", 6 * (strikes - 50))
        resolver.pitch_outcome.add("in_play", -12 * (strikes - 50))
        if strikes > 75:
            elite_bonus = (strikes - 75) ** 1.6
            add_strikes(resolver, 7 * elite_bonus, called_share=0.2)

        if strikes > 80 and accuracy > 80:
            super_elite_bonus = (strikes + accuracy - 150) ** 1.5
            resolver.pitch_outcome.add("ball", -5.5 * super_elite_bonus)
            add_strikes(resolver, 5.5 * super_elite_bonus, called_share=0.5)
            resolver.pitch_outcome.add("hit_by_pitch", int(-0.2 * (super_elite_bonus)))
            resolver.pitch_outcome.add("wild_pitch", int(-0.2 * (super_elite_bonus)))

    @staticmethod
    def modify_for_platoon(
        resolver, batter: PlayerInGame, pitcher: PlayerInGame
    ) -> None:
        """Modify for handedness of batter and pitcher."""
        pt = pitcher.record.throws  # R, L
        bb = batter.record.bats  # R, L, S
        if pt == bb:  # LvL or RvR
            resolver.pitch_outcome.multiply("ball", 0.95)
            resolver.pitch_outcome.multiply("foul", 1.05)
            resolver.pitch_outcome.multiply("home_run", 0.89)
            resolver.pitch_outcome.multiply("hit_by_pitch", 0.96)
            resolver.pitch_outcome.multiply("in_play", 0.95)
            multiply_strikes(resolver, 1.05)
            # Same-side breaking balls get more chases and whiffs.
            shift_strike_mix(resolver, 0.95)

    @staticmethod
    def modify_for_clutch(
        resolver, batter: PlayerInGame, pitcher: PlayerInGame, game
    ) -> None:
        """
        Adjust outcomes based on the situation and player clutch ratings.
        Determine clutch situations, they can be multiplicative
        score is within 1 run
        runners in scoring position
        high count
        late in game
        clutch is positive with a more clutch batter
        clutch is negative with a more clutch pitcher
        clutch can range between -100 and 100 but tpically will be close to 0
        """
        bclutch = batter.get_effective_stat(batter.skills["clutch"])
        pclutch = pitcher.get_effective_stat(pitcher.skills["clutch"])
        clutch = bclutch - pclutch
        tight_game = False
        scoring_position = False
        high_count = False
        late_game = False
        if -1 < game.score.differential < 1:
            tight_game = True
        if game.bases.runner_on(SECOND) or game.bases.runner_on(THIRD):
            scoring_position = True
        if game.count.balls > 2 or game.count.strikes == 2:
            high_count = True
        if game.inning.number > 7:
            late_game = True

        situation_count = sum([tight_game, scoring_position, high_count, late_game])
        if situation_count == 0 or clutch == 0:
            return

        # Each active situation amplifies the clutch effect
        # 1 situation: 1.4x, 2: 1.6x, 3: 1.8x, 4: 1.9x (diminishing returns)
        situation_multiplier = 1.0 + (0.4 * situation_count**0.6)

        # Base effect: ~1.5% swing per 50 clutch points in a single situation
        # Scales to ~3% at max differential with all 4 situations active
        effect = (clutch / 100) * 0.015 * situation_multiplier

        # Positive effect = batter clutch advantage → more contact, more power
        # Negative effect = pitcher clutch advantage → more strikes, less contact
        resolver.pitch_outcome.multiply("in_play", 1.0 + effect)
        resolver.pitch_outcome.multiply(
            "home_run", 1.0 + effect * 1.5
        )  # power amplified
        multiply_strikes(resolver, 1.0 - effect)
        resolver.pitch_outcome.multiply("foul", 1.0 + effect * 0.4)
        resolver.pitch_outcome.multiply("ball", 1.0 - effect * 0.3)
        resolver.pitch_outcome.multiply("hit_by_pitch", 1.0 - effect * 0.2)
