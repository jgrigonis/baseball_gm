# src/game/modifiers/pitch_modifiers.py
from src.game.bases import Bases
from src.game.count import Count
from src.game.intents.pitch import PrePitchSituation
from src.player.player_in_game import PlayerInGame
from src.game.modifiers.count_modifiers import PITCH_COUNT_MODIFIERS


class PitchModifiers:
    """Modifies pitch outcome probabilities based on game state."""

    @staticmethod
    def apply_all(resolver, game) -> None:
        """Apply all pitch probability modifiers based on game state."""
        PitchModifiers.modify_for_bases(resolver, game.bases)
        PitchModifiers.modify_for_situation(
            resolver, game.situation, game.current_batter.player
        )
        PitchModifiers.modify_for_count(resolver, game.count)
        PitchModifiers.modify_for_batter(resolver, game.current_batter.player)
        PitchModifiers.modify_for_pitcher(resolver, game.pos("p"))
        PitchModifiers.modify_for_platoon(resolver, game.current_batter.player, game.pos("p"))

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

        contact = batter.skills["contact"]
        resolver.pitch_outcome.add("strike", -9.9 * (contact - 50))
        resolver.pitch_outcome.add("foul", int(2 * (contact - 50)))
        resolver.pitch_outcome.add("in_play", int(3.6 * (contact - 50)))

        power = batter.skills["power"]
        resolver.pitch_outcome.add("home_run", 3.7 * (power - 50))

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
        resolver.pitch_outcome.add("strike", 40 * (strikes - 50))
        resolver.pitch_outcome.add("foul", -4 * (strikes - 50))
        resolver.pitch_outcome.add("in_play", -8 * (strikes - 50))

    @staticmethod
    def modify_for_platoon(resolver, batter: PlayerInGame, pitcher: PlayerInGame) -> None:
        """Modify for handedness of batter and pitcher."""
        pt = pitcher.record.throws
        bb = batter.record.bats

