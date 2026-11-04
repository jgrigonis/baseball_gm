# src/game/resolvers/probabilities.py

"""
Baseball event probability constants.

These values tune the likelihood of various outcomes throughout the game.

League-wide scoring is calibrated to MLB 2023-2025 (about 4.5 runs per team
game, .245/.316/.406). After changing anything here or in the pitch /
in-play modifiers, check it with scripts/league_stat_check.py.
"""

# Pitch outcome weights
BALL_PROB = 15900
FOUL_PROB = 6400
HOME_RUN_PROB = 338
HBP_PROB = 130
BALK_PROB = 0
ILLEGAL_PITCH_PROB = 0
CATCHER_INTERFERENCE_PROB = 3
WILD_PITCH_PROB = 300
PASSED_BALL_PROB = 69
IN_PLAY_PROB = 5875
# Called and swinging strikes split the old single STRIKE_PROB (11500).
CALLED_STRIKE_PROB = 5750
SWINGING_STRIKE_PROB = 5950

# In play outcome weights
FLY_OUT_PROB = 4440
GROUND_OUT_PROB = 1740
SINGLE_PROB = 1525
DOUBLE_PROB = 465
TRIPLE_PROB = 55
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
# These are scaled by runner (speed + base_running) / 100 and 50 / the
# outfielder's arm, which nets about 0.9 for a typical runner and outfield.
SCORE_FROM_SECOND_ON_SINGLE = 0.63  # about 57% after scaling (MLB ~60%)
FIRST_TO_THIRD_ON_SINGLE = 0.35  # 35% chance runner goes 1st to 3rd
SCORE_FROM_FIRST_ON_DOUBLE = 0.32  # about 29% after scaling
FIRST_TO_HOME_ON_SINGLE = 0.03  # 3% chance runner scores from 1st on single

# Pickoff probabilities
PICKOFF_SUCCESS_PROB = 0.09  # 9% successful
PICKOFF_ERROR_PROB = 0.02  # 2% throwing error
STEAL_ON_PICKOFF_MODIFIER = 1.5

# Steal success rates
# Scaled by runner (2 * speed + base_running) / 150 over catcher
# (arm + catching) / 100. A typical base stealer (1.26) against a typical
# catcher (1.43) succeeds about 80% of the time, as in MLB since 2023.
STEAL_SECOND_SUCCESS_PROB = 0.95
STEAL_THIRD_SUCCESS_PROB = 0.97
STEAL_HOME_SUCCESS_PROB = 0.25  # 25% success rate

# Error and throwout rates
BASE_ERROR_RATE = 0.047

# Error chances on specific plays, as multiples of the fielder's base
# fielding / throwing error chance (see src/game/resolvers/errors.py).
# Double plays and fielder's choices: the ball is usually hit right at
# someone, the feed to second is short, the relay to first is hurried.
DP_FIELD_FACTOR = 0.4  # fielder boots the grounder, everyone safe
DP_FEED_FACTOR = 0.25  # bad feed to the man covering second, everyone safe
DP_PIVOT_DROP_FACTOR = 0.2  # pivot man drops the feed, everyone safe
# A wild relay is only an error if it lets a runner take an extra base
# (Rule 9.12(d)(3)), so this is the chance of a throw that bad.
DP_RELAY_FACTOR = 0.25
DP_RELAY_DROP_FACTOR = 0.15  # first baseman drops the relay
FC_FIELD_FACTOR = 0.4
FC_THROW_FACTOR = 0.4
FC_DROP_FACTOR = 0.15
# Sac bunts: charging fielder throwing on the run.
BUNT_FIELD_FACTOR = 0.4
BUNT_THROW_FACTOR = 0.6
BUNT_DROP_FACTOR = 0.15
# Outfield: a muffed fly ball, a bobbled base hit, a bad throw home.
FLY_DROP_FACTOR = 0.1
FLY_DROP_BATTER_TO_SECOND_PROB = 0.4
HIT_BOBBLE_FACTOR = 0.2
SAC_FLY_THROW_FACTOR = 0.3
# Steals: catcher's throw into center field, or the cover man drops it.
STEAL_THROW_FACTOR = 1.0
STEAL_DROP_FACTOR = 0.1
BASE_THROWOUT_PROB = 0.24

# Favor ss over 2b for covering second.
SS_OVER_2B_PROB = 0.55

# Probability for strategy decisions
# Pickoff
BASE_PICKOFF_ATTEMPT_PROB = 0.01  # 1% per pitch

# Steal
BASE_STEAL_SECOND_PROB = 0.028  # per pitch from first, before speed and count
BASE_STEAL_THIRD_PROB = 0.006  # per pitch from second
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
BUNT_PROB = 0.018
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
HNR_SLOW_SPEED = 40  # Below this speed, a runner is rarely sent on the hit and run
HNR_SLOW_MOD = 0.2
HNR_FAVORABLE_COUNT_MOD = 1.3

# Pitcher Change
# Bullpen usage, tuned (Nov 2026) so 30-team seasons land near MLB
# 2023-2025: starters ~5.4 IP and ~87 pitches, ~3.1 relievers a team game
# at ~1.15 IP each.
# From this pitch count on, a starter is usually pulled (a "let them work"
# manager adds to it).
PITCH_COUNT_THRESHOLD = 85
# A leading starter with fewer outs than this is pulled less often.
STARTER_LEAD_OUTS = 15
STARTER_LEAD_HOOK = 0.6
# Chance a reliever who has done his inning (two for a long man) sits
# before the next one starts.
RELIEVER_INNING_DONE_PROB = 0.9
CLOSER_ENTRANCE_PROB = 0.92

# Injury/Fatigue
INJURY_BASE_PROB = 0.000225  # per plate appearance (lowered from 0.00025 when fatigue multipliers were added)
FATIGUE_MULTIPLIER = 1.6  # injury multiplier for fatigued players
LOW_ENERGY = 0.50  # threshold for low player energy
BASE_ENERGY_DEPLETION = 0.035  # base energy depletion per plate appearance
DURABILITY_MOD = 0.3  # Modifies the multiplier for injury chances by up to 30 percent in either direction
FREE_STREAK_DAYS = (
    3  # Number of days before a streak penalty is applied to energy drain
)
MAX_STREAK_PENALTY = 0.05  # Max amount of energy drained during a long streak
ENERGY_PENALTY_PER_STREAK_DAY = 0.015  # After FREE_STREAK_DAYS, each day's energy drain penalty is multiplied by this, until it crosses MAX_STREAK_PENALTY
# Injury type probabilities
MINOR_INJURY_PROB = 50
MODERATE_INJURY_PROB = 30
PITCHER_INJURY_PROB = 35  # currently unused
SEVERE_INJURE_PROB = 5
SURGERY_INJURY_PROB = 2

# Injury probability multipliers by activity
INJURY_ACTIVITY_WEIGHT = {
    "pitching": 7.55,  # raised from 6.8 to keep pitcher injury rate unchanged when INJURY_BASE_PROB was lowered
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
