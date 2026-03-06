# src/game/resolvers/count_modifiers.py

"""
Count-based probability modifiers for pitch and in-play outcomes.

Each count (balls, strikes) has multipliers that affect the likelihood
of different outcomes.
"""

# Pitch outcome modifiers by count (balls, strikes)
PITCH_COUNT_MODIFIERS = {
    (0, 0): {
        "ball": 1.15,
        "strike": 1.33,
        "foul": 0.66,
        "home_run": 0.61,
        "in_play": 0.66,
    },
    (1, 0): {
        "ball": 0.92,
        "strike": 1.12,
        "foul": 0.94,
        "home_run": 1.1,
        "in_play": 1.1,
    },
    (0, 1): {
        "ball": 1.13,
        "strike": 0.74,
        "foul": 1.11,
        "home_run": 0.78,
        "in_play": 0.84,
    },
    (2, 0): {
        "ball": 1.08,
        "strike": 1.44,
        "foul": 0.57,
        "home_run": 0.69,
        "in_play": 0.7,
    },
    (1, 1): {
        "ball": 0.96,
        "strike": 0.78,
        "foul": 1.34,
        "home_run": 1.15,
        "in_play": 1.1,
    },
    (0, 2): {
        "ball": 1.37,
        "strike": 0.6,
        "foul": 1.02,
        "home_run": 0.74,
        "in_play": 0.77,
    },
    (3, 0): {
        "ball": 0.89,
        "strike": 2.56,
        "foul": 0.08,
        "home_run": 0.21,
        "in_play": 0.2,
    },
    (2, 1): {
        "ball": 0.69,
        "strike": 0.89,
        "foul": 1.19,
        "home_run": 1.71,
        "in_play": 1.64,
    },
    (1, 2): {
        "ball": 0.97,
        "strike": 0.71,
        "foul": 1.26,
        "home_run": 1.16,
        "in_play": 1.17,
    },
    (3, 1): {
        "ball": 0.95,
        "strike": 0.76,
        "foul": 0.79,
        "home_run": 1.57,
        "in_play": 1.56,
    },
    (2, 2): {
        "ball": 0.65,
        "strike": 0.76,
        "foul": 1.54,
        "home_run": 1.63,
        "in_play": 1.51,
    },
    (3, 2): {
        "ball": 0.62,
        "strike": 0.65,
        "foul": 1.36,
        "home_run": 1.66,
        "in_play": 1.72,
    },
}

# In-play outcome modifiers by count (balls, strikes)
IN_PLAY_COUNT_MODIFIERS = {
    (0, 0): {
        "fly_out": 0.66,
        "ground_out": 0.66,
        "single": 0.61,
        "double": 0.61,
        "triple": 0.61,
    },
    (1, 0): {
        "fly_out": 1.01,
        "ground_out": 1.01,
        "single": 1.1,
        "double": 1.1,
        "triple": 1.1,
    },
    (0, 1): {
        "fly_out": 1.08,
        "ground_out": 1.08,
        "single": 0.78,
        "double": 0.78,
        "triple": 0.78,
    },
    (2, 0): {
        "fly_out": 0.72,
        "ground_out": 0.72,
        "single": 0.69,
        "double": 0.69,
        "triple": 0.69,
    },
    (1, 1): {
        "fly_out": 1.01,
        "ground_out": 1.01,
        "single": 1.15,
        "double": 1.15,
        "triple": 1.15,
    },
    (0, 2): {
        "fly_out": 0.82,
        "ground_out": 0.82,
        "single": 0.74,
        "double": 0.74,
        "triple": 0.74,
    },
    (3, 0): {
        "fly_out": 0.09,
        "ground_out": 0.09,
        "single": 0.21,
        "double": 0.21,
        "triple": 0.21,
    },
    (2, 1): {
        "fly_out": 1.47,
        "ground_out": 1.47,
        "single": 1.71,
        "double": 1.71,
        "triple": 1.71,
    },
    (1, 2): {
        "fly_out": 1.2,
        "ground_out": 1.2,
        "single": 1.16,
        "double": 1.16,
        "triple": 1.16,
    },
    (3, 1): {
        "fly_out": 1.56,
        "ground_out": 1.56,
        "single": 1.57,
        "double": 1.57,
        "triple": 1.57,
    },
    (2, 2): {
        "fly_out": 1.39,
        "ground_out": 1.39,
        "single": 1.63,
        "double": 1.63,
        "triple": 1.63,
    },
    (3, 2): {
        "fly_out": 1.88,
        "ground_out": 1.88,
        "single": 1.66,
        "double": 1.66,
        "triple": 1.66,
    },
}
