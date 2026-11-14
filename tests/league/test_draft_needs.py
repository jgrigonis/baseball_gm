# tests/league/test_draft_needs.py
"""
Tests for draft_needs.py: weak 26-man starters and thin depth (against fixed
targets) get need chips, weak lineups and staffs get a player-type chip, and
the suggestion stays short.
"""

from src.league.offseason.draft_needs import (
    HIGH_BELOW,
    MAX_AGE,
    MAX_CHIPS,
    league_needs,
)
from src.league.offseason.draft_strategy import HIGH, MED, group, ratings
from src.player.player_skills import PlayerSkills
from tests.factories.player_record_factory import make_player_record

HITTING = dict(contact=60, power=60, eye=60, speed=60, clutch=60, base_running=60)
SPECS = {
    "c": ("c", dict(HITTING, arm=70, catching=90, infield=20, outfield=20)),
    "if": ("ss", dict(HITTING, speed=85, arm=85, infield=90, catching=20, outfield=20)),
    "of": ("cf", dict(HITTING, arm=70, outfield=90, infield=20, catching=20)),
    "sp": ("sp", dict(strikes=85, stamina=85, recovery=70, accuracy=70)),
    "rp": ("rp", dict(strikes=85, stamina=40, recovery=85, accuracy=70)),
}
# Every team gets this many usable players at each spot unless a test says
DEPTH = {"c": 2, "if": 4, "of": 4, "sp": 6, "rp": 7}


def _player(spot, age=25, **skills):
    position, base = SPECS[spot]
    return make_player_record(
        position=position, skills=PlayerSkills({**base, **skills}, age=age)
    )


def _roster(depth=DEPTH, status="26man", **skills):
    return [
        (_player(spot, **skills), status) for spot, n in depth.items() for _ in range(n)
    ]


def _league(staff=None, **teams):
    """Six average teams, with any named in `teams` replacing one of them."""
    rosters = {f"avg{i}": _roster() for i in range(6)}
    rosters.update(teams)
    return league_needs(rosters, staff)


def test_specs_are_usable_at_their_spot():
    for spot in SPECS:
        p = _player(spot)
        r = ratings(p)
        assert group(p, r) == spot
        assert r[spot] >= 55


def test_average_team_needs_nothing():
    needs = _league()
    assert all(n.chips == {} for n in needs.values())


def test_missing_position_is_high_with_a_reason():
    needs = _league(thin=_roster({**DEPTH, "c": 0}))
    assert needs["thin"].chips["c"] == HIGH
    assert needs["thin"].reasons["c"] == "Starting catcher grades F"


def test_somewhat_short_position_is_med():
    # Three good outfielders start, but 3 of a target of 4 is short (not half)
    needs = _league(thin=_roster({**DEPTH, "of": 3}))
    assert needs["thin"].chips.get("of") == MED
    assert needs["thin"].reasons["of"].startswith("3 usable, target 4")
    assert 3 / 4 >= HIGH_BELOW


def test_a_weak_starter_is_a_need_even_with_depth():
    # Four infielders, but the shortstop can't field: the IF starter grade.
    weak = _player("if", infield=20, arm=20, speed=20)
    ifs = [_player("if") for _ in range(3)] + [weak]
    roster = _roster({**DEPTH, "if": 0}) + [(p, "26man") for p in ifs]
    roster += [(_player("if"), "minors") for _ in range(4)]
    needs = _league(weak=roster)
    assert needs["weak"].chips.get("if") in (MED, HIGH)
    assert needs["weak"].reasons["if"].startswith("Starter at")


def test_minor_leaguers_count_half():
    # One catcher is short of the target of 2; two in the minors make it up.
    assert _league(thin=_roster({**DEPTH, "c": 1}))["thin"].chips.get("c") == MED
    minors = _roster({"c": 2}, status="minors")
    needs = _league(thin=_roster({**DEPTH, "c": 1}) + minors)
    assert "c" not in needs["thin"].chips


def test_old_players_dont_count():
    old = _roster({"rp": 5}, age=MAX_AGE + 1)
    needs = _league(old=_roster({**DEPTH, "rp": 0}) + old)
    assert needs["old"].chips.get("rp") == HIGH


def test_starters_beyond_the_rotation_count_as_relievers():
    # Thirteen starters and no relievers: five fill the rotation, the rest relieve
    needs = _league(deep=_roster({**DEPTH, "sp": 13, "rp": 0}))
    assert "rp" not in needs["deep"].chips
    assert "sp" not in needs["deep"].chips


def test_pitchers_count_where_the_staff_uses_them():
    roster = _roster({**DEPTH, "sp": 7, "rp": 0})
    staff = {p.id: "rp" for p, _ in roster if p.is_pitcher()}
    needs = _league(staff=staff, pen=roster)
    assert "rp" not in needs["pen"].chips
    assert needs["pen"].chips["sp"] == HIGH


def test_weak_lineup_gets_one_hitting_chip():
    weak = _roster(contact=30, power=30, eye=30, speed=30, base_running=30)
    needs = _league(weak=weak)
    hitting = {"offense", "lead_off", "contact", "power", "speed"}
    assert len(hitting & needs["weak"].chips.keys()) == 1
    assert any("of 7 in the league" in r for r in needs["weak"].reasons.values())


def test_never_more_than_max_chips():
    empty = _roster({spot: 0 for spot in DEPTH})
    needs = _league(empty=empty)
    assert len(needs["empty"].chips) == MAX_CHIPS
    assert set(needs["empty"].chips.values()) == {HIGH}


def test_strategy_carries_the_chips():
    needs = _league(thin=_roster({**DEPTH, "c": 0}))
    assert needs["thin"].strategy().chips == needs["thin"].chips
