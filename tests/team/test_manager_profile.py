# tests/team/test_manager_profile.py
"""
The Strategy tab's settings as the game engine reads them
(src/team/manager_profile.py), and the engine hooks that use them. The
default profile must leave every chance exactly where it was.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.game.bases import FIRST, SECOND
from src.game.resolvers import hits
from src.game.strategy import GameStrategy
from src.player.fatigue import FatigueLevel
from src.team.manager_profile import (
    DEFAULT_PROFILE,
    ManagerProfile,
    profile_of,
)


class FixedRng:
    """random() returns these values in turn."""

    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.values.pop(0)


def runner(speed=50, base_running=50):
    return SimpleNamespace(skills={"speed": speed, "base_running": base_running})


def bases(**on):
    b = MagicMock()
    by_base = {FIRST: on.get("first"), SECOND: on.get("second")}
    b.runner_on.side_effect = lambda base: by_base.get(base)
    b.is_empty = not any(by_base.values())
    b.is_loaded = False
    return b


# ── The profile itself ────────────────────────────────────────────────────────


def test_from_row_reads_known_values_and_ignores_the_rest():
    p = ManagerProfile.from_row(
        {
            "baserunning": "very-aggressive",
            "sac_bunt": "never",
            "rotation_size": 4,
            "skip_fifth_starter": True,
            "closer_usage": "nonsense",
        }
    )
    assert p.baserunning == "very-aggressive"
    assert p.bunt_factor == 0.0
    assert p.rotation_size == 4
    assert p.skip_fifth_starter
    assert p.closer_usage == "saves-only"


def test_no_row_is_the_default():
    assert ManagerProfile.from_row(None) == DEFAULT_PROFILE


def test_default_changes_nothing():
    p = DEFAULT_PROFILE
    assert p.steal_factor == p.extra_base_factor == p.bunt_factor == 1.0
    assert p.pitch_count_offset == 0
    assert p.starter_hook(batters_faced=30) == 1.0
    assert p.playoff_rotation_size is None


def test_baserunning_steps_rise():
    factors = [
        ManagerProfile(baserunning=b).steal_factor
        for b in (
            "very-conservative",
            "conservative",
            "standard",
            "aggressive",
            "very-aggressive",
        )
    ]
    assert factors == sorted(factors) and len(set(factors)) == 5


def test_matchup_based_pulls_sooner_third_time_through():
    p = ManagerProfile(starter_usage="matchup-based")
    assert p.starter_hook(batters_faced=10) == 1.0
    assert p.starter_hook(batters_faced=19) > 1.0


def test_catchers_rest_sooner_but_iron_men_never_rest():
    p = ManagerProfile(rest_days="standard")
    assert p.rest_energy("c") > p.rest_energy("ss") > 0
    assert ManagerProfile(rest_days="iron-man").rest_energy("c") == 0


def test_profile_of_falls_back_to_default():
    assert profile_of(None) is DEFAULT_PROFILE
    assert profile_of(MagicMock()) is DEFAULT_PROFILE
    team = SimpleNamespace(profile=ManagerProfile(sac_bunt="never"))
    assert profile_of(team).sac_bunt == "never"


# ── Engine hooks ──────────────────────────────────────────────────────────────


def steal(aggression, roll):
    return GameStrategy.should_attempt_steal(
        FIRST,
        bases(first=runner()),
        0,
        SimpleNamespace(balls=1, strikes=1),
        SimpleNamespace(differential=0),
        rng=FixedRng(roll),
        aggression=aggression,
    )


def test_aggressive_runners_steal_more():
    # A roll just above the standard chance: only the aggressive runner goes.
    base_chance = next(r / 10000 for r in range(1, 10000) if not steal(1.0, r / 10000))
    assert not steal(1.0, base_chance)
    assert steal(1.75, base_chance)
    assert not steal(0.4, base_chance * 0.5)


def test_never_bunt():
    kwargs = dict(
        bases=bases(first=runner()),
        outs=0,
        strikes=0,
        balls=0,
        rng=FixedRng(0.0),
    )
    assert GameStrategy.should_bunt(**kwargs)
    kwargs["rng"] = FixedRng(0.0)
    assert not GameStrategy.should_bunt(**kwargs, bunt_factor=0.0)


def starter(pitch_count, outs=0, hits=0, runs=0):
    p = MagicMock()
    p.is_starter = True
    p.bullpen_role = None
    p.pitcher_fatigue.get_level.return_value = FatigueLevel.GOOD
    st = p.game_stats.pitching
    st.pitch_count, st.outs, st.hits, st.runs, st.walks, st.hb = (
        pitch_count,
        outs,
        hits,
        runs,
        0,
        0,
    )
    return p


def test_let_them_work_has_a_longer_leash():
    inning = SimpleNamespace(number=7)
    tired = starter(pitch_count=105, outs=18, hits=5, runs=3)
    strict = GameStrategy.should_consider_pitching_change(tired, inning, 0)
    patient = GameStrategy.should_consider_pitching_change(
        tired, inning, 0, ManagerProfile(starter_usage="let-them-work")
    )
    assert strict >= 0.72
    assert patient < strict


def closer_team(usage, *pitchers):
    return SimpleNamespace(
        profile=ManagerProfile(closer_usage=usage), players=list(pitchers)
    )


def reliever(role, cp):
    p = MagicMock()
    p.bullpen_role = role
    p.ratings = {"cp": cp}
    p.game_stats.pitching.pitch_count = 0
    p.pitcher_fatigue.get_level.return_value = FatigueLevel.FRESH
    p.current_position = None
    return p


ALWAYS = SimpleNamespace(random=lambda: 0.0)


@pytest.mark.parametrize(
    "usage, inning, lead, expected",
    [
        ("saves-only", 9, 1, True),
        ("saves-only", 8, 1, False),
        ("saves-only", 9, 0, False),
        ("high-leverage", 8, 1, True),
        ("high-leverage", 9, 0, True),
        ("high-leverage", 7, 1, False),
    ],
)
def test_closer_situations(usage, inning, lead, expected):
    closer = reliever("Closer", 70)
    current = reliever("Setup", 50)
    got = GameStrategy.find_closer(
        current,
        closer_team(usage, closer, current),
        SimpleNamespace(number=inning),
        lead,
        ALWAYS,
    )
    assert (got is closer) == expected


def test_best_available_uses_the_best_arm_whatever_his_role():
    closer = reliever("Closer", 60)
    ace = reliever("Middle", 80)
    current = MagicMock(bullpen_role=None, ratings={"cp": 40})
    team = closer_team("best-available", closer, ace)
    got = GameStrategy.find_closer(current, team, SimpleNamespace(number=9), 2, ALWAYS)
    assert got is ace


# ── Extra bases on a hit ──────────────────────────────────────────────────────


def send(baserunning, *rolls, prob=0.5):
    game = SimpleNamespace(
        bat_team=SimpleNamespace(profile=ManagerProfile(baserunning=baserunning))
    )
    rng = FixedRng(*rolls)
    resolver = SimpleNamespace(rng=rng)
    return hits._send_runner(resolver, game, prob, 50, 50, 50), rng.calls


def test_standard_sends_draw_one_number():
    assert send("standard", 0.4) == (hits.SAFE, 1)
    assert send("standard", 0.6) == (hits.HELD, 1)


def test_cautious_runner_holds_on_close_plays():
    assert send("very-conservative", 0.45)[0] == hits.HELD
    assert send("very-conservative", 0.3)[0] == hits.SAFE


def test_aggressive_runner_risks_being_thrown_out():
    # 0.55 is past the standard chance but inside the aggressive one, so he
    # goes, and the second number decides the throw.
    assert send("very-aggressive", 0.55, 0.0) == (hits.OUT, 2)
    assert send("very-aggressive", 0.55, 0.99) == (hits.SAFE, 2)


def test_held_runner_still_draws_a_number():
    game = SimpleNamespace(bat_team=None)
    rng = FixedRng(0.0)
    got = hits._send_runner(
        SimpleNamespace(rng=rng), game, 0.9, 50, 50, 50, allowed=False
    )
    assert got == hits.HELD and rng.calls == 1


# ── Rest days ─────────────────────────────────────────────────────────────────


def rest_team(rest_days, energies):
    """A team of hitters with these energies (the first one a catcher)."""
    from src.player.position_fatigue import PositionPlayerFatigue
    from src.team.team_in_game import TeamInGame

    team = TeamInGame.__new__(TeamInGame)
    team.profile = ManagerProfile(rest_days=rest_days)
    players = []
    for i, energy in enumerate(energies):
        p = MagicMock()
        p.id = f"h{i}"
        p.record.position = "C" if i == 0 else "SS"
        p.player_energy = PositionPlayerFatigue()
        p.player_energy.energy = energy
        players.append(p)
    return team, players


def resting(team, players, saved=None):
    return sorted(p.id for p in team._rest_days(players, saved))


def test_tired_regulars_sit():
    team, players = rest_team("standard", [1.0] * 10 + [0.3, 0.45])
    # 0.3 is below 40%; the 0.45 shortstop plays.
    assert resting(team, players) == ["h10"]


def test_catchers_sit_sooner():
    team, players = rest_team("standard", [0.45] + [1.0] * 10)
    assert resting(team, players) == ["h0"]


def test_rest_often_and_iron_man():
    energies = [1.0] * 10 + [0.5]
    assert resting(*rest_team("rest-often", energies)) == ["h10"]
    assert resting(*rest_team("iron-man", [0.05] * 12)) == []


def test_never_rests_below_nine_hitters():
    team, players = rest_team("standard", [0.1] * 10 + [1.0])
    assert len(resting(team, players)) == 2
