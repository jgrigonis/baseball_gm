# tests/test_score.py
from tests.utils import fake_game

from src.game.events.scoring import RunScoredEvent
from src.player.player_in_game import PlayerInGame
from tests.factories.player_record_factory import make_player_record


def test_score_uses_inning_state():
    game = fake_game()
    game.inning.number = 3
    game.inning.top = False

    RunScoredEvent(
        runner=PlayerInGame(make_player_record()),
        rbi_batter=PlayerInGame(make_player_record()),
        reason="test",
        pitcher=PlayerInGame(make_player_record()),
        responsible_pitcher=PlayerInGame(make_player_record()),
    ).apply(game)

    assert game.score.home == 1
    assert game.score.away == 0


def test_home_run_charged_to_pitcher_on_the_mound():
    """A batter who reached earlier off the starter, then homers off a
    reliever: the run is the reliever's, not the starter's."""
    from src.game.events.runners import RunnerAdvancedEvent

    starter = PlayerInGame(make_player_record())
    reliever = PlayerInGame(make_player_record())
    batter = PlayerInGame(make_player_record())
    batter.responsible_pitcher = starter  # left over from an earlier single

    (scored,) = RunnerAdvancedEvent(
        runner=batter, pitcher=reliever, from_base=None, to_base=4
    ).apply(fake_game())

    assert scored.responsible_pitcher is reliever


def test_runner_already_on_base_stays_charged_to_his_pitcher():
    from src.game.events.runners import RunnerAdvancedEvent

    starter = PlayerInGame(make_player_record())
    reliever = PlayerInGame(make_player_record())
    runner = PlayerInGame(make_player_record())
    runner.responsible_pitcher = starter
    game = fake_game()
    game.bases.place_runner(3, runner)

    (scored,) = RunnerAdvancedEvent(
        runner=runner, pitcher=reliever, from_base=3, to_base=4
    ).apply(game)

    assert scored.responsible_pitcher is starter
