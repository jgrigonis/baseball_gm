# src/game/resolvers/probabilities.py

"""
Baseball event probability constants.

These values tune the likelihood of various outcomes throughout the game.
"""

# Foul ball outcomes
FOUL_TIP_CAUGHT_PROB = 0.05
FOUL_FLY_OUT_WITH_TWO_STRIKES_PROB = 0.05
FOUL_FLY_OUT_BEFORE_TWO_STRIKES_PROB = 0.05
FOULED_OFF_THIRD_STRIKE_PROB = 0.95

# Triple play thresholds
TRIPLE_PLAY_FIRST_SECOND_THRESHOLD = 0.3333
TRIPLE_PLAY_FIRST_THIRD_THRESHOLD = 0.6666

# Tag up probabilities
PROB_TAGUP_FROM_SECOND_FLYOUT = 0.7
PROB_TAGUP_FROM_FIRST_FLYOUT = 0.3

# Base advancement probabilities
SCORE_FROM_SECOND_ON_SINGLE = 0.60  # 60% chance runner scores from 2nd
FIRST_TO_THIRD_ON_SINGLE = 0.35      # 35% chance runner goes 1st to 3rd
SCORE_FROM_FIRST_ON_DOUBLE = 0.21    # 21% chance runner scores from 1st on double
FIRST_TO_HOME_ON_SINGLE = 0.03       # 3% chance runner scores from 1st on single

# Pickoff probabilities
PICKOFF_SUCCESS_PROB = 0.15  # 15% successful
PICKOFF_ERROR_PROB = 0.05    # 5% throwing error
STEAL_ON_PICKOFF_MODIFIER = 1.5

# Steal success rates
STEAL_SECOND_SUCCESS_PROB = 0.75  # 75% success rate
STEAL_THIRD_SUCCESS_PROB = 0.60   # 60% success rate
STEAL_HOME_SUCCESS_PROB = 0.05    # 5% success rate

# Error and throwout rates
BASE_ERROR_RATE = 0.025
BASE_THROWOUT_PROB = 0.05
