# src/player/player_constants.py

# Pitching constants
FRESH_THRESHOLD = 0.85
GOOD_THRESHOLD = 0.65
TIRED_THRESHOLD = 0.40
EXHAUSTED_THRESHOLD = 0.01

MOD_FRESH = 1.05
MOD_GOOD = 1.0
MOD_TIRED = 0.9
MOD_EXHAUSTED = 0.75
MOD_ZERO = 0.5

FASTBALL_DRAIN = 0.008

CAP_DMG_LOW = 0.0008
CAP_DMG_HIGH = 0.0018

# General player constants
VALID_ROLES = {"Closer", "Setup", "Middle", "Long", "Specialist", "Utility"}

VALID_BATS = {"L", "R", "S"}
VALID_THROWS = {"L", "R"}
DEFAULT_LEFT_HANDED_PROB = 0.21  # Much higher than general population
