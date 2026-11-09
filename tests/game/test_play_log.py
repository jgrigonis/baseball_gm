# tests/game/test_play_log.py
"""The play-by-play the engine keeps for the game panel (src/game/play_log.py)
and the words the panel puts on it (src/api/view_models/play_by_play.py)."""

from random import Random

import pytest

from src.api.view_models import play_by_play
from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

TEAM = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "1b"] + ["sp"] * 10


def _play(seed):
    rng = Random(seed)
    players = lambda: [make_player_record(position=p, rng=rng) for p in TEAM]
    home = TeamInGameFactory.from_record(make_team_record(players=players()))
    away = TeamInGameFactory.from_record(make_team_record(players=players()))
    game = Game(home, away, rng=Random(seed), injuries_enabled=False)
    home.set_lineup()
    away.set_lineup()
    game.play()
    return game, home, away


@pytest.mark.parametrize("seed", range(8))
def test_plays_account_for_every_run_and_plate_appearance(seed):
    game, home, away = _play(seed)
    plays = game.play_log.plays
    assert plays[-1]["sc"] == [game.score.away, game.score.home]
    assert sum(len(p.get("s", [])) for p in plays) == game.score.away + game.score.home
    pa = sum(
        p.game_stats.batting.plate_appearances for t in (home, away) for p in t.players
    )
    assert sum(1 for p in plays if p["b"]) == pa
    # Every play reads as a sentence
    for p in plays:
        assert play_by_play.describe(p).endswith(".")


def test_build_groups_half_innings_and_places_moves_between_plays():
    game = {
        "away_team_id": "A",
        "home_team_id": "H",
        "away_mascot": "Ants",
        "home_mascot": "Hawks",
    }
    plays = [
        {
            "i": 1,
            "t": True,
            "b": "A. One",
            "r": "strikeout",
            "o": 1,
            "sc": [0, 0],
            "g": 4,
        },
        {
            "i": 1,
            "t": True,
            "b": "A. Two",
            "r": "home_run",
            "o": 1,
            "sc": [2, 0],
            "g": 4,
            "s": ["A. Zed", "A. Two"],
        },
        {
            "i": 1,
            "t": False,
            "b": "H. One",
            "r": "ground_out",
            "o": 1,
            "sc": [2, 0],
            "g": 5,
            "f": ["1b", "ss"],
        },
    ]
    events = [
        {"event_type": "lineup_set", "team_id": "A", "reason": "9 players"},
        {"event_type": "lineup_set", "team_id": "H", "reason": "9 players"},
        {"event_type": "pitcher_start", "team_id": "A", "reason": "X starts"},
        {"event_type": "pitcher_start", "team_id": "H", "reason": "Y starts"},
        {"event_type": "pitching_change", "team_id": "H", "reason": "Z replaces Y"},
    ]
    halves = play_by_play.build(plays, events, game)
    assert [h["label"] for h in halves] == ["Top 1st", "Bottom 1st"]
    top, bottom = halves
    assert top["runs"] == 2 and top["hits"] == 1 and top["team"] == "Ants"
    assert top["items"][1]["text"] == "A. Two hits a two-run homer, A. Zed scores."
    assert top["items"][1]["score"] == "2–0"
    # The change came after the homer, before the bottom half's first play
    assert bottom["items"][0]["kind"] == "event"
    assert bottom["items"][1]["text"] == "H. One grounds out, short to first."


def test_notes_and_a_half_ended_on_the_bases():
    play = {
        "i": 3,
        "t": False,
        "b": None,
        "r": None,
        "o": 3,
        "sc": [0, 0],
        "n": [["sb", "B. Fast", 2], ["cs", "B. Fast", 3]],
    }
    assert play_by_play.describe(play) == (
        "B. Fast steals second. B. Fast is caught stealing third."
    )
