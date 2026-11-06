# tests/game/test_facilities_injuries.py
"""Game(injury_mults=...): a team's Facilities department moves its
players' chance of getting hurt (src/league/budget.py)."""

from random import Random

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

SIDE = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "1b"] + ["sp"] * 8


def _team(rng):
    players = [make_player_record(position=pos, rng=rng) for pos in SIDE]
    return TeamInGameFactory.from_record(make_team_record(players=players))


def _injuries(seed, mults):
    rng = Random(seed)
    home, away = _team(rng), _team(rng)
    game = Game(home, away, rng=Random(seed), injury_mults=mults(home, away))
    home.set_lineup()
    away.set_lineup()
    game.play()
    team = {p.id: "home" for p in home.players} | {p.id: "away" for p in away.players}
    return [team[i[0]] for i in game.new_injuries]


def test_a_team_with_no_injury_risk_gets_none():
    hurt = []
    for seed in range(40):
        hurt += _injuries(seed, lambda h, a: {h.record.id: 0.0, a.record.id: 50.0})
    assert "home" not in hurt and "away" in hurt
