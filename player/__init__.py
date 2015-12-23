__author__ = 'josh'
positions = ['sp',  # starting pitcher
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
template = {
    'sp': {
        'throws_left': 0.25,
        'switch_hitter': 0.01,
        'bats_left': 0.01,
    },
    'rp': {
        'throws_left': 0.35,
        'switch_hitter': 0.01,
        'bats_left': 0.01,
    },
    'c': {
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
        'throws_left': 0.001,
        'switch_hitter': 0.25,
        'bats_left': 0.05,
    },
    '2b': {
        'throws_left': 0.001,
        'switch_hitter': 0.25,
        'bats_left': 0.15,
    },
    '3b': {
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
