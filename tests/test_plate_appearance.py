# tests/test_plate_appearance.py
import pytest

from src.game.game import Game
from tests.utils import FakeRNG, FakeTeam
from src.game.events.plate_appearance import PlateAppearanceEndEvent

import pytest


def test_pa_starts_incomplete(game):
    assert not game._plate_appearance_complete


def test_pa_end_event_marks_plate_appearance_complete(game):
    PlateAppearanceEndEvent("walk").apply(game)
    assert game._plate_appearance_complete


def test_pa_end_advances_batter_and_resets_count(game):
    old = game.current_batter

    PlateAppearanceEndEvent("strikeout").apply(game)
    game._post_event()

    assert game.away.players[0] is not game.away.players[1]

    assert game.current_batter is not old
    assert game.count.balls == 0
    assert game.count.strikes == 0
