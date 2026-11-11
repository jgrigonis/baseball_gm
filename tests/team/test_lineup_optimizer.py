# tests/team/test_lineup_optimizer.py
"""
LineupOptimizer: contracts and invariants, plus the simple cases where the
right answer is obvious (the only catcher catches, the best hitter bats high).

We do not test exact batting orders beyond simple dominance cases, or
PlayerEvaluator.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.player.player_in_game import PlayerInGame
from src.team.lineup_optimizer import (
    FIELD_POSITIONS,
    LINEUP_STYLES,
    PLATOON_PENALTY,
    REGULAR_BONUS,
    LineupOptimizer,
)

HITTING = ("contact", "power", "eye", "speed", "base_running", "bunting", "clutch")


def make_player(id, ratings=None, skills=None, throws="R", bats="R"):
    p = MagicMock(spec=PlayerInGame)
    p.record = SimpleNamespace(id=id)
    p.id = id
    p.ratings = ratings or {}
    p.skills = skills or {}
    p.throws = throws
    p.bats = bats
    p.is_injured = False
    return p


def hitter(id, bat=50, glove=None, throws="R", bats="R", **skills):
    """A hitter with overall_offense `bat`, a rating at each position from
    `glove` (default 40 everywhere), and hitting skills all at `bat` unless
    given."""
    ratings = {pos: 40 for pos in FIELD_POSITIONS}
    ratings.update(glove or {})
    ratings["overall_offense"] = bat
    return make_player(
        id,
        ratings,
        {k: skills.get(k, bat) for k in HITTING},
        throws=throws,
        bats=bats,
    )


def nine_plus(extra=()):
    return [hitter(f"h{i}") for i in range(9)] + list(extra)


def by_position(lineup):
    return {s.position: s.player.id for s in lineup}


def test_select_pitcher_uses_p_rating_then_id():
    p1 = make_player("a", {"p": 80})
    p2 = make_player("b", {"p": 90})
    p3 = make_player("c", {"p": 90})  # tie → higher id wins

    assert LineupOptimizer.select_pitcher([p1, p2, p3]) is p3


def test_optimize_returns_lineup_and_pitcher():
    pitcher = make_player("p", {"p": 99})
    players = nine_plus([pitcher])

    lineup, chosen = LineupOptimizer.optimize(players)

    assert chosen is pitcher
    assert pitcher not in [s.player for s in lineup]


def test_optimize_respects_dh_rule():
    players = nine_plus([hitter("x")])
    pitcher = make_player("p", {"p": 99})

    lineup_dh, _ = LineupOptimizer.optimize(players, dh=True, pitcher=pitcher)
    lineup_no_dh, _ = LineupOptimizer.optimize(players, dh=False, pitcher=pitcher)

    assert len(lineup_dh) == 9
    assert sorted(by_position(lineup_dh)) == sorted(FIELD_POSITIONS + ["dh"])
    assert len(lineup_no_dh) == 8
    assert sorted(by_position(lineup_no_dh)) == sorted(FIELD_POSITIONS)


@pytest.mark.parametrize("style", LINEUP_STYLES)
def test_every_style_builds_a_full_lineup(style):
    lineup, _ = LineupOptimizer.optimize(
        nine_plus(), style=style, pitcher=make_player("p")
    )
    ids = [s.player.id for s in lineup]
    assert len(ids) == len(set(ids)) == 9


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        LineupOptimizer.optimize(nine_plus(), style="chaos")


def test_not_enough_hitters_raises():
    with pytest.raises(ValueError):
        LineupOptimizer.fill([None] * 9, [hitter(f"h{i}") for i in range(5)])


def test_injured_players_are_left_out():
    hurt = hitter("hurt", bat=99)
    hurt.is_injured = True
    lineup, _ = LineupOptimizer.optimize(nine_plus([hurt]), pitcher=make_player("p"))
    assert "hurt" not in [s.player.id for s in lineup]


def test_only_catcher_catches_even_if_he_cant_hit():
    """The old optimizer picked 9 bats first and could leave the catcher out."""
    catcher = hitter("catcher", bat=30, glove={"c": 80})
    bats = [hitter(f"bat{i}", bat=70, glove={"c": 5}) for i in range(9)]

    lineup = LineupOptimizer.fill([None] * 9, bats + [catcher])

    assert by_position(lineup)["c"] == "catcher"


def test_glove_matters_most_up_the_middle():
    """Two equal bats: the better fielder plays short, not first."""
    shortstop = hitter("ss", glove={"ss": 80, "1b": 80})
    first = hitter("1b", glove={"ss": 40, "1b": 60})

    lineup = LineupOptimizer.fill([None] * 9, nine_plus([shortstop, first]))

    assert by_position(lineup)["ss"] == "ss"


def test_defensive_style_takes_the_glove_up_the_middle():
    """A better bat with a weaker glove plays short in Analytics; Defensive
    plays the glove man there and moves the bat."""
    glove = hitter("glove", bat=30, glove={"ss": 80})
    bat = hitter("bat", bat=65, glove={"ss": 66})
    players = [glove, bat] + [hitter(f"h{i}", glove={"ss": 0}) for i in range(8)]

    assert by_position(LineupOptimizer.fill([None] * 9, players))["ss"] == "bat"
    lineup = LineupOptimizer.fill([None] * 9, players, style="defensive")
    assert by_position(lineup)["ss"] == "glove"
    assert "bat" in by_position(lineup).values()


@pytest.mark.parametrize(
    "style,skill", [("speed-first", "speed"), ("power-first", "power")]
)
def test_speed_and_power_styles_start_their_kind_of_bench_bat(style, skill):
    """A slightly weaker bat who is fast (or strong) sits in Analytics but
    starts in the style that wants him."""
    special = hitter("special", bat=48, **{skill: 90})
    players = [hitter(f"h{i}") for i in range(9)] + [special]

    assert (
        "special" not in by_position(LineupOptimizer.fill([None] * 9, players)).values()
    )
    lineup = LineupOptimizer.fill([None] * 9, players, style=style)
    assert "special" in by_position(lineup).values()


def test_big_bat_without_glove_still_plays():
    slugger = hitter("slugger", bat=90, glove={p: 10 for p in FIELD_POSITIONS})

    lineup = LineupOptimizer.fill([None] * 9, nine_plus([slugger]))

    assert by_position(lineup)["dh"] == "slugger"


def test_lefty_kept_off_shortstop_when_a_righty_can_play():
    lefty = hitter("lefty", glove={"ss": 20}, throws="L")
    righty = hitter("righty", glove={"ss": 15})
    players = [lefty, righty] + [hitter(f"h{i}", glove={"ss": 0}) for i in range(8)]

    lineup = LineupOptimizer.fill([None] * 9, players)

    assert by_position(lineup)["ss"] == "righty"


def test_best_hitter_bats_near_the_top():
    star = hitter("star", bat=90)
    lineup = LineupOptimizer.fill([None] * 9, nine_plus([star]))

    assert [s.player.id for s in lineup].index("star") < 4


def test_fast_on_base_hitter_leads_off_traditional():
    leadoff = hitter("leadoff", bat=55, speed=95, contact=70, eye=70, power=20)
    lineup = LineupOptimizer.fill([None] * 9, nine_plus([leadoff]), style="traditional")
    assert lineup[0].player.id == "leadoff"


def test_fill_keeps_locked_players_where_they_are():
    players = nine_plus([hitter("x"), hitter("y")])
    locked = [None] * 9
    locked[2] = (players[0], "cf")
    locked[6] = (players[1], "c")

    lineup = LineupOptimizer.fill(locked, players)

    assert (lineup[2].player.id, lineup[2].position) == ("h0", "cf")
    assert (lineup[6].player.id, lineup[6].position) == ("h1", "c")
    ids = [s.player.id for s in lineup]
    assert len(ids) == len(set(ids)) == 9
    assert sorted(by_position(lineup)) == sorted(FIELD_POSITIONS + ["dh"])


def test_fill_gives_a_locked_player_without_a_position_one():
    players = nine_plus()
    weak = hitter("weak", bat=10)
    locked = [None] * 9
    locked[0] = (weak, None)

    lineup = LineupOptimizer.fill(locked, players + [weak])

    assert lineup[0].player.id == "weak"
    assert lineup[0].position in FIELD_POSITIONS + ["dh"]


def test_optimizer_does_not_mutate_players():
    players = nine_plus()
    before = [(dict(p.ratings), dict(p.skills)) for p in players]

    LineupOptimizer.optimize(players, pitcher=make_player("p"))

    assert [(p.ratings, p.skills) for p in players] == before


def test_deterministic_whatever_the_input_order():
    players = [hitter(f"h{i}", bat=50 + i % 3) for i in range(14)]
    a = LineupOptimizer.fill([None] * 9, players)
    b = LineupOptimizer.fill([None] * 9, list(reversed(players)))
    assert [(s.player.id, s.position) for s in a] == [
        (s.player.id, s.position) for s in b
    ]


# ── Platoons ──────────────────────────────────────────────────────────────────


def test_only_same_side_hitters_lose_offense():
    righty, lefty, switch = hitter("r"), hitter("l", bats="L"), hitter("s", bats="S")
    assert LineupOptimizer.matchup(righty, "R") == PLATOON_PENALTY
    assert LineupOptimizer.matchup(lefty, "R") == 0
    assert LineupOptimizer.matchup(switch, "L") == 0
    assert LineupOptimizer.matchup(righty, None) == 0


def platoon_lineup(bench_bat, platoon, vs_hand="R"):
    """Nine right-handed regulars and a left-handed bench bat who can only DH
    (no glove). Who's the DH?"""
    regulars = [hitter(f"h{i}", bat=60) for i in range(9)]
    bench = hitter(
        "lefty", bat=bench_bat, glove={p: 0 for p in FIELD_POSITIONS}, bats="L"
    )
    lineup = LineupOptimizer.fill(
        [None] * 9, regulars + [bench], vs_hand=vs_hand, platoon=platoon
    )
    return "lefty" in {s.player.id for s in lineup}


def test_platoon_none_ignores_the_starter():
    assert not platoon_lineup(58, "none")


def test_aggressive_plays_the_best_matchup():
    # 60 less the same-side penalty is below 58.
    assert 60 - PLATOON_PENALTY < 58
    assert platoon_lineup(58, "aggressive")
    # Against a lefty the righties have the platoon edge.
    assert not platoon_lineup(58, "aggressive", vs_hand="L")


def test_vs_handedness_keeps_a_regular_unless_the_bench_is_close():
    edge = 60 - PLATOON_PENALTY + REGULAR_BONUS
    assert not platoon_lineup(edge - 1, "vs-handedness")
    assert platoon_lineup(edge + 1, "vs-handedness")


def test_form_moves_who_plays():
    """A hot bench bat a few points behind a regular plays for a GM who
    weighs stats, and doesn't without his form."""
    regulars = [hitter(f"h{i}", bat=60) for i in range(9)]
    bench = hitter("hot", bat=57, glove={p: 0 for p in FIELD_POSITIONS})

    def plays(form):
        lineup = LineupOptimizer.fill([None] * 9, regulars + [bench], form=form)
        return "hot" in {s.player.id for s in lineup}

    assert not plays(None)
    assert plays({"hot": 5.0})
    # A cold regular can lose his spot the same way.
    assert plays({"h0": -5.0})


def test_form_counts_with_the_regulars_bonus():
    """Under vs-handedness, form adds to the regular's bonus rather than
    replacing it."""
    regulars = [hitter(f"h{i}", bat=60) for i in range(9)]
    bench = hitter("lefty", bat=54, glove={p: 0 for p in FIELD_POSITIONS}, bats="L")
    edge = 60 - PLATOON_PENALTY + REGULAR_BONUS

    def plays(form):
        lineup = LineupOptimizer.fill(
            [None] * 9,
            regulars + [bench],
            vs_hand="R",
            platoon="vs-handedness",
            form=form,
        )
        return "lefty" in {s.player.id for s in lineup}

    assert 54 < edge < 57
    assert not plays(None)
    assert plays({"lefty": 3.0})


def test_defense_weight_decides_a_glove_first_shortstop():
    """A weak bat with a good glove at short plays for a normal GM, but a
    bat-first GM (glove counts half) plays a better hitter there."""
    glove = hitter("glove", bat=32, glove={"ss": 70})

    normal = LineupOptimizer.fill([None] * 8, nine_plus([glove]), dh=False)
    bat_first = LineupOptimizer.fill(
        [None] * 8, nine_plus([glove]), dh=False, defense=0.5
    )

    assert by_position(normal)["ss"] == "glove"
    assert "glove" not in by_position(bat_first).values()


def test_position_value_scales_the_glove():
    p = hitter("p", bat=50, glove={"c": 60})
    assert LineupOptimizer.position_value(p, "c") == 110
    assert LineupOptimizer.position_value(p, "c", defense=1.5) == 140
    assert LineupOptimizer.position_value(p, "dh", defense=1.5) == 50


@pytest.mark.parametrize("style", LINEUP_STYLES)
def test_best_on_base_hitter_leads_off_every_style(style):
    # The best contact + eye leads off even over a faster hitter or a
    # better all-around bat. (Average power, so Power-first still plays him.)
    on_base = hitter("on_base", bat=55, contact=80, eye=80, speed=50, power=50)
    burner = hitter("burner", bat=55, contact=50, eye=40, speed=99, base_running=99)
    slugger = hitter("slugger", bat=75, contact=60, eye=60, power=99)
    lineup = LineupOptimizer.fill(
        [None] * 9, nine_plus([on_base, burner, slugger]), style=style
    )
    assert lineup[0].player.id == "on_base"


def test_leadoff_slot_matches_the_card_leadoff_grade():
    from src.player.player_evaluator import ROLE_WEIGHTS
    from src.team.lineup_optimizer import BATTING_ROLES

    for roles in BATTING_ROLES.values():
        assert roles[0] == ROLE_WEIGHTS["lead_off"]


def test_form_moves_a_hitter_up_the_order():
    """Among equal hitters, a hot one bats higher and a cold one lower for a
    GM who weighs stats."""
    players = [hitter(f"h{i}", bat=60) for i in range(9)]

    def slot(pid, form):
        lineup = LineupOptimizer.fill([None] * 9, players, form=form)
        return [s.player.id for s in lineup].index(pid)

    assert slot("h8", {"h8": 5.0}) == 0
    assert slot("h0", {"h0": -5.0}) == 8
