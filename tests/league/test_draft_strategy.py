# tests/league/test_draft_strategy.py
"""
Tests for draft_strategy.py: strategy validation, who a chip applies to, the
scoring bounds, pins, wear-off and the in-memory pick projection.
"""

import random

import pytest

from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.draft_strategy import (
    AGE_POINTS,
    BONUS_CAP,
    CHIPS,
    HIGH,
    LEVEL_POINTS,
    LOW,
    MAX_PINS,
    MED,
    ROTATION,
    DraftStrategy,
    StrategyScorer,
    group,
    project_picks,
    ratings,
    staff_groups,
)
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from tests.factories.player_record_factory import make_player_record


@pytest.fixture(scope="module")
def scorer():
    pool = DraftGenerator(None, random.Random(7))._generate_prospects()
    rated = sorted(
        ((p, PlayerEvaluator.prospect_rating(p.skills)) for p in pool),
        key=lambda x: x[1],
        reverse=True,
    )
    return StrategyScorer(rated)


def _best(scorer, strategy):
    return scorer.choose(set(scorer.order), strategy)


# ── DraftStrategy ─────────────────────────────────────────────────────────────


class TestDraftStrategyValidation:
    def test_unknown_chip_rejected(self):
        with pytest.raises(ValueError, match="Unknown"):
            DraftStrategy(chips={"2b": HIGH})

    def test_level_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="0-2"):
            DraftStrategy(chips={"if": 3})

    def test_age_pref_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="age_pref"):
            DraftStrategy(age_pref=1.5)

    def test_too_many_pins_rejected(self):
        with pytest.raises(ValueError, match="pinned"):
            DraftStrategy(pins=[f"p{i}" for i in range(MAX_PINS + 1)])

    def test_copy_is_independent(self):
        s = DraftStrategy(chips={"if": HIGH}, pins=["a"])
        c = s.copy()
        c.chips["if"] = LOW
        c.pins.append("b")
        assert s.chips["if"] == HIGH and s.pins == ["a"]


class TestOrNeeds:
    def test_no_chips_on_takes_the_needs(self):
        s = DraftStrategy(chips={"c": LOW}, age_pref=0.5, pins=["a"])
        assert s.or_needs({"sp": HIGH}) == DraftStrategy(
            chips={"sp": HIGH}, age_pref=0.5, pins=["a"]
        )

    def test_any_chip_on_keeps_the_strategy(self):
        s = DraftStrategy(chips={"c": MED})
        assert s.or_needs({"sp": HIGH}) is s


# ── Groups ────────────────────────────────────────────────────────────────────


class TestGroup:
    def test_listed_2b_who_plays_outfield_is_of(self):
        p = make_player_record(
            position="2b",
            skills=PlayerSkills({"outfield": 90, "infield": 5, "catching": 5}),
        )
        assert group(p, ratings(p)) == "of"

    def test_first_baseman_counts_as_infield(self):
        p = make_player_record(
            position="1b",
            skills=PlayerSkills({"infield": 90, "outfield": 5, "catching": 5}),
        )
        assert group(p, ratings(p)) == "if"

    def test_pitchers_go_by_ratings_not_their_listed_role(self):
        # Listed RP, built to start; listed SP, built to relieve
        starter = make_player_record(
            position="rp",
            skills=PlayerSkills(dict(strikes=85, stamina=85, recovery=70, accuracy=70)),
        )
        reliever = make_player_record(
            position="sp",
            skills=PlayerSkills(dict(strikes=85, stamina=40, recovery=85, accuracy=70)),
        )
        assert group(starter, ratings(starter)) == "sp"
        assert group(reliever, ratings(reliever)) == "rp"

    def test_staff_job_beats_ratings(self):
        p = make_player_record(
            position="sp",
            skills=PlayerSkills(dict(strikes=85, stamina=85, recovery=70, accuracy=70)),
        )
        assert group(p, ratings(p), "rp") == "rp"


class TestStaffGroups:
    STARTER = dict(strikes=85, stamina=85, recovery=70, accuracy=70)

    def _starters(self, n):
        return [
            make_player_record(
                position="sp",
                skills=PlayerSkills(dict(self.STARTER, stamina=65 + 5 * i)),
            )
            for i in range(n)
        ]

    def test_starters_beyond_the_rotation_are_relievers(self):
        pitchers = [(p, ratings(p)) for p in self._starters(ROTATION + 2)]
        groups = staff_groups(pitchers, {})
        assert sum(g == "sp" for g in groups.values()) == ROTATION
        # The two weakest starters go to the bullpen
        weakest = sorted(pitchers, key=lambda x: x[1]["sp"])[:2]
        assert all(groups[p.id] == "rp" for p, _ in weakest)

    def test_named_starters_take_rotation_spots_first(self):
        pitchers = [(p, ratings(p)) for p in self._starters(ROTATION + 1)]
        # The team named its two weakest as starters and one more as a reliever
        by_sp = sorted(pitchers, key=lambda x: x[1]["sp"])
        staff = {by_sp[0][0].id: "sp", by_sp[1][0].id: "sp", by_sp[-1][0].id: "rp"}
        groups = staff_groups(pitchers, staff)
        assert sum(g == "sp" for g in groups.values()) == ROTATION
        assert groups[by_sp[0][0].id] == "sp"
        assert groups[by_sp[-1][0].id] == "rp"


class TestChipsApply:
    def test_position_chip_only_fits_its_group(self, scorer):
        for pid in scorer.order:
            if scorer.group[pid] != "if":
                assert scorer.fit(pid, "if") == 0.0

    def test_hitter_archetype_never_fits_pitchers(self, scorer):
        for pid in scorer.order:
            if scorer.group[pid] in ("sp", "rp"):
                assert scorer.fit(pid, "power") == 0.0

    def test_fits_are_between_0_and_1(self, scorer):
        for pid in scorer.order:
            for chip in CHIPS:
                assert 0.0 <= scorer.fit(pid, chip) <= 1.0


# ── Scoring ───────────────────────────────────────────────────────────────────


class TestScoring:
    def test_no_strategy_scores_prospect_rating(self, scorer):
        for pid in scorer.order[:50]:
            assert scorer.score(pid, DraftStrategy()) == scorer.prospect[pid]

    def test_no_strategy_picks_best_prospect(self, scorer):
        assert _best(scorer, DraftStrategy()) == scorer.order[0]

    def test_bonus_never_exceeds_cap(self, scorer):
        everything = DraftStrategy(chips={k: HIGH for k in CHIPS})
        for pid in scorer.order:
            assert scorer.score(pid, everything) - scorer.prospect[pid] <= BONUS_CAP

    def test_need_chip_picks_from_that_group_when_close(self, scorer):
        catcher = next(p for p in scorer.order if scorer.group[p] == "c")
        close = {
            p
            for p in scorer.order
            if scorer.prospect[p] <= scorer.prospect[catcher] + 2
        }
        assert scorer.choose(close, DraftStrategy()) != catcher
        pid = scorer.choose(close, DraftStrategy(chips={"c": HIGH}))
        assert scorer.group[pid] == "c"

    def test_need_never_reaches_more_than_its_points(self, scorer):
        strategy = DraftStrategy(chips={"c": HIGH})
        pid = _best(scorer, strategy)
        top = scorer.prospect[scorer.order[0]]
        assert scorer.prospect[pid] >= top - LEVEL_POINTS[HIGH]

    def test_upside_prefers_younger(self, scorer):
        young = _best(scorer, DraftStrategy(age_pref=-1.0))
        old = _best(scorer, DraftStrategy(age_pref=1.0))
        assert scorer.age[young] <= scorer.age[old]

    def test_age_moves_score_by_at_most_age_points(self, scorer):
        for pid in scorer.order[:50]:
            for pref in (-1.0, 1.0):
                delta = scorer.score(pid, DraftStrategy(age_pref=pref))
                assert abs(delta - scorer.prospect[pid]) <= AGE_POINTS


class TestPins:
    def test_pin_wins_over_score(self, scorer):
        last = scorer.order[-1]
        assert _best(scorer, DraftStrategy(pins=[last])) == last

    def test_taken_pin_is_skipped(self, scorer):
        first, last = scorer.order[0], scorer.order[-1]
        available = set(scorer.order) - {last}
        pick = scorer.choose(available, DraftStrategy(pins=[last, first]))
        assert pick == first


class TestWearOff:
    def test_filled_chip_drops_a_level(self, scorer):
        strategy = DraftStrategy(chips={"if": HIGH, "c": MED})
        filler = next(p for p in scorer.order if scorer.fit(p, "if") >= 0.5)
        scorer.wear_off(filler, strategy)
        assert strategy.chips == {"if": MED, "c": MED}

    def test_level_never_goes_below_low(self, scorer):
        strategy = DraftStrategy(chips={"if": LOW})
        filler = next(p for p in scorer.order if scorer.fit(p, "if") >= 0.5)
        scorer.wear_off(filler, strategy)
        assert strategy.chips["if"] == LOW


# ── Projection ────────────────────────────────────────────────────────────────


class TestProjectPicks:
    teams = [f"t{i}" for i in range(1, 9)]

    def test_returns_n_picks_in_snake_slots(self, scorer):
        picks = project_picks(scorer, self.teams, 20, {}, "t3", n=3)
        assert [overall for overall, _ in picks] == [3, 14, 19]

    def test_ai_only_draft_follows_prospect_rating(self, scorer):
        picks = project_picks(scorer, self.teams, 20, {}, "t1", n=2)
        assert [pid for _, pid in picks] == [scorer.order[0], scorer.order[15]]

    def test_need_wears_off_across_picks(self, scorer):
        strategy = DraftStrategy(chips={"c": HIGH})
        picks = project_picks(scorer, self.teams, 20, {"t1": strategy}, "t1", n=5)
        catchers = [pid for _, pid in picks if scorer.group[pid] == "c"]
        assert 1 <= len(catchers) < len(picks)
        assert strategy.chips == {"c": HIGH}  # the caller's strategy is untouched

    def test_reports_who_other_teams_take(self, scorer):
        taken = {}
        mine = project_picks(
            scorer, self.teams, 20, {}, "t2", n=1, taken_by_others=taken
        )
        assert mine == [(2, scorer.order[1])]
        assert taken == {scorer.order[0]: 1}
