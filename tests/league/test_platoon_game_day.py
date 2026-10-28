# tests/league/test_platoon_game_day.py
"""Game day uses the opposing starter's throwing hand for platoons."""

from types import SimpleNamespace

from src.league.play_season import _throws


def test_throws_finds_the_starters_hand():
    team = SimpleNamespace(
        players=[
            SimpleNamespace(id="a", throws="L"),
            SimpleNamespace(id="b", throws="r"),
        ]
    )
    assert _throws(team, "a") == "L"
    assert _throws(team, "b") == "R"
    assert _throws(team, "missing") is None
    assert _throws(team, None) is None
