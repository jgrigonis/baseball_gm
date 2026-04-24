# src/game/resolvers/probabilities.py

"""
Baseball event probability constants.

These values tune the likelihood of various outcomes throughout the game.
"""

# Pitch outcome weights
BALL_PROB = 15000
FOUL_PROB = 5100
HOME_RUN_PROB = 280
HBP_PROB = 118
BALK_PROB = 0
ILLEGAL_PITCH_PROB = 0
CATCHER_INTERFERENCE_PROB = 3
WILD_PITCH_PROB = 275
PASSED_BALL_PROB = 69
IN_PLAY_PROB = 5875
STRIKE_PROB = 11500

# In play outcome weights
FLY_OUT_PROB = 4440
GROUND_OUT_PROB = 1740
SINGLE_PROB = 1320
DOUBLE_PROB = 372
TRIPLE_PROB = 51
DOUBLE_PLAY_PROB = 0
FIELDERS_CHOICE_PROB = 0
SAC_FLY_PROB = 0
SAC_BUNT_PROB = 0
TRIPLE_PLAY_PROB = 0

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
STEAL_SECOND_SUCCESS_PROB = 0.74  # 74% success rate
STEAL_THIRD_SUCCESS_PROB = 0.83  # 83% success rate
STEAL_HOME_SUCCESS_PROB = 0.25  # 25% success rate

# Error and throwout rates
BASE_ERROR_RATE = 0.062
BASE_THROWOUT_PROB = 0.24

# Favor ss over 2b for covering second.
SS_OVER_2B_PROB = 0.55

# Probability for strategy decisions
# Pickoff
BASE_PICKOFF_ATTEMPT_PROB = 0.01  # 1% per pitch

# Steal
BASE_STEAL_SECOND_PROB = 0.020  # 2.0% from first
BASE_STEAL_THIRD_PROB = 0.005  # 0.5% from second
BASE_STEAL_HOME_PROB = 0.00001  # 0.0001% from third
STEAL_FULL_COUNT_MOD = 1.6
STEAL_BEHIND_COUNT_MOD = 0.4
STEAL_TWO_OUT_MOD = 0.5
STEAL_CLOSE_GAME_MOD = 1.27
STEAL_BLOWOUT_MOD = 0.7
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

# Injury/Fatigue
INJURY_BASE_PROB = 0.00025  # per plate appearance
FATIGUE_MULTIPLIER = 1.6  # injury multiplier for fatigued players
LOW_ENERGY = 0.50  # threshold for low player energy
BASE_ENERGY_DEPLETION = 0.035 # base energy depletion per plate appearance
DURABILITY_MOD = 0.3 # Modifies the multiplier for injury chances by up to 30 percent in either direction
FREE_STREAK_DAYS = 3 # Number of days before a streak penalty is applied to energy drain
MAX_STREAK_PENALTY = 0.05 # Max amount of energy drained during a long streak
ENERGY_PENALTY_PER_STREAK_DAY = 0.015 # After FREE_STREAK_DAYS, each day's energy drain penalty is multiplied by this, until it crosses MAX_STREAK_PENALTY
# Injury type probabilities
MINOR_INJURY_PROB = 50
MODERATE_INJURY_PROB = 30
PITCHER_INJURY_PROB = 35 # currently unused
SEVERE_INJURE_PROB = 5
SURGERY_INJURY_PROB = 2

# Injury probability multipliers by activity
INJURY_ACTIVITY_WEIGHT = {
    "pitching": 6.8,
    "batting": 0.6,
    "running": 1.2,
    "fielding": 1.0,  # baseline, modified by position below
}

# Fielding position multipliers (applied on top of fielding weight)
INJURY_POSITION_WEIGHT = {
    "c": 1.4,
    "cf": 1.1,
    "ss": 1.0,
    "2b": 1.0,
    "3b": 0.8,
    "1b": 0.7,
    "lf": 0.7,
    "rf": 0.7,
    "dh": 0.0,
}


# Pitcher Change Probabilities
PITCHER_CHANGE_PROB = {
    "fresh": 0.01,
    "good": 0.03,
    "tired": 0.15,
    "exhausted": 0.40,
    "zero": 0.95,
}

PITCHER_CHANGE_MULTIPLIERS = {
    "runs_0": 0.21,
    "runs_1": 0.52,
    "runs_2_positive_diff": 0.61,
    "no_hits": 0.11,
}
