"""Pinch hitters (src/game/bench.py): who goes up, when, and what happens
to the lineup."""

import random
from random import Random

from src.game import bench
from src.game.game import Game
from src.team.team_in_game import TeamInGame
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

HITTER_POSITIONS = ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf", "dh"]


def _team(bench_positions=("of", "if", "c", "1b")) -> TeamInGame:
    rng = random.Random(7)
    players = [make_player_record(position=p, rng=rng) for p in HITTER_POSITIONS]
    players += [make_player_record(position=p, rng=rng) for p in bench_positions]
    players += [make_player_record(position="sp", rng=rng) for _ in range(5)]
    players += [make_player_record(position="rp", rng=rng) for _ in range(8)]
    return TeamInGame(make_team_record(players=players))


def _game(inning=8, top=True, away=2, home=3) -> Game:
    away_team, home_team = _team(), _team()
    away_team.set_lineup()
    home_team.set_lineup()
    game = Game(home_team, away_team, rng=Random(1))
    game.inning.number = inning
    game.inning.top = top
    game.score._away_innings = [away]
    game.score._home_innings = [home]
    game._sync_players()
    return game


def _make_bench_bat(game: Game, value: float):
    """The batting team's first bench hitter, with this bat."""
    team = game.bat_team
    sub = sorted(team.bench_players, key=lambda p: p.id)[0]
    for p in team.bench_players:
        p.ratings["overall_offense"] = 0
    sub.ratings["overall_offense"] = value
    batter = game.current_batter.player
    position = batter.current_position
    sub.ratings[position] = batter.ratings.get(position, 0)
    sub.bats = sub.throws = "R"
    return sub, batter


def test_pinch_hitter_goes_up_late_in_a_close_game():
    game = _game()
    batter = game.current_batter.player
    batter.ratings["overall_offense"] = 30
    sub, _ = _make_bench_bat(game, 60)
    assert bench.pinch_hitter(game) is sub


def test_no_pinch_hitter_early_or_in_a_blowout():
    game = _game(inning=5)
    game.current_batter.player.ratings["overall_offense"] = 30
    _make_bench_bat(game, 60)
    assert bench.pinch_hitter(game) is None

    game = _game(away=1, home=9)
    game.current_batter.player.ratings["overall_offense"] = 30
    _make_bench_bat(game, 60)
    assert bench.pinch_hitter(game) is None


def test_small_edge_stays_on_the_bench():
    game = _game()
    game.current_batter.player.ratings["overall_offense"] = 50
    _make_bench_bat(game, 53)
    assert bench.pinch_hitter(game) is None


def test_platoon_edge_counts():
    """A lefty bat against a lefty, with an equal righty on the bench:
    the platoon edge sends the righty up."""
    game = _game(inning=9)
    game.current_pitcher.throws = "L"
    batter = game.current_batter.player
    batter.bats = "L"
    batter.ratings["overall_offense"] = 55
    sub, _ = _make_bench_bat(game, 55)
    assert bench.pinch_hitter(game) is sub
    game.current_pitcher.throws = "R"
    assert bench.pinch_hitter(game) is None


def test_tired_or_used_bench_players_dont_pinch_hit():
    game = _game()
    game.current_batter.player.ratings["overall_offense"] = 30
    sub, _ = _make_bench_bat(game, 60)
    game.bat_team.removed_ids.add(sub.id)
    assert bench.pinch_hitter(game) is not sub


def test_pinch_hitter_takes_the_slot_and_position():
    game = _game()
    slot = game.current_batter
    batter = slot.player
    batter.ratings["overall_offense"] = 30
    position = batter.current_position
    sub, _ = _make_bench_bat(game, 60)
    game._consider_pinch_hitter()
    assert game.current_batter.player is sub
    assert sub.current_position == position
    assert sub.game_stats.batting.game_played == 1
    assert batter.id in game.bat_team.removed_ids
    assert batter not in game.bat_team.bench_players


def test_bench_is_todays_roster_only():
    team = _team()
    everyone = {p.id for p in team.players}
    team.set_lineup(restrict_to_ids=everyone)
    bench_ids = {p.id for p in team.bench_players}
    farmhand = sorted(bench_ids)[0]
    team.set_lineup(restrict_to_ids=everyone - {farmhand})
    assert farmhand not in {p.id for p in team.bench_players}


def test_games_still_finish_with_pinch_hitters():
    for seed in range(20):
        away_team, home_team = _team(), _team()
        away_team.set_lineup()
        home_team.set_lineup()
        game = Game(home_team, away_team, rng=Random(seed))
        game.play()
        for team in (home_team, away_team):
            ids = [s.player.id for s in team.lineup]
            assert len(set(ids)) == len(ids)
            assert not set(ids) & team.removed_ids


# ---------------------------------------------------------------- runners


def _runner_game(inning=9, away=2, home=3):
    """Top of the inning, the batting team down a run with its second
    hitter on first: he's the tying run."""
    game = _game(inning=inning, away=away, home=home)
    team = game.bat_team
    runner = team.lineup[1].player
    game.bases.place_runner(1, runner)
    return game, runner


def _fast_bench(game, speed=95):
    team = game.bat_team
    sub = sorted(team.bench_players, key=lambda p: p.id)[0]
    for p in team.bench_players:
        p.skills = {**p.skills, "speed": 20, "base_running": 20}
    sub.skills = {**sub.skills, "speed": speed, "base_running": speed}
    return sub


def _slow(player):
    player.skills = {**player.skills, "speed": 20, "base_running": 20}


def test_fast_runner_goes_in_for_a_slow_tying_run():
    game, runner = _runner_game()
    _slow(runner)
    sub = _fast_bench(game)
    # His bat and glove don't matter much this late.
    sub.ratings["overall_offense"] = runner.ratings["overall_offense"]
    sub.ratings[runner.current_position] = runner.ratings.get(
        runner.current_position, 0
    )
    assert bench.pinch_runners(game) == [(1, runner, sub)]


def test_no_pinch_runner_when_his_run_doesnt_matter():
    game, runner = _runner_game(away=1, home=5)
    _slow(runner)
    _fast_bench(game)
    assert bench.pinch_runners(game) == []


def test_no_pinch_runner_for_a_fast_runner_or_early():
    game, runner = _runner_game()
    runner.skills = {**runner.skills, "speed": 85, "base_running": 85}
    _fast_bench(game)
    assert bench.pinch_runners(game) == []

    game, runner = _runner_game(inning=5)
    _slow(runner)
    _fast_bench(game)
    assert bench.pinch_runners(game) == []


def test_pinch_runner_takes_the_base_slot_and_position():
    game, runner = _runner_game()
    _slow(runner)
    sub = _fast_bench(game)
    sub.ratings["overall_offense"] = runner.ratings["overall_offense"]
    position = runner.current_position
    sub.ratings[position] = runner.ratings.get(position, 0)
    pitcher = game.current_pitcher
    runner.responsible_pitcher = pitcher
    game._consider_pinch_runners()
    assert game.bases.runner_on(1) is sub
    assert sub.responsible_pitcher is pitcher
    assert game.bat_team.lineup[1].player is sub
    assert sub.current_position == position
    assert sub.game_stats.batting.game_played == 1
    assert runner.id in game.bat_team.removed_ids
    assert sub.id in game.batters_this_game
