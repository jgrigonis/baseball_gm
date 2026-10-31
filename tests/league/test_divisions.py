# tests/league/test_divisions.py
import random

import pytest

from src.league import divisions
from src.league.divisions import Conference, Division


def test_world_lineup_has_every_city_once():
    cities = [
        c
        for divs in divisions.WORLD_LINEUP.values()
        for cs in divs.values()
        for c in cs
    ]
    assert len(cities) == len(set(cities)) == 30
    for divs in divisions.WORLD_LINEUP.values():
        assert [len(cs) for cs in divs.values()] == [5, 5, 5]


def test_world_league_teams_get_the_fixed_lineup():
    teams = [(f"id-{c}", c) for c in sorted(divisions.world_cities())]
    confs = divisions.draw(teams, random.Random(1))
    assert [c.name for c in confs] == ["Atlantic League", "Pacific League"]
    assert confs[1].divisions[0].name == "Pacific Rim"
    assert confs[1].divisions[0].team_ids == [
        "id-Los Angeles",
        "id-San Francisco",
        "id-Mexico City",
        "id-Sydney",
        "id-Tokyo",
    ]


@pytest.mark.parametrize("n", [16, 20, 24, 28, 32])
def test_other_sizes_draw_four_even_divisions(n):
    teams = [(f"t{i}", f"City {i}") for i in range(n)]
    confs = divisions.draw(teams, random.Random(n))
    assert len(confs) == 2
    sizes = [len(d.team_ids) for c in confs for d in c.divisions]
    assert sizes == [n // 4] * 4
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
