# src/game/rules/common.py


def pitch(game):
    game.current_pitcher.stats.pitching.pitch()


def batting_at_bat(batter):
    batter.stats.batting.at_bat()
