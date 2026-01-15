# tests/game/test_simplest_game.py
import logging
import pytest
from random import Random

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.team_record_factory import make_team_record

@pytest.fixture
def team1():
    return TeamInGameFactory.from_record(make_team_record())

@pytest.fixture
def team2():
    return TeamInGameFactory.from_record(make_team_record())

# game = Game(team1, team2, rng=Random(2))
# game.dbg = logging.DEBUG
# game.home.set_lineup()
# game.away.set_lineup()
# game.play()


def test_game_advances_inning(team1, team2):
    game = Game(team1, team2, rng=Random(2))
    game.home.set_lineup()
    game.away.set_lineup()
    game.play()
