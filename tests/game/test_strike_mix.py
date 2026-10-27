# tests/game/test_strike_mix.py
"""Called vs swinging strike split in the pitch outcome weights."""

from random import Random
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.game.count import Count
from src.game.events.strikeout import StrikeOutEvent
from src.game.modifiers.pitch_modifiers import (
    CALLED,
    SWINGING,
    PitchModifiers,
    add_strikes,
    multiply_strikes,
    shift_strike_mix,
)
from src.stats.batting_stats import BattingStats
from src.stats.pitching_stats import PitchingStats
from src.util.weighted_choice import WeightedChoice


def make_resolver(called=5000, swinging=5000):
    wc = WeightedChoice({CALLED: called, SWINGING: swinging, "ball": 10000}, Random(1))
    return SimpleNamespace(pitch_outcome=wc)


def strikes(resolver):
    return resolver.pitch_outcome.get(CALLED), resolver.pitch_outcome.get(SWINGING)


def make_player(**skills):
    player = Mock()
    player.skills = skills
    player.get_effective_stat = lambda value: value
    return player


def batter(contact=50, eye=50, power=50):
    return make_player(contact=contact, eye=eye, power=power)


def pitcher(accuracy=50, strikes=50, ground_balls=40):
    return make_player(accuracy=accuracy, strikes=strikes, ground_balls=ground_balls)


class TestHelpers:
    def test_add_splits_by_share(self):
        r = make_resolver()
        add_strikes(r, 1000, called_share=0.7)
        assert strikes(r) == (5700, 5300)

    def test_add_spills_shortfall_to_other_kind(self):
        r = make_resolver(called=1000, swinging=5000)
        add_strikes(r, -4000, called_share=0.5)
        assert strikes(r) == (0, 2000)

    def test_multiply_scales_both(self):
        r = make_resolver(called=4000, swinging=2000)
        multiply_strikes(r, 0.5)
        assert strikes(r) == (2000, 1000)

    @pytest.mark.parametrize("factor", [0.5, 1.0, 1.5, 5.0])
    def test_shift_keeps_total(self, factor):
        r = make_resolver(called=4000, swinging=3000)
        shift_strike_mix(r, factor)
        called, swinging = strikes(r)
        assert called + swinging == 7000
        assert called == min(7000, int(4000 * factor))


def called_share(resolver):
    called, swinging = strikes(resolver)
    return called / (called + swinging)


class TestSkillsSkewMix:
    def test_contact_cuts_swinging_strikes(self):
        lo, hi = make_resolver(), make_resolver()
        PitchModifiers.modify_for_batter(lo, batter(contact=30))
        PitchModifiers.modify_for_batter(hi, batter(contact=80))
        assert sum(strikes(hi)) < sum(strikes(lo))
        assert called_share(hi) > called_share(lo)

    def test_power_hitters_swing_through_more(self):
        lo, hi = make_resolver(), make_resolver()
        PitchModifiers.modify_for_batter(lo, batter(power=30))
        PitchModifiers.modify_for_batter(hi, batter(power=80))
        assert sum(strikes(hi)) == pytest.approx(sum(strikes(lo)), abs=2)
        assert called_share(hi) < called_share(lo)

    def test_control_gets_called_strikes_stuff_gets_whiffs(self):
        control, stuff = make_resolver(), make_resolver()
        PitchModifiers.modify_for_pitcher(control, pitcher(accuracy=75))
        PitchModifiers.modify_for_pitcher(stuff, pitcher(strikes=69))
        assert called_share(control) > 0.5 > called_share(stuff)

    def test_two_strikes_shift_toward_swinging(self):
        early, late = make_resolver(), make_resolver()
        PitchModifiers.modify_strike_mix_for_count(early, Count(0, 0))
        PitchModifiers.modify_strike_mix_for_count(late, Count(1, 2))
        assert sum(strikes(early)) == sum(strikes(late)) == 10000
        assert called_share(early) > 0.5 > called_share(late)


class TestStrikeoutStats:
    @pytest.mark.parametrize("swinging", [True, False])
    def test_looking_recorded(self, swinging):
        b = SimpleNamespace(game_stats=SimpleNamespace(batting=BattingStats()))
        p = SimpleNamespace(game_stats=SimpleNamespace(pitching=PitchingStats()))
        event = StrikeOutEvent(batter=b, pitcher=p, swinging=swinging)
        event.apply(game=None)
        looking = 0 if swinging else 1
        assert b.game_stats.batting.strike_outs == 1
        assert b.game_stats.batting.strike_outs_looking == looking
        assert p.game_stats.pitching.strike_outs == 1
        assert p.game_stats.pitching.strike_outs_looking == looking
        assert event.describe(None) == (
            "Strikeout swinging" if swinging else "Strikeout looking"
        )
