# tests/game/test_result_innings.py
"""A finished game's result carries its runs by inning, which the game panel
shows as a line score."""

import logging
from random import Random

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from src.util.logger import setup_logger
from tests.factories.team_record_factory import make_team_record


def test_runs_by_inning_add_up_to_the_final_score():
    logger = setup_logger(
        name="game",
        level=logging.WARNING,
        console_level=logging.WARNING,
        log_to_file=False,
    )
    home_record, away_record = make_team_record(), make_team_record()
    for seed in range(20):
        home = TeamInGameFactory.from_record(home_record)
        away = TeamInGameFactory.from_record(away_record)
        game = Game(home, away, rng=Random(seed), logger=logger)
        game.home.set_lineup()
        game.away.set_lineup()

        result = game.play()

        assert sum(result.away_innings) == result.away_score
        assert sum(result.home_innings) == result.home_score
        assert len(result.away_innings) <= result.innings_played
        assert len(result.home_innings) <= result.innings_played
