__author__ = 'josh'

positions = [
    'sp',  # starting pitcher
    'rp',  # relief pitcher
    'c',   # catcher
    '1b',  # first baseman
    '2b',  # second baseman
    'ss',  # shortstop
    '3b',  # third baseman
    'lf',  # left fielder
    'cf',  # center fielder
    'rf',  # right fielder
    'if',  # utility infielder
    'of',  # outfielder
    'dh',  # designated hitter
]

position_name = [
    'starting pitcher',
    'relief pitcher',
    'catcher',
    'first baseman',
    'second baseman',
    'shortstop',
    'third baseman',
    'left fielder',
    'center fielder',
    'right fielder',
    'utility infielder',
    'outfielder',
    'designated hitter',
]

rated_positions = [
    'p',               # pitcher
    'c',               # catcher
    '1b',              # first baseman
    '2b',              # second baseman
    'ss',              # shortstop
    '3b',              # third baseman
    'lf',              # left fielder
    'cf',              # center fielder
    'rf',              # right fielder
    'lead_off',        # lead off hitter
    'contact_hitter',  # contact hitter
    'power_hitter'     # power hitter
]

template = {
    'sp': {
        # 25% of startig pitchers are left handed
        'throws_left': 0.25,
        'switch_hitter': 0.01,
        # bats_left really means bats opposite
        'bats_left': 0.01,
    },
    'rp': {
        # 35% of startig pitchers are left handed
        'throws_left': 0.35,
        'switch_hitter': 0.01,
        'bats_left': 0.01,
    },
    'c': {
        # Almost impossible to be a left handed catcher
        'throws_left': 0.001,
        'switch_hitter': 0.16,
        'bats_left': 0.12,
    },
    '1b': {
        'throws_left': 0.33,
        'switch_hitter': 0.12,
        'bats_left': 0.12,
    },
    'ss': {
        # Almost impossible to be a left handed ss
        'throws_left': 0.001,
        'switch_hitter': 0.25,
        'bats_left': 0.05,
    },
    '2b': {
        # Almost impossible to be a left handed 2b
        'throws_left': 0.001,
        'switch_hitter': 0.25,
        'bats_left': 0.15,
    },
    '3b': {
        # Almost impossible to be a left handed 3b
        'throws_left': 0.001,
        'switch_hitter': 0.15,
        'bats_left': 0.05,
    },
    'lf': {
        'throws_left': 0.25,
        'switch_hitter': 0.10,
        'bats_left': 0.15,
    },
    'cf': {
        'throws_left': 0.33,
        'switch_hitter': 0.16,
        'bats_left': 0.15,
    },
    'rf': {
        'throws_left': 0.25,
        'switch_hitter': 0.1,
        'bats_left': 0.15,
    },
    'if': {
        # Almost impossible to be a left handed infielder
        'throws_left': 0.001,
        'switch_hitter': 0.25,
        'bats_left': 0.15,
    },
    'of': {
        'throws_left': 0.3,
        'switch_hitter': 0.2,
        'bats_left': 0.15,
    },
    'dh': {
        'throws_left': 0.33,
        'switch_hitter': 0.15,
        'bats_left': 0.2,
    }
}

skill_template = {
    'sp': {
        'accuracy': 60,
        'stamina': 70,
        'recovery': 60,
        'power': 20,
        'eye': 30,
        'contact': 30,
        'base_running': 40,
        'catching': 20,
        'infield': 40,
        'outfield': 40,
        'arm': 60
    },
    'rp': {
        'accuracy': 60,
        'recovery': 60,
        'power': 20,
        'eye': 30,
        'contact': 30,
        'base_running': 40,
        'catching': 20,
        'infield': 40,
        'outfield': 40,
        'arm': 60
    },
    'c': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'base_running': 40,
        'catching': 70,
        'outfield': 40,
        'arm': 60
    },
    '1b': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 30,
        'power': 60,
        'base_running': 40,
        'outfield': 40,
    },
    'ss': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 60,
        'power': 35,
        'infield': 70,
    },
    '2b': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 60,
        'power': 35,
        'infield': 70,
    },
    '3b': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'infield': 60,
    },
    'lf': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 60,
        'power': 60,
        'catching': 40,
        'infield': 40,
        'outfield': 60,
    },
    'cf': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 65,
        'catching': 40,
        'infield': 40,
        'outfield': 65,
        'arm': 60,
    },
    'rf': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 60,
        'power': 60,
        'catching': 40,
        'infield': 40,
        'outfield': 60,
        'arm': 60,
    },
    'if': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'infield': 60,
    },
    'of': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'speed': 55,
        'catching': 40,
        'infield': 40,
        'outfield': 60,
    },
    'dh': {
        'accuracy': 10,
        'stamina': 10,
        'recovery': 10,
        'ground_balls': 10,
        'strikes': 10,
        'power': 65,
        'catching': 40,
        'infield': 40,
        'outfield': 40,
        'arm': 40,
    }
}

skills = {
    # pitching
    'accuracy': 0,      # Pitching accuracy
    'stamina': 0,       # Pitching stamina, think of this as the size 
                        # of the tank. A 50 stamina pitcher is expected
                        # to be completely gassed after 100 pitches.
                        # 1 point of stamina is worth about 2 pitches
    'recovery': 0,      # Pitching stamina recovery speed with rest
                        # A 50 recovery pitcher is expected to recover 
                        # from completely gassed to full stamina in 5
                        # days. Each point of recovery makes 1% diff.
                        # So a 60 recovery pitcher would recover from
                        # 0 to 100 in 4.5 days. A 100 recovery pitcher
                        # could recover in 2.5 days.
    'ground_balls': 0,  # Ground ball pitcher
    'strikes': 0,       # Pitcher ability to get strikes
    # general
    'clutch': 0,        # Clutch
    'speed': 0,         # Running speed
    # hitting
    'power': 0,         # Hitting power
    'eye': 0,           # Eye
    'contact': 0,       # Batting contact
    'base_running': 0,  # Base-running skill
    'bunting': 0,       # Bunting
    # defensive
    'catching': 0,      # Skill as a catcher
    'infield': 0,       # In-fielding skill
    'outfield': 0,      # Fly-ball catching
    'arm': 0,           # Arm strength
}

# These are unused, just the skills broken out into types
# pitching_skills = {
#     # pitching
#     'accuracy': 0,      # Pitching accuracy
#     'stamina': 0,       # Pitching stamina
#     'recovery': 0,      # Pitching stamina recovery speed with rest
#     'ground_balls': 0,  # Ground ball pitcher
#     'strikes': 0,       # Pitcher ability to get strikes
# }

# general_skills = {
#     # general
#     'clutch': 0,        # Clutch
#     'speed': 0,         # Running speed
# }

# hitting_skills = {
#     # hitting
#     'power': 0,         # Hitting power
#     'eye': 0,           # Eye
#     'contact': 0,       # Batting contact
#     'base_running': 0,  # Base-running skill
#     'bunting': 0,       # Bunting
# }

# defensive_skills = {
#     # defensive
#     'catching': 0,      # Skill as a catcher
#     'infield': 0,       # In-fielding skill
#     'outfield': 0,      # Fly-ball catching
#     'arm': 0,           # Arm strength
# }
