# tests/game/test_bat_spread.py
"""Batting skills are widened around a typical hitter (BAT_SPREAD), so good
hitters pull away from bad ones while a typical hitter, and so league
scoring, stays where it was."""

import pytest

from src.game.modifiers.pitch_modifiers import (
    BAT_SPREAD,
    TYPICAL_CONTACT,
    bat_term,
)


def test_a_typical_hitter_is_unchanged():
    assert bat_term(TYPICAL_CONTACT, TYPICAL_CONTACT) == TYPICAL_CONTACT - 50


def test_skill_gaps_widen_by_the_spread():
    gap = bat_term(TYPICAL_CONTACT + 10, TYPICAL_CONTACT) - bat_term(
        TYPICAL_CONTACT, TYPICAL_CONTACT
    )
    assert gap == pytest.approx(10 * BAT_SPREAD)


def test_good_hitters_gain_and_bad_ones_lose():
    assert bat_term(80, TYPICAL_CONTACT) > 80 - 50
    assert bat_term(40, TYPICAL_CONTACT) < 40 - 50
