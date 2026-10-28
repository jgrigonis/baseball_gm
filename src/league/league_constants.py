# src/league/league_constants.py

SEASON_LENGTH = 162

# A mid-season break with no games, placed at the end of the round nearest
# game ALL_STAR_BREAK_AFTER_GAMES (MLB's falls about 59% of the way in).
ALL_STAR_BREAK_AFTER_GAMES = 96
ALL_STAR_BREAK_DAYS = 4

# Trades close at the end of the round nearest game TRADE_DEADLINE_AFTER_GAMES,
# two thirds of the way in, like MLB's late-July deadline. Every sim stops
# there, and in multiplayer the next Decision Window is
# TRADE_DEADLINE_WINDOW_MULTIPLIER times as long as usual.
TRADE_DEADLINE_AFTER_GAMES = 108
TRADE_DEADLINE_WINDOW_MULTIPLIER = 3
