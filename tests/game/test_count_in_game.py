# tests/game/test_count_in_game.py
from src.game.events.strike import StrikeEvent
from src.game.events.ball import BallEvent


def test_ball_increments_balls(game):
    BallEvent().apply(game)
    assert game.count.balls == 1


def test_strike_increments_strikes(game):
    StrikeEvent().apply(game)
    assert game.count.strikes == 1
