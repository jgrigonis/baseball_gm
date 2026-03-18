# src/game/modifiers/pitch_modifiers.py
from src.game.bases import Bases, SECOND, THIRD
from src.game.count import Count
from src.game.intents.pitch import PrePitchSituation
from src.player.player_in_game import PlayerInGame
from src.game.modifiers.count_modifiers import PITCH_COUNT_MODIFIERS


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

    @staticmethod
    def modify_for_bases(resolver, bases: Bases) -> None:
        """Modify probabilities based on base state."""
        if bases.is_empty:
            resolver.pitch_outcome.set("illegal_pitch", 10)
        else:
            resolver.pitch_outcome.set("balk", 22)
            resolver.pitch_outcome.multiply("ball", 1.03)
            resolver.pitch_outcome.multiply("strike", 0.97)
            resolver.pitch_outcome.multiply("foul", 0.94)
            resolver.pitch_outcome.multiply("in_play", 1.18)
            resolver.pitch_outcome.multiply("home_run", 1.18)

    @staticmethod
    def modify_for_situation(
        resolver, situation: PrePitchSituation, batter: PlayerInGame
    ) -> None:
        """Modify probabilities based on game situation."""
        bunting = batter.skills["bunting"]
        contact = batter.skills["contact"]

        if situation.bunt_attempt:
            resolver.pitch_outcome.add("strike", -25 * bunting)
            resolver.pitch_outcome.add("foul", 25 * (100 - bunting))
            resolver.pitch_outcome.set("home_run", 0)
            resolver.pitch_outcome.add("in_play", 25 * (100 - bunting))

        if situation.hit_and_run:
            resolver.pitch_outcome.add("strike", -90 * contact)
            resolver.pitch_outcome.set("ball", 10)
            resolver.pitch_outcome.add("foul", 4 * (100 - contact))
            resolver.pitch_outcome.add("home_run", 2 * (contact - 60))
            resolver.pitch_outcome.multiply("balk", 1.2)
            resolver.pitch_outcome.multiply("catcher_interference", 1.2)
            resolver.pitch_outcome.add("in_play", 90 * contact)

        if situation.pitch_out:
            resolver.pitch_outcome.multiply("strike", 0.05)
            resolver.pitch_outcome.multiply("ball", 2.0)
            resolver.pitch_outcome.multiply("foul", 0.05)
            resolver.pitch_outcome.multiply("home_run", 0.01)
            resolver.pitch_outcome.multiply("hit_by_pitch", 0.01)
            resolver.pitch_outcome.multiply("catcher_interference", 1.2)
            resolver.pitch_outcome.multiply("wild_pitch", 0.35)
            resolver.pitch_outcome.multiply("in_play", 0.001)

        if situation.hit_and_run and situation.pitch_out:
            resolver.pitch_outcome.multiply("strike", 25)
            resolver.pitch_outcome.multiply("foul", 10)
            resolver.pitch_outcome.multiply("in_play", 50)

    @staticmethod
    def modify_for_count(resolver, count: Count) -> None:
        """Apply count-based probability modifiers."""
        modifiers = PITCH_COUNT_MODIFIERS.get((count.balls, count.strikes))
        if modifiers:
            for outcome, factor in modifiers.items():
                resolver.pitch_outcome.multiply(outcome, factor)

    @staticmethod
    def modify_for_batter(resolver, batter: PlayerInGame) -> None:
        """Modify probabilities based on batter skills."""
        eye = batter.skills["eye"]
        resolver.pitch_outcome.add("strike", -14 * (eye - 50))
        resolver.pitch_outcome.add("foul", 8 * (eye - 50))
        resolver.pitch_outcome.add("ball", 9 * (eye - 50))
        if eye > 75:
            elite_bonus = (eye - 75) ** 1.6
            resolver.pitch_outcome.add("ball", elite_bonus)
            resolver.pitch_outcome.add("strike", -0.5 * elite_bonus)

        contact = batter.skills["contact"]
        resolver.pitch_outcome.add("strike", -12 * (contact - 50))
        resolver.pitch_outcome.add("foul", int(2 * (contact - 50)))
        resolver.pitch_outcome.add("in_play", int(3.6 * (contact - 50)))
        if contact > 75:
            elite_bonus = (contact - 75) ** 1.6
            resolver.pitch_outcome.add("in_play", elite_bonus)
            resolver.pitch_outcome.add("strike", -0.5 * elite_bonus)

        power = batter.skills["power"]
        resolver.pitch_outcome.add("home_run", 3.8 * (power - 50))
        if power > 75:
            elite_bonus = (power - 75) ** 1.6
            resolver.pitch_outcome.add("home_run", 0.2 * elite_bonus)

    @staticmethod
    def modify_for_catcher(resolver, catcher: PlayerInGame) -> None:
        """Modify passed balls and wild pitches for catcher."""
        catching = catcher.apply_fatigue_to_ratings(catcher.skills["catching"])
        resolver.pitch_outcome.add("wild_pitch", -(catching))
        resolver.pitch_outcome.add("passed_ball", -(catching - 50))

    @staticmethod
    def modify_for_pitcher(resolver, pitcher: PlayerInGame) -> None:
        """Modify probabilities based on pitcher skills."""
        accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
        resolver.pitch_outcome.add("ball", -30 * (accuracy - 50))
        resolver.pitch_outcome.add("strike", 16 * (accuracy - 50))
        resolver.pitch_outcome.add("hit_by_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("wild_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("passed_ball", int(-0.7 * (accuracy - 50)))

        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        resolver.pitch_outcome.add("home_run", -(ground_balls - 40))

        strikes = pitcher.get_effective_stat(pitcher.skills["strikes"])
        resolver.pitch_outcome.add("ball", -12 * (strikes - 50))
        resolver.pitch_outcome.add("strike", 16 * (strikes - 50))
        resolver.pitch_outcome.add("foul", 6 * (strikes - 50))
        resolver.pitch_outcome.add("in_play", -12 * (strikes - 50))

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
            resolver.pitch_outcome.multiply("strike", 1.05)

    @staticmethod
    def modify_for_clutch(resolver, batter, pitcher, game) -> None:
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
        bclutch = batter.skills["clutch"]
        pclutch = pitcher.skills["clutch"]
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
        resolver.pitch_outcome.multiply("strike", 1.0 - effect)
        resolver.pitch_outcome.multiply("foul", 1.0 + effect * 0.4)
        resolver.pitch_outcome.multiply("ball", 1.0 - effect * 0.3)
        resolver.pitch_outcome.multiply("hit_by_pitch", 1.0 - effect * 0.2)
