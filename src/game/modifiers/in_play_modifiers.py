# src/game/modifiers/in_play_modifiers.py
from src.game.bases import Bases, FIRST, SECOND, THIRD
from src.game.count import Count
from src.game.score import Score
from src.game.intents.pitch import PrePitchSituation
from src.player.player_in_game import PlayerInGame
from src.game.modifiers.count_modifiers import IN_PLAY_COUNT_MODIFIERS


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
        InPlayModifiers.modify_for_platoon(
            resolver, game.current_batter.player, game.pos("p")
        )
        InPlayModifiers.apply_constraints(resolver, game.bases, game.inning.outs)

    @staticmethod
    def modify_for_bases_outs(resolver, bases: Bases, outs: int):
        """Modify in-play probabilities based on bases and outs."""
        if bases.runner_on(THIRD) and outs < 2:
            resolver.in_play_outcome.set("sac_fly", 1700)
            resolver.in_play_outcome.set("fly_out", 850)
            resolver.in_play_outcome.multiply("ground_out", 0.1)
            resolver.in_play_outcome.set("fielders_choice", 1850)
        if bases.runner_on(FIRST) and bases.runner_on(SECOND) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 10)
        if bases.runner_on(FIRST) and bases.runner_on(THIRD) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 2)
        if bases.runner_on(SECOND) and bases.runner_on(THIRD) and outs == 0:
            resolver.in_play_outcome.set("triple_play", 2)
            resolver.in_play_outcome.multiply("ground_out", 0.1)
            resolver.in_play_outcome.set("fielders_choice", 1850)
        if bases.runner_on(FIRST) and outs < 2:
            resolver.in_play_outcome.set("double_play", 950)
            resolver.in_play_outcome.multiply("ground_out", 0.1)
            resolver.in_play_outcome.set("fielders_choice", 2450)

    @staticmethod
    def modify_for_situation(
        resolver, situation: PrePitchSituation, batter: PlayerInGame
    ):
        """Modify in-play probabilities based on situation."""
        bunting = batter.get_effective_stat(batter.skills["bunting"])

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
        power = batter.get_effective_stat(batter.skills["power"])
        resolver.in_play_outcome.add("fly_out", -4 * (power - 50))
        resolver.in_play_outcome.add("single", -1 * (power - 50))
        resolver.in_play_outcome.add("double", (power - 50))
        resolver.in_play_outcome.add("triple", int(0.2 * (power - 50)))

        contact = batter.get_effective_stat(batter.skills["contact"])
        resolver.in_play_outcome.add("single", 8 * (contact - 50))
        resolver.in_play_outcome.add("double", 2 * (contact - 50))
        resolver.in_play_outcome.add("ground_out", (contact - 50))
        if contact > 75:
            elite_bonus = (contact - 75) ** 1.6
            resolver.in_play_outcome.add("single", elite_bonus)
            resolver.in_play_outcome.add("ground_out", -0.5 * elite_bonus)

        speed = batter.get_effective_stat(batter.skills["speed"])
        base_running = batter.get_effective_stat(batter.skills["base_running"])
        resolver.in_play_outcome.add("ground_out", -1 * (speed - 50))
        resolver.in_play_outcome.add("single", 0.9 * (speed - 50))
        resolver.in_play_outcome.add("double", 0.6 * (speed - 50))
        resolver.in_play_outcome.add("triple", 0.45 * (speed - 50))
        resolver.in_play_outcome.add("double_play", -2 * (speed - 50))
        resolver.in_play_outcome.add("fielders_choice", (speed - 50))
        if speed + base_running > 150:
            elite_bonus = (speed + base_running - 150) ** 1.6
            resolver.in_play_outcome.add("single", 0.9 * (elite_bonus))
            resolver.in_play_outcome.add("double", 0.6 * (elite_bonus))
            resolver.in_play_outcome.add("triple", 0.45 * (elite_bonus))

        clutch = batter.get_effective_stat(batter.skills["clutch"])
        if -2 < score.differential < 2:
            resolver.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("ground_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("single", (clutch - 50))
            resolver.in_play_outcome.add("double", 0.5 * (clutch - 50))
            resolver.in_play_outcome.add("triple", 0.12 * (clutch - 50))

    @staticmethod
    def modify_for_pitcher(resolver, pitcher: PlayerInGame, score: Score):
        """Modify the probabilities based on pitcher skills."""
        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        resolver.in_play_outcome.add("double_play", 0.8 * ground_balls)
        resolver.in_play_outcome.add("fielders_choice", 5 * ground_balls)
        resolver.in_play_outcome.add("sac_fly", -0.5 * (ground_balls - 50))
        # Only add to ground_out if bases are effectively empty (no force play available)
        # otherwise the ground-ball tendency shows up as DPs and FCs instead
        current_go = resolver.in_play_outcome.get_weights().get("ground_out", 0)
        if current_go > 500:  # hasn't been suppressed by a runner-on-first situation
            resolver.in_play_outcome.add("ground_out", 4 * (ground_balls - 50))

        clutch = pitcher.get_effective_stat(pitcher.skills["clutch"])
        if -2 < score.differential < 2:
            resolver.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            resolver.in_play_outcome.add("single", 50 - clutch)
            resolver.in_play_outcome.add("double", 0.5 * (50 - clutch))
            if (
                current_go > 500
            ):  # hasn't been suppressed by a runner-on-first situation
                resolver.in_play_outcome.add("ground_out", 2 * (clutch - 50))

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
    def modify_for_platoon(
        resolver, batter: PlayerInGame, pitcher: PlayerInGame
    ) -> None:
        """Modify for handedness of batter and pitcher."""
        pt = pitcher.record.throws  # R, L
        bb = batter.record.bats  # R, L, S
        if pt == bb:  # LvL or RvR
            resolver.in_play_outcome.multiply("fly_out", 1.02)
            resolver.in_play_outcome.multiply("ground_out", 1.11)
            resolver.in_play_outcome.multiply("single", 0.95)
            resolver.in_play_outcome.multiply("double", 0.96)
            resolver.in_play_outcome.multiply("triple", 0.97)
            resolver.in_play_outcome.multiply("double_play", 1.02)
            resolver.in_play_outcome.multiply("fielders_choice", 1.02)

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
