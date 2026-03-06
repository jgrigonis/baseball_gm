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
FIRST_TO_THIRD_ON_SINGLE = 0.35  # 35% chance runner goes 1st to 3rd
SCORE_FROM_FIRST_ON_DOUBLE = 0.21  # 21% chance runner scores from 1st on double
FIRST_TO_HOME_ON_SINGLE = 0.03  # 3% chance runner scores from 1st on single

# Pickoff probabilities
PICKOFF_SUCCESS_PROB = 0.09  # 9% successful
PICKOFF_ERROR_PROB = 0.02  # 2% throwing error
STEAL_ON_PICKOFF_MODIFIER = 1.5

# Steal success rates
STEAL_SECOND_SUCCESS_PROB = 0.81  # 81% success rate
STEAL_THIRD_SUCCESS_PROB = 0.63  # 63% success rate
STEAL_HOME_SUCCESS_PROB = 0.05  # 5% success rate

# Error and throwout rates
BASE_ERROR_RATE = 0.062
BASE_THROWOUT_PROB = 0.24

# Favor ss over 2b for covering second.
SS_OVER_2B_PROB = 0.55

# Probability for strategy decisions
# Pickoff
BASE_PICKOFF_ATTEMPT_PROB = 0.01  # 1% per pitch

# Steal
BASE_STEAL_SECOND_PROB = 0.058  # 5.8% from first
BASE_STEAL_THIRD_PROB = 0.005  # 0.5% from second
BASE_STEAL_HOME_PROB = 0.00001  # 0.0001% from third
STEAL_FULL_COUNT_MOD = 1.5
STEAL_BEHIND_COUNT_MOD = 0.5
STEAL_TWO_OUT_MOD = 0.6
STEAL_CLOSE_GAME_MOD = 1.27
STEAL_BLOWOUT_MOD = 0.8
# Double Steal
DOUBLE_STEAL_FIRST_THIRD = 0.003
DOUBLE_STEAL_SECOND_THIRD = 0.00001
DOUBLE_STEAL_FIRST_SECOND = 0.001
DOUBLE_STEAL_TWO_OUT_MOD = 0.2

# Bunt
BUNT_PROB = 0.04
BUNT_ON_FIRST_MOD = 2.0
BUNT_ON_SECOND_MOD = 2.5
BUNT_CLOSE_GAME_MOD = 1.5
BUNT_LATE_INNING_MOD = 1.3

# Intentional Walk
IBB_PROB = 0.0001
IBB_POWERFUL = 0.001
IBB_POWERFUL_LATE_INNING = 0.002
IBB_TWO_OUT_MODIFIER = 1.2
IBB_STRIKES_MODIFIER = 0.01
IBB_MORE_STRIKES_MOD = 0.01

# Pitchout
PITCHOUT_PROB = 0.001
PITCHOUT_FAST_MOD = 4
PITCHOUT_BALLS_OVER_STRIKES = 0.1

# Hit and Run
HNR_PROB = 0.02
HNR_CONTACT_MOD = 1.5
HNR_SPEED_MOD = 1.5
HNR_FAVORABLE_COUNT_MOD = 1.3

# Pitcher Change
PITCH_COUNT_THRESHOLD = 100
CLOSER_ENTRANCE_PROB = 0.92
