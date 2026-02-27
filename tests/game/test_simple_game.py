# tests/simple_game.py
import logging
from random import Random

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.team_record_factory import make_team_record
from src.player.player_formatters import PlayerTableFormatter

def test_simple_game():
    team1 = TeamInGameFactory.from_record(make_team_record(size=10))

    team2 = TeamInGameFactory.from_record(make_team_record(size=10))

    print("Team1")

    print(PlayerTableFormatter.header_skills())
    for player in team1.players:
        print(PlayerTableFormatter.hor_skills(player))
    print(PlayerTableFormatter.header_ratings())
    for player in team1.players:
        print(PlayerTableFormatter.hor_ratings(player))
    print("Team2")
    print(PlayerTableFormatter.header_skills())
    for player in team2.players:
        print(PlayerTableFormatter.hor_skills(player))
    print(PlayerTableFormatter.header_ratings())
    for player in team2.players:
        print(PlayerTableFormatter.hor_ratings(player))
    # game = Game(team1, team2, rng=Random(5))
    # game = Game(team1, team2, rng=Random(67))
    # game = Game(team1, team2, rng=Random(420))
    # game = Game(team1, team2, rng=Random(69))
    # game = Game(team1, team2, rng=Random(18))
    # game = Game(team1, team2, rng=Random(24))
    game = Game(team2, team1, rng=Random(55))
    game.dbg = logging.DEBUG
    game.home.set_lineup()
    game.away.set_lineup()
    game.play()
    print(game.pitcher_appearances)
    print(game.lead_changes)
