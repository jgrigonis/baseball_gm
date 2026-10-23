# tests/game/test_game_exceptions.py

import pytest

import src.game.game_exceptions as game_exceptions


def test_message_is_kept_on_the_exception(capsys):
    """The message used to be printed to stdout and dropped from the exception."""
    with pytest.raises(game_exceptions.InvalidBase, match="bad base 'X'"):
        raise game_exceptions.InvalidBase("bad base 'X'")

    assert capsys.readouterr().out == ""


def test_message_is_optional():
    exc = game_exceptions.BadPositionException()
    assert isinstance(exc, game_exceptions.GameException)
    assert str(exc) == ""
