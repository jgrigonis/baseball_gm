# tests/game/test_ghost_runner.py
"""Game(ghost_runner=True): the regular-season extra-innings rule. From the
10th on, each half-inning starts with a runner on second: the batter in the
lineup spot before the leadoff hitter. His run is unearned."""

from random import Random

from src.game.bases import SECOND
from src.game.events.runners import ReachedBaseEvent, RunnerAdvancedEvent
from src.game.events.scoring import RunScoredEvent
from src.game.game import GHOST_RUNNER_INNING, Game
from src.player.player_in_game import PlayerInGame
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record
from tests.utils import fake_game

TEAM = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "1b"] + ["sp"] * 10


class _Watched(Game):
    """Records every ghost runner: (inning, top, runner, who he should be)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ghosts = []

    def _place_ghost_runner(self):
        lineup = self.bat_team.lineup
        expected = lineup[(self.bat_team.batter_index - 1) % len(lineup)].player
        assert self.bases.is_empty
        super()._place_ghost_runner()
        self.ghosts.append(
            (
                self.inning.number,
                self.inning.top,
                self.bases.runner_on(SECOND),
                expected,
            )
        )


def _play(seed, ghost_runner):
    rng = Random(seed)
    players = lambda: [make_player_record(position=p, rng=rng) for p in TEAM]
    home = TeamInGameFactory.from_record(make_team_record(players=players()))
    away = TeamInGameFactory.from_record(make_team_record(players=players()))
    game = _Watched(
        home, away, rng=Random(seed), injuries_enabled=False, ghost_runner=ghost_runner
    )
    home.set_lineup()
    away.set_lineup()
    game.play()
    return game


def _extra_inning_games(ghost_runner, want=6):
    games = []
    for seed in range(400):
        game = _play(seed, ghost_runner)
        if game.inning.number >= GHOST_RUNNER_INNING:
            games.append(game)
            if len(games) == want:
                break
    assert games, "no extra-inning games in the seeds tried"
    return games


def test_runner_on_second_every_extra_half_inning():
    for game in _extra_inning_games(ghost_runner=True):
        halves = {(inning, top) for inning, top, _, _ in game.ghosts}
        expected = {
            (inning, top)
            for inning in range(GHOST_RUNNER_INNING, game.inning.number + 1)
            for top in (True, False)  # a tied game always plays both halves
        }
        assert halves == expected
        for _, _, runner, should_be in game.ghosts:
            assert runner is should_be
        assert all(inning >= GHOST_RUNNER_INNING for inning, _, _, _ in game.ghosts)


def test_no_ghost_runner_without_the_rule():
    for game in _extra_inning_games(ghost_runner=False, want=3):
        assert game.ghosts == []


def test_ghost_runner_run_is_unearned():
    pitcher = PlayerInGame(make_player_record())
    ghost = PlayerInGame(make_player_record())
    ghost.responsible_pitcher = pitcher
    ghost.ghost_runner = True
    game = fake_game()
    game.bases.place_runner(SECOND, ghost)

    (scored,) = RunnerAdvancedEvent(
        runner=ghost, pitcher=pitcher, from_base=SECOND, to_base=4
    ).apply(game)

    assert scored.responsible_pitcher is pitcher
    assert scored.earned is False
    scored.apply(game)
    assert pitcher.game_stats.pitching.runs == 1
    assert pitcher.game_stats.pitching.earned_runs == 0
    assert ghost.ghost_runner is False


def test_ghost_who_bats_again_and_scores_is_earned():
    """Once he's reached base on his own, he's a normal runner."""
    pitcher = PlayerInGame(make_player_record())
    ghost = PlayerInGame(make_player_record())
    ghost.ghost_runner = True
    game = fake_game()

    ReachedBaseEvent(
        runner=ghost, base=1, reason="single", responsible_pitcher=pitcher
    ).apply(game)
    game.bases.place_runner(1, ghost)
    (scored,) = RunnerAdvancedEvent(
        runner=ghost, pitcher=pitcher, from_base=1, to_base=4
    ).apply(game)

    assert scored.earned is True


def test_unearned_flag_on_run_scored_event():
    pitcher = PlayerInGame(make_player_record())
    RunScoredEvent(
        runner=PlayerInGame(make_player_record()),
        rbi_batter=None,
        reason="test",
        pitcher=pitcher,
        responsible_pitcher=pitcher,
        earned=False,
    ).apply(fake_game())
    assert pitcher.game_stats.pitching.runs == 1
    assert pitcher.game_stats.pitching.earned_runs == 0
