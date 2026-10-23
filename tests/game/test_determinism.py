# tests/game/test_determinism.py
import logging
from random import Random

from src.game.game import Game
from src.game.resolvers.fielder_selector import FielderSelector
from src.team.team_in_game_factory import TeamInGameFactory
from src.util.logger import setup_logger
from src.util.weighted_choice import WeightedChoice
from tests.factories.team_record_factory import make_team_record


def test_fielder_selector_choices_all_use_given_rng():
    rng = Random(1)
    fs = FielderSelector(rng)
    choices = [v for v in vars(fs).values() if isinstance(v, WeightedChoice)]

    assert choices
    for choice in choices:
        assert choice.rng is rng


def _fielding_by_player(home_record, away_record, seed):
    logger = setup_logger(
        name="game",
        level=logging.WARNING,
        console_level=logging.WARNING,
        log_to_file=False,
    )
    home = TeamInGameFactory.from_record(home_record)
    away = TeamInGameFactory.from_record(away_record)
    game = Game(home, away, rng=Random(seed), logger=logger)
    game.home.set_lineup()
    game.away.set_lineup()
    game.play()

    return {
        p.record.id: (p.game_stats.fielding.putouts, p.game_stats.fielding.assists)
        for p in home.players + away.players
    }


def test_same_seed_gives_same_fielding_credit():
    home_record = make_team_record()
    away_record = make_team_record()

    for seed in range(20):
        first = _fielding_by_player(home_record, away_record, seed)
        second = _fielding_by_player(home_record, away_record, seed)
        assert first == second, f"fielding credit differs for seed {seed}"
