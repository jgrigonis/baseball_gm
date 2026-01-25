# tests/test_plate_appearance.py
from tests.factories.player_record_factory import make_player_record
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.player.player_in_game import PlayerInGame


def test_pa_starts_incomplete(game):
    assert not game._plate_appearance_complete


def test_pa_end_event_marks_plate_appearance_complete(game):
    PlateAppearanceEndEvent(
        reason="walk", batter=PlayerInGame(make_player_record())
    ).apply(game)
    assert game._plate_appearance_complete


def test_pa_end_advances_batter_and_resets_count(game):
    old = game.current_batter

    PlateAppearanceEndEvent(
        reason="strikeout", batter=PlayerInGame(make_player_record())
    ).apply(game)
    game._post_event()

    assert game.away.players[0] is not game.away.players[1]

    assert game.current_batter is not old
    assert game.count.balls == 0
    assert game.count.strikes == 0
