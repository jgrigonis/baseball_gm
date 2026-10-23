# src/game/resolvers/fielder_selector.py

from src.player.player_in_game import PlayerInGame
from src.util.weighted_choice import WeightedChoice


class FielderSelector:
    def __init__(self, rng):
        self.infielder_bunt_choice = WeightedChoice(
            {
                "shortstop": 2,
                "second_baseman": 2,
                "third_baseman": 20,
                "pitcher": 15,
                "catcher": 20,
            },
            rng=rng,
        )
        # Infielder selection chooser
        self.infielder_choice = WeightedChoice(
            {
                "shortstop": 32,
                "second_baseman": 25,
                "third_baseman": 20,
                "first_baseman": 18,
                "pitcher": 5,
            },
            rng=rng,
        )

        # Outfielder selection chooser
        self.outfielder_choice = WeightedChoice(
            {
                "center_fielder": 39,
                "right_fielder": 32,
                "left_fielder": 29,
            },
            rng=rng,
        )

        self.foul_fly_choice = WeightedChoice(
            {
                "right_fielder": 32,
                "left_fielder": 30,
                "first_baseman": 9,
                "third_baseman": 9,
                "second_baseman": 4,
                "shortstop": 4,
                "catcher": 4,
                "pitcher": 2,
            },
            rng=rng,
        )

        self.double_play_choice = WeightedChoice(
            {
                "6-4-3": 43,
                "4-6-3": 23,
                "5-4-3": 12,
                "3-6-3": 7,
                "6-3": 4,
                "3-6": 3,
                "4-3": 2,
                "1-6-3": 2,
                "3-6-1": 2,
            },
            rng=rng,
        )

        self._3to1_dp_choice = WeightedChoice(
            {
                "5-2-3": 18,
                "6-2-3": 25,
                "4-2-3": 22,
                "1-2-3": 12,
                "3-2-3": 12,
                "5-5": 4,
                "6-5": 3,
            },
            rng=rng,
        )

        self._2to1_dp_choice = WeightedChoice(
            {
                "6-3": 25,
                "6-5-3": 25,
                "5-3": 25,
                "4-6": 25,
            },
            rng=rng,
        )

    def select_infielder(self, game) -> PlayerInGame:
        """Randomly select which infielder fields a ground ball"""
        position = self.infielder_choice.choose()

        position_map = {
            "shortstop": game.pos("ss"),
            "second_baseman": game.pos("2b"),
            "third_baseman": game.pos("3b"),
            "first_baseman": game.pos("1b"),
            "pitcher": game.pos("p"),
        }

        return position_map[position]

    def select_outfielder(self, game) -> PlayerInGame:
        """Randomly select which outfielder fields a fly ball"""
        position = self.outfielder_choice.choose()

        position_map = {
            "center_fielder": game.pos("cf"),
            "right_fielder": game.pos("rf"),
            "left_fielder": game.pos("lf"),
        }

        return position_map[position]

    def select_foul_out_catcher(self, game) -> PlayerInGame:
        """Randomly select which outfielder fields a fly ball"""
        position = self.foul_fly_choice.choose()

        position_map = {
            "center_fielder": game.pos("cf"),
            "right_fielder": game.pos("rf"),
            "left_fielder": game.pos("lf"),
            "shortstop": game.pos("ss"),
            "second_baseman": game.pos("2b"),
            "third_baseman": game.pos("3b"),
            "first_baseman": game.pos("1b"),
            "pitcher": game.pos("p"),
            "catcher": game.pos("c"),
        }

        return position_map[position]

    def select_infielder_bunt(self, game) -> PlayerInGame:
        """Randomly select which infielder fields a bunted ball"""
        position = self.infielder_bunt_choice.choose()

        position_map = {
            "shortstop": game.pos("ss"),
            "second_baseman": game.pos("2b"),
            "third_baseman": game.pos("3b"),
            "first_baseman": game.pos("1b"),
            "pitcher": game.pos("p"),
            "catcher": game.pos("c"),
        }

        return position_map[position]
