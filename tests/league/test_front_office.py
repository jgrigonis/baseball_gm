# tests/league/test_front_office.py
"""How team state and persona steer an AI team's roster decisions."""

import pytest

from src.league import front_office as fo
from src.league.offseason.draft_strategy import HIGH, LOW, MED
from src.league.personas import Leanings
from src.team.manager_profile import ManagerProfile


def test_neutral_persona_follows_the_state():
    assert fo.youth_tilt("rebuilding", Leanings()) == fo.STATE_YOUTH["rebuilding"]
    assert fo.youth_tilt("all-in", Leanings()) == fo.STATE_YOUTH["all-in"]
    assert fo.youth_tilt(None, Leanings()) == 0


def test_youth_dial_moves_the_tilt():
    kids = fo.youth_tilt("retooling", Leanings(youth=100))
    vets = fo.youth_tilt("retooling", Leanings(youth=0))
    assert kids == pytest.approx(fo.PERSONA_YOUTH)
    assert vets == pytest.approx(-fo.PERSONA_YOUTH)


def test_tilt_is_capped():
    assert fo.youth_tilt("rebuilding", Leanings(youth=100)) == 1.0
    assert fo.youth_tilt("all-in", Leanings(youth=0)) == -1.0


def test_age_points():
    assert fo.age_points(22, 0) == 0
    assert fo.age_points(fo.PRIME_AGE, 1) == 0
    assert fo.age_points(25, 1) == pytest.approx(2 * fo.POINTS_PER_YEAR)
    assert fo.age_points(25, -1) == pytest.approx(-2 * fo.POINTS_PER_YEAR)
    # Capped either way
    assert fo.age_points(18, 1) == fo.MAX_AGE_POINTS
    assert fo.age_points(40, 1) == -fo.MAX_AGE_POINTS


def test_best_available_states_drop_need_chips():
    s = fo.draft_strategy({"c": HIGH, "if": MED}, "rebuilding", Leanings())
    assert s.chips == {"c": MED}


def test_retooling_drafts_for_need():
    s = fo.draft_strategy({"c": MED, "if": LOW}, "retooling", Leanings())
    assert s.chips == {"c": HIGH, "if": MED}


def test_bat_first_gm_asks_for_offense():
    assert fo.draft_strategy({}, None, Leanings(offense_defense=75)).chips == {
        "offense": MED
    }
    assert fo.draft_strategy(
        {"offense": HIGH}, None, Leanings(offense_defense=90)
    ).chips == {"offense": HIGH}
    assert fo.draft_strategy({}, None, Leanings()).chips == {}


def test_draft_age_slider():
    # A rebuilder drafts upside, an all-in team players ready sooner
    assert fo.draft_strategy({}, "rebuilding", Leanings()).age_pref < 0
    assert fo.draft_strategy({}, "all-in", Leanings()).age_pref > 0
    # Youth and risk dials both lean toward upside
    base = fo.draft_strategy({}, "retooling", Leanings()).age_pref
    assert fo.draft_strategy({}, "retooling", Leanings(youth=90)).age_pref < base
    assert fo.draft_strategy({}, "retooling", Leanings(risk=90)).age_pref < base
    assert (
        -1
        <= fo.draft_strategy({}, "rebuilding", Leanings(youth=100, risk=100)).age_pref
    )


def test_defense_weight():
    assert fo.defense_weight(Leanings()) == 1.0
    assert fo.defense_weight(Leanings(offense_defense=0)) == pytest.approx(1.5)
    assert fo.defense_weight(Leanings(offense_defense=100)) == pytest.approx(0.5)


def test_protect_arms():
    p = fo.protect_arms(ManagerProfile(starter_usage="let-them-work"))
    assert p.tired_starters == "protect"
    assert p.starter_usage == "pitch-count-strict"
    p = fo.protect_arms(ManagerProfile(starter_usage="matchup-based"))
    assert p.starter_usage == "matchup-based"
