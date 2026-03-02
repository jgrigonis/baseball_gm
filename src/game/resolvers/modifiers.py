# src/game/resolvers/modifiers.py

"""
Probability modifier engine for pitch and in-play outcomes.

Applies adjustments based on game state, player skills, count, etc.
"""

from src.game.bases import FIRST, SECOND, THIRD, Bases
from src.game.count import Count
from src.game.score import Score
from src.game.intents.pitch import PrePitchSituation
from src.game.resolvers.count_modifiers import (
    PITCH_COUNT_MODIFIERS,
    IN_PLAY_COUNT_MODIFIERS,
)
from src.player.player_in_game import PlayerInGame


class PitchModifiers:
    """Modifies pitch outcome probabilities based on game state."""

    @staticmethod
    def apply_all(resolver, game):
        """Apply all pitch probability modifiers based on game state."""
        PitchModifiers.modify_for_bases(resolver, game.bases)
        PitchModifiers.modify_for_situation(
            resolver, game.situation, game.current_batter.player
        )
        PitchModifiers.modify_for_count(resolver, game.count)
        PitchModifiers.modify_for_batter(resolver, game.current_batter.player)
        PitchModifiers.modify_for_pitcher(resolver, game.pos("p"))

    @staticmethod
    def modify_for_bases(resolver, bases: Bases):
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
    ):
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
    def modify_for_count(resolver, count: Count):
        """Apply count-based probability modifiers."""
        modifiers = PITCH_COUNT_MODIFIERS.get((count.balls, count.strikes))
        if modifiers:
            for outcome, factor in modifiers.items():
                resolver.pitch_outcome.multiply(outcome, factor)

    @staticmethod
    def modify_for_batter(resolver, batter: PlayerInGame):
        """Modify probabilities based on batter skills."""
        eye = batter.skills["eye"]
        resolver.pitch_outcome.add("strike", -10 * (eye - 50))
        resolver.pitch_outcome.add("foul", 5 * (eye - 50))
        resolver.pitch_outcome.add("ball", 5 * (eye - 50))

        contact = batter.skills["contact"]
        resolver.pitch_outcome.add("strike", -6 * (contact - 50))
        resolver.pitch_outcome.add("foul", int(1.2 * (contact - 50)))
        resolver.pitch_outcome.add("in_play", int(1.9 * (contact - 50)))

        power = batter.skills["power"]
        resolver.pitch_outcome.add("home_run", 3 * (power - 50))

    @staticmethod
    def modify_for_pitcher(resolver, pitcher: PlayerInGame):
        """Modify probabilities based on pitcher skills."""
        accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
        resolver.pitch_outcome.add("ball", -24 * (accuracy - 50))
        resolver.pitch_outcome.add("strike", 16 * (accuracy - 50))
        resolver.pitch_outcome.add("hit_by_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("wild_pitch", -(accuracy - 50))
        resolver.pitch_outcome.add("passed_ball", int(-0.7 * (accuracy - 50)))

        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        resolver.pitch_outcome.add("home_run", -(ground_balls - 40))

        strikes = pitcher.get_effective_stat(pitcher.skills["strikes"])
        resolver.pitch_outcome.add("ball", -10 * (strikes - 50))
        resolver.pitch_outcome.add("strike", 27 * (strikes - 50))
        resolver.pitch_outcome.add("foul", 2 * (strikes - 50))


class InPlayModifiers:
    """Modifies in-play outcome probabilities based on game state."""

    @staticmethod
    def apply_all(resolver, game):
        """Apply all in-play probability modifiers."""
        InPlayModifiers.modify_for_bases_outs(resolver, game.bases, game.inning.outs)
        InPlayModifiers.modify_for_situation(
            resolver, game.situation, game.current_batter.player
        )
        InPlayModifiers.modify_for_count(resolver, game.count)
        InPlayModifiers.modify_for_batter(
            resolver, game.current_batter.player, game.score
        )
        InPlayModifiers.modify_for_pitcher(resolver, game.pos("p"), game.score)
        InPlayModifiers.modify_for_defense(resolver, game)
        InPlayModifiers.modify_for_infield_defense(resolver, game)
        InPlayModifiers.apply_constraints(resolver, game.bases, game.inning.outs)

    @staticmethod
    def modify_for_bases_outs(resolver, bases: Bases, outs: int):
        """Modify in-play probabilities based on bases and outs."""
        if bases.runner_on(THIRD) and outs < 2:
            resolver.in_play_outcome.set("sac_fly", 1900)
            resolver.in_play_outcome.set("fly_out", 650)
        if bases.runner_on(FIRST) and bases.runner_on(SECOND) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 10)
        if bases.runner_on(FIRST) and bases.runner_on(THIRD) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 2)
        if bases.runner_on(SECOND) and bases.runner_on(THIRD) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 2)
        if bases.runner_on(FIRST) and outs < 2:
            resolver.in_play_outcome.set("double_play", 900)
            resolver.in_play_outcome.multiply("ground_out", 0.5)
            resolver.in_play_outcome.set("fielders_choice", 1950)

    @staticmethod
    def modify_for_situation(
        resolver, situation: PrePitchSituation, batter: PlayerInGame
    ):
        """Modify in-play probabilities based on situation."""
        bunting = batter.skills["bunting"]

        if situation.bunt_attempt:
            resolver.in_play_outcome.add("fly_out", -15 * bunting)
            resolver.in_play_outcome.add("ground_out", 2 * (100 - bunting))
            resolver.in_play_outcome.multiply("single", 0.08)
            resolver.in_play_outcome.set("double", 0)
            resolver.in_play_outcome.set("triple", 0)
            resolver.in_play_outcome.add("double_play", 50 - bunting)
            resolver.in_play_outcome.add("fielders_choice", -3 * bunting)
            resolver.in_play_outcome.set("sac_bunt", 4000)
            resolver.in_play_outcome.set("sac_fly", 0)

        if situation.double_steal_attempt:
            resolver.in_play_outcome.multiply("double_play", 0.5)
            resolver.in_play_outcome.multiply("fielders_choice", 0.5)
            resolver.in_play_outcome.multiply("ground_out", 2.0)
            resolver.in_play_outcome.multiply("triple_play", 0.5)

        if situation.hit_and_run:
            resolver.in_play_outcome.multiply("ground_out", 2.0)
            resolver.in_play_outcome.multiply("double_play", 0.5)
            resolver.in_play_outcome.multiply("fielders_choice", 0.5)
            resolver.in_play_outcome.multiply("triple_play", 0.5)

        if situation.steal_attempt:
            resolver.in_play_outcome.multiply("ground_out", 2.0)
            resolver.in_play_outcome.multiply("double_play", 0.5)
            resolver.in_play_outcome.multiply("fielders_choice", 0.5)
            resolver.in_play_outcome.multiply("triple_play", 0.5)

    @staticmethod
    def modify_for_count(resolver, count: Count):
        """Apply count-based in-play probability modifiers."""
        modifiers = IN_PLAY_COUNT_MODIFIERS.get((count.balls, count.strikes))
        if modifiers:
            for outcome, factor in modifiers.items():
                resolver.in_play_outcome.multiply(outcome, factor)

    @staticmethod
    def modify_for_batter(resolver, batter: PlayerInGame, score: Score):
        """Modify the probabilities based on the batter skills."""
        power = batter.skills["power"]
        resolver.in_play_outcome.add("fly_out", -4 * (power - 50))
        resolver.in_play_outcome.add("single", -1 * (power - 50))
        resolver.in_play_outcome.add("double", (power - 50))

        contact = batter.skills["contact"]
        resolver.in_play_outcome.add("single", 3 * (contact - 50))
        resolver.in_play_outcome.add("ground_out", (contact - 50))

        speed = batter.skills["speed"]
        resolver.in_play_outcome.add("ground_out", -1 * (speed - 50))
        resolver.in_play_outcome.add("single", 0.9 * (speed - 50))
        resolver.in_play_outcome.add("double", 0.5 * (speed - 50))
        resolver.in_play_outcome.add("triple", 0.3 * (speed - 50))
        resolver.in_play_outcome.add("double_play", -2 * (speed - 50))
        resolver.in_play_outcome.add("fielders_choice", (speed - 50))

        clutch = batter.skills["clutch"]
        if -2 < score.differential < 2:
            resolver.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("ground_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("single", (clutch - 50))
            resolver.in_play_outcome.add("double", 0.5 * (clutch - 50))

    @staticmethod
    def modify_for_pitcher(resolver, pitcher: PlayerInGame, score: Score):
        """Modify the probabilities based on pitcher skills."""
        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        resolver.in_play_outcome.add("ground_out", 4 * (ground_balls - 50))
        resolver.in_play_outcome.add("double_play", 0.8 * ground_balls)
        resolver.in_play_outcome.add("fielders_choice", 0.5 * ground_balls)
        resolver.in_play_outcome.add("sac_fly", -0.5 * (ground_balls - 50))

        clutch = pitcher.skills["clutch"]
        if -2 < score.differential < 2:
            resolver.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("ground_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("single", 50 - clutch)
            resolver.in_play_outcome.add("double", 0.5 * (50 - clutch))

    @staticmethod
    def modify_for_defense(resolver, game):
        """Modify hit probabilities based on defensive positioning."""
        lf_range = int(
            (game.pos("lf").skills["speed"] + game.pos("lf").skills["outfield"]) / 2
        )
        cf_range = int(
            (game.pos("cf").skills["speed"] + game.pos("cf").skills["outfield"]) / 2
        )
        rf_range = int(
            (game.pos("rf").skills["speed"] + game.pos("rf").skills["outfield"]) / 2
        )
        avg_of_range = (lf_range + cf_range + rf_range) / 3

        range_factor = 50 / max(1, avg_of_range)
        resolver.in_play_outcome.multiply("fly_out", range_factor)
        resolver.in_play_outcome.multiply("single", 1 / range_factor)
        resolver.in_play_outcome.multiply("double", 1 / range_factor)
        resolver.in_play_outcome.multiply("triple", 1 / (range_factor * 1.5))

    @staticmethod
    def modify_for_infield_defense(resolver, game):
        """Modify probabilities based on infield defensive skills."""
        ss_skill = game.pos("ss").skills["infield"] + game.pos("ss").skills["arm"]
        _2b_skill = game.pos("2b").skills["infield"] + game.pos("2b").skills["arm"]
        _3b_skill = game.pos("3b").skills["infield"] + game.pos("3b").skills["arm"]
        _1b_skill = game.pos("1b").skills["infield"]

        avg_if_skill = (2 * ss_skill + 2 * _2b_skill + _3b_skill + _1b_skill) / 9
        defense_factor = avg_if_skill / 50

        resolver.in_play_outcome.multiply("double_play", defense_factor)
        resolver.in_play_outcome.multiply("fielders_choice", 1 / defense_factor)
        resolver.in_play_outcome.multiply("ground_out", defense_factor * 1.1)

    @staticmethod
    def apply_constraints(resolver, bases: Bases, outs: int):
        """Apply final constraints to ensure probabilities are valid."""
        if bases.number_of_baserunners < 2:
            resolver.in_play_outcome.set("triple_play", 0)

        if bases.number_of_baserunners < 1:
            resolver.in_play_outcome.set("double_play", 0)
            resolver.in_play_outcome.set("fielders_choice", 0)
            resolver.in_play_outcome.set("sac_fly", 0)
            resolver.in_play_outcome.set("sac_bunt", 0)

        if not bases.runner_on(THIRD):
            resolver.in_play_outcome.set("sac_fly", 0)

        if outs > 0:
            resolver.in_play_outcome.set("triple_play", 0)

        if outs > 1:
            resolver.in_play_outcome.set("double_play", 0)
            resolver.in_play_outcome.set("fielders_choice", 0)
            resolver.in_play_outcome.set("sac_fly", 0)
            resolver.in_play_outcome.set("sac_bunt", 0)
