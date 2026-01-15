# src/game/rules/common.py


def pitch(game):
    game.current_pitcher.game_stats.pitching.pitch()


def batting_at_bat(batter):
    batter.game_stats.batting.at_bat()
