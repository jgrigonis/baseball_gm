__author__ = "josh"

from types import MappingProxyType

# POSITIONS	            Enumeration / identity
# POSITION_TEMPLATES	Handedness + batting probabilities
# SKILL_TEMPLATE	    Positional means
# SKILLS	            Global skill universe + defaults

POSITIONS = [
    "sp",  # starting pitcher
    "rp",  # relief pitcher
    "c",  # catcher
    "1b",  # first baseman
    "2b",  # second baseman
    "ss",  # shortstop
    "3b",  # third baseman
    "lf",  # left fielder
    "cf",  # center fielder
    "rf",  # right fielder
    "if",  # utility infielder
    "of",  # outfielder
    "dh",  # designated hitter
]

POSITION_NAME = {
    "sp": "starting pitcher",
    "rp": "relief pitcher",
    "c": "catcher",
    "1b": "first baseman",
    "2b": "second baseman",
    "ss": "shortstop",
    "3b": "third baseman",
    "lf": "left fielder",
    "cf": "center fielder",
    "rf": "right fielder",
    "if": "utility infielder",
    "of": "outfielder",
    "dh": "designated hitter",
}

POSITION_TEMPLATES = MappingProxyType(
    {
        "sp": {
            # 25% of starting pitchers are left handed
            "throws_left": 0.25,
            "switch_hitter": 0.01,
            # bats_left really means bats opposite
            "bats_left": 0.01,
        },
        "rp": {
            # 35% of relief pitchers are left handed
            "throws_left": 0.35,
            "switch_hitter": 0.01,
            "bats_left": 0.01,
        },
        "c": {
            # Almost impossible to be a left handed catcher
            "throws_left": 0.001,
            "switch_hitter": 0.16,
            "bats_left": 0.12,
        },
        "1b": {
            "throws_left": 0.33,
            "switch_hitter": 0.12,
            "bats_left": 0.12,
        },
        "ss": {
            # Almost impossible to be a left handed ss
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.05,
        },
        "2b": {
            # Almost impossible to be a left handed 2b
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.15,
        },
        "3b": {
            # Almost impossible to be a left handed 3b
            "throws_left": 0.001,
            "switch_hitter": 0.15,
            "bats_left": 0.05,
        },
        "lf": {
            "throws_left": 0.25,
            "switch_hitter": 0.10,
            "bats_left": 0.15,
        },
        "cf": {
            "throws_left": 0.33,
            "switch_hitter": 0.16,
            "bats_left": 0.15,
        },
        "rf": {
            "throws_left": 0.25,
            "switch_hitter": 0.1,
            "bats_left": 0.15,
        },
        "if": {
            # Almost impossible to be a left handed infielder
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.15,
        },
        "of": {
            "throws_left": 0.3,
            "switch_hitter": 0.2,
            "bats_left": 0.15,
        },
        "dh": {
            "throws_left": 0.33,
            "switch_hitter": 0.15,
            "bats_left": 0.2,
        },
    }
)

# If not specified, 50 is implied
SKILL_TEMPLATE = {
    "sp": {
        "accuracy": 60,
        "stamina": 70,
        "recovery": 60,
        "power": 20,
        "eye": 30,
        "contact": 30,
        "base_running": 40,
        "catching": 20,
        "infield": 40,
        "outfield": 40,
        "arm": 60,
    },
    "rp": {
        "accuracy": 60,
        "recovery": 60,
        "power": 20,
        "eye": 30,
        "contact": 30,
        "base_running": 40,
        "catching": 20,
        "infield": 40,
        "outfield": 40,
        "arm": 60,
    },
    "c": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "base_running": 40,
        "catching": 70,
        "infield": 40,
        "outfield": 40,
        "arm": 60,
    },
    "1b": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 30,
        "power": 60,
        "base_running": 40,
        "outfield": 40,
    },
    "ss": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 60,
        "power": 35,
        "infield": 70,
    },
    "2b": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 60,
        "power": 35,
        "infield": 70,
    },
    "3b": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "infield": 60,
    },
    "lf": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 60,
        "power": 60,
        "catching": 40,
        "infield": 40,
        "outfield": 60,
    },
    "cf": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 65,
        "catching": 40,
        "infield": 40,
        "outfield": 65,
        "arm": 60,
    },
    "rf": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 60,
        "power": 60,
        "catching": 40,
        "infield": 40,
        "outfield": 60,
        "arm": 60,
    },
    "if": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "infield": 60,
        "power": 35,
    },
    "of": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "speed": 55,
        "catching": 40,
        "infield": 40,
        "outfield": 60,
    },
    "dh": {
        "accuracy": 10,
        "stamina": 10,
        "recovery": 10,
        "ground_balls": 10,
        "strikes": 10,
        "power": 65,
        "catching": 40,
        "infield": 40,
        "outfield": 40,
        "arm": 40,
    },
}

SKILLS = MappingProxyType(
    {
        # pitching
        "accuracy": 50,  # Pitching accuracy, ability to hit the zone
        # or exactly where they want it.
        # Maybe rename to control
        "stamina": 50,  # Pitching stamina, think of this as the size
        # of the tank. A 50 stamina pitcher is expected
        # to be completely gassed after 100 pitches.
        # 1 point of stamina is worth about 2 pitches
        "recovery": 50,  # Pitching stamina recovery speed with rest
        # A 50 recovery pitcher is expected to recover
        # from completely gassed to full stamina in 5
        # days. Each point of recovery makes 1% diff.
        # So a 60 recovery pitcher would recover from
        # 0 to 100 in 4.5 days. A 100 recovery pitcher
        # could recover in 2.5 days.
        "ground_balls": 50,  # Ground ball pitcher
        "strikes": 50,  # Pitcher ability to make the batter miss.
        # How good is their stuff? Maybe rename to stuff
        # general
        "clutch": 50,  # Clutch
        "speed": 50,  # Running speed
        # hitting
        "power": 50,  # Hitting power
        "eye": 50,  # Eye
        "contact": 50,  # Batting contact
        "base_running": 50,  # Base-running skill
        "bunting": 50,  # Bunting
        # defensive
        "catching": 50,  # Skill as a catcher
        "infield": 50,  # In-fielding skill
        "outfield": 50,  # Fly-ball catching
        "arm": 50,  # Arm strength
    }
)

# rated_positions = [
#     "p",  # pitcher
#     "c",  # catcher
#     "1b",  # first baseman
#     "2b",  # second baseman
#     "ss",  # shortstop
#     "3b",  # third baseman
#     "lf",  # left fielder
#     "cf",  # center fielder
#     "rf",  # right fielder
#     "lead_off",  # lead off hitter
#     "contact_hitter",  # contact hitter
#     "power_hitter",  # power hitter
# ]
