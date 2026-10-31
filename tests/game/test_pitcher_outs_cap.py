# tests/game/test_pitcher_outs_cap.py
"""Game(max_pitcher_outs=...): every pitcher comes out once he has that many
outs, as long as there's someone left to bring in (the All-Star Game)."""

from random import Random

import pytest

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

# An All-Star side: two at each position, a DH, and nine pitchers.
SIDE = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"] * 2 + ["1b"] + ["sp"] * 9


def _team(rng):
    players = [make_player_record(position=pos, rng=rng) for pos in SIDE]
    return TeamInGameFactory.from_record(make_team_record(players=players))


def _play(seed, cap):
    rng = Random(seed)
    home, away = _team(rng), _team(rng)
    game = Game(
        home, away, rng=Random(seed), injuries_enabled=False, max_pitcher_outs=cap
    )
    home.set_lineup()
    away.set_lineup()
    game.play()
    return game


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_pitcher_comes_out_after_the_cap(seed):
    game = _play(seed, 4)
    for team in (game.home, game.away):
        outs = [
            a.outs_recorded
            for a in game.pitcher_appearances
            if a.team_id == team.record.id
        ]
        assert len(outs) >= 6
        # A double play can take him one past it.
        assert all(n <= 5 for n in outs[:-1])
