# src/league/league_constants.py

SEASON_LENGTH = 162

# The year a new league's first season is played. Existing leagues keep the
# years stored with their seasons; this only applies at the start.
LEAGUE_START_YEAR = 2027

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

# Past seasons a new league starts with (src/league/backstory/), generated
# from its rosters rather than played. An admin can change it per league
# before the start; 0 starts with no history and a random first draft order.
DEFAULT_BACKSTORY_YEARS = 10
MAX_BACKSTORY_YEARS = 10
