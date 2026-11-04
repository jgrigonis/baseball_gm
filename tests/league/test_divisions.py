# tests/league/test_divisions.py
import random

import pytest

from src.league import divisions, team_pool
from src.league.divisions import Conference, Division
from src.league.team_pool import TEAM_POOL


def _pool_teams(n, seed=1):
    return [(f"id-{t.city}", t.city) for t in team_pool.draw(n, random.Random(seed))]


@pytest.mark.parametrize(
    "n,per_league", [(16, 2), (20, 2), (24, 2), (28, 2), (30, 3), (32, 2)]
)
def test_pool_teams_split_into_two_leagues_of_even_divisions(n, per_league):
    for seed in range(5):
        teams = _pool_teams(n, seed)
        confs = divisions.draw(teams, random.Random(seed))
        assert [c.name for c in confs] == ["Atlantic League", "Pacific League"]
        sizes = [len(d.team_ids) for c in confs for d in c.divisions]
        assert sizes == [n // (2 * per_league)] * (2 * per_league)
        assert sorted(t for c in confs for t in c.team_ids) == sorted(
            t for t, _ in teams
        )
        names = [d.name for c in confs for d in c.divisions]
        assert len(set(names)) == len(names)


def test_divisions_follow_the_globe():
    teams = [(f"id-{t.city}", t.city) for t in TEAM_POOL if t.city != "Seattle"]
    extra = ("Berlin", "Portland", "Rome", "Boston", "Cairo", "Moscow", "Auckland")
    teams = [t for t in teams if t[1] not in extra]
    confs = divisions.draw(teams, random.Random(1))
    by_team = {t: d.name for c in confs for d in c.divisions for t in d.team_ids}
    # Neighbors play together.
    assert by_team["id-Seoul"] == by_team["id-Tokyo"]
    assert by_team["id-Paris"] == by_team["id-Amsterdam"]
    assert by_team["id-Madrid"] == by_team["id-Lisbon"]
    assert by_team["id-Chicago"] == by_team["id-Toronto"]
    assert "Europe West" in by_team.values() and "Europe East" in by_team.values()
    atlantic = set(confs[0].team_ids)
    assert "id-London" in atlantic and "id-Tokyo" not in atlantic


def test_the_split_doesnt_depend_on_the_rng_for_pool_teams():
    teams = _pool_teams(24)
    assert divisions.draw(teams, random.Random(1)) == divisions.draw(
        teams, random.Random(2)
    )


def test_crowded_regions_still_split_evenly():
    europe = [t for t in TEAM_POOL if t.region == team_pool.EUROPE]
    teams = [(f"id-{t.city}", t.city) for t in europe]
    teams += [
        ("id-Tokyo", "Tokyo"),
        ("id-Sydney", "Sydney"),
        ("id-Dubai", "Dubai"),
    ]
    assert len(teams) == 16
    confs = divisions.draw(teams, random.Random(1))
    names = [d.name for c in confs for d in c.divisions]
    assert [len(d.team_ids) for c in confs for d in c.divisions] == [4] * 4
    assert len(set(names)) == 4


@pytest.mark.parametrize("n", [16, 20, 24, 28, 30, 32])
def test_teams_outside_the_pool_are_drawn_at_random(n):
    teams = [(f"t{i}", f"City {i}") for i in range(n)]
    confs = divisions.draw(teams, random.Random(n))
    assert len(confs) == 2
    per = divisions.divisions_per_league(n)
    sizes = [len(d.team_ids) for c in confs for d in c.divisions]
    assert sizes == [n // (2 * per)] * (2 * per)
    assert sorted(t for c in confs for t in c.team_ids) == sorted(t for t, _ in teams)


def _ranked(order):
    return [{"team_id": t, "wins": 100 - i} for i, t in enumerate(order)]


def test_playoffs_take_division_winners_then_wild_cards():
    confs = [
        Conference(
            "A",
            [Division("A1", ["a1", "a2", "a3"]), Division("A2", ["a4", "a5", "a6"])],
        ),
        Conference(
            "B",
            [Division("B1", ["b1", "b2", "b3"]), Division("B2", ["b4", "b5", "b6"])],
        ),
    ]
    # League A's best three are all in A1, so A2's winner (a4) jumps a2 and a3.
    ranked = _ranked(
        ["a1", "a2", "b1", "a3", "b4", "b2", "a4", "b5", "a5", "b3", "b6", "a6"]
    )
    order = [r["team_id"] for r in divisions.playoff_order(confs, ranked)]
    # Spots 1, 4, 5, 8 are league A (its best record is best overall), 2, 3, 6, 7 B.
    assert order == ["a1", "b1", "b4", "a4", "a2", "b2", "b5", "a3"]


def test_no_divisions_means_no_division_seeding():
    assert divisions.playoff_order([], _ranked(["x"])) is None


def test_teams_that_dont_split_in_four_get_no_divisions():
    assert divisions.draw([(f"t{i}", f"C{i}") for i in range(6)], random.Random()) == []
