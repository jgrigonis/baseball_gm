# src/player/player_constants.py

# Pitching fatigue AND player energy constants
FRESH_THRESHOLD = 0.85
GOOD_THRESHOLD = 0.65
TIRED_THRESHOLD = 0.40
EXHAUSTED_THRESHOLD = 0.01

# Piitching MODs
MOD_FRESH = 1.05
MOD_GOOD = 1.0
MOD_TIRED = 0.9
MOD_EXHAUSTED = 0.75
MOD_ZERO = 0.5

# Pitching fatigue constants
FASTBALL_DRAIN = 0.008

CAP_DMG_LOW = 0.0008
CAP_DMG_HIGH = 0.0018

# Energy injury mod
MOD_INJURY_FRESH = 0.80  # Slightly protected
MOD_INJURY_GOOD = 1.0  # Normal
MOD_INJURY_TIRED = 1.40
MOD_INJURY_EXHAUSTED = 2.00
MOD_INJURY_ZERO = 3.00

# BATTING and Fielding mods
BAT_FRESH = 1.03  # Small bonus when fresh
BAT_GOOD = 1.0
BAT_TIRED = 0.92  # 8% worse
BAT_EXHAUSTED = 0.80  # 20% worse
BAT_ZERO = 0.60  # 40% worse

STREAK_PENALTY = (
    0.005  # Penalty multplier after a STREAK_GAMES + 1 game streak with no rest
)
STREAK_GAMES = 4

# General player constants
VALID_ROLES = {"Closer", "Setup", "Middle", "Long", "Specialist", "Utility"}

VALID_BATS = {"L", "R", "S"}
VALID_THROWS = {"L", "R"}
DEFAULT_LEFT_HANDED_PROB = 0.21  # Much higher than general population
START_AGE = 17
