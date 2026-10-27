# tests/game/test_complete_games.py
from random import Random
from types import SimpleNamespace

import pytest

from src.game.game import Game
from src.game.pitcher_appearance import PitcherAppearance
from src.stats.pitching_stats import PitchingStats
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.team_record_factory import make_team_record


class _Pitcher:
    def __init__(self, outs=27, hits=5, runs=2, started=1):
        self.game_stats = SimpleNamespace(
            pitching=PitchingStats(
                outs=outs, hits=hits, runs=runs, game_started=started
            )
        )


def _credit(*appearances):
    Game._credit_complete_games(SimpleNamespace(pitcher_appearances=list(appearances)))


def _pitching(p):
    s = p.game_stats.pitching
    return s.complete_game, s.shut_out, s.no_hitter


class TestCreditCompleteGames:
    def test_only_pitcher_gets_complete_game(self):
        p = _Pitcher()
        _credit(PitcherAppearance(p, "A", 1))
        assert _pitching(p) == (1, 0, 0)

    def test_no_runs_is_a_shutout(self):
        p = _Pitcher(runs=0)
        _credit(PitcherAppearance(p, "A", 1))
        assert _pitching(p) == (1, 1, 0)

    def test_no_hits_is_a_no_hitter(self):
        p = _Pitcher(hits=0, runs=1)
        _credit(PitcherAppearance(p, "A", 1))
        assert _pitching(p) == (1, 0, 1)

    def test_no_hitter_needs_nine_innings(self):
        # A road loser who went eight hitless innings
        p = _Pitcher(outs=24, hits=0, runs=1)
        _credit(PitcherAppearance(p, "A", 1))
        assert _pitching(p) == (1, 0, 0)

    def test_relieved_starter_gets_nothing(self):
        starter = _Pitcher(outs=24, hits=0, runs=0)
        reliever = _Pitcher(outs=3, hits=0, runs=0, started=0)
        _credit(
            PitcherAppearance(starter, "A", 1),
            PitcherAppearance(reliever, "A", 9),
        )
        assert _pitching(starter) == (0, 0, 0)
        assert _pitching(reliever) == (0, 0, 0)

    def test_teams_are_credited_separately(self):
        a = _Pitcher(runs=0)
        b1 = _Pitcher(outs=21)
        b2 = _Pitcher(outs=3, started=0)
        _credit(
            PitcherAppearance(a, "A", 1),
            PitcherAppearance(b1, "B", 1),
            PitcherAppearance(b2, "B", 8),
        )
        assert _pitching(a) == (1, 1, 0)
        assert _pitching(b1) == (0, 0, 0)


@pytest.mark.parametrize("seed", [3, 55, 420])
def test_played_game_credits_only_sole_pitchers(seed):
    home = TeamInGameFactory.from_record(make_team_record(size=14))
    away = TeamInGameFactory.from_record(make_team_record(size=14))
    game = Game(home, away, rng=Random(seed))
    game.home.set_lineup()
    game.away.set_lineup()
    game.play()

    for team_id in {a.team_id for a in game.pitcher_appearances}:
        pitchers = {a.pitcher for a in game.pitcher_appearances if a.team_id == team_id}
        for p in pitchers:
            s = p.game_stats.pitching
            assert s.complete_game == (len(pitchers) == 1)
            assert s.shut_out == (s.complete_game and s.runs == 0)
            assert s.no_hitter == (s.complete_game and s.hits == 0 and s.outs >= 27)
